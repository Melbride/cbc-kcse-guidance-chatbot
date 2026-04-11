"""
rag_query.py
------------
Clean RAG pipeline. No hardcoded keyword detection. No intent routing.
The LLM handles all intelligence.

Flow per request:
  1. Load user profile + stage from DB
  2. Run onboarding if user has no stage yet
  3. Load last 6 conversation turns
  4. LLM call 1 (tiny): extract Pinecone search term from message
  5. Pinecone search (LangChain) for CBC curriculum documents
  6. PostgreSQL query for school data if question is school-related
  7. LLM call 2 (main): profile + history + docs + schools → guidance response
     The LLM also signals if it thinks the user's stage has changed.
  8. Save conversation to DB
  9. Return response with optional stage_update_prompt for frontend banner
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

REWRITE_SYSTEM = """You extract a short search term from a student's message for use in a vector database search.

Rules:
- Output ONLY the search term. Nothing else. No explanation.
- 1 to 6 words maximum.
- Use conversation history to resolve vague references like "that pathway" or "the first one".
- If the message is a greeting, small talk, or contains nothing specific to search for → output: SKIP
- If the message is about schools → output: SKIP (schools come from a separate database, not vector search)
- If the message is about CBC grades like EE2, ME1 → output: CBC grading performance levels
- If the message is about pathway subject combinations → output: [pathway name] subject combinations
- If the message is about careers → output: careers [field]
- If the message is about a specific pathway → include the pathway name

Examples:
"What does EE2 mean?" → CBC grading EE2 performance level
"What subjects do I take in STEM?" → STEM subject combinations tracks
"I want to be a doctor" → medicine careers CBC pathway
"Which schools offer STEM in Nairobi?" → SKIP
"Hi" → SKIP
"Tell me more" → [use history to determine topic, then output relevant term]
"""

GUIDANCE_SYSTEM = """You are a warm, knowledgeable CBC Education Guidance Counsellor helping students and parents in Kenya navigate the CBC senior school system.

THE CBC SYSTEM:
- After Junior Secondary School (Grade 9), students choose ONE of THREE pathways for senior school:
  1. STEM — Science, Technology, Engineering, Mathematics
  2. Social Sciences — Humanities, Business, Languages
  3. Arts and Sports Science — Creative Arts, Music, Sports, Performance
- CBC grading scale from highest to lowest: EE2, EE1, ME2, ME1, AE2, AE1, BE2, BE1
  EE = Exceeds Expectation, ME = Meets Expectation, AE = Approaches Expectation, BE = Below Expectation

RANKED RECOMMENDATIONS:
- When recommending pathways or subject combinations, always RANK them clearly from most suitable to least suitable based on the student's profile, interests, grades, and career goals
- Explain WHY each option is ranked where it is — what about their profile makes it a good or less good fit
- Be specific: "STEM ranks first for you because..." not just "STEM might be good"
- If the student has grades, use them to inform the ranking
- If the student has career interests, use those to inform the ranking

HONESTY RULES — CRITICAL:
- ONLY use information from the CBC documents and school data provided below
- If specific details are NOT in the provided documents or school data, say honestly: "I don't have that specific detail right now — you can check with your school or the KNEC website"
- NEVER invent pathway tracks, subject combination codes, school names, programme names, or any facts
- NEVER guess or fill gaps with assumed knowledge
- It is better to say "I don't have that detail" than to give wrong information
- If no school data was found for a query, say so honestly

STAGE DETECTION — IMPORTANT:
- Pay attention to what the student says about their situation
- If they mention getting results, grades (like EE2), or having sat exams → they are likely now in Stage 2 (post_results)
- If they mention being placed in a school, form one, reporting date → they are likely in Stage 3 (post_placement)
- If you detect their situation has changed from what their profile shows, add this EXACT text at the very end of your response on a new line:
  STAGE_UPDATE:post_results
  or
  STAGE_UPDATE:post_placement
  (only add this if you are confident their stage has changed — don't add it for vague statements)

CONVERSATION STYLE:
- Warm and direct, like a school counsellor talking face to face
- No heavy markdown, no bullet-point walls
- 2 to 4 short paragraphs maximum per response
- Always end with ONE natural follow-up question to keep the guidance moving
- Never repeat the student's profile back to them
- Use "you" and "your" — never use he/she/they when referring to the student
- If they seem confused, simplify and reassure
- Greetings: respond warmly and ask what they need help with
"""


# ── Query rewrite ─────────────────────────────────────────────────────────────

def rewrite_query(user_message: str, history: list) -> str:
    """
    LLM call 1: extract a Pinecone search term from the user's message.
    Returns empty string if message needs no vector search (SKIP).
    """
    history_text = ""
    for item in (history or [])[-6:]:
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        if q:
            history_text += f"User: {q[:150]}\n"
        if a:
            history_text += f"Assistant: {a[:150]}\n"

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
        return user_message[:100]


# ── School data from PostgreSQL ───────────────────────────────────────────────

def is_school_question(user_message: str, history: list) -> bool:
    """
    Ask the LLM whether this message is asking about schools.
    Simple yes/no call — no keyword matching.
    """
    try:
        resp = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You decide if a message is asking about specific schools, "
                        "school listings, or schools in a county/region. "
                        "Output only YES or NO."
                    )
                },
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return answer == "YES"
    except Exception:
        return False


def fetch_school_data(user_message: str) -> str:
    """
    Pull school data from PostgreSQL based on what the message is asking.
    Uses the LLM to extract county, pathway, gender filters — no hardcoding.
    Returns a formatted string to pass to the main LLM.
    """
    # Ask LLM to extract filters from the message
    try:
        resp = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract school search filters from the message. "
                        "Output ONLY a JSON object with these keys (use null if not mentioned): "
                        '{"county": null, "pathway": null, "gender": null, "school_type": null} '
                        "Pathway must be one of: STEM, SOCIAL SCIENCES, ARTS & SPORTS, or null. "
                        "Gender must be one of: BOYS, GIRLS, MIXED, or null. "
                        "County is a Kenya county name or null."
                    )
                },
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=80,
        )
        raw = resp.choices[0].message.content.strip()
        # Parse JSON
        filters = json.loads(raw)
    except Exception as e:
        print(f"Warning: filter extraction failed: {e}", flush=True)
        filters = {}

    county      = filters.get("county")
    pathway     = filters.get("pathway")
    gender      = filters.get("gender")
    school_type = filters.get("school_type")

    print(f"DEBUG school filters: county={county}, pathway={pathway}, gender={gender}", flush=True)

    try:
        result = get_db().get_schools_catalog(
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
            return f"No schools found in the database for that query (county: {county}, pathway: {pathway})."

        lines = [f"School data from database ({total} total found, showing first {len(schools)}):"]
        for s in schools:
            name       = s.get("school_name") or s.get("name") or "Unknown"
            county_val = s.get("county", "")
            stype      = s.get("type") or s.get("school_type", "")
            sgender    = s.get("gender", "")
            pathways   = s.get("pathways_offered", [])
            if isinstance(pathways, list):
                pathways_str = ", ".join(pathways) if pathways else "Not specified"
            else:
                pathways_str = str(pathways)
            lines.append(
                f"- {name} | {county_val} | {stype} | {sgender} | Pathways: {pathways_str}"
            )
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

    fields = [
        ("name",             "Name"),
        ("favorite_subject", "Favourite subject"),
        ("interests",        "Interests"),
        ("strengths",        "Strengths"),
        ("career_interests", "Career interests"),
        ("learning_style",   "Learning style"),
        ("knec_recommended_pathway", "KNEC recommended pathway"),
        ("placed_school",    "Placed school"),
        ("placed_pathway",   "Placed pathway"),
    ]
    for key, label in fields:
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
        # Strip any STAGE_UPDATE tags from history before sending to LLM
        a = a.split("STAGE_UPDATE:")[0].strip()
        if q:
            messages.append({"role": "user",      "content": q})
        if a:
            messages.append({"role": "assistant",  "content": a[:500]})
    return messages


# ── Main LLM call ─────────────────────────────────────────────────────────────

def call_guidance_llm(
    user_message: str,
    profile_block: str,
    docs_block: str,
    school_block: str,
    history_messages: list,
) -> str:
    """
    Main guidance LLM call.
    Returns raw response including any STAGE_UPDATE tag at the end.
    """
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


# ── Parse LLM response for stage update signal ────────────────────────────────

def parse_stage_update(raw_answer: str) -> tuple[str, dict | None]:
    """
    Check if the LLM included a STAGE_UPDATE signal at the end.
    Returns (clean_answer, stage_update_prompt_dict or None).
    """
    stage_update_prompt = None

    if "STAGE_UPDATE:" in raw_answer:
        parts     = raw_answer.split("STAGE_UPDATE:")
        answer    = parts[0].strip()
        new_stage = parts[1].strip().split()[0].lower() if len(parts) > 1 else ""

        valid_stages = {"post_results", "post_placement", "pre_exam"}
        if new_stage in valid_stages:
            stage_labels = {
                "post_results":   "After Exams (Stage 2)",
                "post_placement": "After Placement (Stage 3)",
                "pre_exam":       "Before Exams (Stage 1)",
            }
            stage_update_prompt = {
                "should_prompt":  True,
                "detected_stage": new_stage,
                "message":        f"It looks like you may now be in {stage_labels.get(new_stage, new_stage)}.",
            }
    else:
        answer = raw_answer

    return answer, stage_update_prompt


# ── Save history ──────────────────────────────────────────────────────────────

def _save_history(user_id, question, answer, mode="general", metadata=None):
    save_conversation_history_safe(
        get_embeddings(), user_id, question, answer, mode, metadata or {}
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def query_rag(req: QueryRequest) -> dict:
    """
    Main RAG pipeline. See module docstring for full flow.
    """
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

        # ── 2. Onboarding if user has no stage set ────────────────────────────
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

        # ── 4. Rewrite query → Pinecone search term ───────────────────────────
        search_term = rewrite_query(question, history)

        # ── 5. Pinecone retrieval (CBC curriculum documents) ──────────────────
        docs_with_scores = []
        if search_term:
            docs_with_scores = retrieve_documents(search_term, k=5)
        print(f"DEBUG: {len(docs_with_scores)} docs from Pinecone for '{search_term}'", flush=True)

        # ── 6. PostgreSQL school data if question is about schools ─────────────
        school_block = ""
        if is_school_question(question, history):
            print("DEBUG: School question detected — querying PostgreSQL", flush=True)
            school_block = fetch_school_data(question)
            print(f"DEBUG: School data: {school_block[:100]}...", flush=True)

        # ── 7. Build context blocks ───────────────────────────────────────────
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

        # ── 9. Parse stage update signal from LLM response ───────────────────
        answer, stage_update_prompt = parse_stage_update(raw_answer)

        # If LLM detected a stage change, update DB silently
        if stage_update_prompt and user_id:
            new_stage = stage_update_prompt.get("detected_stage")
            if new_stage:
                update_stage_in_db(user_id, new_stage)

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

        return {
            "question":           question,
            "answer":             answer,
            "mode":               "personalized" if user_id else "general",
            "stage_update_prompt": stage_update_prompt,
            "metadata": {
                "source_folder":  "pinecone+db" if school_block else "pinecone",
                "documents_used": len(docs_with_scores),
                "search_term":    search_term,
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
