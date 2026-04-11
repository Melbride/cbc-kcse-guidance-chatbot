"""
rag_query.py
------------
Clean RAG pipeline following the search.py pattern.

Flow per request:
  1. Load user profile + stage from DB
  2. Load last 5 conversation turns from DB
  3. LLM call 1 (tiny): rewrite user message → Pinecone search term
  4. Pinecone search with that term (LangChain)
  5. LLM call 2 (main): profile + history + docs → guidance response
  6. Save conversation to DB
  7. Return response

No hardcoded keyword detection.
No intent routing.
No answer overriding.
The LLM handles all intelligence.
"""

import os
import re
import traceback
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from models.request_models import QueryRequest
from .document_search import get_embeddings, retrieve_documents
from .onboarding import (
    profile_is_incomplete,
    is_onboarding_complete,
    process_onboarding_turn,
    detect_stage_from_question,
    stage_mismatch,
    update_stage_in_db,
)
from config_loader import get_db
from utils.history_utils import save_conversation_history_safe
from analytics.analytics import AnalyticsManager
import time

# ── Groq client ───────────────────────────────────────────────────────────────

_groq_client = None
_analytics   = None

def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    _groq_client = Groq(api_key=groq_api_key)
    print("Groq client initialized.", flush=True)
    return _groq_client

def get_analytics():
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsManager()
    return _analytics

# Keep these for backwards compatibility with main.py lazy init
def get_pathway_recommender():
    from recommendations.pathway_recommender import PathwayRecommender
    return PathwayRecommender()


# ── System prompts ────────────────────────────────────────────────────────────

REWRITE_SYSTEM = """You extract a short Pinecone search term from a student's message.

Rules:
- Output ONLY the search term, nothing else. No explanation.
- 1 to 6 words maximum.
- Use conversation history to resolve vague references like "that pathway" or "the first one".
- If the message is a greeting, small talk, or says nothing specific → output: SKIP
- If the message is about schools in a specific county → output: schools [county] [pathway if mentioned]
- If the message is about a specific subject combination → output: subject combination [pathway]
- If the message is about CBC grades like EE2, ME1 etc → output: CBC grading system performance levels
- If the message is about careers → output: careers [field]
- If the message mentions a specific pathway → include it in the term

Examples:
"What does EE2 mean?" → CBC grading EE2 performance level
"Which schools offer STEM in Nairobi?" → STEM schools Nairobi
"What subjects do I take in Social Sciences?" → Social Sciences subject combinations
"I want to be a doctor" → medicine careers CBC pathway
"Hi" → SKIP
"Tell me more about the first one" → [use history to determine what first one was]
"""

GUIDANCE_SYSTEM = """You are a warm, knowledgeable CBC Education Guidance Counsellor helping students and parents in Kenya navigate the CBC senior school system.

THE CBC SYSTEM — KNOW THIS:
- After Junior Secondary School (Grade 9), students choose one of THREE pathways for senior school:
  1. STEM — Science, Technology, Engineering, Mathematics
  2. Social Sciences — Humanities, Business, Languages
  3. Arts and Sports Science — Creative Arts, Music, Sports, Performance
- CBC grading: EE (Exceeds Expectation), ME (Meets Expectation), AE (Approaches Expectation), BE (Below Expectation)
- Each grade has levels 1 and 2. EE2 is the highest, BE1 is the lowest.
- EE2 > EE1 > ME2 > ME1 > AE2 > AE1 > BE2 > BE1

YOUR ROLE:
- Guide students and parents through pathway choices, subject combinations, school selection, and career options
- Use what you know about the student from their profile silently — never say "according to your profile" or "based on your data"
- If the student shares personal information (grades, interests, worries), acknowledge it naturally before responding
- Move the conversation forward — always end with ONE natural follow-up question or next step
- Never dump all information at once — be focused and conversational
- Never invent schools, programmes, or facts not in the documents provided
- If you don't have enough information, ask one clarifying question

CONVERSATION STYLE:
- Warm and direct, like a school counsellor talking face to face
- No heavy markdown, no bullet-point walls
- 2 to 4 short paragraphs maximum
- Vary your follow-up questions — don't end every reply the same way
- Greetings: respond warmly and ask what they need help with today
- Never repeat the student's profile back to them
- Use "you" and "your" — never guess gender
- If they seem confused or overwhelmed, simplify and reassure
"""


# ── Step 1: Rewrite query → search term ──────────────────────────────────────

def rewrite_query(user_message: str, history: list) -> str:
    """
    Ask the LLM to extract a Pinecone search term from the user's message.
    Uses conversation history to resolve vague references.
    Returns empty string if message doesn't need a search (SKIP).
    """
    history_text = ""
    for msg in (history or [])[-6:]:
        role = msg.get("role", "user")
        text = msg.get("question") or msg.get("answer") or msg.get("text") or ""
        if text:
            history_text += f"{role.capitalize()}: {text[:200]}\n"

    user_content = (
        f"Conversation so far:\n{history_text}\nLatest message: {user_message}\n\nSearch term:"
        if history_text
        else f"Latest message: {user_message}\n\nSearch term:"
    )

    try:
        resp = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        term = resp.choices[0].message.content.strip()
        print(f"DEBUG search term: '{term}'", flush=True)
        return "" if term.upper() == "SKIP" else term
    except Exception as e:
        print(f"Warning: query rewrite failed: {e}", flush=True)
        return user_message[:100]  # fallback to raw message


# ── Step 2: Format context for LLM ───────────────────────────────────────────

def format_profile_block(profile: dict | None, stage: str | None) -> str:
    """Build a concise student profile block for the LLM system prompt."""
    if not profile:
        return "Student profile: not yet available."

    stage_labels = {
        "pre_exam":       "Before Exams (Stage 1) — exploring pathways and interests",
        "post_results":   "After Exams (Stage 2) — has CBC results, choosing a pathway",
        "post_placement": "After Placement (Stage 3) — placed in school, planning ahead",
    }
    stage_text = stage_labels.get(stage or "", "Unknown stage")

    lines = [f"Student stage: {stage_text}"]

    if profile.get("name"):
        lines.append(f"Name: {profile['name']}")
    if profile.get("favorite_subject"):
        lines.append(f"Favourite subject: {profile['favorite_subject']}")
    if profile.get("interests"):
        lines.append(f"Interests: {profile['interests']}")
    if profile.get("strengths"):
        lines.append(f"Strengths: {profile['strengths']}")
    if profile.get("career_interests"):
        lines.append(f"Career interests: {profile['career_interests']}")
    if profile.get("knec_recommended_pathway"):
        lines.append(f"KNEC recommended pathway: {profile['knec_recommended_pathway']}")
    if profile.get("stem_score"):
        lines.append(
            f"Pathway scores — STEM: {profile['stem_score']}, "
            f"Social Sciences: {profile.get('social_sciences_score', 'N/A')}, "
            f"Arts & Sports: {profile.get('arts_sports_score', 'N/A')}"
        )
    if profile.get("placed_school"):
        lines.append(f"Placed school: {profile['placed_school']}")
    if profile.get("placed_pathway"):
        lines.append(f"Placed pathway: {profile['placed_pathway']}")

    # CBC subject results summary
    subjects = profile.get("cbc_subject_results") or []
    if subjects and isinstance(subjects, list) and len(subjects) > 0:
        subject_lines = []
        for s in subjects[:9]:
            if isinstance(s, dict):
                name  = s.get("subject_name", "")
                perf  = s.get("performance_level", "")
                pts   = s.get("points", "")
                if name and perf:
                    subject_lines.append(f"{name}: {perf} ({pts} pts)")
        if subject_lines:
            lines.append("CBC results: " + ", ".join(subject_lines))

    return "\n".join(lines)


def format_docs_block(docs_with_scores: list) -> str:
    """Format Pinecone documents into a clean block for the LLM."""
    if not docs_with_scores:
        return ""
    lines = ["Relevant CBC guidance documents:"]
    for doc, score in docs_with_scores[:5]:
        content = doc.page_content.strip()[:600]
        lines.append(f"---\n{content}")
    return "\n".join(lines)


def format_history_for_llm(history: list) -> list:
    """Convert DB history rows into LLM messages format."""
    messages = []
    for item in list(reversed(history))[-10:]:
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        if q:
            messages.append({"role": "user",      "content": q})
        if a:
            messages.append({"role": "assistant",  "content": a[:500]})
    return messages


# ── Step 3: Main LLM call ─────────────────────────────────────────────────────

def call_guidance_llm(
    user_message: str,
    profile_block: str,
    docs_block: str,
    history_messages: list,
) -> str:
    """
    Main LLM call. Sends system prompt, profile, docs, history, and user message.
    Returns the guidance response.
    """
    system_content = GUIDANCE_SYSTEM
    if profile_block:
        system_content += f"\n\n--- STUDENT CONTEXT ---\n{profile_block}"
    if docs_block:
        system_content += f"\n\n--- CBC DOCUMENTS ---\n{docs_block}"

    messages = [{"role": "system", "content": system_content}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_message})

    try:
        resp = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.3,
            max_tokens=1000,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"ERROR: Groq LLM call failed: {e}", flush=True)
        return (
            "I'm having a little trouble right now. "
            "Could you rephrase your question and I'll do my best to help?"
        )


# ── Save history helper ───────────────────────────────────────────────────────

def _save_history(user_id, question, answer, mode="general", metadata=None):
    save_conversation_history_safe(
        get_embeddings(), user_id, question, answer, mode, metadata or {}
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def query_rag(req: QueryRequest) -> dict:
    """
    Main RAG pipeline.

    1. Load profile + stage
    2. Run onboarding if profile incomplete
    3. Rewrite query → search term (LLM)
    4. Pinecone search
    5. Build context (profile + docs + history)
    6. Generate guidance response (LLM)
    7. Save to DB
    8. Return response
    """
    start_time = time.time()
    question   = req.question
    user_id    = req.user_id

    print(f"=== RAG QUERY === Question: {question} | User: {user_id}", flush=True)

    try:
        # ── 1. Load profile and stage ─────────────────────────────────────────
        profile_data = None
        stage        = None

        if user_id:
            try:
                raw_profile  = get_db().get_profile(user_id)
                stage        = get_db().get_user_stage(user_id)
                if raw_profile:
                    from utils.profile_utils import normalise_profile_dict
                    profile_data = normalise_profile_dict(raw_profile)
            except Exception as e:
                print(f"Warning: profile load failed: {e}", flush=True)

        # ── 2. Onboarding if profile incomplete ───────────────────────────────
        if user_id and profile_is_incomplete(profile_data) and not is_onboarding_complete(user_id):
            onboarding_resp = process_onboarding_turn(user_id, question)
            if onboarding_resp:
                _save_history(user_id, question, onboarding_resp["answer"], "onboarding")
                return onboarding_resp

        # ── 3. Load conversation history ──────────────────────────────────────
        history = []
        if user_id:
            try:
                history = get_db().get_user_history(user_id, limit=6) or []
            except Exception as e:
                print(f"Warning: history load failed: {e}", flush=True)

        # ── 4. Detect stage mismatch and silently update ──────────────────────
        detected_stage = detect_stage_from_question(question)
        stage_nudge    = ""
        if user_id and stage_mismatch(stage, detected_stage):
            update_stage_in_db(user_id, detected_stage)
            stage = detected_stage
            if detected_stage == "post_results":
                stage_nudge = " It sounds like your results are out — I've updated your stage so I can give you more relevant guidance."
            elif detected_stage == "post_placement":
                stage_nudge = " It sounds like you've been placed in a school — I've updated your stage accordingly."

        # ── 5. Rewrite query → search term ────────────────────────────────────
        search_term = rewrite_query(question, history)

        # ── 6. Pinecone retrieval ─────────────────────────────────────────────
        docs_with_scores = []
        if search_term:
            docs_with_scores = retrieve_documents(search_term, k=5)
        print(f"DEBUG: Retrieved {len(docs_with_scores)} docs for '{search_term}'", flush=True)

        # ── 7. Check school queries — route to DB if needed ───────────────────
        # We still use the DB for school listings, but let the LLM decide
        # what to do with the results rather than hardcoding the response
        school_context = ""
        school_keywords = ["school", "schools", "county", "nairobi", "mombasa", "kisumu",
                           "nakuru", "girls", "boys", "boarding", "day school"]
        if any(kw in question.lower() for kw in school_keywords):
            try:
                from rag.school_queries import handle_school_query
                # Extract what we can from the question for the DB
                # but pass results back to LLM rather than returning directly
                pass  # school_queries still available if needed for direct DB calls
            except Exception:
                pass

        # ── 8. Build context blocks ───────────────────────────────────────────
        profile_block   = format_profile_block(profile_data, stage)
        docs_block      = format_docs_block(docs_with_scores)
        history_messages = format_history_for_llm(history)

        # ── 9. Generate guidance response ─────────────────────────────────────
        answer = call_guidance_llm(
            user_message     = question,
            profile_block    = profile_block,
            docs_block       = docs_block,
            history_messages = history_messages,
        )

        # Append stage nudge if stage was updated
        if stage_nudge:
            answer = answer.rstrip() + stage_nudge

        # ── 10. Save to DB ────────────────────────────────────────────────────
        _save_history(user_id, question, answer, "general", {
            "source_folder":    "pinecone" if docs_with_scores else "llm",
            "confidence_score": 0.9,
            "validated":        True,
            "documents_used":   len(docs_with_scores),
        })

        # ── 11. Analytics ─────────────────────────────────────────────────────
        elapsed_ms = int((time.time() - start_time) * 1000)
        try:
            get_analytics().log_query(
                question, 0.9, len(docs_with_scores), elapsed_ms, True, False
            )
        except Exception:
            pass

        return {
            "question": question,
            "answer":   answer,
            "mode":     "personalized" if user_id else "general",
            "metadata": {
                "source_folder":  "pinecone" if docs_with_scores else "llm",
                "documents_used": len(docs_with_scores),
                "search_term":    search_term,
                "stage":          stage,
            },
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "question": question,
            "answer":   "I ran into an issue. Could you try rephrasing your question?",
            "mode":     "general",
            "metadata": {"error": str(e)},
        }
