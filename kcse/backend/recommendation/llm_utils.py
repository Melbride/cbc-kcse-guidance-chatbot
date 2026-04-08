"""
LLM prompt and explanation utilities for recommendations.
"""
from groq import Groq
import os
import json
import time
from dotenv import load_dotenv
from .conversation_context import get_conversation_context, update_conversation_context

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq client directly
try:
    client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    print(f"Error initializing Groq client: {e}")
    client = None


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

    return {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "mean_grade": profile.get("mean_grade", ""),
        "interests": profile.get("interests", ""),
        "career_goals": profile.get("career_goals", ""),
        "subjects": subjects,
        "extra_data": extra_data,
    }


def build_program_lines(results):
    lines = []
    for i, res in enumerate(results, 1):
        if isinstance(res, dict) and "data" in res:
            data = res["data"]
            source = res.get("source", "Unknown")
            details = [str(item) for item in data if item not in (None, "")]
            if details:
                lines.append(f"{i}. [{source}] " + " | ".join(details))
            else:
                lines.append(f"{i}. [{source}] {res}")
        else:
            lines.append(f"{i}. {res}")
    return "\n".join(lines)

def rerank_with_llm(results, user_profile, conversation_id=None, user_input=None):
    """
    Use LLM to re-rank results based on user profile (interests, goals, etc).
    """
    if not results:
        return []

    profile = normalize_user_profile(user_profile)
    subjects = profile.get("subjects", [])
    subjects_text = ", ".join(subjects) if subjects else "Not provided"

    prompt = f"""You are a KCSE career guidance expert.

Respond directly to the user in second person using "you" and "your".
Do not refer to the user in third person.
Do not guess or infer gender.
Do not invent interests or career goals that are not in the profile.
If interests or goals are missing, say they are not yet provided.
Use a warm, natural, in-person counseling tone.
Do not sound robotic, academic, or overly formal.
Avoid heavy markdown, bold styling, and long report formatting.
Keep the answer practical and easy to read.

Rank the programs for this user based on the profile below.

STUDENT PROFILE:
Name: {profile.get("name") or "Not provided"}
Mean grade: {profile.get("mean_grade") or "Not provided"}
Subjects: {subjects_text}
Interests: {profile.get("interests") or "Not yet provided"}
Career goals: {profile.get("career_goals") or "Not provided"}

AVAILABLE PROGRAMS:
{build_program_lines(results)}
    
TASK:
1. Use all the subject details provided above. Do not skip subjects when assessing fit.
2. Use the mean grade, interests, and career goals if they are present.
3. If interests or career goals are missing, say so plainly and do not make them up.
4. Start with a short natural overview of how the field fits the user's profile.
5. Then recommend the best 3 to 5 options only, in order.
6. For each option, explain the fit in plain conversational language.
7. Mention any important caution, such as a likely weakness in subject requirements.
8. If engineering or another field usually needs Physics and it is not shown in the profile, mention that clearly.
9. Do not claim a university is top-ranked, flexible, or famous unless that is directly present in the provided data.
10. Do not use the user's name repeatedly.
11. Keep the reply concise and human, like speaking to a student in person.

USER'S CURRENT QUESTION: {user_input or 'General program search'}

Write the answer as a natural reply, not as a formal report."""
    
    # Add conversation context if available
    if conversation_id and user_input:
        ctx = get_conversation_context(conversation_id)
        if ctx:
            prompt = f"PREVIOUS CONTEXT: Student asked '{ctx.get('last_user_input', '')}' and got advice about '{ctx.get('last_system_response', '')}'.\n\n" + prompt
    
    # Use Groq client directly
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000
        )
        response_text = response.choices[0].message.content
        
        # Update context
        if conversation_id and user_input:
            update_conversation_context(conversation_id, user_input, response_text)
        return response_text
    except Exception as e:
        print(f"Groq client error: {e}")
        # Only use fallback if LLM fails
        return simple_rerank(results, profile, user_input=user_input)

def simple_rerank(results, user_profile, user_input=None):
    """
    Emergency fallback only when both LLMs fail
    """
    profile = normalize_user_profile(user_profile)
    subjects = profile.get("subjects", [])
    mean_grade = profile.get("mean_grade") or "not provided"

    response = (
        f"Based on your profile, including your mean grade ({mean_grade}) and subjects "
        f"({', '.join(subjects) if subjects else 'not provided'}), here are some options you can start with:\n\n"
    )

    for i, res in enumerate(results[:5], 1):
        if isinstance(res, dict) and 'data' in res:
            data = res['data']
            source = res.get('source', 'Unknown')
            if len(data) >= 3:
                response += f"{i}. [{source}] {data[1]} - {data[2]}\n"
        else:
            response += f"{i}. {res}\n"

    response += "\nI could not give a deeper personalized ranking just now, but these are the closest matches from the database. If you want, ask about one option and I can break it down further."
    return response

def explain_recommendation(program, user_profile):
    """Use LLM to explain why a program is a good fit"""
    prompt = f"""You are a KCSE career guidance expert.

Respond directly to the user in second person using "you" and "your".
Do not refer to user in third person.
Do not guess or infer gender.
Do not invent missing goals or interests.

Explain why this program is suitable for this user.
Keep it under 150 words and be encouraging:

PROGRAM: {program}

USER PROFILE: {normalize_user_profile(user_profile)}

Start immediately with the explanation."""
    
    # Use Groq client directly
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150
        )
        response_text = response.choices[0].message.content
        return response_text.strip()
    except Exception as e:
        print(f"Groq client error: {e}")
        return f"This program aligns well with your academic background. Consider reviewing the specific admission requirements and career opportunities in this field."


def generate_general_explanation(topic, user_profile=None, matched_results=None):
    """
    Generate a clearly-labeled general explanation for a field or course area
    when the current database does not store rich descriptive content.
    """
    profile = normalize_user_profile(user_profile or {})
    subjects = ", ".join(profile.get("subjects", [])) if profile.get("subjects") else "Not provided"
    matches_text = build_program_lines(matched_results[:5]) if matched_results else "No direct programme rows provided."

    prompt = f"""You are supporting a Kenyan education guidance chatbot.

The learner asked a simple descriptive question about a course or field.
Write a short, natural explanation that sounds like a real person talking to one student.

Rules:
1. Speak directly to the learner using "you" and "your".
2. Sound warm, clear, and human. Avoid robotic phrases, headings, and report-like wording.
3. Answer the question directly in the first sentence.
4. Keep it brief. Prefer 2 to 4 sentences total.
5. Do not use bullet points unless absolutely necessary.
6. Do not claim rankings, prestige, fees, competitiveness, or exact entry requirements unless they are explicitly given.
7. Do not invent the learner's interests or goals.
8. If relevant, connect lightly to the learner's profile in one short phrase only.
9. Focus on what the field is about, what someone usually learns, and the kind of work it can lead to.
10. This is a general explanation, so do not present it as an official database fact.
11. Do not start with phrases like "General explanation", "Based on the database", or "From the current programme database".

TOPIC:
{topic}

USER PROFILE:
Mean grade: {profile.get("mean_grade") or "Not provided"}
Subjects: {subjects}
Interests: {profile.get("interests") or "Not provided"}
Career goals: {profile.get("career_goals") or "Not provided"}

MATCHED DATABASE ROWS:
{matches_text}

Start immediately with the explanation."""

    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7
        )
        response = response.choices[0].message.content
    except Exception as e:
        print(f"Groq API error: {e}")
        response = None

    if response:
        return response.strip()

    return (
        f"{topic.title()} is mainly about learning the core knowledge and practical skills used in that field. "
        "You would usually build that through coursework, hands-on tasks, and career-focused training. "
        "If you want, I can also show you the main course requirements I can see for it."
    )


def generate_profile_guidance(user_query, user_profile=None, matched_results=None):
    """
    Turn retrieved programme matches plus a learner profile into a natural,
    personalized guidance reply while keeping a clear database-first boundary.
    """
    profile = normalize_user_profile(user_profile or {})
    subjects = ", ".join(profile.get("subjects", [])) if profile.get("subjects") else "Not provided"
    matches_text = build_program_lines(matched_results[:8]) if matched_results else "No direct programme rows provided."

    prompt = f"""You are supporting a RAG-powered Kenyan education guidance chatbot.

Write a natural, supportive reply to a learner who asked a broad guidance question.
Your reply must stay grounded in the retrieved programme matches below.

Rules:
1. Speak directly to the learner using "you" and "your".
2. Sound natural, warm, and conversational, like a supportive in-person counselor.
3. Do not invent exact entry requirements, prestige, fees, or rankings.
4. Use the learner profile when it helps, especially subjects, interests, and career goals.
5. If interests or career goals are missing, say that briefly and naturally.
6. Start with a short overview of what the current database suggests for this learner.
7. Then mention 2-4 promising directions or programme areas from the matched results.
8. Refer to programmes or fields that are actually visible in the matched database rows.
9. End with one natural follow-up question that helps narrow the next search.
10. Keep it concise and readable.
11. Do not present unsupported claims as facts.
12. Do not use unsupported phrases like "well-recognized", "top", "affordable", "prestigious", "best university", or similar reputation/value claims unless those exact facts are present in the retrieved rows.
13. Avoid stiff phrases like "based on your grades and interests" unless they sound natural in the sentence.
14. Do not sound like a report. Sound like you are talking to one student kindly and clearly.
15. Show a little understanding, especially when the learner sounds unsure.
16. Prefer plain English over polished marketing language.

USER QUESTION:
{user_query}

USER PROFILE:
Mean grade: {profile.get("mean_grade") or "Not provided"}
Subjects: {subjects}
Interests: {profile.get("interests") or "Not provided"}
Career goals: {profile.get("career_goals") or "Not provided"}

MATCHED DATABASE ROWS:
{matches_text}

Start immediately with the reply. Do not add headings, markdown headers, or bold text."""

    # Use Groq client directly
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        response_text = response.choices[0].message.content
        return response_text.strip()
    except Exception as e:
        print(f"Groq client error: {e}")
        return (
            "You do seem to have some workable options in the current database. "
            "I do not yet have enough detail to rank them confidently from the database alone, but I can help you narrow them by field, such as technology, business, teaching, health, or hands-on skills. "
            "Which area would you like to focus on next?"
        )
