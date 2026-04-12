"""
rag_query.py
------------
Clean RAG pipeline. No hardcoded keyword detection. No intent routing.
The LLM handles all intelligence.

Flow per request:
  1. Load user profile + stage from DB
  2. Run onboarding if user has no stage yet
  3. Load last 6 conversation turns
  4. LLM call 1 (tiny): decide what to search and where
     - Returns: pinecone_term (or SKIP), needs_schools (YES/NO),
                county, pathway, gender filters for school query
  5. Pinecone search if pinecone_term is not SKIP
  6. PostgreSQL school query if needs_schools is YES
  7. LLM call 2 (main): profile + history + docs + schools → response
     LLM also signals stage changes via STAGE_UPDATE: tag
  8. Parse stage update, save to DB, return response

Two LLM calls only. Fast and clean.
"""

import os
import json
import traceback
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
    update_stage_in_db,
)
from config_loader import get_db
from utils.history_utils import save_conversation_history_safe
from analytics.analytics import AnalyticsManager
import time

# ── Singletons ────────────────────────────────────────────────────────────────

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


def get_pathway_recommender():
    from recommendations.pathway_recommender import PathwayRecommender
    return PathwayRecommender()


# ── Prompts ───────────────────────────────────────────────────────────────────

# Single routing call — decides BOTH what to search in Pinecone AND
# whether to query the school database, in one LLM call.
ROUTER_SYSTEM = """You are a search router for a CBC education guidance system.

Given a student's message and conversation history, output a JSON object deciding what data to fetch.

Output ONLY valid JSON, nothing else:
{
  "pinecone_term": "search term for CBC curriculum documents, or SKIP if not needed",
  "needs_schools": "YES or NO",
  "county": "Kenya county name or null",
  "pathway": "STEM or SOCIAL SCIENCES or ARTS & SPORTS or null",
  "gender": "BOYS or GIRLS or MIXED or null",
  "school_type": "NATIONAL or COUNTY or SUB-COUNTY or null"
}

Rules for pinecone_term:
- Use 1-6 words for CBC curriculum topics: pathway explanations, grade meanings, career guidance
- SKIP for greetings, small talk, vague messages, or when the question is ONLY about schools
- SKIP for school listings (those come from the school database instead)
- Examples: "CBC grading EE2 meaning" | "STEM pathway explanation" | "Social Sciences careers" | SKIP

Rules for needs_schools:
- YES if the message asks about specific schools, school listings, schools in a county/region,
  schools offering a pathway, boarding schools, girls/boys schools, or school types
- NO for everything else (grades, pathways, careers, subjects, general guidance)

Use conversation history to resolve vague references.
"""

GUIDANCE_SYSTEM = """You are a warm, knowledgeable CBC Education Guidance Counsellor helping students and parents in Kenya navigate the CBC senior school system.

THE CBC SYSTEM:
- After Junior Secondary School (Grade 9), students choose ONE of THREE pathways for senior school:
  1. STEM — Science, Technology, Engineering, Mathematics
  2. Social Sciences — Humanities, Business, Languages
  3. Arts and Sports Science — Creative Arts, Music, Sports, Performance
- CBC grading from highest to lowest: EE2 > EE1 > ME2 > ME1 > AE2 > AE1 > BE2 > BE1
  EE = Exceeds Expectation, ME = Meets Expectation, AE = Approaches Expectation, BE = Below Expectation

RANKED RECOMMENDATIONS:
- When recommending pathways or subject combinations, RANK them from most to least suitable
- Explain WHY each is ranked where it is based on the student's profile, grades, and career goals
- Be specific: "STEM ranks first for you because your mathematics score is strong and you want to engineer"

HONESTY RULES — CRITICAL — READ CAREFULLY:
- ONLY use facts from the CBC documents and school data provided in this prompt
- If specific details like pathway tracks, subject combination codes, or school names are NOT in the provided data, say: "I don't have that specific detail right now — check with your school or the KNEC website"
- NEVER invent pathway tracks, subject codes, school names, or any facts not in the data
- NEVER guess. If it is not in the documents provided, say so.
- It is always better to say "I don't have that detail" than to give wrong information

STAGE DETECTION:
- If the student mentions receiving results or specific grades (EE2, ME1 etc) → add STAGE_UPDATE:post_results on a new line at the very end
- If the student mentions being placed in a school or form one → add STAGE_UPDATE:post_placement on a new line at the very end
- Only add STAGE_UPDATE if you are confident their situation has changed — not for vague statements

GREETING BEHAVIOUR:
- If the student says "Hi", "Hello", or any greeting:
  - If this is their first time: welcome them warmly and ask what they need help with
  - If they are returning: say something like "Welcome back! What would you like to explore today?"
  - NEVER dump their profile information back at them in a greeting
  - NEVER mention their name, interests, or career goals unprompted in a greeting
  - Keep greetings to 1-2 sentences maximum

CONVERSATION STYLE:
- Warm and direct, like a school counsellor talking face to face
- No heavy markdown, no bullet-point walls
- 2 to 4 short paragraphs maximum per response
- Always end with ONE natural follow-up question
- Never repeat the student's profile back to them
- Use "you" and "your" — never use he/she/they when referring to the student
- If they seem confused, simplify and reassure
"""


# ── Step 1: Single routing call ───────────────────────────────────────────────

def route_query(user_message: str, history: list) -> dict:
    """
    Single LLM call that decides:
    - What to search in Pinecone (or SKIP)
    - Whether to query the school database
    - What filters to use for school query

    Returns a dict with keys:
      pinecone_term, needs_schools, county, pathway, gender, school_type
    """
    history_text = ""
    for item in (history or [])[-6:]:
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        # Strip STAGE_UPDATE tags from history
        a = a.split("STAGE_UPDATE:")[0].strip()
        if q:
            history_text += f"User: {q[:150]}\n"
        if a:
            history_text += f"Assistant: {a[:150]}\n"

    user_content = (
        f"Conversation so far:\n{history_text}\nLatest message: {user_message}"
        if history_text
        else f"Latest message: {user_message}"
    )

    defaults = {
        "pinecone_term": user_message[:80],
        "needs_schools": "NO",
        "county": None,
        "pathway": None,
        "gender": None,
        "school_type": None,
    }

    try:
        resp = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.0,
            max_tokens=120,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        print(f"DEBUG router: {parsed}", flush=True)
        return {**defaults, **parsed}
    except Exception as e:
        print(f"Warning: router call failed: {e}", flush=True)
        return defaults


# ── Step 2a: Pinecone retrieval ───────────────────────────────────────────────

def run_pinecone_search(pinecone_term: str) -> list:
    """Search Pinecone for CBC curriculum documents."""
    if not pinecone_term or pinecone_term.upper() == "SKIP":
        return []
    docs = retrieve_documents(pinecone_term, k=5)
    print(f"DEBUG: {len(docs)} docs from Pinecone for '{pinecone_term}'", flush=True)
    return docs


# ── Step 2b: PostgreSQL school query ─────────────────────────────────────────

def run_school_query(route: dict) -> str:
    """
    Query PostgreSQL for schools using filters from the router.
    Returns a formatted string for the main LLM, or empty string if not needed.
    """
    if route.get("needs_schools", "NO").upper() != "YES":
        return ""

    county      = route.get("county")
    pathway     = route.get("pathway")
    gender      = route.get("gender")
    school_type = route.get("school_type")

    print(f"DEBUG: School query — county={county}, pathway={pathway}, gender={gender}", flush=True)

    try:
        result  = get_db().get_schools_catalog(
            pathway=pathway,
            county=county,
            gender=gender,
            school_type=school_type,
            page=1,
            page_size=20,
        )
        schools = result.get("schools", [])
        total   = result.get("total", 0)

        if not schools:
            filters = f"county={county}, pathway={pathway}, gender={gender}"
            return f"No schools found in the database matching: {filters}."

        lines = [f"School data from database ({total} total, showing {len(schools)}):"]
        for s in schools:
            name     = s.get("school_name") or s.get("name") or "Unknown"
            cty      = s.get("county", "")
            stype    = s.get("type") or s.get("school_type", "")
            sgender  = s.get("gender", "")
            pathways = s.get("pathways_offered", [])
            if isinstance(pathways, list):
                pathways_str = ", ".join(pathways) if pathways else "Not specified"
            else:
                pathways_str = str(pathways) if pathways else "Not specified"
            lines.append(f"- {name} | {cty} | {stype} | {sgender} | {pathways_str}")

        return "\n".join(lines)

    except Exception as e:
        print(f"Warning: school DB query failed: {e}", flush=True)
        return "School data is temporarily unavailable."


# ── Context formatters ────────────────────────────────────────────────────────

def format_profile_block(profile: dict | None, stage: str | None) -> str:
    """Build a concise student profile block for the LLM."""
    if not profile:
        return "Student profile: not yet available."

    stage_labels = {
        "pre_exam":       "Stage 1: Before Exams — exploring pathways and interests",
        "post_results":   "Stage 2: After Exams — has CBC results, choosing a pathway",
        "post_placement": "Stage 3: After Placement — placed in school, planning ahead",
    }
    lines = [f"Student stage: {stage_labels.get(stage or '', 'Unknown')}"]

    for key, label in [
        ("name",             "Name"),
        ("favorite_subject", "Favourite subject"),
        ("interests",        "Interests"),
        ("strengths",        "Strengths"),
        ("career_interests", "Career interests"),
        ("learning_style",   "Learning style"),
        ("knec_recommended_pathway", "KNEC recommended pathway"),
        ("placed_school",    "Placed school"),
        ("placed_pathway",   "Placed pathway"),
    ]:
        if profile.get(key):
            lines.append(f"{label}: {profile[key]}")

    if profile.get("stem_score"):
        lines.append(
            f"Pathway scores — STEM: {profile['stem_score']}, "
            f"Social Sciences: {profile.get('social_sciences_score', 'N/A')}, "
            f"Arts & Sports: {profile.get('arts_sports_score', 'N/A')}"
        )

    subjects = profile.get("cbc_subject_results") or []
    if subjects and isinstance(subjects, list):
        subject_lines = []
        for s in subjects[:9]:
            if isinstance(s, dict):
                name = s.get("subject_name", "")
                perf = s.get("performance_level", "")
                pts  = s.get("points", "")
                if name and perf:
                    subject_lines.append(f"{name}: {perf} ({pts} pts)")
        if subject_lines:
            lines.append("CBC results: " + ", ".join(subject_lines))

    return "\n".join(lines)


def format_docs_block(docs_with_scores: list) -> str:
    """Format Pinecone documents for the LLM."""
    if not docs_with_scores:
        return ""
    lines = ["CBC curriculum documents:"]
    for doc, score in docs_with_scores[:5]:
        content = doc.page_content.strip()[:600]
        lines.append(f"---\n{content}")
    return "\n".join(lines)


def format_history_for_llm(history: list) -> list:
    """Convert DB history rows into LLM message format."""
    messages = []
    for item in list(reversed(history))[-10:]:
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        a = a.split("STAGE_UPDATE:")[0].strip()
        if q:
            messages.append({"role": "user",      "content": q})
        if a:
            messages.append({"role": "assistant",  "content": a[:500]})
    return messages


# ── Step 3: Main LLM guidance call ───────────────────────────────────────────

def call_guidance_llm(
    user_message: str,
    profile_block: str,
    docs_block: str,
    school_block: str,
    history_messages: list,
) -> str:
    """Main guidance LLM call. Returns raw response."""
    system_content = GUIDANCE_SYSTEM
    if profile_block:
        system_content += f"\n\n--- STUDENT CONTEXT ---\n{profile_block}"
    if docs_block:
        system_content += f"\n\n--- CBC CURRICULUM DOCUMENTS ---\n{docs_block}"
    if school_block:
        system_content += f"\n\n--- SCHOOL DATA FROM DATABASE ---\n{school_block}"

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
        return "I'm having a little trouble right now. Could you try again?"


# ── Parse stage update signal ─────────────────────────────────────────────────

def parse_stage_update(raw_answer: str) -> tuple[str, dict | None]:
    """
    Check if LLM included a STAGE_UPDATE signal.
    Returns (clean_answer, stage_update_prompt_dict or None).
    """
    if "STAGE_UPDATE:" not in raw_answer:
        return raw_answer, None

    parts     = raw_answer.split("STAGE_UPDATE:")
    answer    = parts[0].strip()
    new_stage = parts[1].strip().split()[0].lower() if len(parts) > 1 else ""

    valid = {"post_results", "post_placement", "pre_exam"}
    if new_stage not in valid:
        return answer, None

    labels = {
        "post_results":   "After Exams (Stage 2)",
        "post_placement": "After Placement (Stage 3)",
        "pre_exam":       "Before Exams (Stage 1)",
    }
    return answer, {
        "should_prompt":  True,
        "detected_stage": new_stage,
        "message":        f"It looks like you may now be in {labels.get(new_stage, new_stage)}.",
    }


# ── Save history ──────────────────────────────────────────────────────────────

def _save_history(user_id, question, answer, mode="general", metadata=None):
    save_conversation_history_safe(
        get_embeddings(), user_id, question, answer, mode, metadata or {}
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def query_rag(req: QueryRequest) -> dict:
    """Main RAG pipeline."""
    start_time = time.time()
    question   = req.question
    user_id    = req.user_id

    print(f"=== RAG QUERY === Q: {question[:80]} | User: {user_id}", flush=True)

    try:
        # ── 1. Load profile and stage ─────────────────────────────────────────
        profile_data = None
        stage        = None

        if user_id:
            try:
                raw_profile = get_db().get_profile(user_id)
                stage       = get_db().get_user_stage(user_id)
                if raw_profile:
                    from utils.profile_utils import normalise_profile_dict
                    profile_data = normalise_profile_dict(raw_profile)
            except Exception as e:
                print(f"Warning: profile load failed: {e}", flush=True)

        # ── 2. Onboarding if user has no stage ────────────────────────────────
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

        # ── 4. Single routing call — decides search strategy ──────────────────
        route = route_query(question, history)

        # ── 5. Pinecone search (CBC curriculum docs) ──────────────────────────
        docs_with_scores = run_pinecone_search(route.get("pinecone_term", ""))

        # ── 6. PostgreSQL school query if needed ──────────────────────────────
        school_block = run_school_query(route)

        # ── 7. Build context ──────────────────────────────────────────────────
        profile_block    = format_profile_block(profile_data, stage)
        docs_block       = format_docs_block(docs_with_scores)
        history_messages = format_history_for_llm(history)

        # ── 8. Generate guidance response ─────────────────────────────────────
        raw_answer = call_guidance_llm(
            user_message     = question,
            profile_block    = profile_block,
            docs_block       = docs_block,
            school_block     = school_block,
            history_messages = history_messages,
        )

        # ── 9. Parse stage update signal ──────────────────────────────────────
        answer, stage_update_prompt = parse_stage_update(raw_answer)

        if stage_update_prompt and user_id:
            update_stage_in_db(user_id, stage_update_prompt["detected_stage"])

        # ── 10. Save to DB ────────────────────────────────────────────────────
        _save_history(user_id, question, answer, "general", {
            "source_folder":    "pinecone+db" if school_block else "pinecone",
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

        print(f"DEBUG: Done in {elapsed_ms}ms — {len(docs_with_scores)} docs, school_block={bool(school_block)}", flush=True)

        return {
            "question":            question,
            "answer":              answer,
            "mode":                "personalized" if user_id else "general",
            "stage_update_prompt": stage_update_prompt,
            "metadata": {
                "source_folder":  "pinecone+db" if school_block else "pinecone",
                "documents_used": len(docs_with_scores),
                "search_term":    route.get("pinecone_term"),
                "stage":          stage,
                "school_query":   bool(school_block),
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
