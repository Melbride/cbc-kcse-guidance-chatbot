"""
school_queries.py
All school/subject database query handlers and conversation-continuation logic.
No LLM calls — pure DB lookups and response formatting.

PostgreSQL column names (from kenya_senior_schools_pathways.xlsx):
  school_name, county, region, sub_county, knec_code, cluster,
  type, accommodation, gender, pathway_type, pathways_offered,
  combo_pathway, combo_track, subject_1, subject_2, subject_3

FIXES applied:
  1. Schools are deduplicated by name+county before display — the DB has one
     row per subject combination so each school appears N times.
  2. Accommodation "Unknown" bug fixed — data is always BOARDING/DAY (clean).
     The bug was lowercasing then title-casing a value that was already uppercase.
  3. Response language is now conversational, not robotic.
  4. Conversation continuation now passes recent history context so follow-ups
     like "can I get the girls school?" actually filter the previous result.
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

# Per-user last school query result (for follow-up filtering)
_last_school_query: dict[str, dict] = {}


#Main dispatcher

def handle_school_query(
    analysis: dict,
    question: str,
    profile_context: str = "",
    user_id: str = None,
    profile_data: dict | None = None,
    pathway_recommendation: dict | None = None,
) -> dict:
    query_type = analysis.get("query_type")

    try:
        if query_type == "schools_by_pathway":
            result = _handle_schools_by_pathway(analysis)
        elif query_type == "schools_by_county":
            result = _handle_schools_by_county(analysis)
        elif query_type == "subjects_by_pathway":
            result = _handle_subjects_by_pathway(
                analysis, question, user_id, profile_data, pathway_recommendation
            )
        elif query_type == "schools_by_subjects":
            result = _handle_schools_by_subjects(analysis)
        elif query_type == "school_search":
            result = _handle_school_search(analysis)
        else:
            return {
                "answer": (
                    "I can help you find schools! Try asking something like: "
                    "'Girls boarding schools in Nairobi with STEM' or "
                    "'Which schools in Kisumu offer Social Sciences pathway?'"
                ),
                "sources": "database",
                "confidence": "low",
            }

        # Save last query context per user for follow-up handling
        if user_id and result.get("answer"):
            _last_school_query[user_id] = {
                "analysis": analysis,
                "question": question,
                "answer":   result["answer"],
            }

        return result

    except Exception as e:
        print(f"Error handling school query: {e}")
        return {
            "answer": "Sorry, I had trouble searching for that. Please try again.",
            "sources": "database",
            "confidence": "low",
        }


# ── Deduplication helper ──────────────────────────────────────────────────────

def _deduplicate_schools(schools: list[dict]) -> list[dict]:
    """
    The DB has one row per subject combination — a school offering 3 pathways
    appears 3+ times. Deduplicate by (school_name, county), keeping the row
    with the richest pathways_offered string.
    """
    seen: dict[tuple, dict] = {}
    for school in schools:
        key = (
            (school.get("school_name") or "").upper().strip(),
            (school.get("county") or "").upper().strip(),
        )
        if key not in seen:
            seen[key] = school
        else:
            # Prefer the entry that has more pathways info
            existing_pw = seen[key].get("pathways_offered") or ""
            new_pw      = school.get("pathways_offered") or ""
            if len(str(new_pw)) > len(str(existing_pw)):
                seen[key] = school
    return list(seen.values())


# ── Shared formatting ─────────────────────────────────────────────────────────

def _format_school_row(i: int, school: dict) -> str:
    """
    Format a single DB row into a readable response line.

    FIX: accommodation was being .lower()'d then .title()'d which turned
    'BOARDING' into 'Boarding' correctly but an empty/None value became
    'Unknown' (from the fallback). Now we check the raw value directly.
    """
    school_type   = (school.get("type") or "Public").title()
    gender_raw    = (school.get("gender") or "").strip().upper()
    accom_raw     = (school.get("accommodation") or "").strip().upper()
    name_upper    = (school.get("school_name") or "").strip().upper()

    # Data quality: trust school name over gender column when they conflict
    if "GIRLS" in name_upper:
        gender_raw = "GIRLS"
    elif "BOYS" in name_upper:
        gender_raw = "BOYS"

    gender_display = gender_raw.title() if gender_raw else "Mixed"

    # FIX: accommodation is always BOARDING or DAY in the dataset — never unknown
    if accom_raw == "BOARDING":
        accom_display = "Boarding"
    elif accom_raw == "DAY":
        accom_display = "Day"
    else:
        accom_display = accom_raw.title() if accom_raw else "Day/Boarding"

    # Pathways
    raw_pathways = school.get("pathways_offered", "")
    if isinstance(raw_pathways, list):
        pathways = ", ".join(raw_pathways) if raw_pathways else "Various pathways"
    elif isinstance(raw_pathways, str) and raw_pathways.strip():
        pathways = raw_pathways.strip()
    else:
        pathways = "Various pathways"

    return (
        f"{i}. {school['school_name']} ({school['county']}) — "
        f"{school_type} {gender_display.lower()} school, {accom_display.lower()}. "
        f"Offers: {pathways}. "
    )


def _format_school_list(schools: list[dict], requested_count: int, intro: str) -> str:
    """Build a full formatted response for a list of schools."""
    deduped       = _deduplicate_schools(schools)
    display_count = min(requested_count, len(deduped))
    response      = intro.format(total=len(deduped), count=display_count)

    for i, school in enumerate(deduped[:requested_count], 1):
        response += _format_school_row(i, school)

    remaining = len(deduped) - requested_count
    if remaining > 0:
        response += (
            f"\n\nThere are {remaining} more schools available. "
            "You can use the Find Schools page to browse all of them with filters for county, type, and gender. "
            "Would you like me to narrow this down — for example, by boarding only, or a specific sub-county?"
        )
    else:
        response += (
            "\n\nYou can also use the Find Schools page to filter by boarding, type, or sub-county. "
            "Would you like more details about any of these schools?"
        )
    return response


# ── Query handlers ────────────────────────────────────────────────────────────

def _handle_schools_by_pathway(analysis: dict) -> dict:
    pathway         = analysis.get("pathway")
    county          = analysis.get("county")
    gender          = analysis.get("gender")
    requested_count = analysis.get("requested_count", 10)

    if not pathway:
        return {
            "answer": "Which pathway are you interested in — STEM, Social Sciences, or Arts & Sports?",
            "sources": "database",
            "confidence": "low",
        }

    schools = get_db().get_schools_by_pathway(pathway, county, gender=gender)
    if not schools:
        location_txt = f" in {county}" if county else ""
        gender_txt   = f"{gender} " if gender else ""
        return {
            "answer": (
                f"I couldn't find {gender_txt}schools offering the {pathway} pathway{location_txt}. "
                "Try a different county or check the Find Schools page for the full list."
            ),
            "sources": "database",
            "confidence": "low",
        }

    gender_txt   = f"{gender} " if gender else ""
    location_txt = f" in {county}" if county else ""

    intro = (
        f"I found {{total}} {gender_txt}schools offering the {pathway} pathway{location_txt}. "
        f"Here are {{count}} options:\n\n"
    )
    answer = _format_school_list(schools, requested_count, intro)
    return {"answer": answer, "sources": "database", "confidence": "high"}


def _handle_schools_by_county(analysis: dict) -> dict:
    county          = analysis.get("county")
    gender          = analysis.get("gender")
    requested_count = analysis.get("requested_count", 10)

    if not county:
        return {
            "answer": "Which county are you looking for schools in?",
            "sources": "database",
            "confidence": "low",
        }

    schools = get_db().get_schools_by_county(county, gender=gender)
    if not schools:
        gender_txt = f"{gender} " if gender else ""
        return {
            "answer": f"I couldn't find {gender_txt}schools in {county}. Double-check the county name or try the Find Schools page.",
            "sources": "database",
            "confidence": "low",
        }

    gender_txt = f"{gender} " if gender else ""
    intro = (
        f"I found {{total}} {gender_txt}schools in {county}. "
        f"Here are {{count}} options:\n\n"
    )
    answer = _format_school_list(schools, requested_count, intro)
    return {"answer": answer, "sources": "database", "confidence": "high"}


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
            "answer": "Which pathway are you asking about — STEM, Social Sciences, or Arts & Sports?",
            "sources": "database",
            "confidence": "low",
        }

    unique_combinations = get_db().get_subject_combinations_by_pathway(pathway, county)
    if not unique_combinations and county:
        unique_combinations = get_db().get_subject_combinations_by_pathway(pathway)

    if not unique_combinations:
        return {
            "answer": (
                f"I couldn't find subject combinations for the {pathway} pathway"
                f"{' in ' + county if county else ''}. "
                "Try asking without a county filter."
            ),
            "sources": "database",
            "confidence": "low",
        }

    # Group by combo_track
    grouped: dict[str, list] = {}
    for combo in unique_combinations:
        track = combo.split(":", 1)[0].strip() if ":" in combo else "OTHER"
        grouped.setdefault(track, []).append(combo)
    for track in grouped:
        grouped[track] = sorted(grouped[track])

    if track_filter:
        matched = [t for t in grouped if track_filter.lower() in t.lower()]
        if matched:
            grouped = {k: grouped[k] for k in matched}

    sorted_tracks  = sorted(grouped.keys())
    is_best_query  = any(kw in question_lower for kw in ["best", "recommended", "ideal"])

    if expansion_mode == "more" or any(kw in question_lower for kw in ["more", "full", "all"]):
        sample_per_track = 5
    elif is_best_query:
        sample_per_track = 1
    else:
        sample_per_track = 2

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
        response = (
            f"For the {pathway} pathway{location_text}, there are {len(unique_combinations)} subject combinations "
            f"spread across {len(sorted_tracks)} tracks:\n\n"
        )

    display_tracks = [display_track_name(t) for t in sorted_tracks]
    if display_tracks:
        response += f"Available tracks: {', '.join(display_tracks)}.\n\n"

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

        response   += f"{display_track} ({len(combinations)} combinations):\n"
        page_slice  = combinations[start_index:start_index + sample_per_track]

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
        response = f"You've seen all available combinations for the {pathway} pathway{location_text}."

    if paging_key:
        _subject_combo_paging_context[paging_key] = {
            "pathway":      pathway,
            "track_filter": current_filter,
            "start_index":  start_index,
            "page_size":    sample_per_track,
        }

    if is_best_query:
        response += "\nTell me the learner's favourite subjects or dream career and I can narrow it down to the top 2–3 combinations."
    else:
        response += "Want more? Just say 'show me more' or ask for a specific track like 'show more Pure Sciences combinations'."

    return {"answer": response, "sources": "database", "confidence": "high"}


def _handle_schools_by_subjects(analysis: dict) -> dict:
    subjects        = analysis.get("subjects", [])
    county          = analysis.get("county")
    requested_count = analysis.get("requested_count", 10)

    if not subjects:
        return {
            "answer": "Which subjects are you looking for in a school?",
            "sources": "database",
            "confidence": "low",
        }

    schools = get_db().get_schools_by_subjects(subjects, county)
    if not schools:
        location_txt = f" in {county}" if county else ""
        return {
            "answer": (
                f"I couldn't find schools offering {', '.join(subjects)}{location_txt}. "
                "Try broadening your search or using the Find Schools page."
            ),
            "sources": "database",
            "confidence": "low",
        }

    intro = (
        f"Great news — I found {{total}} schools offering {', '.join(subjects)}"
        f"{' in ' + county if county else ''}. Here are {{count}}:\n\n"
    )
    answer = _format_school_list(schools, requested_count, intro)
    return {"answer": answer, "sources": "database", "confidence": "high"}


def _handle_school_search(analysis: dict) -> dict:
    search_term = analysis.get("search_term")
    if not search_term:
        return {
            "answer": "What school name or location are you searching for?",
            "sources": "database",
            "confidence": "low",
        }

    schools = get_db().search_schools(search_term)
    if not schools:
        return {
            "answer": f"I couldn't find any schools matching '{search_term}'. Try a different name or county.",
            "sources": "database",
            "confidence": "low",
        }

    deduped  = _deduplicate_schools(schools)
    response = f"Here are the schools I found matching '{search_term}':\n\n"
    for i, school in enumerate(deduped[:10], 1):
        raw_pw = school.get("pathways_offered", "")
        if isinstance(raw_pw, list):
            pathways = ", ".join(raw_pw) or "Various pathways"
        elif isinstance(raw_pw, str) and raw_pw.strip():
            pathways = raw_pw.strip()
        else:
            pathways = "Various pathways"
        response += (
            f"{i}. {school['school_name']} ({school['county']}) — {pathways}. "
        )
    response += "\n\nWould you like more details about any of these schools?"
    return {"answer": response, "sources": "database", "confidence": "high"}


# ── Conversation continuation ─────────────────────────────────────────────────

def is_conversation_continuation(question: str) -> bool:
    """
    Return True if the question is a generic follow-up with no new query content.
    NOTE: "can I get the girls school?" is NOT a continuation — it has a gender
    filter. The query_analyzer should catch it and route to _handle_schools_by_county
    or _handle_schools_by_pathway with gender="girls". Only truly generic phrases
    hit this function.
    """
    q = question.lower().strip()

    # These have content — don't treat as continuation
    has_content = any(kw in q for kw in [
        "girls", "boys", "mixed", "boarding", "day school",
        "stem", "social sciences", "arts", "nairobi", "kisumu",
        "mombasa", "county", "school in",
    ])
    if has_content:
        return False

    continuation_patterns = [
        "yes please", "yes", "sure", "ok", "okay", "please show me",
        "tell me more", "more options", "show me more",
        "would you like", "i'd like to know more",
    ]
    return any(q == p or q.startswith(p) for p in continuation_patterns)


def handle_conversation_continuation(question: str, user_id: str) -> dict:
    """
    Handle generic follow-ups. When possible, use the last query context
    to give a more helpful answer.
    """
    q    = question.lower().strip()
    last = _last_school_query.get(user_id) if user_id else None

    # "show me more" — point back to Find Schools or re-run with higher count
    if any(p in q for p in ["more options", "show me more", "more schools"]):
        if last and last.get("analysis"):
            last_analysis = dict(last["analysis"])
            last_analysis["requested_count"] = last_analysis.get("requested_count", 10) + 10
            return handle_school_query(last_analysis, last["question"], user_id=user_id)
        return {
            "answer": (
                "Sure! To show you more schools, tell me what you're looking for — "
                "for example: 'More girls schools in Nairobi with STEM' or "
                "'Show me 20 boarding schools in Kisumu'."
            ),
            "sources": "database",
            "confidence": "high",
        }

    if any(p in q for p in ["information about", "tell me about", "details about"]):
        return {
            "answer": "Which school would you like to know more about? Just tell me the name and I'll help.",
            "sources": "database",
            "confidence": "high",
        }

    if any(p in q for p in ["yes", "sure", "ok", "okay", "yes please"]):
        if last:
            return {
                "answer": (
                    f"Here's a quick recap of what I found earlier:\n\n{last['answer'][:300]}...\n\n"
                    "What else would you like to know? I can filter by boarding, county, gender, or pathway."
                ),
                "sources": "database",
                "confidence": "high",
            }
        return {
            "answer": (
                "Great! What would you like to know? For example:\n"
                "- 'Girls boarding schools in Nairobi with STEM'\n"
                "- 'Subject combinations for Social Sciences'\n"
                "- 'What pathway is best for a doctor?'"
            ),
            "sources": "database",
            "confidence": "high",
        }

    return {
        "answer": (
            "I'm here to help! You can ask me things like:\n"
            "- 'Show me STEM schools in Kiambu'\n"
            "- 'What subjects are in Arts & Sports pathway?'\n"
            "- 'Which boarding schools are in Mombasa?'"
        ),
        "sources": "database",
        "confidence": "high",
    }
