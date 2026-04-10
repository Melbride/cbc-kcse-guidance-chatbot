"""
rag_query.py
------------
Main orchestration module for the CBC/KCSE Guidance Chatbot RAG pipeline.

This file is intentionally slim — it wires together specialist modules:
  document_search.py      → Pinecone retrieval + LLM generation
  query_analyzer.py       → intent detection and routing
  school_queries.py       → DB school/subject query handlers
  profile_utils.py        → profile normalisation and context building
  history_utils.py        → conversation save / recent-context
  text_cleaning.py        → answer cleanup, greeting detection
  recommendation_utils.py → combination scoring helpers
  config_loader.py        → DB singleton, JSON configs

Pinecone handles: curriculum content, career guidance, pathway explanations.
PostgreSQL handles: school listings, subject combinations.
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

# ── Lazy initialization functions ─────────────────────────────────────────────
_query_analyzer = None
_pathway_recommender = None
_analytics = None

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

# ── Thin wrapper so call sites don't need to pass embeddings explicitly ───────
def _save_history(user_id, question, answer, mode, metadata=None):
    save_conversation_history_safe(embeddings, user_id, question, answer, mode, metadata)


# ── Build a warm, contextual greeting based on what we know about the user ────
def _build_greeting(profile_data: dict | None, stage: str | None) -> str:
    """
    Instead of a fixed greeting, open with a warm question that starts
    the guidance conversation naturally — like a counsellor would.
    """
    if profile_data:
        name = profile_data.get("student_name") or profile_data.get("name")
        stage = stage or ""

        if stage == "post_results":
            opener = f"Welcome back{', ' + name if name else ''}! "
            return (
                opener +
                "I see you've already shared some results with me. "
                "How are you feeling about them? Are you looking to understand what they mean, "
                "or are you ready to start thinking about which pathway might suit you?"
            )
        elif stage == "post_placement":
            opener = f"Hello{', ' + name if name else ''}! "
            return (
                opener +
                "I can see you've been placed in a school — congratulations! "
                "Is there something specific you'd like guidance on, like subject combinations "
                "or what to expect in your chosen pathway?"
            )
        elif stage == "pre_exam":
            opener = f"Hi{', ' + name if name else ''}! "
            return (
                opener +
                "Good to see you. Since you're still preparing for your exams, "
                "would you like to talk about what the CBC pathways look like, "
                "or is there something specific you're trying to prepare for?"
            )

    # No profile — open with a question to learn about the user
    return (
        "Hello! I'm here to help you navigate CBC pathways, subject choices, careers, and schools. "
        "To give you the most helpful guidance, could you tell me a little about your situation? "
        "For example — are you a parent or student, and have results come out yet?"
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def query_rag(req: QueryRequest) -> dict:
    """
    Unified RAG pipeline.

    Routing:
      greeting            → contextual opening question (not a fixed response)
      personalized_guidance → text_cleaning.build_personalized_guidance_response
      source == database  → school_queries.handle_school_query
      continuation        → school_queries.handle_conversation_continuation
      cache hit           → return cached answer
      everything else     → Pinecone retrieval → LLM → validate → return
    """
    start_time = time.time()
    question = req.question
    user_id  = req.user_id
    print(f"=== RAG QUERY ===")
    print(f"Question: {question}")
    print(f"User ID: {user_id}")
    print(f"==================")
    sys.stdout.flush()

    from pydantic import ValidationError
    try:
        # ── 1. Load user profile and stage ────────────────────────────────────
        stage_context        = ""
        stage_update_prompt  = None
        pathway_recommendation = None
        profile_context      = ""
        profile_data         = None
        stage                = None

        if user_id:
            profile = get_db().get_profile(user_id)
            stage   = get_db().get_user_stage(user_id)

            if stage == "pre_exam":
                stage_context = "The student is preparing for CBC exams and hasn't received results yet."
            elif stage == "post_results":
                stage_context = "The student has received their CBC results and is deciding on a pathway."
            elif stage == "post_placement":
                stage_context = "The student has been placed in a school and is navigating their chosen pathway."

            stage_check = get_db().should_prompt_for_stage_update(user_id)
            if stage_check.get("should_prompt"):
                stage_update_prompt = stage_check

            if profile:
                profile_data    = normalise_profile_dict(profile)
                profile_context = build_profile_context(profile_data)

                user_profile_obj       = UserProfile(**profile_data)
                pathway_recommendation = get_pathway_recommender().recommend(user_profile_obj)
                if pathway_recommendation.get("basis") == "no_data":
                    pathway_recommendation = None

        # ── 2. Greeting — open with a question, not a wall of info ────────────
        try:
            if is_greeting_question(question):
                greeting_answer = _build_greeting(profile_data, stage)
                _save_history(user_id, question, greeting_answer, "general",
                              {"source_folder": "greeting", "validated": True, "intent": "greeting"})
                elapsed_ms = int((time.time() - start_time) * 1000)
                get_analytics().log_query(question, 1.0, 0, elapsed_ms, True, False)
                return {
                    "question": question,
                    "answer":   greeting_answer,
                    "mode":     "general",
                    "metadata": {
                        "source_folder":    "greeting",
                        "confidence_score": 1.0,
                        "validated":        True,
                        "intent":           "greeting",
                    },
                }
        except Exception:
            pass

        # ── 3. Analyse query intent ───────────────────────────────────────────
        analysis   = get_query_analyzer().analyze_query(question, user_id)
        query_type = analysis.get("query_type")

        # ── 4. Personalized guidance shortcut ─────────────────────────────────
        if query_type == "personalized_guidance":
            answer = build_personalized_guidance_response(
                question, profile_data, pathway_recommendation
            )
            _save_history(user_id, question, answer, "personalized",
                          {"source_folder": "personalized_logic", "validated": True,
                           "intent": "personalized_guidance"})
            elapsed_ms = int((time.time() - start_time) * 1000)
            get_analytics().log_query(question, 0.9, 0, elapsed_ms, True, False)
            return {
                "question":             question,
                "answer":               answer,
                "mode":                 "personalized" if user_id else "general",
                "stage_update_prompt":  stage_update_prompt,
                "pathway_recommendation": pathway_recommendation,
                "metadata": {
                    "intent":        "personalized_guidance",
                    "source_folder": "personalized_logic",
                    "validated":     True,
                },
            }

        # ── 5. Database shortcut (school/subject queries) ─────────────────────
        if analysis.get("source") == "database":
            db_response = handle_school_query(
                analysis, question, profile_context,
                user_id, profile_data, pathway_recommendation
            )
            _save_history(user_id, question, db_response.get("answer", ""), "database",
                          {"source_folder": "database", "validated": True, "intent": query_type})
            elapsed_ms = int((time.time() - start_time) * 1000)
            get_analytics().log_query(question, 0.85, 1, elapsed_ms, True, False)
            return db_response

        # ── 6. Conversation continuation shortcut ─────────────────────────────
        if is_conversation_continuation(question) and query_type in (None, "general_info"):
            cont_response = handle_conversation_continuation(question, user_id)
            _save_history(user_id, question, cont_response.get("answer", ""), "general",
                          {"source_folder": "continuation", "validated": True,
                           "intent": "continuation"})
            elapsed_ms = int((time.time() - start_time) * 1000)
            get_analytics().log_query(question, 0.8, 0, elapsed_ms, True, False)
            return cont_response

        # ── 7. Cache lookup ───────────────────────────────────────────────────
        question_embedding = np.array(embeddings.embed_query(question))
        cached = get_db().search_cache(question_embedding)
        if cached:
            _save_history(user_id, question, cached.get("answer", ""), "general",
                          {"source_folder": cached.get("source_folder", "cache"),
                           "from_cache": True,
                           "validated":  cached.get("validated", True),
                           "intent":     analysis.get("intent")})
            elapsed_ms = int((time.time() - start_time) * 1000)
            get_analytics().log_query(question, cached.get("confidence_score", 0.85), 1, elapsed_ms, True, False)
            return cached

        # ── 8. Pinecone vector search ─────────────────────────────────────────
        retrieval_query  = analysis.get("reformulated_query", question)
        print(f"DEBUG: Retrieval query: {retrieval_query}")
        print(f"DEBUG: Analysis source: {analysis.get('source')}")
        print(f"DEBUG: Query type: {analysis.get('query_type')}")

        docs_with_scores = retrieve_documents(retrieval_query, k=5)
        print(f"DEBUG: Retrieved {len(docs_with_scores)} documents")

        if not docs_with_scores:
            fallback_answer = (
                "I don't have specific information about that in my documents. "
                "Could you tell me a bit more about your situation? For example, "
                "are you asking about a specific pathway, subject, or school? "
                "That way I can try to point you in the right direction."
            )
            fallback = {
                "question": question,
                "answer":   fallback_answer,
                "mode":     "general",
                "metadata": {"no_docs_found": True},
            }
            _save_history(user_id, question, fallback["answer"], "general",
                          {"source_folder": "pinecone", "validated": False,
                           "intent": analysis.get("intent"), "no_docs_found": True})
            elapsed_ms = int((time.time() - start_time) * 1000)
            get_analytics().log_knowledge_gap(question, "No matching documents", "General knowledge base")
            return fallback

        top_docs      = [doc for doc, _ in docs_with_scores[:4]]
        context       = " ".join(doc.page_content for doc in top_docs)
        source_folder = top_docs[0].metadata.get("folder", "unknown")
        recent_history = build_recent_history_context(get_db, user_id, limit=5)

        # Build full prompt context
        enriched_context = "\n".join(filter(None, [
            stage_context,
            profile_context,
            f"Recent conversation:\n{recent_history}" if recent_history else "",
            f"CBC Information:\n{context}",
        ]))

        # ── 9. LLM generation ─────────────────────────────────────────────────
        answer = generate_rag_answer(
            question=question,
            context=enriched_context,
            history=recent_history,
            query_type=query_type,
        )

        # ── 10. Post-process answer ───────────────────────────────────────────
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

        # ── 11. Grounding validation ──────────────────────────────────────────
        validation_result = validate_answer_grounding(context, answer, question)
        is_grounded       = validation_result.get("is_grounded", True)
        confidence_score  = 0.9 if is_grounded else 0.6

        question_lower = question.lower()
        answer_lower   = answer.lower()

        out_of_context_indicators = [
            ("who developed" in question_lower and "computer" in answer_lower),
            ("infrastructure" in question_lower and ("transport" in answer_lower or "sustainability" in answer_lower)),
            ("cbc" in question_lower and ("computer" in answer_lower or "transport" in answer_lower)),
            ("school" in question_lower and ("computer" in answer_lower or "transport" in answer_lower)),
            ("infrastructure in schools" in question_lower and ("sustainability" in answer_lower or "development" in answer_lower)),
            ("lack of infrastructure" in question_lower and ("sustainability" in answer_lower or "development" in answer_lower)),
            ("infrastructure in schools" in question_lower and ("peer training" in answer_lower or "mentorship" in answer_lower)),
            ("lack of infrastructure" in question_lower and ("peer training" in answer_lower or "mentorship" in answer_lower)),
        ]

        if any(out_of_context_indicators) or (not is_grounded and validation_result.get("confidence", 1) < 0.3):
            answer = (
                "I don't have enough information in my documents to answer that confidently. "
                "Would you like to ask about something else — like pathways, subject combinations, "
                "or schools in a specific county?"
            )
            confidence_score = 0.2

        _save_history(user_id, question, answer, "general",
                      {"source_folder": source_folder,
                       "confidence_score": confidence_score,
                       "validated": is_grounded,
                       "intent":    analysis.get("intent")})

        elapsed_ms = int((time.time() - start_time) * 1000)
        get_analytics().log_query(question, confidence_score, len(top_docs), elapsed_ms, True, False)
        for doc in top_docs:
            get_analytics().log_document_usage(doc.metadata.get("source", "unknown"), confidence_score)

        mode = "personalized" if user_id else "general"
        return {
            "question":              question,
            "answer":                answer,
            "mode":                  mode,
            "stage_update_prompt":   stage_update_prompt,
            "pathway_recommendation": pathway_recommendation,
            "metadata": {
                "source_folder":    source_folder,
                "confidence_score": confidence_score,
                "validated":        is_grounded,
                "intent":           analysis.get("intent"),
                "documents_used":   len(top_docs),
                "stage":            get_db().get_user_stage(user_id) if user_id else None,
            },
        }

    except ValidationError as ve:
        return {
            "question": getattr(req, 'question', None) or "",
            "answer":   "Please enter a question so I can help you. (Your message was empty.)",
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
