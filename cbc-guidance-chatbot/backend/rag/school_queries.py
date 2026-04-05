"""
school_queries.py
-----------------
All school/subject database query handlers and conversation-continuation logic.
No LLM calls — pure DB lookups and response formatting.

PostgreSQL column names (from kenya_senior_schools_pathways_v3.xlsx):
  school_name, county, region, sub_county, knec_code, cluster,
  type, accommodation, gender, pathway_type, pathways_offered,
  combo_pathway, combo_track, subject_1, subject_2, subject_3
"""

from config_loader import get_db
from utils.recommendation_utils import (
    score_combination_for_user,
    build_best_combination_intro,
    build_combination_reason,
    extract_combo_subjects,
    display_track_name,
    extract_track_name,
)
from utils.profile_utils import build_profile_context

# Per-user paging state for subject-combination continuation
_subject_combo_paging_context = {}


# ── Main dispatcher ───────────────────────────────────────────────────────────

def handle_school_query(
    analysis: dict,
    question: str,
    profile_context: str = "",
    user_id: str = None,
    profile_data: dict | None = None,
    pathway_recommendation: dict | None = None,
) -> dict:
    """
    Route to the correct DB handler based on query_type from query_analyzer.
    query_type values:
      schools_by_pathway   → _handle_schools_by_pathway
      schools_by_county    → _handle_schools_by_county
      subjects_by_pathway  → _handle_subjects_by_pathway
      schools_by_subjects  → _handle_schools_by_subjects
      school_search        → _handle_school_search
    """
    query_type = analysis.get("query_type")

    try:
        if query_type == "schools_by_pathway":
            return _handle_schools_by_pathway(analysis)
        elif query_type == "schools_by_county":
            return _handle_schools_by_county(analysis)
        elif query_type == "subjects_by_pathway":
            return _handle_subjects_by_pathway(
                analysis, question, user_id, profile_data, pathway_recommendation
            )
        elif query_type == "schools_by_subjects":
            return _handle_schools_by_subjects(analysis)
        elif query_type == "school_search":
            return _handle_school_search(analysis)
        else:
            return {
                "answer": "I'm not sure how to help with that school query. Try asking about schools by pathway, subject combinations, or school name.",
                "sources": "database", "confidence": "low"
            }
    except Exception as e:
        print(f"Error handling school query: {e}")
        return {
            "answer": "Sorry, I encountered an error while searching for school information. Please try again.",
            "sources": "database", "confidence": "low"
        }


# ── Shared formatting ─────────────────────────────────────────────────────────

def _format_school_row(i: int, school: dict) -> str:
    """
    Format a single DB row into a response string.
    Reads columns: school_name, county, type, gender, accommodation, pathways_offered.
    Corrects gender display if school_name contradicts the gender column (data quality fix).
    """
    school_type   = school.get('type', 'Unknown').lower()
    gender        = school.get('gender', 'Unknown').lower()
    accommodation = school.get('accommodation', 'Unknown').lower()
    pathways      = ', '.join(school.get('pathways_offered', [])) or 'Various pathways'
    name_upper    = school.get('school_name', '').upper()

    if 'GIRLS' in name_upper and gender != 'girls':
        gender = 'girls'
    elif 'BOYS' in name_upper and gender != 'boys':
        gender = 'boys'

    return (
        f"{i}. {school['school_name']} ({school['county']}) - "
        f"{school_type.title()} {gender} school. "
        f"{accommodation.title()} accommodation. "
        f"Offers: {pathways}. "
    )


# ── Query handlers ────────────────────────────────────────────────────────────

def _handle_schools_by_pathway(analysis: dict) -> dict:
    pathway           = analysis.get("pathway")
    county            = analysis.get("county")
    original_subjects = analysis.get("original_subjects")
    requested_count   = analysis.get("requested_count", 10)

    if not pathway:
        return {
            "answer": "Which pathway are you interested in — STEM, Social Sciences, or Arts & Sports?",
            "sources": "database", "confidence": "low"
        }

    schools = get_db().get_schools_by_pathway(pathway, county)
    if not schools:
        return {
            "answer": f"I couldn't find schools offering {pathway} pathway{' in ' + county if county else ''}.",
            "sources": "database", "confidence": "low"
        }

    display_count = min(requested_count, len(schools))
    location_text = f" in {county}" if county else ""

    if original_subjects:
        response = f"I found {len(schools)} schools offering {', '.join(original_subjects)}. Here are {display_count} excellent options that offer {pathway} pathway: "
    elif requested_count >= len(schools):
        response = f"I found {len(schools)} schools offering {pathway} pathway{location_text}. Here are all the options: "
    else:
        response = f"I found {len(schools)} schools offering {pathway} pathway{location_text}. Here are {display_count} excellent options: "

    for i, school in enumerate(schools[:requested_count], 1):
        response += _format_school_row(i, school)

    if len(schools) > requested_count:
        response += f"There are {len(schools) - requested_count} more schools available. Use the Find Schools page for the full list. Would you like more options or details about any of these schools?"
    else:
        response += "You can also use the Find Schools page to browse with county, type, and gender filters. Would you like more information about any of these schools?"

    return {"answer": response, "sources": "database", "confidence": "high"}


def _handle_schools_by_county(analysis: dict) -> dict:
    county          = analysis.get("county")
    requested_count = analysis.get("requested_count", 10)

    if not county:
        return {
            "answer": "Which county are you interested in?",
            "sources": "database", "confidence": "low"
        }

    schools = get_db().get_schools_by_county(county)
    if not schools:
        return {
            "answer": f"I couldn't find schools in {county}.",
            "sources": "database", "confidence": "low"
        }

    display_count = min(requested_count, len(schools))

    if requested_count >= len(schools):
        response = f"I found {len(schools)} schools in {county}. Here are all the options: "
    else:
        response = f"I found {len(schools)} schools in {county}. Here are {display_count} excellent options: "

    for i, school in enumerate(schools[:requested_count], 1):
        response += _format_school_row(i, school)

    if len(schools) > requested_count:
        response += f"There are {len(schools) - requested_count} more schools available. Use the Find Schools page for the full list."
    else:
        response += "You can also use the Find Schools page to browse with pathway, type, and gender filters."

    return {"answer": response, "sources": "database", "confidence": "high"}


def _handle_subjects_by_pathway(
    analysis: dict,
    question: str,
    user_id: str,
    profile_data: dict | None,
    pathway_recommendation: dict | None,
) -> dict:
    pathway        = analysis.get("pathway")
    county         = analysis.get("county")
    expansion_mode = analysis.get("expansion_mode")
    track_filter   = analysis.get("track_filter")
    question_lower = question.lower()

    if not pathway:
        return {
            "answer": "Which pathway are you interested in — STEM, Social Sciences, or Arts & Sports? Tracks are available for each pathway.",
            "sources": "database", "confidence": "low"
        }

    # Fetch from DB; fall back to national if county returns nothing
    unique_combinations = get_db().get_subject_combinations_by_pathway(pathway, county)
    if not unique_combinations and county:
        unique_combinations = get_db().get_subject_combinations_by_pathway(pathway)

    if not unique_combinations:
        return {
            "answer": f"I couldn't find subject combinations or tracks for the {pathway} pathway{' in ' + county if county else ''}. No subject combinations or tracks were found for this pathway.",
            "sources": "database", "confidence": "low"
        }

    # Group by combo_track
    grouped: dict[str, list] = {}
    for combo in unique_combinations:
        track = combo.split(":", 1)[0].strip() if ":" in combo else "OTHER"
        grouped.setdefault(track, []).append(combo)
    for track in grouped:
        grouped[track] = sorted(grouped[track])

    # Optional track filter for follow-ups
    if track_filter:
        matched = [t for t in grouped if track_filter.lower() in t.lower()]
        if matched:
            grouped = {k: grouped[k] for k in matched}

    sorted_tracks = sorted(grouped.keys())
    is_best_query = any(kw in question_lower for kw in ["best", "recommended", "ideal"])

    if expansion_mode == "more" or any(kw in question_lower for kw in ["more", "full", "all"]):
        sample_per_track = 5
    elif is_best_query:
        sample_per_track = 1
    else:
        sample_per_track = 2

    # Pagination
    paging_key     = str(user_id) if user_id else None
    previous_state = _subject_combo_paging_context.get(paging_key) if paging_key else None
    current_filter = track_filter or "all_tracks"

    if (expansion_mode == "more" and previous_state
            and previous_state.get("pathway") == pathway
            and previous_state.get("track_filter") == current_filter):
        start_index = previous_state.get("start_index", 0) + previous_state.get("page_size", 2)
    else:
        start_index = 0

    location_text = f" in {county}" if county else ""

    if is_best_query:
        response = build_best_combination_intro(pathway, county, profile_data, pathway_recommendation)
    else:
        response = f"For {pathway} pathway{location_text}, I found {len(unique_combinations)} subject combinations across {len(sorted_tracks)} tracks:\n\n"

    display_tracks = [display_track_name(t) for t in sorted_tracks]
    if display_tracks:
        response += f"Tracks available: {', '.join(display_tracks)}.\n\n"

    item_index      = 1
    any_items_shown = False

    for track in sorted_tracks:
        combinations  = grouped[track]
        display_track = display_track_name(track)

        if is_best_query:
            combinations = sorted(
                combinations,
                key=lambda c: score_combination_for_user(c, pathway, profile_data, pathway_recommendation),
                reverse=True,
            )

        response  += f"{display_track} ({len(combinations)} combinations):\n"
        page_slice = combinations[start_index:start_index + sample_per_track]

        for combo in page_slice:
            if is_best_query:
                combo_text   = ", ".join(extract_combo_subjects(combo))
                combo_reason = build_combination_reason(combo, pathway, profile_data)
                response    += f"- {combo_text}: {combo_reason}.\n"
            else:
                response += f"{item_index}. {combo}\n"
            item_index      += 1
            any_items_shown  = True

        remaining = len(combinations) - (start_index + len(page_slice))
        if remaining > 0 and not is_best_query:
            response += f"... and {remaining} more in this track.\n"
        elif expansion_mode == "more" and not page_slice:
            response += "No more combinations in this track.\n"
        response += "\n"

    if expansion_mode == "more" and not any_items_shown:
        response = f"You've seen all available combinations for {pathway} pathway{location_text}."

    if paging_key:
        _subject_combo_paging_context[paging_key] = {
            "pathway": pathway, "track_filter": current_filter,
            "start_index": start_index, "page_size": sample_per_track,
        }

    if is_best_query:
        response += "Share the learner's top subjects or target career and I can narrow this to the best 2 or 3 combinations."
    else:
        response += "For more, ask: 'Show more options' or 'Show more Pure Sciences combinations'."

    return {"answer": response, "sources": "database", "confidence": "high"}


def _handle_schools_by_subjects(analysis: dict) -> dict:
    subjects        = analysis.get("subjects", [])
    county          = analysis.get("county")
    requested_count = analysis.get("requested_count", 10)

    if not subjects:
        return {
            "answer": "Which subjects are you looking for?",
            "sources": "database", "confidence": "low"
        }

    schools = get_db().get_schools_by_subjects(subjects, county)
    if not schools:
        return {
            "answer": f"I couldn't find schools offering {', '.join(subjects)}{' in ' + county if county else ''}.",
            "sources": "database", "confidence": "low"
        }

    display_count = min(requested_count, len(schools))
    location_text = f" in {county}" if county else ""

    if requested_count >= len(schools):
        response = f"I found {len(schools)} schools that offer {', '.join(subjects)}{location_text}. Here are all the options: "
    else:
        response = f"I found {len(schools)} schools that offer {', '.join(subjects)}{location_text}. Here are {display_count} excellent options: "

    for i, school in enumerate(schools[:requested_count], 1):
        response += _format_school_row(i, school)

    response += "Would you like to know more about any of these schools or the pathways they offer?"
    return {"answer": response, "sources": "database", "confidence": "high"}


def _handle_school_search(analysis: dict) -> dict:
    search_term = analysis.get("search_term")
    if not search_term:
        return {
            "answer": "What school name or location are you searching for?",
            "sources": "database", "confidence": "low"
        }

    schools = get_db().search_schools(search_term)
    if not schools:
        return {
            "answer": f"I couldn't find schools matching '{search_term}'.",
            "sources": "database", "confidence": "low"
        }

    response = f"I found some schools matching '{search_term}': "
    for i, school in enumerate(schools[:10], 1):
        pathways = ', '.join(school.get('pathways_offered', [])) or 'Various pathways'
        response += f"{i}. {school['school_name']} ({school['county']}) - Offers: {pathways}. "
    response += "Would you like more details about any of these schools?"

    return {"answer": response, "sources": "database", "confidence": "high"}


# ── Conversation continuation ─────────────────────────────────────────────────

def is_conversation_continuation(question: str) -> bool:
    """Return True if the question is a generic follow-up with no specific content."""
    q = question.lower()
    continuation_patterns = [
        "yes please", "yes", "sure", "ok", "okay", "please show me",
        "tell me more", "i'd like to know more", "can you tell me",
        "what about", "how about", "show me more", "more options",
        "information about", "details about", "tell me about",
        "would you like"
    ]
    return any(pattern in q for pattern in continuation_patterns)


def handle_conversation_continuation(question: str, user_id: str) -> dict:
    """Provide contextual responses for generic follow-up interactions."""
    q = question.lower()

    if any(p in q for p in ["more options", "show me more", "more schools"]):
        return {
            "answer": "I'd be happy to show you more! Could you specify what you're looking for? For example: 'Show me 5 more schools in Nairobi with STEM pathway'.",
            "sources": "database", "confidence": "high"
        }

    if any(p in q for p in ["information about", "tell me about", "details about"]):
        return {
            "answer": "I can provide details about specific schools! Which school would you like to know more about?",
            "sources": "database", "confidence": "high"
        }

    if any(p in q for p in ["help", "can you help", "i need help"]):
        return {
            "answer": "I'm here to help! You can ask me about: 1) Schools by pathway (STEM, Social Sciences, Arts & Sports), 2) Schools offering specific subjects, 3) Schools in specific counties, 4) Subject combinations per pathway. What would you like to know?",
            "sources": "database", "confidence": "high"
        }

    if any(p in q for p in ["yes", "sure", "ok", "okay", "yes please"]):
        return {
            "answer": "Great! What specific information would you like? For example: 'Tell me about boarding schools in Nairobi' or 'Show me STEM schools in Kisumu'.",
            "sources": "database", "confidence": "high"
        }

    # Default — personalise if profile available
    default_answer = "I'd be happy to continue helping! You can ask about schools, pathways, subjects, or specific locations."
    if user_id:
        try:
            profile = get_db().get_profile(user_id)
            if profile:
                profile_dict = dict(profile) if hasattr(profile, '_asdict') else profile
                profile_ctx  = build_profile_context(profile_dict)
                if profile_ctx and 'interests:' in profile_ctx.lower():
                    interests_part = profile_ctx.lower().split('interests:')[1].split('\n')[0]
                    interests      = [i.strip() for i in interests_part.split(',')][:2]
                    if interests:
                        default_answer = (
                            f"Based on your interests in {', '.join(interests)}, you might want to ask "
                            "about relevant pathways, subject combinations, or schools offering those areas."
                        )
        except Exception:
            pass

    return {"answer": default_answer, "sources": "database", "confidence": "high"}
