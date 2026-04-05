"""
Lazy document retrieval and answer generation utilities.

This version avoids network-heavy initialization during module import so that
the FastAPI server can start even when external model endpoints are unavailable.
"""

import hashlib
import os
import re
from types import SimpleNamespace

from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

_EMBEDDINGS = None
_VECTORSTORE = None
_LLM = None
_EMBEDDINGS_ERROR = None
_VECTORSTORE_ERROR = None
_LLM_ERROR = None


class _FallbackEmbeddings:
    """Deterministic local fallback so DB/cache code can keep working."""

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


class _EmbeddingsProxy:
    def embed_query(self, text: str):
        return get_embeddings().embed_query(text)


class _LLMProxy:
    def invoke(self, prompt: str):
        return get_llm().invoke(prompt)


embeddings = _EmbeddingsProxy()
llm = _LLMProxy()


def get_embeddings():
    global _EMBEDDINGS, _EMBEDDINGS_ERROR
    if _EMBEDDINGS is not None:
        return _EMBEDDINGS

    try:
        from langchain_huggingface import HuggingFaceEmbeddings

        _EMBEDDINGS = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    except Exception as e:
        _EMBEDDINGS_ERROR = e
        print(f"Warning: falling back to local embeddings because Hugging Face init failed: {e}")
        _EMBEDDINGS = _FallbackEmbeddings()
    return _EMBEDDINGS


def get_vectorstore():
    global _VECTORSTORE, _VECTORSTORE_ERROR
    if _VECTORSTORE is not None:
        return _VECTORSTORE

    if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
        _VECTORSTORE_ERROR = RuntimeError("Missing Pinecone configuration")
        return None

    try:
        from langchain_pinecone import PineconeVectorStore
        from pinecone import Pinecone

        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)
        _VECTORSTORE = PineconeVectorStore(index=index, embedding=get_embeddings())
    except Exception as e:
        _VECTORSTORE_ERROR = e
        print(f"Warning: Pinecone vector store unavailable: {e}")
        _VECTORSTORE = None
    return _VECTORSTORE


def get_llm():
    global _LLM, _LLM_ERROR
    if _LLM is not None:
        return _LLM

    if not HUGGINGFACEHUB_API_TOKEN:
        _LLM_ERROR = RuntimeError("Missing Hugging Face API token")
        _LLM = _FallbackLLM()
        return _LLM

    try:
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

        hf_llm = HuggingFaceEndpoint(
            repo_id="mistralai/Mistral-7B-Instruct-v0.2",
            huggingfacehub_api_token=HUGGINGFACEHUB_API_TOKEN,
            temperature=0.1,
            max_new_tokens=200,
            repetition_penalty=1.05,
            timeout=120,
            do_sample=False,
        )
        _LLM = ChatHuggingFace(llm=hf_llm)
    except Exception as e:
        _LLM_ERROR = e
        print(f"Warning: remote LLM unavailable, using fallback responder: {e}")
        _LLM = _FallbackLLM()
    return _LLM


class _FallbackLLM:
    def invoke(self, prompt: str):
        return SimpleNamespace(
            content=(
                "I can help once the document retrieval and language model services are available. "
                "For now, please try again after confirming the model endpoints are configured."
            )
        )


def retrieve_documents(query: str, k: int = 5):
    """
    Retrieve top-k documents from Pinecone for the given query.
    Returns list of (Document, score) tuples, or an empty list when retrieval is unavailable.
    """
    vectorstore = get_vectorstore()
    if vectorstore is None:
        return []

    try:
        return vectorstore.similarity_search_with_score(query, k=k)
    except Exception as e:
        print(f"Warning: document retrieval failed: {e}")
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
