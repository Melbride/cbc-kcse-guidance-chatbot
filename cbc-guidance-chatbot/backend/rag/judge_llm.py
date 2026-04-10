"""
judge_llm.py
------------
Validates that LLM answers are grounded in the retrieved context.
Uses the same Groq client as document_search.py.

FIX: The previous version initialised Groq directly with `Groq(api_key=...)`.
groq==0.9.0 passes `proxies={}` to httpx internally — httpx>=0.28 removed
that kwarg and crashes with "unexpected keyword argument 'proxies'".

Solution: use langchain_groq.ChatGroq (same as document_search.py) which
handles version differences, OR pin httpx==0.27.2 in requirements.txt.
Both fixes are applied here for defence in depth.
"""

import os
from dotenv import load_dotenv

load_dotenv()

_llm_client = None
judge_model_available = True


def _get_llm():
    """Lazy singleton — reuses langchain_groq to avoid the proxies crash."""
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    try:
        from langchain_groq import ChatGroq
        _llm_client = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.1-8b-instant",
            temperature=0.1,
            max_tokens=300,
        )
        return _llm_client
    except Exception as e:
        print(f"Judge LLM init failed: {e}")
        return None


def validate_answer_grounding(context: str, answer: str, question: str) -> dict:
    """
    Check whether an answer is grounded in the retrieved context.
    Returns a dict with is_grounded, needs_improvement, improved_answer, etc.
    Falls back gracefully if the LLM is unavailable.
    """
    global judge_model_available

    _default = {
        "is_grounded": True,
        "needs_improvement": False,
        "is_parent_friendly": True,
        "improved_answer": None,
        "reasoning": "Judge model disabled or unavailable.",
        "raw_response": "",
        "confidence": 0.7,
    }

    if not judge_model_available:
        return _default

    try:
        client = _get_llm()
        if not client:
            raise RuntimeError("Judge LLM client unavailable")

        judge_prompt = f"""You are reviewing a response from a CBC Education Guidance chatbot used by Kenyan students and parents.

CONTEXT (what the bot retrieved):
{context}

QUESTION asked:
{question}

ANSWER given:
{answer}

Evaluate only these three things:
1. Is the answer factually grounded in the context above? (GROUNDED: YES or NO)
2. Is the language clear and simple enough for a parent or Form 1 student? (CLARITY: GOOD or NEEDS IMPROVEMENT)
3. Is the tone appropriate — encouraging, not scary or confusing? (PARENT_FRIENDLY: YES or NO)

If clarity needs improvement, provide a better version.

Respond in EXACTLY this format and nothing else:
GROUNDED: YES
CLARITY: GOOD
PARENT_FRIENDLY: YES
IMPROVED_VERSION: [only if CLARITY is NEEDS IMPROVEMENT]
REASONING: [one sentence]
"""

        response = client.invoke(judge_prompt)
        result_text = getattr(response, "content", "").strip()

        is_grounded        = "GROUNDED: YES" in result_text
        needs_improvement  = "CLARITY: NEEDS IMPROVEMENT" in result_text
        is_parent_friendly = "PARENT_FRIENDLY: YES" in result_text

        improved_answer = None
        if needs_improvement and "IMPROVED_VERSION:" in result_text:
            try:
                part = result_text.split("IMPROVED_VERSION:")[1]
                part = part.split("REASONING:")[0].strip()
                if part:
                    improved_answer = part
            except Exception:
                pass

        reasoning = ""
        if "REASONING:" in result_text:
            reasoning = result_text.split("REASONING:")[1].strip()

        return {
            "is_grounded":        is_grounded,
            "needs_improvement":  needs_improvement,
            "is_parent_friendly": is_parent_friendly,
            "improved_answer":    improved_answer,
            "reasoning":          reasoning,
            "raw_response":       result_text,
            "confidence":         0.9 if (is_grounded and is_parent_friendly) else 0.6,
        }

    except Exception as e:
        error_text = str(e).lower()
        if "quota" in error_text or "429" in error_text:
            judge_model_available = False
            print("Judge LLM: rate limit hit, disabling for this session.")
        else:
            print(f"Judge LLM error: {e}")
        return _default
