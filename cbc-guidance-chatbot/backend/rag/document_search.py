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
    """
    Returns singleton LLM instance.
    FIX: The groq==0.9.0 + httpx>=0.28 combination crashes with
    'unexpected keyword argument proxies'. We now create the Groq client
    directly via langchain_groq (which handles the version differences)
    and avoid passing any httpx client manually.
    The real fix is pinning httpx==0.27.2 in requirements.txt — do that too.
    """
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
                temperature=0.3,   # Slightly higher = more natural, less robotic
                max_tokens=1000,
            )
            # Smoke-test
            test = _LLM.invoke("Hi")
            print("Using Groq LLM — OK.", flush=True)
            return _LLM
        except Exception as e:
            print(f"Groq init failed: {e}", flush=True)

    print("WARNING: Falling back to static LLM responses.", flush=True)
    _LLM = _FallbackLLM()
    return _LLM


class _FallbackLLM:
    def invoke(self, prompt: str):
        return SimpleNamespace(
            content=(
                "I don't have enough information to answer that right now. "
                "You can try rephrasing your question, or check with your school's guidance teacher for help."
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

    IMPROVED: Prompts are now warm and conversational — responses should
    feel like a real guidance counsellor talking to a student or parent,
    not a search engine returning a result.
    """

    # ── Subject count queries need a short, direct answer only ───────────────
    if query_type == "subject_count_query":
        prompt = f"""You are a friendly CBC guidance counsellor helping a student or parent in Kenya.

Question: {question}

Relevant information:
{context}

Give a short, direct answer in one or two sentences. Be warm and clear.
Don't repeat the question. Don't add greetings or extra explanations.

Answer:"""

    # ── All other queries ─────────────────────────────────────────────────────
    else:
        history_section = f"\nRecent conversation:\n{history}\n" if history else ""

        prompt = f"""You are a warm, friendly CBC guidance counsellor helping students and parents in Kenya navigate the new CBC curriculum.

Your job is to give clear, honest, encouraging guidance — like a trusted teacher who truly cares.
You speak simply and directly, as if chatting with a Form 1 student or their parent.
{history_section}
Relevant information from CBC documents:
{context}

Student/Parent question: {question}

How to respond:
- If they greeted you, greet back briefly then answer
- Be conversational — avoid bullet points unless listing schools or subjects  
- Never say "Based on the context" or "According to the document" — just answer naturally
- If you don't know something, say so honestly and suggest they ask their teacher or check the KNEC website
- Keep it to 2–3 short paragraphs at most
- Be encouraging — CBC is new and many learners are confused, so reassure them

Answer:"""

    response = get_llm().invoke(prompt)
    answer = getattr(response, "content", "") or ""
    answer = re.sub(r"\s+", " ", answer).strip()
    return answer
