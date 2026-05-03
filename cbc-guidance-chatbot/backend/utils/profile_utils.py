"""
profile_utils.py
Replaces utils.py. Profile loading, context-string building, and raw
profile-dict normalisation.

All display label lists come from career_subject_hints.json — no interest
field names or subject names are hardcoded here.

  normalise_profile_dict()    → clean DB row to typed dict for UserProfile
  build_profile_context()     → build LLM prompt context string from profile
  profile_text_blob()         → lowercase blob of free-text fields for matching
  build_recent_history_context() → recent chat turns for conversational continuity
"""

from config_loader import CAREER_SUBJECT_HINTS

#Load label maps from career_subject_hints.json

# avg score field → "User is strong in X"
_AVG_STRENGTH_LABELS: dict[str, str] = CAREER_SUBJECT_HINTS.get(
    "avg_field_to_strength_label", {}
)

# interest field → display label (e.g. "interest_stem" → "STEM")
_INTEREST_LABELS: dict[str, str] = CAREER_SUBJECT_HINTS.get(
    "interest_field_to_label", {}
)


#Profile dict normalisation

def normalise_profile_dict(profile_row) -> dict:
    """
    Convert a DB row (RealDictRow or plain dict) to a clean typed dict
    suitable for UserProfile validation and downstream use.
    Fields listed here mirror the DB schema — this is intentional, not hardcoding.
    """
    if hasattr(profile_row, '_asdict'):
        profile_dict = dict(profile_row)
    else:
        profile_dict = profile_row

    return {
        **profile_dict,
        'stem_score':                   profile_dict.get('stem_score'),
        'social_sciences_score':        profile_dict.get('social_sciences_score'),
        'arts_sports_score':            profile_dict.get('arts_sports_score'),
        'knec_recommended_pathway':     profile_dict.get('knec_recommended_pathway'),
        'career_goals':                 profile_dict.get('career_goals') or [],
        'favorite_subject':             profile_dict.get('favorite_subject'),
        'interests':                    profile_dict.get('interests'),
        'strengths':                    profile_dict.get('strengths'),
        'career_interests':             profile_dict.get('career_interests'),
        'learning_style':               profile_dict.get('learning_style'),
        'mathematics_avg':              profile_dict.get('mathematics_avg'),
        'science_avg':                  profile_dict.get('science_avg'),
        'english_avg':                  profile_dict.get('english_avg'),
        'kiswahili_avg':                profile_dict.get('kiswahili_avg'),
        'social_studies_avg':           profile_dict.get('social_studies_avg'),
        'business_studies_avg':         profile_dict.get('business_studies_avg'),
        'problem_solving_level':        profile_dict.get('problem_solving_level'),
        'scientific_reasoning_level':   profile_dict.get('scientific_reasoning_level'),
        'collaboration_level':          profile_dict.get('collaboration_level'),
        'communication_level':          profile_dict.get('communication_level'),
        'interest_stem':                profile_dict.get('interest_stem'),
        'interest_arts':                profile_dict.get('interest_arts'),
        'interest_social':              profile_dict.get('interest_social'),
        'interest_creative':            profile_dict.get('interest_creative'),
        'interest_sports':              profile_dict.get('interest_sports'),
        'interest_dance':               profile_dict.get('interest_dance'),
        'interest_visual_arts':         profile_dict.get('interest_visual_arts'),
        'interest_music':               profile_dict.get('interest_music'),
        'interest_writing':             profile_dict.get('interest_writing'),
        'interest_technology':          profile_dict.get('interest_technology'),
        'interest_business':            profile_dict.get('interest_business'),
        'interest_agriculture':         profile_dict.get('interest_agriculture'),
        'interest_healthcare':          profile_dict.get('interest_healthcare'),
        'interest_media':               profile_dict.get('interest_media'),
    }


#Profile context string

def build_profile_context(profile: dict) -> str:
    """
    Build a personalised context string from a user profile dict.
    Injected into the LLM prompt in rag_query.py.

    Free-text fields are listed here — they are stable frontend fields.
    Academic strength flags come from avg_field_to_strength_label in JSON.
    Interest flags come from interest_field_to_label in JSON.
    Adding/removing a field only requires a JSON change, not a code change.
    """
    context_parts = []

    # Free-text frontend fields
    for field, label in [
        ('favorite_subject', 'favorite subject'),
        ('interests',        'interests'),
        ('strengths',        'strengths'),
        ('career_interests', 'career interests'),
        ('learning_style',   'learning style'),
    ]:
        if profile.get(field):
            context_parts.append(f"User's {label}: {profile[field]}")

    # Academic strength flags — from avg_field_to_strength_label in career_subject_hints.json
    for avg_field, strength_label in _AVG_STRENGTH_LABELS.items():
        if (profile.get(avg_field) or 0) > 70:
            context_parts.append(strength_label)

    # Competency strengths (rating >= 4 on 1–5 scale) — stable DB fields
    competencies = [
        label for field, label in [
            ('problem_solving_level',      'Problem Solving'),
            ('scientific_reasoning_level', 'Scientific Reasoning'),
            ('collaboration_level',        'Collaboration'),
            ('communication_level',        'Communication'),
        ]
        if (profile.get(field) or 0) >= 4
    ]
    if competencies:
        context_parts.append(f"Strong competencies: {', '.join(competencies)}")

    # Interest flags (rating >= 3) — from interest_field_to_label in career_subject_hints.json
    interests = [
        label for field, label in _INTEREST_LABELS.items()
        if (profile.get(field) or 0) >= 3
    ]
    if interests:
        context_parts.append(f"Your interests: {', '.join(interests)}")

    return "\n".join(context_parts) if context_parts else ""


#Profile text blob

def profile_text_blob(profile: dict | None) -> str:
    """
    Build a lowercase text blob from free-text profile fields.
    Used by recommendation_utils to match career keywords against
    what the user typed in their profile (interests, strengths, etc.).
    """
    if not profile:
        return ""

    text_parts = []
    for key in ["favorite_subject", "interests", "strengths", "career_interests", "learning_style"]:
        value = profile.get(key)
        if value:
            text_parts.append(str(value))

    for goal in profile.get("career_goals") or []:
        text_parts.append(str(goal))

    return " ".join(text_parts).lower()


#Recent history context

def build_recent_history_context(get_db_fn, user_id: str | None, limit: int = 3) -> str:
    """
    Build a compact recent chat context string for conversational continuity.
    Injected into the LLM prompt in rag_query.py.
    get_db_fn is passed in to avoid circular imports with config_loader.
    """
    if not user_id:
        return ""

    try:
        history = get_db_fn().get_user_history(user_id, limit)
        if not history:
            return ""

        lines = []
        for item in reversed(history):
            question = str(item.get("question", "")).strip()
            answer   = str(item.get("answer", "")).strip()
            if question:
                lines.append(f"User: {question}")
            if answer:
                lines.append(f"Assistant: {answer[:220]}")

        return "\n".join(lines) if lines else ""
    except Exception as e:
        print(f"Warning: failed to load recent history context: {e}")
        return ""
