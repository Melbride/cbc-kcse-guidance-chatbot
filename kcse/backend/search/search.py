# search.py  
"""
Search and recommendation logic for the KCSE guidance chatbot.

Flow per request:
  1. Rewrite the user's message into a DB search term (using conversation history)
  2. Run the DB search with that term
  3. Deduplicate results by (institution, programme)
  4. Filter results by student's mean grade
  5. Pass [system prompt + user profile + full history + DB results] to the LLM
  6. Return the LLM response
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

GRADE_ORDER = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "E"]

def grade_to_int(grade: str) -> int:
    """Convert letter grade to integer rank. Lower = better."""
    grade = str(grade).strip().upper()
    try:
        return GRADE_ORDER.index(grade)
    except ValueError:
        # unknown grade → don't filter out
        return 999  

def student_qualifies(student_grade: str, cutoff: str) -> bool:
    """
    Return True if student's mean grade meets or exceeds the cutoff.
    Handles letter grades (B-, C+) and numeric points (38.64, 28.706).
    If cutoff is unknown/unparseable, always return True (don't filter).
    """
    if not cutoff or str(cutoff).strip() in ("", "None", "N/A", "Not Available"):
        return True

    cutoff = str(cutoff).strip()

    # Try numeric cutoff (KUCCPS cluster points)
    try:
        cutoff_points = float(cutoff)
        # Convert student grade to approximate cluster points
        student_points = GRADE_POINTS.get(student_grade.strip().upper(), 0)
        # Cluster points scale differently — rough map: A=12pts≈48, B-=8pts≈32
        # Just compare proportionally: student_points * 4 vs cutoff_points
        return (student_points * 4) >= cutoff_points
    except ValueError:
        pass

    # Try letter grade cutoff
    student_rank = grade_to_int(student_grade)
    cutoff_rank = grade_to_int(cutoff)
    if cutoff_rank == 999:
        return True  # can't parse cutoff → show it anyway
    return student_rank <= cutoff_rank  


# Profile normalisation
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
    normalized["mean_grade"]   = normalized.get("mean_grade", "")   or ""
    normalized["interests"]    = normalized.get("interests", "")    or ""
    normalized["career_goals"] = normalized.get("career_goals", "") or ""
    return normalized


#DB search
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
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                label, rest = line.split("]", 1)
                label = label.strip("[] ")
                row = eval(rest.strip())
                rows.append({"source": label, "data": row})
            except Exception:
                continue
        return rows
    except subprocess.TimeoutExpired:
        return []


def deduplicate_results(rows: list) -> list:
    """
    Remove duplicate rows that have the same (source, institution, programme).
    This fixes the issue where Kabarak University BSc Nursing appeared 10 times.
    """
    seen = set()
    unique = []
    for item in rows:
        source = item.get("source", "")
        data = item.get("data", [])

        if source == "Degree" and len(data) >= 3:
            key = (source, str(data[1]).strip().lower(), str(data[2]).strip().lower())
        elif source == "Diploma" and len(data) >= 3:
            key = (source, str(data[1]).strip().lower(), str(data[2]).strip().lower())
        elif source == "Artisan" and len(data) >= 3:
            key = (source, str(data[1]).strip().lower(), str(data[2]).strip().lower())
        elif source == "SkillBuilding" and len(data) >= 2:
            key = (source, str(data[0]).strip().lower(), str(data[1]).strip().lower())
        else:
            key = (source, str(data))

        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def filter_by_grade(rows: list, student_grade: str) -> list:
    """
    For Degree results, filter out programmes the student doesn't qualify for.
    Diploma and Artisan are kept as-is since cutoffs vary widely.
    SkillBuilding has no grade requirement.
    """
    if not student_grade:
        # no grade info → show everything
        return rows  

    filtered = []
    for item in rows:
        source = item.get("source", "")
        data = item.get("data", [])

        if source == "Degree" and len(data) >= 4:
            cutoff = str(data[3]).strip()
            if student_qualifies(student_grade, cutoff):
                filtered.append(item)
        else:
            # Diploma, Artisan, SkillBuilding always included
            filtered.append(item)  

    return filtered


#Format DB results for the LLM prompt
def format_db_rows_for_prompt(rows: list) -> str:
    if not rows:
        return "No matching records found in the database."

    by_source = {}
    for item in rows:
        source = item.get("source", "")
        by_source.setdefault(source, []).append(item)

    lines = []

    if "Degree" in by_source:
        lines.append("Degree Programmes")
        for i, item in enumerate(by_source["Degree"][:20], 1):
            data = item.get("data", [])
            if len(data) >= 4:
                institution = str(data[1]).strip()
                programme   = str(data[2]).strip()
                cutoff      = str(data[3]).strip()
                lines.append(f"{i}. {institution} — {programme} (Cutoff: {cutoff})")
        lines.append("")

    if "Diploma" in by_source:
        lines.append("Diploma Programmes")
        for i, item in enumerate(by_source["Diploma"][:15], 1):
            data = item.get("data", [])
            if len(data) >= 3:
                institution = str(data[1]).strip()
                programme   = str(data[2]).strip()
                mean_grade  = str(data[3]).strip() if len(data) > 3 else ""
                grade_str   = f" (Min grade: {mean_grade})" if mean_grade and mean_grade not in ("None","") else ""
                lines.append(f"{i}. {institution} — {programme}{grade_str}")
        lines.append("")

    if "Artisan" in by_source:
        lines.append("Artisan & Certificate Programmes")
        for i, item in enumerate(by_source["Artisan"][:10], 1):
            data = item.get("data", [])
            if len(data) >= 3:
                level       = str(data[0]).strip()
                institution = str(data[1]).strip()
                programme   = str(data[2]).strip()
                lines.append(f"{i}. {institution} — {programme} ({level})")
        lines.append("")

    if "SkillBuilding" in by_source:
        lines.append("Online Courses & Bootcamps")
        for i, item in enumerate(by_source["SkillBuilding"][:15], 1):
            data = item.get("data", [])
            if len(data) >= 6:
                company   = str(data[0]).strip()
                programme = str(data[1]).strip()
                duration  = str(data[3]).strip()
                cost      = str(data[4]).strip()
                link      = str(data[5]).strip()
                lines.append(f"{i}. {company} — {programme}")
                lines.append(f"   Duration: {duration} | Cost: {cost}")
                lines.append(f"   Link: {link}")
        lines.append("")

    #Fallback
    if not lines:
        lines.append("Available Programmes")
        for i, item in enumerate(rows[:20], 1):
            source = item.get("source", "")
            data   = item.get("data", [])
            parts  = [str(x) for x in data if x not in (None, "")]
            lines.append(f"{i}. [{source}] " + " | ".join(parts))

    return "\n".join(lines)


def format_history_for_prompt(history: list) -> str:
    if not history:
        return ""
    lines = []
    for msg in history[-10:]:
        role = msg.get("role", "user")
        text = msg.get("text") or msg.get("content") or ""
        if text:
            lines.append(f"{role.capitalize()}: {text}")
    return "\n".join(lines)


#Rewrite user message → DB search term
REWRITE_SYSTEM = """You extract a short database search term from a student's question.
Rules:
- Output ONLY the search term, nothing else.
- 1-5 words, no punctuation.
- Use the conversation history to resolve vague references like "the second one" or "that course".
- If the question is a greeting or small talk, output: SKIP
- If the question is about career guidance with no specific field mentioned, output: SKIP
- If the student asks for "another course" or "something different", pick a NEW field based on their profile interests or career goals — do NOT repeat the last search term.
- If the student mentions a specific institution (e.g. "Meru University"), include it in the term.

For skill building:
- Online learning / short courses / bootcamps / coding / digital skills → output: IT Coding
- A specific platform by name → output that company name exactly
- Free courses → output: free IT Coding
"""

def rewrite_query(user_message: str, history: list) -> str:
    history_text = format_history_for_prompt(history)
    user_content = (
        f"Conversation so far:\n{history_text}\n\n"
        f"Latest message: {user_message}\n\nSearch term:"
    ) if history_text else f"Latest message: {user_message}\n\nSearch term:"

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
        return ""



#build LLM prompt and call Groq
ADVISOR_SYSTEM = """You are a warm, knowledgeable KCSE career guidance advisor for Kenyan students.

KENYA GRADING SYSTEM — MEMORISE THIS:
Grade order from BEST to WORST: A, A-, B+, B, B-, C+, C, C-, D+, D, D-, E

A student QUALIFIES for a programme if their grade is THE SAME OR BETTER than the cutoff.
"Better" means appearing EARLIER in the list above.

Qualification table:
- Student has A   → qualifies for ALL cutoffs
- Student has A-  → qualifies for: A-, B+, B, B-, C+, C, C-, D+, D, D-, E
- Student has B+  → qualifies for: B+, B, B-, C+, C, C-, D+, D, D-, E
- Student has B   → qualifies for: B, B-, C+, C, C-, D+, D, D-, E
- Student has B-  → qualifies for: B-, C+, C, C-, D+, D, D-, E
- Student has C+  → qualifies for: C+, C, C-, D+, D, D-, E
- Student has C   → qualifies for: C, C-, D+, D, D-, E
- Student has C-  → qualifies for: C-, D+, D, D-, E
- Student has D+  → qualifies for: D+, D, D-, E
- Student has D   → qualifies for: D, D-, E
- Student has D-  → qualifies for: D-, E
- Student has E   → qualifies for: E only

NEVER tell a student they don't qualify when their grade equals or is better than the cutoff.
Example: Student has B-, cutoff is C+ → B- is better than C+ → student QUALIFIES.
Example: Student has B-, cutoff is B- → same grade → student QUALIFIES.
Example: Student has B-, cutoff is B+ → B+ is better than B- → student does NOT qualify.

YOUR CORE RULES:
1. Use ONLY the database results provided. Never invent programmes, institutions, grades, or links.
2. If the database returned results, list ALL of them — do not pick favourites or skip any.
3. Never show the same institution+programme more than once.
4. If the database returned nothing for a specific request, say so honestly. Do not guess. Do NOT say phrases like "I've checked the database results" or "the database results show" or 
   "based on the database results" — just present the information naturally as if you already know it.
   Say things like "Here are some options for you:" or "You qualify for these programmes:" instead.
5. When listing programmes, always show: Institution name, Programme name, and Cutoff/grade if available.
6. Only recommend programmes the student actually qualifies for based on their mean grade using the table above.
7. If the student doesn't qualify for any results, say so kindly and suggest alternatives (diploma, TVET).

HANDLING VAGUE REQUESTS:
- If the student says something vague like "I need guidance", "help me", "I need help", or anything without mentioning a specific field or course — do NOT list courses.
- Instead ask ONE focused question: "What field or career are you interested in?" or "What subjects do you enjoy most?"
- Only search and list programmes once the student has mentioned a specific interest or field.

CONVERSATION STYLE:
- Warm and direct, like a school counsellor talking face to face.
- No heavy markdown. No bold headers. No bullet-point walls.
- Most replies: 2-4 sentences of guidance + the list of programmes + ONE follow-up question.
- Do NOT end every reply with "Do you think you might be interested in...?" — vary your follow-up questions.
- Good follow-up examples: "Would you like to explore diploma options too?", "Do you have a location preference?", "Want me to compare those options for you?"
- Greetings: one sentence only — say "Hello! What can I help you with today?" and nothing else. Do NOT mention the student's name, interests, career goals, or profile in the greeting.
- Never repeat the student's profile back to them at any point.
- If the student asks for your opinion or recommendation, give a clear one based on their grade and interests — don't dodge it.
- If the student says "I want another course" or "something else", suggest a genuinely different field. Don't repeat the last topic.
- Never say "I've checked the database", "the database returned", "database results show", "I found in the database", or any similar phrase. Just present information naturally and conversationally.
- Talk directly using "you" and "your". Never guess gender.
"""

def call_llm(user_message: str, user_profile: dict, history: list, db_results: list) -> str:
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
        f"Database results (already deduplicated and grade-filtered):\n{format_db_rows_for_prompt(db_results)}"
        if db_results else
        "Database results: none found for this query."
    )

    messages = [{"role": "system", "content": ADVISOR_SYSTEM}]
    messages.append({"role": "system", "content": f"{profile_block}\n\n{db_block}"})

    for msg in (history or [])[-10:]:
        role = msg.get("role", "user")
        text = msg.get("text") or msg.get("content") or ""
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})

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
        return "I'm having a little trouble right now. Could you rephrase your question and I'll do my best to help?"

# Logging helpers
def detect_topic(text):
    text_lower = (text or "").lower()
    topic_map = {
        "Engineering":      ["engineering", "mechanical", "electrical", "civil"],
        "Computer Science": ["computer", "software", "ict", "it", "programming", "data science"],
        "Medicine":         ["medicine", "nursing", "clinical", "pharmacy"],
        "Business":         ["business", "commerce", "accounting", "finance"],
        "Teaching":         ["teaching", "education", "teacher"],
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


# Main entry point
def perform_semantic_search(user_query, user_profile, conversation_id=None, history=None, previous_results=None):
    if isinstance(user_profile, str):
        try:
            user_profile = json.loads(user_profile)
        except Exception:
            user_profile = {}
    user_profile = normalize_user_profile(user_profile)
    history = history or []

    #rewrite query → search term
    search_term = rewrite_query(user_query, history)
    print(f"DEBUG search_term: '{search_term}'")

    #search DB
    if not search_term and previous_results:
        db_results = previous_results
    else:
        db_results = run_database_search(search_term) if search_term else []
    print(f"DEBUG db_results count (raw): {len(db_results)}")

    #deduplicate
    db_results = deduplicate_results(db_results)
    print(f"DEBUG db_results count (after dedup): {len(db_results)}")

    #filter by student grade
    student_grade = user_profile.get("mean_grade", "")
    if student_grade:
        db_results = filter_by_grade(db_results, student_grade)
        print(f"DEBUG db_results count (after grade filter): {len(db_results)}")

    #LLM response
    response_text = call_llm(user_query, user_profile, history, db_results)

    #persist context + log
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
