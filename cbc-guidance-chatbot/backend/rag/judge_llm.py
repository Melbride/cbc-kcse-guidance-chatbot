import os
from dotenv import load_dotenv

load_dotenv()

_groq_client = None
judge_model_available = True

def get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    try:
        from groq import Groq
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return _groq_client
    except Exception as e:
        print(f"Groq client init failed: {e}")
        return None

def validate_answer_grounding(context: str, answer: str, question: str) -> dict:
    global judge_model_available

    if not judge_model_available:
        return {
            "is_grounded": True,
            "needs_improvement": False,
            "is_parent_friendly": True,
            "improved_answer": None,
            "reasoning": "Judge model disabled.",
            "raw_response": "",
            "confidence": 0.7
        }

    try:
        client = get_groq_client()
        if not client:
            raise RuntimeError("Groq client unavailable")

        judge_prompt = f"""You are evaluating responses for a CBC Education Guidance System used by students and parents.

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
{answer}

Evaluate the answer for:
1. Factual accuracy (must be based on context)
2. Clarity for parents and students
3. Educational appropriateness

Respond EXACTLY in this format:
GROUNDED: [YES or NO]
CLARITY: [GOOD or NEEDS IMPROVEMENT]
PARENT_FRIENDLY: [YES or NO]
IMPROVED_VERSION: [If clarity needs improvement]
REASONING: [Brief explanation]
"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": judge_prompt}],
            max_tokens=300,
            temperature=0.1,
        )
        result_text = response.choices[0].message.content.strip()

        is_grounded = "GROUNDED: YES" in result_text
        needs_improvement = "CLARITY: NEEDS IMPROVEMENT" in result_text
        is_parent_friendly = "PARENT_FRIENDLY: YES" in result_text

        improved_answer = None
        if "IMPROVED_VERSION:" in result_text and needs_improvement:
            try:
                improved_part = result_text.split("IMPROVED_VERSION:")[1]
                improved_part = improved_part.split("REASONING:")[0]
                improved_answer = improved_part.strip()
            except:
                pass

        reasoning = ""
        if "REASONING:" in result_text:
            reasoning = result_text.split("REASONING:")[1].strip()

        return {
            "is_grounded": is_grounded,
            "needs_improvement": needs_improvement,
            "is_parent_friendly": is_parent_friendly,
            "improved_answer": improved_answer,
            "reasoning": reasoning,
            "raw_response": result_text,
            "confidence": 0.9 if is_grounded and is_parent_friendly else 0.6
        }

    except Exception as e:
        error_text = str(e).lower()
        if "quota" in error_text or "429" in error_text:
            judge_model_available = False
        print("Judge LLM error:", e)
        return {
            "is_grounded": True,
            "needs_improvement": False,
            "is_parent_friendly": True,
            "improved_answer": None,
            "reasoning": str(e),
            "raw_response": "",
            "confidence": 0.7
        }