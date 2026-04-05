"""
Helpers for small answer-cleaning and guidance text tasks used by rag_query.py.
"""

import re


GREETING_PATTERNS = [
    r"^\s*hi\s*$",
    r"^\s*hello\s*$",
    r"^\s*hey\s*$",
    r"^\s*good\s+(morning|afternoon|evening)\s*$",
    r"^\s*how are you\s*\??\s*$",
]


def is_greeting_question(question: str) -> bool:
    if not question:
        return False
    text = str(question).strip().lower()
    return any(re.match(pattern, text) for pattern in GREETING_PATTERNS)


def strip_leading_filler(answer: str, question: str = "") -> str:
    if not answer:
        return ""

    cleaned = answer.strip()
    filler_patterns = [
        r"^(sure|certainly|of course|absolutely|okay|alright)[,!\.\s]+",
        r"^(here('?s| is) (the )?(answer|response))[,:!\.\s]+",
        r"^(based on (the )?(context|information provided))[,:!\.\s]+",
    ]

    for pattern in filler_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned


def normalize_subject_count_answer(question: str, context: str, answer: str) -> str:
    if not answer:
        return ""

    cleaned = strip_leading_filler(answer, question)
    cleaned = re.sub(r"\bthere are are\b", "there are", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthere is is\b", "there is", cleaned, flags=re.IGNORECASE)
    return cleaned


def build_personalized_guidance_response(question: str, profile_data: dict | None, pathway_recommendation: dict | None) -> str:
    profile_data = profile_data or {}
    pathway_recommendation = pathway_recommendation or {}

    name = profile_data.get("name") or "you"
    favorite_subject = profile_data.get("favorite_subject")
    interests = profile_data.get("interests")
    strengths = profile_data.get("strengths")

    recommended_pathway = (
        pathway_recommendation.get("pathway")
        or pathway_recommendation.get("recommended_pathway")
        or pathway_recommendation.get("top_pathway")
    )

    parts = [f"Based on your profile, {name} would benefit from guidance that matches your strengths and interests."]

    if recommended_pathway:
        parts.append(f"Your strongest current pathway fit looks like {recommended_pathway}.")

    if favorite_subject:
        parts.append(f"Your favorite subject, {favorite_subject}, is an important clue when choosing subjects and careers.")

    if interests:
        parts.append(f"Your interests in {interests} should shape the pathways and school options you explore next.")

    if strengths:
        parts.append(f"Your strengths in {strengths} can help you succeed in the right learning environment.")

    if not recommended_pathway and not favorite_subject and not interests and not strengths:
        parts.append("Add more profile details so the chatbot can give more accurate pathway and school guidance.")

    return " ".join(parts)
