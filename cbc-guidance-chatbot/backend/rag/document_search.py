"""
document_search.py
------------------
Handles two things only:
  1. Embeddings via HuggingFace Inference API (no torch, no local model)
  2. Pinecone vector retrieval via LangChain

The LLM lives in rag_query.py — not here.
"""

import hashlib
import os
import requests

from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY         = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME      = os.getenv("PINECONE_INDEX_NAME")
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

_EMBEDDINGS  = None
_VECTORSTORE = None

print(f"LOADING document_search from: {__file__}", flush=True)


# ── Embeddings ────────────────────────────────────────────────────────────────

class _FallbackEmbeddings:
    """Hash-based fallback — always works, no network needed."""
    dimension = 384

    def embed_query(self, text: str) -> list:
        text = text or ""
        values = []
        for idx in range(self.dimension):
            seed   = f"{text}:{idx}".encode("utf-8")
            digest = hashlib.sha256(seed).digest()
            number = int.from_bytes(digest[:4], "big", signed=False)
            values.append((number / 2147483647.5) - 1.0)
        return values

    def embed_documents(self, texts: list) -> list:
        return [self.embed_query(t) for t in texts]


class _HuggingFaceAPIEmbeddings:
    """
    HuggingFace Inference API v2 embeddings.
    Same model (all-MiniLM-L6-v2) as original local version
    so existing Pinecone vectors stay compatible.
    No torch, no local download, minimal memory.
    """
    dimension = 384
    MODEL_URL = (
        "https://router.huggingface.co/hf-inference/models/"
        "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
    )

    def __init__(self, api_token: str):
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type":  "application/json",
        }
        print("HuggingFace API embeddings initialized.", flush=True)

    def _query(self, inputs) -> list:
        response = requests.post(
            self.MODEL_URL,
            headers=self.headers,
            json={"inputs": inputs},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def embed_query(self, text: str) -> list:
        return self._query(text)

    def embed_documents(self, texts: list) -> list:
        return self._query(texts)


def get_embeddings():
    """Singleton embeddings instance. Called at startup."""
    global _EMBEDDINGS
    if _EMBEDDINGS is not None:
        return _EMBEDDINGS

    if HUGGINGFACEHUB_API_TOKEN:
        try:
            instance    = _HuggingFaceAPIEmbeddings(HUGGINGFACEHUB_API_TOKEN)
            test_result = instance.embed_query("test")
            if isinstance(test_result, list) and len(test_result) > 0:
                _EMBEDDINGS = instance
                print(f"HuggingFace API embeddings: OK (dim={len(test_result)})", flush=True)
                return _EMBEDDINGS
        except Exception as e:
            print(f"HuggingFace API embeddings failed: {e}", flush=True)
    else:
        print("WARNING: HUGGINGFACEHUB_API_TOKEN not set.", flush=True)

    print("WARNING: Using hash-based fallback embeddings.", flush=True)
    _EMBEDDINGS = _FallbackEmbeddings()
    return _EMBEDDINGS


# ── Pinecone vector store ─────────────────────────────────────────────────────

def get_vectorstore():
    """Singleton Pinecone vector store. Called at startup."""
    global _VECTORSTORE
    if _VECTORSTORE is not None:
        return _VECTORSTORE

    if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
        print("Warning: Missing Pinecone config.", flush=True)
        return None

    try:
        from langchain_pinecone import PineconeVectorStore
        from pinecone import Pinecone

        print("Connecting to Pinecone...", flush=True)
        pc           = Pinecone(api_key=PINECONE_API_KEY)
        index        = pc.Index(PINECONE_INDEX_NAME)
        _VECTORSTORE = PineconeVectorStore(index=index, embedding=get_embeddings())
        print("Pinecone vector store connected.", flush=True)
    except Exception as e:
        print(f"Warning: Pinecone unavailable: {e}", flush=True)
        _VECTORSTORE = None

    return _VECTORSTORE


def retrieve_documents(query: str, k: int = 5) -> list:
    """
    Retrieve top-k documents from Pinecone for the given query.
    Returns list of (Document, score) tuples, or empty list if unavailable.
    """
    vectorstore = get_vectorstore()
    if not vectorstore or not query or not query.strip():
        return []
    try:
        return vectorstore.similarity_search_with_score(query, k=k)
    except Exception as e:
        print(f"Warning: Pinecone retrieval failed: {e}", flush=True)
        return []
