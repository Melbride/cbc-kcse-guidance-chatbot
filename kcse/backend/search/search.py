# search.py
"""
Search and recommendation API logic for the KCSE backend.
Handles semantic search, reranking, and related utilities.
"""
from fastapi import HTTPException
from agents.query_analyzer import analyze_query
from recommendation.conversation_context import get_conversation_context, update_conversation_context
from recommendation.llm_utils import generate_general_explanation, generate_profile_guidance
from results import GRADE_POINTS
from user.admin_store import create_question_log
from conversation.conversation_manager import ConversationManager
from conversation.adaptive_responses import AdaptiveResponseGenerator
import subprocess
import sys
import os
import json

FOLLOW_UP_REQUIREMENT_QUERIES = {
    "what are the requirements",
    "requirements",
    "what requirements",
    "entry requirements",
    "what do i need",
    "what are the entry requirements",
}

INTEREST_HINTS = {
    "laptops": "computer science",
    "computers": "computer science",
    "coding": "computer science",
    "software": "computer science",
    "technology": "computer science",
    "tech": "computer science",
    "business": "business studies",
    "teaching": "teaching",
    "medicine": "medicine",
    "nursing": "nursing",
    "farming": "agriculture",
    "agriculture": "agriculture",
    "design": "animation",
}

SUBJECT_FIELD_HINTS = {
    "Mathematics": ["mathematics", "actuarial science"],
    "English": ["journalism", "communication"],
    "Biology": ["biology", "health"],
    "Chemistry": ["chemistry", "laboratory science"],
    "Physics": ["engineering", "physics"],
    "Business Studies": ["business studies", "commerce"],
    "Computer Studies": ["computer science", "information technology"],
    "Geography": ["geography", "environmental studies"],
}

INTEREST_PREFIXES = [
    "i enjoy",
    "i like",
    "i love",
    "i am interested in",
    "i'm interested in",
    "i prefer",
]

DESCRIPTIVE_PATTERNS = [
    "what is ",
    "what are ",
    "tell me about ",
    "what is the course about",
    "what is this course about",
    "what does ",
    "what do you learn in ",
    "what can i do with ",
]


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
    normalized["mean_grade"] = normalized.get("mean_grade", "") or ""
    normalized["interests"] = normalized.get("interests", "") or ""
    normalized["career_goals"] = normalized.get("career_goals", "") or ""
    return normalized


def normalize_query_text(text):
    return (text or "").strip().lower().rstrip("?.!")


def detect_topic(text):
    text_lower = (text or "").lower()
    topic_map = {
        "Engineering": ["engineering", "mechanical", "electrical", "civil"],
        "Computer Science": ["computer", "software", "ict", "it", "programming"],
        "Medicine": ["medicine", "nursing", "clinical", "pharmacy", "doctor"],
        "Business": ["business", "commerce", "accounting", "finance", "marketing"],
        "Teaching": ["teaching", "education", "teacher"],
    }
    for topic, keywords in topic_map.items():
        if any(keyword in text_lower for keyword in keywords):
            return topic
    return "General"


def log_search_interaction(conversation_id, user_query, response_text, status):
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
    except Exception as error:
        print(f"Question log failed: {error}")


def build_response(payload, conversation_id, user_query, status="answered"):
    message = payload.get("message")
    if conversation_id and message:
        try:
            update_conversation_context(conversation_id, user_query, message)
        except Exception as error:
            print(f"Conversation logging failed: {error}")
        log_search_interaction(conversation_id, user_query, message, status)
    return payload


def run_database_search(search_term):
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "semantic_search.py"), search_term],
            capture_output=True,
            timeout=45,
        )
        if result.returncode != 0:
            print(f"Semantic search subprocess failed: {result.stderr.decode(errors='ignore')}")
        output = result.stdout.decode()
        lines = [line for line in output.splitlines() if line.strip() and line.startswith("[")]
        formatted = []
        for line in lines:
            try:
                label, rest = line.split("]", 1)
                label = label.strip("[] ")
                row = eval(rest.strip())
                formatted.append({"source": label, "data": row})
            except Exception:
                continue
        return formatted
    except subprocess.TimeoutExpired:
        return None


def infer_query_from_interest(text):
    lowered = (text or "").lower()
    for keyword, mapped in INTEREST_HINTS.items():
        if keyword in lowered:
            return mapped
    return ""


def is_interest_statement(text):
    lowered = normalize_query_text(text)
    return any(lowered.startswith(prefix) for prefix in INTEREST_PREFIXES)


def is_descriptive_query(text):
    lowered = normalize_query_text(text)
    return any(lowered.startswith(pattern) for pattern in DESCRIPTIVE_PATTERNS)


def extract_topic_from_descriptive_query(text):
    lowered = (text or "").strip()
    lowered_comp = lowered.lower()
    patterns = [
        "what is the course about",
        "what is this course about",
        "what is ",
        "what are ",
        "tell me about ",
        "what does ",
        "what do you learn in ",
        "what can i do with ",
    ]
    for pattern in patterns:
        if lowered_comp.startswith(pattern):
            topic = lowered[len(pattern):].strip(" ?.")
            if topic:
                if pattern == "what does " and topic.endswith(" involve"):
                    topic = topic[:-len(" involve")].strip()
                if topic.lower().endswith(" about"):
                    topic = topic[:-len(" about")].strip()
                return topic
    return lowered.strip(" ?.")


def resolve_follow_up_topic(previous_query):
    if not previous_query:
        return ""
    if is_descriptive_query(previous_query):
        return extract_topic_from_descriptive_query(previous_query)
    return previous_query


def get_previous_user_query(history, current_query):
    if not history:
        return ""
    current_normalized = (current_query or "").strip().lower()
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if text.lower() == current_normalized:
            continue
        return text
    return ""


def get_profile_guidance_terms(user_profile):
    profile = normalize_user_profile(user_profile)
    terms = []
    seen = set()

    def add_term(value):
        text = (value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            terms.append(text)

    interests = profile.get("interests", "")
    career_goals = profile.get("career_goals", "")

    add_term(infer_query_from_interest(interests))
    add_term(infer_query_from_interest(career_goals))
    add_term(career_goals)
    add_term(interests)

    subject_points = []
    for subject_entry in profile.get("subjects", []):
        text = str(subject_entry)
        if ":" not in text:
            continue
        subject_name, grade = text.split(":", 1)
        points = safe_grade_points(grade)
        if points is None:
            continue
        subject_points.append((points, subject_name.strip()))

    subject_points.sort(reverse=True)
    for _, subject_name in subject_points[:3]:
        for mapped_term in SUBJECT_FIELD_HINTS.get(subject_name, [subject_name]):
            add_term(mapped_term)

    return terms


def merge_result_sets(result_sets, limit=12):
    merged = []
    seen = set()
    for results in result_sets:
        for item in results or []:
            key = (item.get("source", ""), tuple((item.get("data") or [])[:5]))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def parse_subject_map(subject_entries):
    aliases = {
        "math": "Mathematics",
        "mathematics": "Mathematics",
        "eng": "English",
        "english": "English",
        "kis": "Kiswahili",
        "kiswahili": "Kiswahili",
        "bio": "Biology",
        "biology": "Biology",
        "chem": "Chemistry",
        "chemistry": "Chemistry",
        "geo": "Geography",
        "geography": "Geography",
        "hist": "History",
        "history": "History",
        "history & government": "History",
        "physics": "Physics",
        "business": "Business Studies",
        "business studies": "Business Studies",
        "computer": "Computer Studies",
        "computer studies": "Computer Studies",
        "cre": "CRE/IRE",
        "ire": "CRE/IRE",
    }
    parsed = {}
    for entry in subject_entries or []:
        text = str(entry)
        if ":" not in text:
            continue
        subject_name, grade = text.split(":", 1)
        subject_key = aliases.get(subject_name.strip().lower(), subject_name.strip())
        parsed[subject_key] = grade.strip().upper()
    return parsed


def dedupe_results(results):
    seen = set()
    deduped = []
    for item in results:
        source = item.get("source", "")
        row = item.get("data", [])
        key = (source, tuple(row[:5]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def prioritize_results(results, user_query):
    query = (user_query or "").lower()
    source_priority = {"Degree": 3, "Diploma": 3, "Artisan": 3, "SkillBuilding": 3}

    if "diploma" in query:
        source_priority["Diploma"] = 0
        source_priority["Degree"] = 1
        source_priority["Artisan"] = 2
    elif "artisan" in query:
        source_priority["Artisan"] = 0
        source_priority["Diploma"] = 1
        source_priority["Degree"] = 2
    elif "degree" in query or "bachelor" in query:
        source_priority["Degree"] = 0
        source_priority["Diploma"] = 1
        source_priority["Artisan"] = 2
    elif "skill" in query or "online" in query:
        source_priority["SkillBuilding"] = 0

    def score(item):
        source = item.get("source", "")
        row = item.get("data", [])
        text = " ".join(str(part).lower() for part in row[:5])
        keyword_hits = sum(1 for word in query.split() if len(word) > 2 and word in text)
        return (source_priority.get(source, 9), -keyword_hits)

    return sorted(results, key=score)


def safe_grade_points(grade):
    return GRADE_POINTS.get(str(grade or "").strip().upper())


def infer_mean_grade_from_subjects(subject_entries):
    subject_map = parse_subject_map(subject_entries)
    if not subject_map:
        return ""
    points = [safe_grade_points(grade) for grade in subject_map.values()]
    points = [value for value in points if value is not None]
    if not points:
        return ""
    average = sum(points) / len(points)
    nearest = min(GRADE_POINTS.items(), key=lambda item: abs(item[1] - average))
    return nearest[0]


def generate_personalized_guidance(user_name, interests, career_goals, mean_grade, user_subjects):
    """
    Generate highly personalized guidance based on complete user profile
    """
    # Analyze interests and goals to provide specific recommendations
    interest_keywords = interests.lower().split()
    goal_keywords = career_goals.lower().split()
    
    # Map interests to career fields
    field_mapping = {
        'technology': ['computer science', 'software development', 'data science', 'cybersecurity'],
        'business': ['business administration', 'finance', 'marketing', 'entrepreneurship'],
        'medical': ['medicine', 'nursing', 'pharmacy', 'public health'],
        'teaching': ['education', 'teaching', 'educational administration'],
        'engineering': ['engineering', 'technical fields', 'architecture']
    }
    
    # Find matching fields
    suggested_fields = []
    for field, careers in field_mapping.items():
        if any(keyword in interests.lower() for keyword in [field] + careers):
            suggested_fields.extend(careers[:2])  # Top 2 careers per field
    
    # Generate personalized message
    message = (
        f"Perfect! I can see you're interested in {interests} and your goal is {career_goals}. "
        f"That's an excellent combination with your mean grade of {mean_grade}!\n\n"
        f"Based on your profile, here's what I recommend:\n\n"
    )
    
    if suggested_fields:
        message += f"**Career Paths to Consider:**\n"
        for i, field in enumerate(suggested_fields[:3], 1):
            message += f"• {field.title()} - Aligns with your interests in {interests}\n"
    else:
        message += f"**Career Paths to Consider:**\n"
        message += f"• {career_goals.title()} - Direct path to your stated goal\n"
        message += f"• Related fields in {interests} - Build on your natural interests\n"
    
    message += (
        f"\n**Next Steps:**\n"
        f"• Focus on subjects that support {career_goals}\n"
        f"• Look for internships or projects in {interests}\n"
        f"• Consider the specific programmes I found that match your profile\n\n"
        f"Would you like me to show you specific programmes for any of these career paths?"
    )
    
    return message

def generate_general_guidance(user_name, mean_grade, user_subjects, user_query):
    """
    Generate general guidance when profile is incomplete
    """
    # Infer potential fields from subjects if available
    subject_strengths = []
    if user_subjects:
        subject_map = parse_subject_map(user_subjects)
        for subject, grade in subject_map.items():
            if grade in ['A', 'A-', 'B+', 'B']:
                subject_strengths.append(subject)
    
    message = (
        f"Hi {user_name}! I'd be happy to help you explore career options. "
        f"I can see you have a mean grade of {mean_grade or 'not specified yet'}"
    )
    
    if subject_strengths:
        message += f" and strengths in {', '.join(subject_strengths[:3])}"
    
    message += (
        ".\n\n"
        f"To give you the most personalized guidance, it would help to know:\n"
        f"• What subjects or activities do you enjoy?\n"
        f"• What kind of work do you see yourself doing in the future?\n"
        f"• Are there any specific fields you're curious about?\n\n"
        f"You can share this information by updating your profile, or just tell me what interests you right now!"
    )
    
    return message

def format_grounded_results(results, user_profile, user_query):
    profile = normalize_user_profile(user_profile)
    subject_map = parse_subject_map(profile.get("subjects", []))
    mean_grade = profile.get("mean_grade", "") or infer_mean_grade_from_subjects(profile.get("subjects", []))
    mean_points = safe_grade_points(mean_grade)
    interests = profile.get("interests", "")
    career_goals = profile.get("career_goals", "")
    deduped = prioritize_results(dedupe_results(results), user_query)

    if not deduped:
        return "I could not find matching programmes in the current database for that search."

    intro_parts = []
    if subject_map:
        intro_parts.append("your saved subjects")
    if mean_grade:
        intro_parts.append(f"your mean grade ({mean_grade})")
    if interests:
        intro_parts.append("your interests")
    if career_goals:
        intro_parts.append("your career goals")

    intro = "I looked through the course options I have"
    if intro_parts:
        intro += " using " + ", ".join(intro_parts)
    intro += f" and found these matches for \"{user_query}\":"

    lines = [intro, ""]

    degree_note_added = False
    diploma_note_added = False

    for index, item in enumerate(deduped[:5], 1):
        source = item.get("source", "Unknown")
        row = item.get("data", [])

        if source == "Degree":
            programme_code = row[0] if len(row) > 0 else ""
            institution = row[1] if len(row) > 1 else "Unknown institution"
            programme = row[2] if len(row) > 2 else "Programme"
            cutoff = row[3] if len(row) > 3 else None
            qualification_type = row[4] if len(row) > 4 else ""
            minimum_mean = row[5] if len(row) > 5 else ""
            subject_requirements = row[6] if len(row) > 6 else ""
            cluster_info = row[7] if len(row) > 7 else ""
            course_description = row[8] if len(row) > 8 else ""
            career_paths = row[9] if len(row) > 9 else ""
            notes = row[10] if len(row) > 10 else ""
            line = f"{index}. [Degree] {programme} at {institution}"
            details = []
            if programme_code and str(programme_code).lower() != "nan":
                details.append(f"Code: {programme_code}")
            if cutoff not in (None, "", "NaN"):
                details.append(f"Stored cutoff: {cutoff}")
            if minimum_mean:
                details.append(f"Minimum mean grade in the database: {minimum_mean}")
            if details:
                line += f" ({'; '.join(details)})"
            line += "."
            if not degree_note_added:
                if subject_requirements or course_description or career_paths:
                    line += " I found extra degree details in the current dataset, but you should still verify final eligibility with the institution or KUCCPS listing."
                else:
                    line += " I can match degree programmes by name and stored cutoff here, but the current degree table does not include subject-by-subject requirements, so treat these as leads to review rather than confirmed eligibility."
                degree_note_added = True
            extras = []
            if qualification_type and qualification_type.lower() != "degree":
                extras.append(f"Qualification type: {qualification_type}")
            if subject_requirements:
                extras.append(f"Stored subject requirements: {subject_requirements}")
            if cluster_info:
                extras.append(f"Cluster or points info: {cluster_info}")
            if course_description:
                extras.append(f"Course description: {course_description}")
            if career_paths:
                extras.append(f"Career paths: {career_paths}")
            if notes:
                extras.append(f"Notes: {notes}")
            if extras:
                line += " " + " ".join(extras[:3])
            lines.append(line)
            continue

        if source == "Diploma":
            programme_code = row[0] if len(row) > 0 else ""
            institution = row[1] if len(row) > 1 else "Unknown institution"
            programme = row[2] if len(row) > 2 else "Programme"
            required_mean = row[3] if len(row) > 3 else ""
            requirements = row[4] if len(row) > 4 else ""
            line = f"{index}. [Diploma] {programme} at {institution}"
            details = []
            if programme_code:
                details.append(f"Code: {programme_code}")
            if required_mean:
                details.append(f"Minimum mean grade in the database: {required_mean}")
            if requirements:
                details.append(f"Stored requirements: {requirements}")
            if details:
                line += f" ({'; '.join(details)})"
            line += "."
            if not diploma_note_added and mean_grade and required_mean:
                required_points = safe_grade_points(required_mean)
                if mean_points is not None and required_points is not None:
                    if mean_points >= required_points:
                        line += f" Your saved mean grade meets or exceeds that minimum."
                    else:
                        line += f" Your saved mean grade is below that minimum."
                diploma_note_added = True
            lines.append(line)
            continue

        if source == "Artisan":
            level = row[0] if len(row) > 0 else "Artisan"
            institution = row[1] if len(row) > 1 else "Unknown institution"
            programme = row[2] if len(row) > 2 else "Programme"
            required_mean = row[3] if len(row) > 3 else ""
            requirements = row[4] if len(row) > 4 else ""
            line = f"{index}. [Artisan] {programme} at {institution}"
            details = [f"Level: {level}"]
            if required_mean:
                details.append(f"Minimum mean grade in the database: {required_mean}")
            if requirements:
                details.append(f"Stored requirements: {requirements}")
            line += f" ({'; '.join(details)})."
            lines.append(line)
            continue

        if source == "SkillBuilding":
            company = row[0] if len(row) > 0 else "Provider"
            programme = row[1] if len(row) > 1 else "Programme"
            pathway = row[2] if len(row) > 2 else ""
            duration = row[3] if len(row) > 3 else ""
            cost = row[4] if len(row) > 4 else ""
            line = f"{index}. [Skill] {programme} by {company}"
            details = []
            if pathway:
                details.append(f"Pathway: {pathway}")
            if duration:
                details.append(f"Duration: {duration}")
            if cost:
                details.append(f"Cost: {cost}")
            if details:
                line += f" ({'; '.join(details)})"
            line += "."
            lines.append(line)
            continue

        lines.append(f"{index}. {source}: {row}")

    if interests and career_goals:
        closing = "Since you've shared your interests and career goals, these recommendations are tailored to your profile. Would you like more details about any of these options?"
    elif interests or career_goals:
        closing = "I can see some of your preferences. To get more personalized recommendations, consider sharing both your interests and career goals. Would you like more details about any of these options?"
    else:
        closing = "I do not yet have your interests or career goals, so this is still a database match list rather than a final personal recommendation. If you share what you enjoy or the career area you want, I can narrow it further."

    lines.extend(["", closing])
    return "\n".join(lines)


def collect_degree_facts(results):
    facts = {
        "minimum_mean_grade": [],
        "subject_requirements": [],
        "cluster_info": [],
        "course_description": [],
        "career_paths": [],
    }
    seen = {key: set() for key in facts}

    for item in results or []:
        if item.get("source") != "Degree":
            continue
        row = item.get("data", [])
        fact_map = {
            "minimum_mean_grade": row[5] if len(row) > 5 else "",
            "subject_requirements": row[6] if len(row) > 6 else "",
            "cluster_info": row[7] if len(row) > 7 else "",
            "course_description": row[8] if len(row) > 8 else "",
            "career_paths": row[9] if len(row) > 9 else "",
        }
        for key, value in fact_map.items():
            text = str(value or "").strip()
            if text and text not in seen[key]:
                seen[key].add(text)
                facts[key].append(text)
    return facts


def format_descriptive_summary(topic, matched_results):
    facts = collect_degree_facts(matched_results)
    lines = []

    if facts["course_description"]:
        lines.append(f"For the course options I can see here, {topic} usually covers {facts['course_description'][0].rstrip('.')}.")

    if facts["minimum_mean_grade"] or facts["subject_requirements"]:
        req_parts = []
        if facts["minimum_mean_grade"]:
            req_parts.append(f"a minimum mean grade of {facts['minimum_mean_grade'][0]}")
        if facts["subject_requirements"]:
            req_parts.append(f"subject requirements such as {facts['subject_requirements'][0]}")
        if req_parts:
            lines.append("The course options I found also show " + " and ".join(req_parts) + ".")

    return "\n".join(lines)


def format_requirement_summary(topic, matched_results, user_profile):
    profile = normalize_user_profile(user_profile)
    mean_grade = profile.get("mean_grade", "") or infer_mean_grade_from_subjects(profile.get("subjects", []))
    mean_points = safe_grade_points(mean_grade)
    facts = collect_degree_facts(matched_results)
    lines = [f"Here are the main requirements I can see for {topic}:"]

    if facts["minimum_mean_grade"]:
        lines.append(f"- Minimum mean grade shown in related degree entries: {facts['minimum_mean_grade'][0]}")
        required_points = safe_grade_points(facts["minimum_mean_grade"][0])
        if mean_points is not None and required_points is not None:
            if mean_points >= required_points:
                lines.append(f"- Your saved mean grade ({mean_grade}) meets or exceeds that minimum.")
            else:
                lines.append(f"- Your saved mean grade ({mean_grade}) is below that minimum.")

    if facts["subject_requirements"]:
        lines.append(f"- Common stored subject requirements: {facts['subject_requirements'][0]}")
    if facts["cluster_info"]:
        lines.append(f"- Related cluster or points info: {facts['cluster_info'][0]}")

    diploma_rows = [item for item in matched_results if item.get("source") == "Diploma"]
    if diploma_rows:
        row = diploma_rows[0].get("data", [])
        diploma_req = row[4] if len(row) > 4 else ""
        diploma_mean = row[3] if len(row) > 3 else ""
        if diploma_mean or diploma_req:
            details = []
            if diploma_mean:
                details.append(f"minimum mean grade: {diploma_mean}")
            if diploma_req:
                details.append(f"stored requirements: {diploma_req}")
            lines.append(f"- A related diploma entry shows {', '.join(details)}.")

    lines.append("- It would still be wise to confirm the final KUCCPS or institution listing before applying.")
    return "\n".join(lines)


def perform_semantic_search(user_query, user_profile, conversation_id=None, history=None):
    # Parse user profile if it's a JSON string
    if isinstance(user_profile, str):
        try:
            user_profile = json.loads(user_profile)
        except Exception:
            user_profile = {}
    user_profile = normalize_user_profile(user_profile)

    user_query_lower = normalize_query_text(user_query)

    # Step 0: Handle greetings and lightweight follow-ups directly
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
    if user_query_lower in greetings:
        return build_response(
            {
                "results": [],
                "message": "Hello! I can help you explore courses, understand requirements, and look at career options that may suit you. If you want, you can start by asking what you can study with your grades or by naming a field you’re interested in.",
            },
            conversation_id,
            user_query,
            status="greeting",
        )

    follow_up_yes = {"yes", "yeah", "yap", "sure", "okay", "ok", "go on", "continue"}
    if user_query_lower in follow_up_yes:
        ctx = get_conversation_context(conversation_id) if conversation_id else {}
        previous_question = ctx.get("last_user_input", "")
        if previous_question:
            return build_response(
                {
                    "results": [],
                    "message": (
                        "I can continue from your last question, but to keep the guidance grounded in the database, "
                        "tell me the field or programme area you want me to search, such as a specific career path or course name."
                    ),
                },
                conversation_id,
                user_query,
                status="guidance",
            )

    if user_query_lower in FOLLOW_UP_REQUIREMENT_QUERIES:
        previous_query = get_previous_user_query(history, user_query)
        if previous_query:
            resolved_topic = resolve_follow_up_topic(previous_query)
            formatted = run_database_search(resolved_topic)
            if formatted:
                response_text = format_requirement_summary(resolved_topic, formatted, user_profile)
                return build_response(
                    {"results": formatted, "message": response_text},
                    conversation_id,
                    user_query,
                    status="answered",
                )

    inferred_interest_query = infer_query_from_interest(user_query)
    if inferred_interest_query and is_interest_statement(user_query):
        formatted = run_database_search(inferred_interest_query)
        if formatted:
            cleaned_interest = user_query.strip()
            for prefix in INTEREST_PREFIXES:
                if normalize_query_text(cleaned_interest).startswith(prefix):
                    cleaned_interest = cleaned_interest[len(prefix):].strip(" .")
                    break
            response_text = (
                f"You mentioned that you enjoy {cleaned_interest or user_query.strip()}. "
                f"That sounds closest to {inferred_interest_query}, so I checked the course options I have for that area.\n\n"
            )
            response_text += format_grounded_results(formatted, user_profile, inferred_interest_query)
            return build_response(
                {"results": formatted, "message": response_text},
                conversation_id,
                user_query,
                status="answered",
            )

    if is_descriptive_query(user_query):
        descriptive_topic = extract_topic_from_descriptive_query(user_query)
        matched_results = run_database_search(descriptive_topic) or []
        general_explanation = generate_general_explanation(descriptive_topic, user_profile=user_profile, matched_results=matched_results)

        if matched_results:
            database_summary = format_descriptive_summary(descriptive_topic, matched_results)
            response_text = general_explanation.strip()
            if database_summary:
                response_text += f"\n\n{database_summary}"
        else:
            response_text = (
                f"{general_explanation}\n\n"
                "I do not yet have a stored course description for that exact topic in the current records, so I answered that part more generally."
            )

        return build_response(
            {"results": matched_results, "message": response_text},
            conversation_id,
            user_query,
            status="answered",
        )

    # Handle broad guidance questions without making unsupported recommendations.
    general_questions = [
        "what courses can i pursue",
        "what can i study",
        "which course can i do with my grades",
        "which courses can i do with my grades",
        "what course can i do with my grades",
        "career options",
        "what should i study",
        "courses for my grades",
        "what programmes",
        "career advice",
        "which courses fit my kcse results",
        "i want career guidance based on my profile",
        "based on my subjects",
        "based on my profile",
    ]

    if any(q in user_query_lower for q in general_questions):
        user_name = user_profile.get("name", "Student")
        user_subjects = user_profile.get("subjects", [])
        mean_grade = user_profile.get("mean_grade", "") or infer_mean_grade_from_subjects(user_subjects)
        interests = user_profile.get("interests", "")
        career_goals = user_profile.get("career_goals", "")

        if user_subjects:
            subjects_text = ", ".join(user_subjects)
            profile_terms = get_profile_guidance_terms(user_profile)
            profile_matches = []
            for term in profile_terms:
                formatted = run_database_search(term)
                if formatted:
                    profile_matches.append(formatted)

            merged_matches = merge_result_sets(profile_matches)
            if merged_matches:
                natural_guidance = generate_profile_guidance(user_query, user_profile=user_profile, matched_results=merged_matches)
                response_text = (
                    f"{natural_guidance}\n\n"
                    "Here are the course options I found:\n\n"
                    f"{format_grounded_results(merged_matches, user_profile, user_query)}"
                )
                return build_response(
                    {"results": merged_matches, "message": response_text},
                    conversation_id,
                    user_query,
                    status="answered",
                )

            guidance_message = (
                f"Hi {user_name}! I can see your profile with mean grade {mean_grade or 'not yet provided'}, "
                f"subjects {subjects_text}, interests {interests or 'not yet provided'}, "
                f"and career goals {career_goals or 'not yet provided'}. "
                "To keep the guidance accurate and grounded in the database, tell me the field, programme, or career area you want me to search. "
                f"For example, you can name a field like computer science, teaching, business, nursing, or agriculture."
            )
            return build_response(
                {"results": [], "message": guidance_message},
                conversation_id,
                user_query,
                status="guidance",
            )

    conversation_manager = ConversationManager()
    response_generator = AdaptiveResponseGenerator(conversation_manager)
    
    # Use adaptive response generation instead of hardcoded logic
    try:
        adaptive_response = response_generator.generate_response(
            user_id=conversation_id or "default",
            message=user_query,
            user_profile=user_profile
        )
        
        return build_response(
            {"results": [], "message": adaptive_response},
            conversation_id,
            user_query,
            status="guidance",
        )
    except Exception as e:
        # Fallback to basic response if adaptive system fails
        return build_response(
            {"results": [], "message": "I'm here to help you explore career options! What would you like to know about?"},
            conversation_id,
            user_query,
            status="guidance",
        )

    # Step 2: Use semantic_search.py for multi-table retrieval
    formatted = run_database_search(subject)
    if not formatted and subject.strip().lower() != user_query.strip().lower():
        formatted = run_database_search(user_query)
    if formatted is None:
        return build_response(
            {
                "results": [],
                "message": "I could not complete the programme lookup right now. Please try again in a moment.",
            },
            conversation_id,
            user_query,
            status="failed",
        )

    if not formatted:
        return build_response(
            {"results": [], "message": "No similar programmes found."},
            conversation_id,
            user_query,
            status="no_result",
        )

    response_text = format_grounded_results(formatted, user_profile, user_query)
    return build_response(
        {"results": formatted, "llm_analysis": analysis, "message": response_text},
        conversation_id,
        user_query,
        status="answered",
    )
