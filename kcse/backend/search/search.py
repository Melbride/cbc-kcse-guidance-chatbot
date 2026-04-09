# search.py  (clean rewrite)
"""
Search and recommendation logic for the KCSE guidance chatbot.

Flow per request:
  1. Rewrite the user's message into a DB search term (using conversation history)
  2. Run the DB search with that term
  3. If no results, retry with a broader 1-2 word fallback term
  4. Pass [system prompt + user profile + full history + DB results] to the LLM
  5. Return the LLM response

Nothing else. No keyword trees. No hardcoded templates.
"""

import json
import os
import sys
import subprocess
from groq import Groq
from dotenv import load_dotenv
from results import GRADE_POINTS
from user.admin_store import create_question_log
from recommendation.conversation_context import update_conversation_context

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------------------------------------------------------------
# Helpers kept from the original (DB search + profile normalisation)
# ---------------------------------------------------------------------------

def normalize_user_profile(user_profile):
    profile = user_profile or {}
    extra_data = profile.get("extra_data", {}) if isinstance(profile, dict) else {}
    if isinstance(extra_data, str):
        try:
            extra_data = json.loads(extra_data)
        except Exception:
            extra_data = {}
    subjects = profile.get("subjects") or extra_data.get("subjects") or []
    if not isinstance(subjects, list):
        subjects = []
    normalized = dict(profile) if isinstance(profile, dict) else {}
    normalized["extra_data"] = extra_data
    normalized["subjects"] = subjects
    normalized["mean_grade"]    = normalized.get("mean_grade", "")    or ""
    normalized["interests"]     = normalized.get("interests", "")     or ""
    normalized["career_goals"]  = normalized.get("career_goals", "") or ""
    return normalized


def run_database_search(search_term: str):
    """Run semantic_search.py as a subprocess and return structured rows."""
    if not search_term or not search_term.strip():
        return []
    try:
        result = subprocess.run(
            [sys.executable,
             os.path.join(os.path.dirname(__file__), "semantic_search.py"),
             search_term],
            capture_output=True, timeout=45,
            encoding='utf-8', errors='replace'
        )
        output = result.stdout
        rows = []
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                label, rest = line.split("]", 1)
                label = label.strip("[] ")
                row = eval(rest.strip())          # same as original
                rows.append({"source": label, "data": row})
            except Exception:
                continue
        return rows
    except subprocess.TimeoutExpired:
        return []


def format_db_rows_for_prompt(rows: list) -> str:
    if not rows:
        return "No matching records found in the database."
    
    # Group by source for better organization
    by_source = {}
    for item in rows:
        source = item.get("source", "")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)
    
    lines = []
    
    # Format SkillBuilding results with clean numbered list
    if "SkillBuilding" in by_source:
        lines.append("\n=== Online Courses & Bootcamps ===")
        skillbuilding_items = by_source["SkillBuilding"][:50]  # Show top 50
        for i, item in enumerate(skillbuilding_items, 1):
            data = item.get("data", [])
            if len(data) >= 6:
                company, programme, pathway, duration, cost, link = data[:6]
                # Clean up the formatting
                company = str(company).strip()
                programme = str(programme).strip()
                pathway = str(pathway).strip()
                duration = str(duration).strip()
                cost = str(cost).strip()
                link = str(link).strip()
                
                # Format as clean numbered list with better spacing
                lines.append(f"{i}. {company}")
                lines.append(f"   Course: {programme}")
                lines.append(f"   Pathway: {pathway}")
                lines.append(f"   Duration: {duration} | Cost: {cost}")
                lines.append(f"   Link: {link}")
                lines.append("")  # Add spacing between items
        lines.append("")  # Add spacing after section
    
    # Format Degree results
    if "Degree" in by_source:
        lines.append("=== Degree Programmes ===")
        degree_items = by_source["Degree"][:15]  # Show top 15
        for i, item in enumerate(degree_items, 1):
            data = item.get("data", [])
            if len(data) >= 4:
                prog_code, institution, programme, cutoff = data[:4]
                # Clean up the formatting
                institution = str(institution).strip()
                programme = str(programme).strip()
                cutoff = str(cutoff).strip()
                
                lines.append(f"{i}. {institution}")
                lines.append(f"   Programme: {programme}")
                lines.append(f"   Cutoff: {cutoff}")
                lines.append("")  # Add spacing between items
        lines.append("")  # Add spacing after section
    
    # Format Diploma results
    if "Diploma" in by_source:
        lines.append("=== Diploma Programmes ===")
        diploma_items = by_source["Diploma"][:10]  # Show top 10
        for i, item in enumerate(diploma_items, 1):
            data = item.get("data", [])
            if len(data) >= 3:
                prog_code, institution, programme = data[:3]
                institution = str(institution).strip()
                programme = str(programme).strip()
                
                lines.append(f"{i}. {institution} - {programme}")
        lines.append("")  # Add spacing after section
    
    # Format Artisan results
    if "Artisan" in by_source:
        lines.append("=== Artisan & Certificate Programmes ===")
        artisan_items = by_source["Artisan"][:10]  # Show top 10
        for i, item in enumerate(artisan_items, 1):
            data = item.get("data", [])
            if len(data) >= 3:
                level, institution, programme = data[:3]
                institution = str(institution).strip()
                programme = str(programme).strip()
                
                lines.append(f"{i}. {institution} - {programme} ({level})")
    
    # If no recognized sources, fallback to original format
    if not lines:
        lines.append("=== Available Programmes ===")
        for i, item in enumerate(rows[:20], 1):
            source = item.get("source", "")
            data = item.get("data", [])
            parts = [str(x) for x in data if x not in (None, "")]
            lines.append(f"{i}. [{source}] " + " | ".join(parts))
    
    return "\n".join(lines)


def format_history_for_prompt(history: list) -> str:
    """Turn the history list sent by the frontend into a readable block."""
    if not history:
        return ""
    lines = []
    for msg in history[-10:]:           # last 10 turns is plenty
        role = msg.get("role", "user")
        text = msg.get("text") or msg.get("content") or ""
        if text:
            lines.append(f"{role.capitalize()}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1 – rewrite the user's message into a clean DB search term
# ---------------------------------------------------------------------------

REWRITE_SYSTEM = """You extract a short database search term from a student's question.
Rules:
- Output ONLY the search term, nothing else.
- 1-5 words, no punctuation.
- Use the conversation history to resolve vague references like "the second one" or "that course".
- If the question is a greeting or small talk, output: SKIP
- If the question is about career guidance with no specific field mentioned, output: SKIP

For skill building and online learning, map the intent to what exists in the database:
- Any question about online learning, short courses, self-paced courses, learning from home,
  digital skills, coding bootcamps, or skill building → output: IT Coding
- Any question about a specific platform by name (Udacity, Coursera, ALX, edX, Ajira, 
  FreeCodeCamp, Codecademy, LinkedIn Learning, Khan Academy, Udemy, Skillshare, 
  Pluralsight, MIT, Harvard Online) → output just that company name exactly as written above
- Any question about free courses → output: free IT Coding
- Any question about paid courses → output: paid IT Coding
- Any question about languages or general skills → output: Languages
"""

def rewrite_query(user_message: str, history: list) -> str:
    """Ask the LLM to turn the user message into a DB search term."""
    history_text = format_history_for_prompt(history)
    user_content = (
        f"Conversation so far:\n{history_text}\n\n"
        f"Latest message: {user_message}\n\n"
        "Search term:"
    ) if history_text else (
        f"Latest message: {user_message}\n\nSearch term:"
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        term = resp.choices[0].message.content.strip()
        return "" if term.upper() == "SKIP" else term
    except Exception:
        return ""          # fall through to LLM-only response


# ---------------------------------------------------------------------------
# Step 2 – build the main LLM prompt and call Groq
# ---------------------------------------------------------------------------

ADVISOR_SYSTEM = """You are a warm, knowledgeable KCSE career guidance advisor for Kenyan students.

Your job:
- Help students figure out what to study after high school (universities, diplomas, TVETs, short courses).
- Use ONLY the database results provided to make recommendations. Never invent programmes, grades, or institutions.
- NEVER invent or assume programme names, institution names, grades, requirements, fees, or links that are not in the database results.
- When the database returns multiple results, list ALL of them clearly.
  Do not pick just one or two and ignore the rest.
- For each result show the institution name and programme name on its own line.
- If there are more than 10 results, group them: first Degree programmes, then Diploma, then Artisan, then Skill/Short courses.
- Never say "I only found one" if the database returned more than one result.
- When a student asks what programmes an institution offers, list ALL of them 
  from the database results grouped by type: first Degrees, then Diplomas, 
  then Artisan/Craft certificates. Show every single one — do not summarize 
  or pick favourites. The student needs the full picture.
- Format each programme on its own line like: "• Programme Name (cutoff/grade)"
- If the database returned nothing, say so honestly and ask a clarifying question.
- Keep conversation flowing naturally. If the student changes topic, follow them.
- Ask one focused follow-up question at the end of each response to keep guiding them.
- If the database results include short courses with links, always show the link so the student can visit directly.
- Format links cleanly: "You can visit their website here: [link]"
- When starting a fresh conversation, greet the user warmly but briefly. 
  Do not summarize their entire profile back to them. Just say hello and ask 
  what they need help with today.  
- If the database returned nothing, say honestly: "I don't have that specific information in my database right now." Then suggest the student to visit the institution's website for more information. Do NOT name any institution or course that isn't in the results.


Style:
- Talk directly to the student using "you" and "your".
- Warm and conversational, like a counsellor in person.
- No heavy markdown, no bold headers, no bullet-point walls.
- Keep it concise. Most replies should be 3-6 sentences plus a follow-up question.
- Never guess gender. Never invent interests or goals the student hasn't stated.
- If interests or goals are missing from the profile, mention that naturally and use what you do have.
- Keep greetings short. One sentence maximum. Then ask one question.
"""

def call_llm(user_message: str, user_profile: dict, history: list, db_results: list) -> str:
    """Build the full prompt and get a response from Groq."""
    profile = normalize_user_profile(user_profile)
    subjects_text = ", ".join(profile["subjects"]) if profile["subjects"] else "not provided"

    profile_block = (
        f"Student profile:\n"
        f"  Name: {profile.get('name') or 'not provided'}\n"
        f"  Mean grade: {profile['mean_grade'] or 'not provided'}\n"
        f"  Subjects: {subjects_text}\n"
        f"  Interests: {profile['interests'] or 'not provided'}\n"
        f"  Career goals: {profile['career_goals'] or 'not provided'}"
    )

    db_block = (
        f"Database results:\n{format_db_rows_for_prompt(db_results)}"
        if db_results else
        "Database results: none found for this query."
    )

    history_block = format_history_for_prompt(history)

    # Build messages array — history first, then current turn
    messages = [{"role": "system", "content": ADVISOR_SYSTEM}]

    # Inject profile + DB results as a system-level context message
    messages.append({
        "role": "system",
        "content": f"{profile_block}\n\n{db_block}"
    })

    # Replay recent history so the LLM has full conversational context
    for msg in (history or [])[-10:]:
        role = msg.get("role", "user")
        text = msg.get("text") or msg.get("content") or ""
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})

    # Current user message
    messages.append({"role": "user", "content": user_message})

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.3,
            max_tokens=1500,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM error: {e}")
        return (
            "I'm having a little trouble right now. "
            "Could you rephrase your question and I'll do my best to help?"
        )


# ---------------------------------------------------------------------------
# Logging helpers (unchanged from original)
# ---------------------------------------------------------------------------

def detect_topic(text):
    text_lower = (text or "").lower()
    topic_map = {
        "Engineering":     ["engineering", "mechanical", "electrical", "civil"],
        "Computer Science":["computer", "software", "ict", "it", "programming"],
        "Medicine":        ["medicine", "nursing", "clinical", "pharmacy"],
        "Business":        ["business", "commerce", "accounting", "finance"],
        "Teaching":        ["teaching", "education", "teacher"],
    }
    for topic, keywords in topic_map.items():
        if any(k in text_lower for k in keywords):
            return topic
    return "General"


def log_interaction(conversation_id, user_query, response_text, status):
    if not conversation_id or not user_query:
        return
    try:
        create_question_log(
            conversation_id=conversation_id,
            question=user_query,
            response=response_text or "",
            status=status,
            topic=detect_topic(user_query),
        )
    except Exception as err:
        print(f"Question log failed: {err}")


# ---------------------------------------------------------------------------
# Main entry point (called from main.py)
# ---------------------------------------------------------------------------

def perform_semantic_search(user_query, user_profile, conversation_id=None, history=None, previous_results=None):
    # --- normalise inputs ---
    if isinstance(user_profile, str):
        try:
            user_profile = json.loads(user_profile)
        except Exception:
            user_profile = {}
    user_profile = normalize_user_profile(user_profile)
    history = history or []

    # --- Step 1: rewrite query → DB search term ---
    search_term = rewrite_query(user_query, history)
    print(f"DEBUG search_term: '{search_term}'")

    # --- Step 2: search the database (only if we have a term) ---
    # If no search term (SKIP) but we have previous results, use those
    if not search_term and previous_results:
        db_results = previous_results
    else:
        db_results = run_database_search(search_term) if search_term else []
    print(f"DEBUG db_results count: {len(db_results)}")   # ADD THIS LINE

    # --- Step 3: LLM generates the response ---
    response_text = call_llm(user_query, user_profile, history, db_results)

    # --- Step 4: persist context + log ---
    if conversation_id:
        try:
            update_conversation_context(conversation_id, user_query, response_text)
        except Exception as err:
            print(f"Context update failed: {err}")
        log_interaction(
            conversation_id, user_query, response_text,
            status="answered" if db_results else "guidance"
        )

    return {
        "results": db_results,
        "message": response_text,
    }