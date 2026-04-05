import os
import logging
import json as pyjson
import requests
import time
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
logger = logging.getLogger("kcse_query_analyzer")

# Rate limiting cache
_last_api_call = {"gemini": 0, "mistral": 0}
_MIN_API_INTERVAL = 1.0  # seconds between API calls

def analyze_query(user_query: str) -> dict:
    """
    Uses LLM to analyze a user query and extract subject, filters, and intent.
    Returns a dict with keys: subject, filters (dict), intent (string).
    """
    # Check if this is a simple query we can handle intelligently without API
    intelligent_result = intelligent_keyword_analysis(user_query)
    if intelligent_result:
        logger.info(f"Used intelligent keyword analysis for: {user_query}")
        return intelligent_result
    
    # Try LLMs with rate limiting
    llm_prompt = (
        f"""
        Analyze the following user query for a university programme search system. Extract:
        - subject: the main course or programme of interest
        - filters: any constraints (e.g., location, institution type, year)
        - intent: what the user wants (e.g., list, eligibility, requirements)
        Respond in JSON with keys: subject, filters (dict), intent (string).
        User query: {user_query}
        """
    )
    
    # Try Gemini first with rate limiting
    try:
        response = call_gemini_with_rate_limit(llm_prompt)
        if response:
            analysis = parse_llm_response(response, user_query)
            if analysis:
                return analysis
    except Exception as e:
        logger.error(f"Gemini query analysis error: {e}")
    
    # Try Mistral with rate limiting
    try:
        response = call_mistral_with_rate_limit(llm_prompt)
        if response:
            analysis = parse_llm_response(response, user_query)
            if analysis:
                return analysis
    except Exception as e:
        logger.error(f"Mistral query analysis error: {e}")
    
    # Use intelligent fallback
    logger.warning("Both LLMs failed for query analysis, using intelligent keyword extraction")
    return intelligent_keyword_analysis(user_query) or keyword_fallback(user_query)

def intelligent_keyword_analysis(user_query: str) -> dict:
    """
    Intelligent analysis without API calls for common patterns
    """
    user_query_lower = user_query.lower().strip()
    
    # Handle general career guidance questions
    general_patterns = [
        ("what courses can i pursue", "general_career_guidance"),
        ("what can i study", "general_career_guidance"), 
        ("career options", "general_career_guidance"),
        ("what should i study", "general_career_guidance"),
        ("courses for my grades", "general_career_guidance"),
        ("what programmes", "general_career_guidance"),
        ("career advice", "general_career_guidance")
    ]
    
    for pattern, intent in general_patterns:
        if pattern in user_query_lower:
            return {"subject": "career_guidance", "filters": {}, "intent": intent}
    
    # Handle specific subject queries with location
    subject_location_patterns = [
        ("computer science", "computer science"),
        ("engineering", "engineering"),
        ("business", "business studies"),
        ("medical", "medical studies"),
        ("nursing", "nursing"),
        ("teaching", "teaching"),
        ("education", "education"),
        ("medicine", "medicine"),
        ("commerce", "commerce")
    ]
    
    # Extract location
    location_keywords = ["nairobi", "mombasa", "kisumu", "nakuru", "eldoret"]
    location = None
    for loc in location_keywords:
        if loc in user_query_lower:
            location = loc
            break
    
    # Extract subject
    subject = None
    for pattern, subject_name in subject_location_patterns:
        if pattern in user_query_lower:
            subject = subject_name
            break
    
    if subject:
        filters = {}
        if location:
            filters["location"] = location
        return {"subject": subject, "filters": filters, "intent": "search"}
    
    return None  # No intelligent match found

def parse_llm_response(response: str, user_query: str) -> dict:
    """Parse LLM response and validate"""
    try:
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            analysis = pyjson.loads(json_match.group())
        else:
            analysis = pyjson.loads(response)

        subject = analysis.get("subject")
        if subject is None or not isinstance(subject, str) or not subject.strip():
            logger.warning(f"LLM did not extract a valid subject from: {user_query} | Got: {subject}")
            return None
        
        analysis["subject"] = subject.strip()
        return analysis
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}")
        return None

def call_gemini_with_rate_limit(prompt):
    """Gemini API call with rate limiting"""
    current_time = time.time()
    if current_time - _last_api_call["gemini"] < _MIN_API_INTERVAL:
        time.sleep(_MIN_API_INTERVAL - (current_time - _last_api_call["gemini"]))
    
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500}
        }
        response = requests.post(f"{url}?key={GEMINI_API_KEY}", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        _last_api_call["gemini"] = time.time()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return None

def call_mistral_with_rate_limit(prompt):
    """Mistral API call with rate limiting"""
    current_time = time.time()
    if current_time - _last_api_call["mistral"] < _MIN_API_INTERVAL:
        time.sleep(_MIN_API_INTERVAL - (current_time - _last_api_call["mistral"]))
    
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MISTRAL_API_KEY}"
        }
        data = {
            "model": "mistral-tiny",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "temperature": 0.3
        }
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        _last_api_call["mistral"] = time.time()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Mistral API error: {e}")
        return None

def keyword_fallback(user_query: str) -> dict:
    """
    Emergency fallback when all else fails
    """
    user_query_lower = user_query.lower()
    
    # Extract location keywords
    location_keywords = ["nairobi", "mombasa", "kisumu", "nakuru", "eldoret"]
    location = None
    for loc in location_keywords:
        if loc in user_query_lower:
            location = loc
            break
    
    # Simple keyword extraction as last resort
    stop_words = {'in', 'at', 'for', 'the', 'a', 'an', 'and', 'or', 'but', 'with', 'programs', 'programme', 'courses', 'course', 'of', 'to', 'on'}
    words = [word for word in user_query_lower.split() if word not in stop_words and len(word) > 2]
    
    if words:
        subject = ' '.join(words[:3])
    else:
        subject = user_query
        
    filters = {}
    if location:
        filters["location"] = location
        
    return {
        "subject": subject,
        "filters": filters,
        "intent": "search"
    }
