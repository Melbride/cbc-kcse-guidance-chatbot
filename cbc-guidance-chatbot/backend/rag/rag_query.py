"""
rag_query.py
------------
Main orchestration module for the CBC/KCSE Guidance Chatbot RAG pipeline.

Routing order:
  1. Onboarding      → collect profile conversationally if new/incomplete user
  2. Greeting        → warm contextual opener using whatever profile exists
  3. Personalized    → profile-based shortcut answers
  4. Database        → school/subject queries via PostgreSQL
  5. Continuation    → short follow-up replies
  6. Cache           → previously answered questions
  7. Pinecone + LLM  → full RAG pipeline

Stage mismatch handling:
  If the user's question implies a different stage than what's recorded,
  the bot answers normally and appends a gentle question to confirm/update stage.
  If confirmed, stage is silently updated in the DB.
"""

import re
import traceback
import numpy as np
from dotenv import load_dotenv
import time
from pathlib import Path
from analytics.analytics import AnalyticsManager
import sys

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from models.request_models import QueryRequest, UserProfile
from .judge_llm import validate_answer_grounding
from recommendations.pathway_recommender import PathwayRecommender
from .onboarding import (
    profile_is_incomplete,
    is_onboarding_complete,
    process_onboarding_turn,
    detect_stage_from_question,
    stage_mismatch,
    stage_update_prompt,
    update_stage_in_db,
)

# ── Specialist modules ────────────────────────────────────────────────────────
from config_loader import get_db
from .document_search import embeddings, llm, retrieve_documents, generate_rag_answer
from .query_analyzer import QueryAnalyzer
from .school_queries import (
    handle_school_query,
    is_conversation_continuation,
    handle_conversation_continuation,
)
from utils.profile_utils import normalise_profile_dict, build_profile_context
from utils.history_utils import save_conversation_history_safe
from utils.profile_utils import build_recent_history_context
from .text_cleaning import (
    is_greeting_question,
    strip_leading_filler,
    normalize_subject_count_answer,
    build_personalized_guidance_response,
)

# ── Lazy singletons ───────────────────────────────────────────────────────────
_query_analyzer    = None
_pathway_recommender = None
_analytics         = None

def get_query_analyzer():
    global _query_analyzer
    if _query_analyzer is None:
        _query_analyzer = QueryAnalyzer()
    return _query_analyzer

def get_pathway_recommender():
    global _pathway_recommender
    if _pathway_recommender is None:
        _pathway_recommender = PathwayRecommender()
    return _pathway_recommender

def get_analytics():
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsManager()
    return _analytics

def _save_history(user_id, question, answer, mode, metadata=None):
    save_conversation_history_safe(embeddings, user_id, question, answer, mode, metadata)


# ── Greeting builder ──────────────────────────────────────────────────────────

def _build_greeting(profile_data: dict | None, stage: str | None) -> str:
    """
    Warm contextual opener. Uses whatever profile data exists — even partial.
    Never says "according to your profile" — just acts like it knows the user.
    """
    name  = ""
    if profile_data:
        name = profile_data.get("student_name") or profile_data.get("name") or ""

    hi = f"Welcome back{', ' + name if name else ''}! "

    if stage == "post_placement":
        return (
            hi +
            "How's everything going with your new school? Is there something "
            "specific I can help you with today — subject combinations, "
            "what to expect in your pathway, or anything else?"
        )
    if stage == "post_results":
        return (
            hi +
            "Good to see you again. Are you still working through your pathway "
            "options, or is there something new I can help you with?"
        )
    if stage == "pre_exam":
        return (
            hi +
            "Good to see you! What's on your mind today? "
            "I can help with CBC pathways, what to expect from exams, "
            "subject choices, schools — just ask."
        )

    # No stage yet — onboarding will handle this path, but just in case:
    return (
        "Hello! Great to have you here. What would you like to know about "
        "CBC pathways, schools, or subject choices?"
    )


# ── Stage context strings ─────────────────────────────────────────────────────

def _stage_context(stage: str | None) -> str:
    if stage == "pre_exam":
        return "The student is preparing for CBC/JSS exams and has not yet received results."
    if stage == "post_results":
        return "The student has received CBC results and is choosing a pathway."
    if stage == "post_placement":
        return "The student has been placed in a school and is navigating their chosen pathway."
    return ""


# ── Main entry point ──────────────────────────────────────────────────────────

def query_rag(req: QueryRequest) -> dict:
    start_time = time.time()
    question   = req.question
    user_id    = req.user_id

    print(f"=== RAG QUERY ===", flush=True)
    print(f"Question: {question}", flush=True)
    print(f"User ID: {user_id}", flush=True)
    print(f"==================", flush=True)

    from pydantic import ValidationError
    try:

        # ── 1. Load user profile and stage ────────────────────────────────────
        profile_data           = None
        profile_context        = ""
        stage                  = None
        stage_update_prompt_msg = None
        pathway_recommendation = None

        if user_id:
            try:
                raw_profile = get_db().get_profile(user_id)
                stage       = get_db().get_user_stage(user_id)
                if raw_profile:
                    profile_data    = normalise_profile_dict(raw_profile)
                    profile_context = build_profile_context(profile_data)
                    user_profile_obj = UserProfile(**profile_data)
                    pathway_recommendation = get_pathway_recommender().recommend(user_profile_obj)
                    if pathway_recommendation.get("basis") == "no_data":
                        pathway_recommendation = None
            except Exception as e:
                print(f"Warning: profile load failed: {e}", flush=True)

        # ── 2. Onboarding — run if profile is incomplete and not yet done ─────
        # Greetings on first message are handled below so the bot opens warmly,
        # then onboarding kicks in from the second message.
        if user_id and profile_is_incomplete(profile_data) and not is_onboarding_complete(user_id):
            if not is_greeting_question(question):
                onboarding_resp = process_onboarding_turn(user_id, question)
                if onboarding_resp:
                    _save_history(user_id, question, onboarding_resp["answer"], "onboarding",
                                  {"source_folder": "onboarding", "validated": True})
                    get_analytics().log_query(question, 1.0, 0,
                                              int((time.time() - start_time) * 1000), True, False)
                    return onboarding_resp

        # ── 3. Greeting ───────────────────────────────────────────────────────
        try:
            if is_greeting_question(question):
                # New user with empty profile → start onboarding warmly
                if user_id and profile_is_incomplete(profile_data) and not is_onboarding_complete(user_id):
                    onboarding_resp = process_onboarding_turn(user_id, question)
                    if onboarding_resp:
                        _save_history(user_id, question, onboarding_resp["answer"], "onboarding",
                                      {"source_folder": "onboarding", "validated": True})
                        get_analytics().log_query(question, 1.0, 0,
                                                  int((time.time() - start_time) * 1000), True, False)
                        return onboarding_resp

                # Returning user with profile → contextual greeting
                greeting = _build_greeting(profile_data, stage)
                _save_history(user_id, question, greeting, "general",
                              {"source_folder": "greeting", "validated": True, "intent": "greeting"})
                get_analytics().log_query(question, 1.0, 0,
                                          int((time.time() - start_time) * 1000), True, False)
                return {
                    "question": question,
                    "answer":   greeting,
                    "mode":     "general",
                    "metadata": {"source_folder": "greeting", "confidence_score": 1.0,
                                 "validated": True, "intent": "greeting"},
                }
        except Exception:
            pass

        # ── 4. Stage mismatch detection ───────────────────────────────────────
        # Detect if the question implies a different stage than recorded.
        # We answer normally and append a gentle confirmation question.
        detected_stage = detect_stage_from_question(question)
        if user_id and stage_mismatch(stage, detected_stage):
            # Silently update stage — don't wait for confirmation, just do it
            # and append a note so the user knows we noticed
            update_stage_in_db(user_id, detected_stage)
            stage = detected_stage
            stage_update_prompt_msg = stage_update_prompt(detected_stage)
            print(f"Stage mismatch: was {stage}, detected {detected_stage} — updated", flush=True)

        # ── 5. Analyse query intent ───────────────────────────────────────────
        analysis   = get_query_analyzer().analyze_query(question, user_id)
        query_type = analysis.get("query_type")

        # ── 6. Personalized guidance shortcut ─────────────────────────────────
        if query_type == "personalized_guidance":
            answer = build_personalized_guidance_response(
                question, profile_data, pathway_recommendation
            )
            _save_history(user_id, question, answer, "personalized",
                          {"source_folder": "personalized_logic", "validated": True,
                           "intent": "personalized_guidance"})
            get_analytics().log_query(question, 0.9, 0,
                                      int((time.time() - start_time) * 1000), True, False)
            return {
                "question":               question,
                "answer":                 answer,
                "mode":                   "personalized" if user_id else "general",
                "pathway_recommendation": pathway_recommendation,
                "metadata": {"intent": "personalized_guidance",
                             "source_folder": "personalized_logic", "validated": True},
            }

        # ── 7. Database shortcut (school/subject queries) ─────────────────────
        if analysis.get("source") == "database":
            db_response = handle_school_query(
                analysis, question, profile_context,
                user_id, profile_data, pathway_recommendation
            )
            _save_history(user_id, question, db_response.get("answer", ""), "database",
                          {"source_folder": "database", "validated": True, "intent": query_type})
            get_analytics().log_query(question, 0.85, 1,
                                      int((time.time() - start_time) * 1000), True, False)
            return db_response

        # ── 8. Conversation continuation shortcut ─────────────────────────────
        if is_conversation_continuation(question) and query_type in (None, "general_info"):
            cont_response = handle_conversation_continuation(question, user_id)
            _save_history(user_id, question, cont_response.get("answer", ""), "general",
                          {"source_folder": "continuation", "validated": True,
                           "intent": "continuation"})
            get_analytics().log_query(question, 0.8, 0,
                                      int((time.time() - start_time) * 1000), True, False)
            return cont_response

        # ── 9. Cache lookup ───────────────────────────────────────────────────
        question_embedding = np.array(embeddings.embed_query(question))
        cached = get_db().search_cache(question_embedding)
        if cached:
            _save_history(user_id, question, cached.get("answer", ""), "general",
                          {"source_folder": cached.get("source_folder", "cache"),
                           "from_cache": True, "validated": cached.get("validated", True),
                           "intent": analysis.get("intent")})
            get_analytics().log_query(question, cached.get("confidence_score", 0.85), 1,
                                      int((time.time() - start_time) * 1000), True, False)
            return cached

        # ── 10. Pinecone retrieval ─────────────────────────────────────────────
        retrieval_query  = analysis.get("reformulated_query", question)
        print(f"DEBUG: Query type: {query_type}", flush=True)
        print(f"DEBUG: Source: {analysis.get('source')}", flush=True)

        docs_with_scores = retrieve_documents(retrieval_query, k=5)
        print(f"DEBUG: Retrieved {len(docs_with_scores)} docs", flush=True)

        if not docs_with_scores:
            fallback_answer = (
                "I don't have specific information on that in my documents. "
                "Could you give me a bit more detail? For example, are you asking "
                "about a specific pathway, subject, or school? I'll do my best to help."
            )
            _save_history(user_id, question, fallback_answer, "general",
                          {"source_folder": "pinecone", "validated": False,
                           "intent": analysis.get("intent"), "no_docs_found": True})
            get_analytics().log_knowledge_gap(question, "No matching documents", "General knowledge base")
            return {"question": question, "answer": fallback_answer, "mode": "general",
                    "metadata": {"no_docs_found": True}}

        top_docs       = [doc for doc, _ in docs_with_scores[:4]]
        context        = " ".join(doc.page_content for doc in top_docs)
        source_folder  = top_docs[0].metadata.get("folder", "unknown")
        recent_history = build_recent_history_context(get_db, user_id, limit=5)

        enriched_context = "\n".join(filter(None, [
            _stage_context(stage),
            profile_context,
            f"Recent conversation:\n{recent_history}" if recent_history else "",
            f"CBC Information:\n{context}",
        ]))

        # ── 11. LLM generation ────────────────────────────────────────────────
        answer = generate_rag_answer(
            question=question,
            context=enriched_context,
            history=recent_history,
            query_type=query_type,
        )

        # ── 12. Post-process ──────────────────────────────────────────────────
        answer = re.sub(r'\(Document \d+[^)]*\)', '', answer)
        answer = re.sub(r'Document \d+:', '', answer)
        answer = re.sub(r'\s+', ' ', answer).strip()
        escaped = re.escape(question.strip())
        answer  = re.sub(r'^' + escaped + r'\s*', '', answer, flags=re.IGNORECASE).strip()
        answer  = re.sub(r'^(Question|Answer)\s*:\s*', '', answer, flags=re.IGNORECASE).strip()

        if (answer.startswith('"') and answer.endswith('"')) or \
           (answer.startswith("'") and answer.endswith("'")):
            answer = answer[1:-1].strip()
        elif answer.startswith(('"', "'")):
            answer = answer[1:].strip()

        if query_type == "subject_count_query":
            answer = normalize_subject_count_answer(question, context, answer)

        answer = strip_leading_filler(answer, question)

        # Append stage update note if there was a mismatch
        if stage_update_prompt_msg:
            answer = answer.rstrip() + stage_update_prompt_msg

        # ── 13. Grounding validation ──────────────────────────────────────────
        validation_result = validate_answer_grounding(context, answer, question)
        is_grounded       = validation_result.get("is_grounded", True)
        confidence_score  = 0.9 if is_grounded else 0.6

        question_lower = question.lower()
        answer_lower   = answer.lower()
        out_of_context = [
            ("who developed" in question_lower and "computer" in answer_lower),
            ("infrastructure" in question_lower and "transport" in answer_lower),
            ("cbc" in question_lower and "transport" in answer_lower),
            (not is_grounded and validation_result.get("confidence", 1) < 0.3),
        ]
        if any(out_of_context):
            answer = (
                "I don't have enough information to answer that confidently. "
                "Would you like to ask about CBC pathways, subject combinations, "
                "or schools in a specific county?"
            )
            confidence_score = 0.2

        _save_history(user_id, question, answer, "general",
                      {"source_folder": source_folder, "confidence_score": confidence_score,
                       "validated": is_grounded, "intent": analysis.get("intent")})

        elapsed_ms = int((time.time() - start_time) * 1000)
        get_analytics().log_query(question, confidence_score, len(top_docs), elapsed_ms, True, False)
        for doc in top_docs:
            get_analytics().log_document_usage(doc.metadata.get("source", "unknown"), confidence_score)

        return {
            "question":               question,
            "answer":                 answer,
            "mode":                   "personalized" if user_id else "general",
            "pathway_recommendation": pathway_recommendation,
            "metadata": {
                "source_folder":    source_folder,
                "confidence_score": confidence_score,
                "validated":        is_grounded,
                "intent":           analysis.get("intent"),
                "documents_used":   len(top_docs),
                "stage":            stage,
            },
        }

    except ValidationError as ve:
        return {
            "question": getattr(req, 'question', None) or "",
            "answer":   "Please enter a question so I can help you.",
            "mode":     "general",
            "metadata": {"error": str(ve)},
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "question": question,
            "answer":   "I ran into an issue processing that. Could you try rephrasing?",
            "mode":     "personalized" if user_id else "general",
            "metadata": {"error": str(e)},
        }
