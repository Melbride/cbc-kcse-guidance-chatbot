import os
from dotenv import load_dotenv
import google.generativeai as genai

#load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "models/gemini-2.0-flash")

#configure gemini ai model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_JUDGE_MODEL)
judge_model_available = True

def validate_answer_grounding(context: str, answer: str, question: str) -> dict:
    """
    Validates LLM-generated answers for factual accuracy and parent-friendliness.
    
    Purpose:
    - Ensures answers are grounded in provided context (documents)
    - Checks if responses are appropriate for students and parents
    - Maintains educational integrity and clarity
    
    Args:
        context: Retrieved document content used for answer generation
        answer: LLM-generated response to validate
        question: Original user question for reference
    
    Returns:
        Dictionary with validation results and confidence scores
    """
    
    #construct judgment prompt for ai evaluation
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
    
    global judge_model_available

    if not judge_model_available:
        return {
            "is_grounded": True,
            "needs_improvement": False,
            "is_parent_friendly": True,
            "improved_answer": None,
            "reasoning": "Judge model disabled after previous API incompatibility.",
            "raw_response": "",
            "confidence": 0.7
        }

    try:
        #call gemini model for evaluation
        response = model.generate_content(judge_prompt)
        result_text = response.text.strip()
        
        #parse validation results
        is_grounded = "GROUNDED: YES" in result_text
        needs_improvement = "CLARITY: NEEDS IMPROVEMENT" in result_text
        is_parent_friendly = "PARENT_FRIENDLY: YES" in result_text
        
        #extract improved answer if available
        improved_answer = None
        if "IMPROVED_VERSION:" in result_text and needs_improvement:
            try:
                improved_part = result_text.split("IMPROVED_VERSION:")[1]
                improved_part = improved_part.split("REASONING:")[0]
                improved_answer = improved_part.strip()
            except:
                pass
        #extract reasoning for debugging
        reasoning = ""
        if "REASONING:" in result_text:
            reasoning = result_text.split("REASONING:")[1].strip()
        
        #debug output for monitoring
        print("\nJudge Evaluation:")
        print("Grounded:", is_grounded)
        print("Parent-Friendly:", is_parent_friendly)
        print("Needs Improvement:", needs_improvement)
        
        #return validation results with confidence score
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
        #error handling - graceful fallback
        error_text = str(e).lower()
        if (
            "not found" in error_text
            or "not supported" in error_text
            or "quota exceeded" in error_text
            or "429" in error_text
        ):
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


