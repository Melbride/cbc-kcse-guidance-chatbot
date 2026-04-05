"""
recommendation_utils.py
-----------------------
Subject-combination scoring and recommendation helpers.
All functions are pure — no DB calls, no LLM calls.

NO subject names, county names, or career descriptions are hardcoded here.

Data sources:
  config/pathway_subject_priority.json
      Scoring weights per pathway. Also used to derive competency bonus
      subject sets at module load time.

  config/career_subject_hints.json
      career_to_pathway, profile_interest_to_career_keyword,
      avg_field_to_strength_label, interest_field_to_label

  config/track_descriptions.json
      Track name → fallback reason string (UI copy, not data)

  PostgreSQL (combo strings arrive from school_queries.py)
      Actual subject combinations per track/pathway

  Pinecone (via rag_query.py)
      Career explanations and pathway guidance
"""

import os
import json
from config_loader import PATHWAY_SUBJECT_PRIORITY, CAREER_SUBJECT_HINTS

# ── Load configs ──────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_BASE_DIR)
with open(os.path.join(_BACKEND_DIR, 'config', 'track_descriptions.json'), 'r', encoding='utf-8') as f:
    _TRACK_DESCRIPTIONS: dict = json.load(f)

_INTEREST_TO_CAREER_KEYWORD: dict[str, str] = CAREER_SUBJECT_HINTS.get(
    "profile_interest_to_career_keyword", {}
)
_CAREER_TO_PATHWAY: dict[str, str] = CAREER_SUBJECT_HINTS.get(
    "career_to_pathway", {}
)
_AVG_STRENGTH_LABELS: dict[str, str] = CAREER_SUBJECT_HINTS.get(
    "avg_field_to_strength_label", {}
)
_INTEREST_LABELS: dict[str, str] = CAREER_SUBJECT_HINTS.get(
    "interest_field_to_label", {}
)

# ── Derive competency subject sets from pathway_subject_priority.json ─────────
# No subject names written in this file — all derived from the JSON at load time.

def _high_priority_subjects(pathway: str, min_weight: int = 4) -> set[str]:
    return {s for s, w in PATHWAY_SUBJECT_PRIORITY.get(pathway, {}).items() if w >= min_weight}

# Communication → high-priority subjects across social sciences + arts & sports
_COMMUNICATION_SUBJECTS: set[str] = (
    _high_priority_subjects("social sciences") | _high_priority_subjects("arts & sports")
)

# Collaboration → high-priority subjects across arts & sports + social sciences
_COLLABORATION_SUBJECTS: set[str] = (
    _high_priority_subjects("arts & sports") | _high_priority_subjects("social sciences")
)


# ── Low-level helpers ─────────────────────────────────────────────────────────

def normalize_pathway_name(pathway: str) -> str:
    """Normalize pathway labels for internal matching."""
    p = pathway.strip().lower()
    if p in {"arts and sports", "arts and sports science", "arts", "sports"}:
        return "arts & sports"
    if p in {"social science", "social sciences"}:
        return "social sciences"
    return p


def extract_combo_subjects(combo: str) -> list[str]:
    """
    Extract subjects from a DB combination string.
    DB format (built from combo_track + subject_1/2/3 columns):
      "PURE SCIENCES: Physics, Chemistry, Biology, Advanced Mathematics"
    Returns: ["Physics", "Chemistry", "Biology", "Advanced Mathematics"]
    """
    combo_text = combo.split(":", 1)[1] if ":" in combo else combo
    return [s.strip() for s in combo_text.split(",") if s.strip()]


def extract_track_name(combo: str) -> str:
    """Extract the track from a DB combination string."""
    return combo.split(":", 1)[0].strip() if ":" in combo else "OTHER"


def display_track_name(track: str) -> str:
    """Return a clean user-facing track label."""
    name = track.strip()
    if name.upper() == "CAREER & TECHNICAL STUDIES (CTS)":
        return "Career & Technical Studies (CTS)"
    return name.title()


def _get_track_description(normalized_pathway: str, track_name: str) -> str | None:
    """
    Look up a fallback reason from track_descriptions.json.
    Substring match against track_name; falls back to pathway default.
    """
    pathway_tracks = _TRACK_DESCRIPTIONS.get(normalized_pathway, {})
    for key, description in pathway_tracks.items():
        if key != "default" and key in track_name.lower():
            return description
    return pathway_tracks.get("default")


# ── Scoring ───────────────────────────────────────────────────────────────────

def _base_combination_score(combo: str, pathway: str) -> tuple[int, int, str]:
    """
    Score a combination using pathway_subject_priority.json weights.
    Subjects come from the DB combo string. Weights come from JSON config.
    Returns (total_score, priority_subject_count, combo).
    """
    normalized_pathway = normalize_pathway_name(pathway)
    subjects = extract_combo_subjects(combo)
    pathway_priority = PATHWAY_SUBJECT_PRIORITY.get(normalized_pathway, {})

    total_score = sum(pathway_priority.get(s.lower(), 1) for s in subjects)
    priority_subject_count = sum(1 for s in subjects if s.lower() in pathway_priority)
    return (total_score, priority_subject_count, combo)


def score_combination_for_user(
    combo: str,
    pathway: str,
    profile: dict | None = None,
    pathway_recommendation: dict | None = None,
) -> tuple[int, int, str]:
    """
    Score a subject combination for a specific learner.

    Base score: pathway_subject_priority.json weights for each subject in the combo.

    Profile bonuses:
      1. Academic averages — avg field keys from career_subject_hints.json.
         If student scores >= 70, reward combos with high-priority pathway subjects.

      2. Career interest alignment — interest → career keyword → pathway
         via career_subject_hints.json. If career aligns with pathway, +3.
         Career content lives in Pinecone, not here.

      3. Competency bonuses — subject sets derived from pathway_subject_priority.json
         at module load. No subject names written in this file.

      4. Pathway recommendation match — +3 if PathwayRecommender already
         suggested this pathway for this user.

    Returns (final_score, priority_subject_count, combo).
    """
    normalized_pathway = normalize_pathway_name(pathway)
    base_score, priority_subject_count, combo_text = _base_combination_score(
        combo, normalized_pathway
    )

    if not profile:
        return (base_score, priority_subject_count, combo_text)

    subjects = {s.lower() for s in extract_combo_subjects(combo)}
    pathway_priority = PATHWAY_SUBJECT_PRIORITY.get(normalized_pathway, {})
    high_priority = {s for s, w in pathway_priority.items() if w >= 4}
    profile_bonus = 0

    # ── 1. Academic average bonuses ───────────────────────────────────────────
    strong_avg_count = sum(
        1 for f in _AVG_STRENGTH_LABELS
        if (profile.get(f) or 0) >= 70
    )
    if strong_avg_count > 0:
        profile_bonus += strong_avg_count * len(subjects & high_priority)

    # ── 2. Career interest alignment ──────────────────────────────────────────
    for interest_field, career_keyword in _INTEREST_TO_CAREER_KEYWORD.items():
        if (profile.get(interest_field) or 0) >= 4:
            if _CAREER_TO_PATHWAY.get(career_keyword) == normalized_pathway:
                profile_bonus += 3
                break

    # ── 3. Competency bonuses ─────────────────────────────────────────────────
    if (profile.get("problem_solving_level") or 0) >= 4:
        profile_bonus += len(subjects & high_priority)

    if (profile.get("scientific_reasoning_level") or 0) >= 4:
        profile_bonus += len(subjects & high_priority)

    if (profile.get("communication_level") or 0) >= 4:
        profile_bonus += len(subjects & _COMMUNICATION_SUBJECTS)

    if (profile.get("collaboration_level") or 0) >= 4:
        profile_bonus += len(subjects & _COLLABORATION_SUBJECTS)

    # ── 4. Pathway recommendation match ──────────────────────────────────────
    recommended = (pathway_recommendation or {}).get("pathway", "").strip().lower()
    if recommended and recommended == normalized_pathway:
        profile_bonus += 3

    return (base_score + profile_bonus, priority_subject_count, combo_text)


# ── Response builders ─────────────────────────────────────────────────────────

def build_best_combination_intro(
    pathway: str,
    county: str | None,
    profile: dict | None,
    pathway_recommendation: dict | None,
) -> str:
    """Create a short intro sentence for a 'best combinations' response."""
    location_text = f" in {county}" if county else ""
    recommended = (pathway_recommendation or {}).get("pathway", "").strip().lower()

    if profile and recommended == normalize_pathway_name(pathway):
        return (
            f"Based on the learner's current profile, {pathway.upper()} looks like a strong fit. "
            f"Here are strong subject combinations for {pathway} pathway{location_text}:\n\n"
        )
    return (
        f"The best {pathway.upper()} subject combination depends on the learner's strengths, "
        f"interests, and career goal. "
        f"Here are strong options for {pathway} pathway{location_text}:\n\n"
    )


def build_combination_reason(combo: str, pathway: str, profile: dict | None = None) -> str:
    """
    Return a short reason explaining why a combination suits a learner.

    With profile:
      1. Academic strength — label from avg_field_to_strength_label in JSON.
      2. Career interest — career keyword from career_to_pathway in JSON.
    Without profile or no match:
      Fallback from track_descriptions.json.
    """
    subjects = {s.lower() for s in extract_combo_subjects(combo)}
    track_name = extract_track_name(combo)
    normalized_pathway = normalize_pathway_name(pathway)
    pathway_priority = PATHWAY_SUBJECT_PRIORITY.get(normalized_pathway, {})
    high_priority = {s for s, w in pathway_priority.items() if w >= 4}
    reasons = []

    if profile:
        # Academic strength reason
        for avg_field, strength_label in _AVG_STRENGTH_LABELS.items():
            if (profile.get(avg_field) or 0) >= 70 and subjects & high_priority:
                subject_area = strength_label.replace("User is strong in ", "")
                reasons.append(f"matches strong {subject_area} performance")
                break

        # Career interest reason
        for interest_field, career_keyword in _INTEREST_TO_CAREER_KEYWORD.items():
            if ((profile.get(interest_field) or 0) >= 4
                    and _CAREER_TO_PATHWAY.get(career_keyword) == normalized_pathway):
                reasons.append(f"supports {career_keyword}-related career goals")
                break

        if len(reasons) >= 2:
            return "; ".join(reasons[:2])

    # Fallback: track-level description from track_descriptions.json
    if not reasons:
        fallback = _get_track_description(normalized_pathway, track_name)
        if fallback:
            reasons.append(fallback)

    return "; ".join(reasons[:2]) if reasons else "offers a balanced pathway option"
