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

PINECONE_API_KEY         = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME      = os.getenv("PINECONE_INDEX_NAME")
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

_EMBEDDINGS  = None
_VECTORSTORE = None
_LLM         = None

print(f"LOADING document_search from: {__file__}", flush=True)


# ── Embeddings ────────────────────────────────────────────────────────────────

class _FallbackEmbeddings:
    """Hash-based fallback — no network required, always works."""
    dimension = 384

    def embed_query(self, text: str):
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
    Uses all-MiniLM-L6-v2 — same model as the old local version
    so existing Pinecone vectors stay compatible.
    No torch, no local download.
    """
    dimension = 384
    MODEL_URL = (
        "https://router.huggingface.co/hf-inference/models/"
        "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
    )

    def __init__(self, api_token: str):
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
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


class _EmbeddingsProxy:
    def embed_query(self, text: str):
        return get_embeddings().embed_query(text)

    def embed_documents(self, texts: list):
        return get_embeddings().embed_documents(texts)


class _LLMProxy:
    def invoke(self, prompt: str):
        return get_llm().invoke(prompt)


embeddings = _EmbeddingsProxy()
llm        = _LLMProxy()


def get_embeddings():
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
            print(f"HuggingFace API unexpected result: {test_result}", flush=True)
        except Exception as e:
            print(f"HuggingFace API embeddings failed: {e}", flush=True)
    else:
        print("WARNING: HUGGINGFACEHUB_API_TOKEN not set.", flush=True)

    print("WARNING: Falling back to hash-based embeddings. Semantic search will not work.", flush=True)
    _EMBEDDINGS = _FallbackEmbeddings()
    return _EMBEDDINGS


def get_vectorstore():
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


def get_llm():
    global _LLM
    if _LLM is not None:
        return _LLM

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        print("ERROR: GROQ_API_KEY not set.", flush=True)
        _LLM = _FallbackLLM()
        return _LLM

    try:
        from langchain_groq import ChatGroq
        _LLM = ChatGroq(
            api_key=groq_api_key,
            model_name="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=1000,
        )
        test = _LLM.invoke("Say OK")
        print(f"Groq LLM: OK ({getattr(test, 'content', '')[:20]})", flush=True)
        return _LLM
    except Exception as e:
        print(f"ERROR: Groq failed: {e}", flush=True)
        _LLM = _FallbackLLM()
        return _LLM


class _FallbackLLM:
    def invoke(self, prompt: str):
        return SimpleNamespace(
            content="I'm having a technical issue right now. Please try again in a moment."
        )


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve_documents(query: str, k: int = 5):
    vectorstore = get_vectorstore()
    if vectorstore is None:
        return []
    try:
        return vectorstore.similarity_search_with_score(query, k=k)
    except Exception as e:
        print(f"Warning: retrieval failed: {e}", flush=True)
        return []


# ── Answer generation ─────────────────────────────────────────────────────────

def generate_rag_answer(
    question: str,
    context: str,
    history: str,
    query_type: str,
) -> str:
    """
    Generate a conversational guidance answer using the LLM.

    The prompt is designed so the bot behaves like a warm human counsellor:
    - Uses what it knows about the student silently (no "according to your profile")
    - Gives a focused answer, then asks one natural follow-up question
    - Never dumps all CBC information at once
    - Uses correct CBC terminology (STEM, Social Sciences, Arts and Sports Science)
    - Understands the 3-stage journey (pre_exam, post_results, post_placement)
    """

    if query_type == "subject_count_query":
        prompt = f"""You are a CBC Education Guidance Assistant in Kenya.

Question: {question}

{context}

Instructions:
- Answer the subject count question in ONE clear sentence only
- Do NOT explain pathways unless directly asked
- Do NOT add a greeting

Answer:"""

    else:
        prompt = f"""You are a warm, knowledgeable CBC Education Guidance Counsellor helping students and parents in Kenya.

You are having an ongoing conversation. Use the context below to understand who you are talking to, where they are in their journey, and what has been discussed.

--- CONTEXT ---
{context}
--- END CONTEXT ---

The person just said: "{question}"

How to respond:
- Respond like a human counsellor having a natural conversation — not like a search engine returning results
- Use information you know about the student silently. Do NOT say "according to your profile" or "based on your data"
- If they share personal information (grades, interests, worries), acknowledge it naturally before answering
- Give a focused, helpful answer — do NOT list everything you know about CBC at once
- Always use the correct CBC pathway names: STEM, Social Sciences, Arts and Sports Science
- The CBC grading scale is: EE (Exceeds Expectation), ME (Meets Expectation), AE (Approaches Expectation), BE (Below Expectation) — each with levels 1-4
- After your answer, ask ONE natural follow-up question to keep the guidance going
  (e.g. "What subjects does she feel strongest in?" or "Has she thought about any particular career?")
- Keep it conversational — 2 to 3 short paragraphs at most
- If you don't have enough information to answer well, ask a clarifying question instead of guessing
- If the question is about a specific grade like EE2, ME3 etc., explain clearly what it means in the CBC system

Answer:"""

    response = get_llm().invoke(prompt)
    answer   = getattr(response, "content", "") or ""
    answer   = re.sub(r"\s+", " ", answer).strip()
    return answer
