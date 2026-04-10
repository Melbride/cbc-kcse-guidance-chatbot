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
    Calls the HuggingFace Inference API v2 (router endpoint) to embed text.
    Uses all-MiniLM-L6-v2 — same model as the old local version so existing
    Pinecone vectors stay compatible. No torch, no local download.
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
        print("HuggingFace API embeddings initialized (no local model).", flush=True)

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
llm = _LLMProxy()


def get_embeddings():
    global _EMBEDDINGS
    if _EMBEDDINGS is not None:
        return _EMBEDDINGS

    if HUGGINGFACEHUB_API_TOKEN:
        try:
            instance = _HuggingFaceAPIEmbeddings(HUGGINGFACEHUB_API_TOKEN)
            test_result = instance.embed_query("test")
            if isinstance(test_result, list) and len(test_result) > 0:
                _EMBEDDINGS = instance
                print(f"HuggingFace API embeddings: OK (dim={len(test_result)})", flush=True)
                return _EMBEDDINGS
            else:
                print(f"HuggingFace API returned unexpected result: {test_result}", flush=True)
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
    if not groq_api_key:
        print("ERROR: GROQ_API_KEY is not set. LLM will use fallback.", flush=True)
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
        test_response = _LLM.invoke("Say OK")
        print(f"Groq LLM: OK (test={getattr(test_response, 'content', '')[:20]})", flush=True)
        return _LLM
    except Exception as e:
        print(f"ERROR: Groq init/test failed: {e}", flush=True)
        _LLM = _FallbackLLM()
        return _LLM


class _FallbackLLM:
    def invoke(self, prompt: str):
        return SimpleNamespace(
            content=(
                "I'm experiencing technical difficulties right now. "
                "Please try again in a moment."
            )
        )


def retrieve_documents(query: str, k: int = 5):
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
    Build a prompt that makes the LLM behave like a warm guidance counsellor —
    not a question-answering machine. The bot should:
      - Use what it knows about the user from context/history
      - Answer the question, then naturally move the conversation forward
      - Ask one follow-up question to deepen the guidance
      - Never dump all information at once
    """

    if query_type == "subject_count_query":
        # For simple factual counts, stay concise — no follow-up needed
        prompt = f"""You are a CBC Education Guidance Assistant in Kenya.

Question: {question}

{context}

Instructions:
- Answer the subject count question in ONE clear sentence
- Do NOT explain pathways unless asked
- Do NOT add a greeting

Answer:"""

    else:
        # Conversational guidance prompt — the key to natural flow
        prompt = f"""You are a warm, knowledgeable CBC Education Guidance Counsellor helping students and parents in Kenya navigate the CBC system.

You are having an ongoing conversation. Use the context below to understand who you are talking to and what has already been discussed.

--- CONTEXT ---
{context}
--- END CONTEXT ---

The person just said: "{question}"

Your role:
- Respond like a human counsellor, not a search engine
- Use what you know about the student/parent from the context (their results, pathway, interests, stage)
- If they share personal information (e.g. "my daughter got ME2"), acknowledge it warmly and use it
- Give a focused, helpful answer — do NOT list everything you know about CBC at once
- Use the correct CBC pathway names: STEM, Social Sciences, Arts and Sports Science
- After answering, ask ONE natural follow-up question to continue the guidance conversation
  (e.g. "What subjects does she enjoy most?" or "Is she leaning towards any particular career?")
- Keep your response conversational — 2 to 4 short paragraphs maximum
- If you don't have enough information to answer well, ask a clarifying question instead of guessing
- Never say "Based on the documents" or reference your context directly

Answer:"""

    response = get_llm().invoke(prompt)
    answer = getattr(response, "content", "") or ""
    answer = re.sub(r"\s+", " ", answer).strip()
    return answer
