"""
Document retrieval and answer generation utilities.

Uses the HuggingFace Inference API for embeddings (no local model download,
no torch, no memory issues on free-tier hosting).
"""

import hashlib
import os
import re
import requests
from types import SimpleNamespace

from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

_EMBEDDINGS = None
_VECTORSTORE = None
_LLM = None

print(f"LOADING document_search from: {__file__}", flush=True)


class _FallbackEmbeddings:
    """Deterministic local fallback — no network, no torch, always works."""

    dimension = 384

    def embed_query(self, text: str):
        text = text or ""
        values = []
        for idx in range(self.dimension):
            seed = f"{text}:{idx}".encode("utf-8")
            digest = hashlib.sha256(seed).digest()
            number = int.from_bytes(digest[:4], "big", signed=False)
            values.append((number / 2147483647.5) - 1.0)
        return values

    def embed_documents(self, texts: list) -> list:
        return [self.embed_query(t) for t in texts]


class _HuggingFaceAPIEmbeddings:
    """
    Calls the HuggingFace Inference API to embed text.
    Uses the same model (all-MiniLM-L6-v2) as the old local version
    so existing Pinecone vectors stay compatible.
    No torch, no local download — just a lightweight HTTP call.
    """

    dimension = 384
    MODEL_URL = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, api_token: str):
        self.headers = {"Authorization": f"Bearer {api_token}"}
        print("HuggingFace API embeddings initialized (no local model).", flush=True)

    def _query(self, payload: dict) -> list:
        response = requests.post(self.MODEL_URL, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def embed_query(self, text: str) -> list:
        result = self._query({"inputs": text, "options": {"wait_for_model": True}})
        return result

    def embed_documents(self, texts: list) -> list:
        result = self._query({"inputs": texts, "options": {"wait_for_model": True}})
        return result


class _EmbeddingsProxy:
    def embed_query(self, text: str):
        return get_embeddings().embed_query(text)

    def embed_documents(self, texts: list):
        return get_embeddings().embed_documents(texts)


class _LLMProxy:
    def invoke(self, prompt: str):
        return get_llm().invoke(prompt)


embeddings = _EmbeddingsProxy()
llm = _LLMProxy()


def get_embeddings():
    """
    Returns singleton embeddings instance.
    Prefers HuggingFace Inference API (lightweight), falls back to hash-based dummy.
    Called at startup in main.py so it's ready before first request.
    """
    global _EMBEDDINGS
    if _EMBEDDINGS is not None:
        return _EMBEDDINGS

    if HUGGINGFACEHUB_API_TOKEN:
        try:
            _EMBEDDINGS = _HuggingFaceAPIEmbeddings(HUGGINGFACEHUB_API_TOKEN)
            # Smoke-test it works
            _EMBEDDINGS.embed_query("test")
            print("HuggingFace API embeddings: OK", flush=True)
            return _EMBEDDINGS
        except Exception as e:
            print(f"HuggingFace API embeddings failed: {e}", flush=True)

    print("WARNING: Falling back to hash-based embeddings. Semantic search will not work.", flush=True)
    _EMBEDDINGS = _FallbackEmbeddings()
    return _EMBEDDINGS


def get_vectorstore():
    """
    Returns singleton Pinecone vector store.
    Called at startup in main.py.
    """
    global _VECTORSTORE
    if _VECTORSTORE is not None:
        return _VECTORSTORE

    if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
        print("Warning: Missing Pinecone configuration.", flush=True)
        return None

    try:
        from langchain_pinecone import PineconeVectorStore
        from pinecone import Pinecone

        print("Connecting to Pinecone...", flush=True)
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)
        _VECTORSTORE = PineconeVectorStore(index=index, embedding=get_embeddings())
        print("Pinecone vector store connected.", flush=True)
    except Exception as e:
        print(f"Warning: Pinecone vector store unavailable: {e}", flush=True)
        _VECTORSTORE = None

    return _VECTORSTORE


def get_llm():
    global _LLM
    if _LLM is not None:
        return _LLM

    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            from langchain_groq import ChatGroq
            _LLM = ChatGroq(
                api_key=groq_api_key,
                model_name="llama-3.1-8b-instant",
                temperature=0.1,
                max_tokens=1000,
            )
            print("Using Groq LLM.", flush=True)
            return _LLM
        except Exception as e:
            print(f"Groq init failed: {e}", flush=True)

    _LLM = _FallbackLLM()
    return _LLM


class _FallbackLLM:
    def invoke(self, prompt: str):
        return SimpleNamespace(
            content=(
                "I'm experiencing technical difficulties with my language model service. "
                "I do not have information about that right now. "
                "Please try again later or ask your teacher for help with this question."
            )
        )


def retrieve_documents(query: str, k: int = 5):
    """
    Retrieve top-k documents from Pinecone for the given query.
    Returns list of (Document, score) tuples, or empty list if unavailable.
    """
    vectorstore = get_vectorstore()
    if vectorstore is None:
        return []

    try:
        return vectorstore.similarity_search_with_score(query, k=k)
    except Exception as e:
        print(f"Warning: document retrieval failed: {e}", flush=True)
        return []


def generate_rag_answer(
    question: str,
    context: str,
    history: str,
    query_type: str,
) -> str:
    """
    Build a prompt from the question and enriched context, call the LLM,
    and return the cleaned answer string.
    """
    if query_type == "subject_count_query":
        prompt = f"""You are a helpful CBC Education Guidance Assistant.

Question: {question}

{context}

Instructions:
- Answer ONLY the subject count question in ONE short sentence
- Do NOT explain pathways unless asked
- Do NOT add greetings
- Use only the information provided above

Answer:"""

    else:
        prompt = f"""You are a helpful CBC Education Guidance Assistant for students and parents in Kenya.

{context}

Question: {question}

Instructions:
- Do NOT repeat or restate the question
- Do NOT reference the context directly
- Start with a greeting ONLY if the user's message is itself a greeting
- For general pathway questions: briefly explain all 3 pathways
- For specific subject or career questions: answer directly
- Answer clearly and briefly in 1-2 short paragraphs only
- Use only the information provided above
- Use simple language for parents and students
- Be encouraging and supportive

Answer:"""

    response = get_llm().invoke(prompt)
    answer = getattr(response, "content", "") or ""
    answer = re.sub(r"\s+", " ", answer).strip()
    return answer
