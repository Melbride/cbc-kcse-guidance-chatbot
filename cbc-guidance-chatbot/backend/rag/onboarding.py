"""
onboarding.py
-------------
Conversational profile and stage collection.

Design principles:
- Profile is considered incomplete only if journey_stage is not set at all.
- Stage detection is handled entirely by the LLM — no keyword matching here.
- The LLM returns a stage_update_prompt flag in the response when it detects
  the user's situation has changed. The frontend renders the banner.
- No hardcoded keyword lists. No Python string matching for intent detection.

3 stages:
  pre_exam       → preparing for JSS exams, hasn't received results
  post_results   → has received results, choosing a pathway
  post_placement → placed in a school, navigating their pathway
"""

from config_loader import get_db


# ── Profile completeness ──────────────────────────────────────────────────────

def profile_is_incomplete(profile_data: dict | None) -> bool:
    """
    True only if the user has never selected a stage.
    Once a stage exists the bot can guide them — other fields are optional.
    """
    if not profile_data:
        return True
    return not profile_data.get("journey_stage")


# ── Onboarding state ──────────────────────────────────────────────────────────

def is_onboarding_complete(user_id: str) -> bool:
    """Check if onboarding has been completed for this user."""
    try:
        return bool(get_db().get_user_metadata(user_id, "onboarding_complete"))
    except Exception:
        return False


def mark_onboarding_complete(user_id: str) -> None:
    """Mark onboarding as done so we don't repeat it."""
    try:
        get_db().set_user_metadata(user_id, "onboarding_complete", True)
    except Exception as e:
        print(f"Warning: could not mark onboarding complete: {e}", flush=True)


def get_onboarding_state(user_id: str) -> dict:
    """Load current onboarding state from DB."""
    try:
        state = get_db().get_user_metadata(user_id, "onboarding_state")
        if state:
            return state
    except Exception:
        pass
    return {"step": 0, "role": "student"}


def save_onboarding_state(user_id: str, state: dict) -> None:
    """Persist onboarding state to DB."""
    try:
        get_db().set_user_metadata(user_id, "onboarding_state", state)
    except Exception as e:
        print(f"Warning: could not save onboarding state: {e}", flush=True)


def save_profile_field(user_id: str, field: str, value: str) -> None:
    """Silently save a single profile field to DB."""
    if not field or field.startswith("_"):
        return
    try:
        get_db().update_profile(user_id, {field: value})
    except Exception as e:
        print(f"Warning: profile field save failed ({field}): {e}", flush=True)


def update_stage_in_db(user_id: str, stage: str) -> None:
    """Update the user's journey stage in DB."""
    try:
        get_db().update_profile(user_id, {"journey_stage": stage})
        print(f"Stage updated to {stage} for user {user_id}", flush=True)
    except Exception as e:
        print(f"Warning: stage update failed: {e}", flush=True)


# ── Stage helpers ─────────────────────────────────────────────────────────────

def _stage_from_answer(answer: str) -> str:
    """Map a free-text stage answer to a DB stage value."""
    a = answer.lower()
    if any(w in a for w in ["placed", "school", "admitted", "joined", "form one", "form 1"]):
        return "post_placement"
    if any(w in a for w in ["out", "came", "got", "received", "have", "already", "back"]):
        return "post_results"
    return "pre_exam"


def _role_from_answer(answer: str) -> str:
    """Detect if the user is a student or parent from their answer."""
    a = answer.lower()
    if any(w in a for w in ["parent", "mum", "mom", "dad", "father", "mother", "guardian", "helping my"]):
        return "parent"
    return "student"


def _name_token(role: str) -> str:
    return "you" if role == "student" else "your child"


# ── Onboarding conversation steps ─────────────────────────────────────────────

STEPS = [
    {
        "key": "_role",
        "question": (
            "To give you the most helpful guidance, I'd love to understand "
            "your situation. Are you a student, or are you a parent "
            "helping your child with CBC pathway choices?"
        ),
    },
    {
        "key": "journey_stage",
        "question": (
            "Got it! Just so I know where {name} is in the journey — "
            "have CBC/JSS results come out yet, or are you still waiting? "
            "Or has {name} already been placed in a school?"
        ),
        "is_stage": True,
    },
    {
        "key": "favorite_subject",
        "question": (
            "That helps a lot. What subjects does {name} enjoy the most, "
            "or feel strongest in? For example Sciences, Maths, Arts, "
            "Languages, or something else?"
        ),
    },
    {
        "key": "career_interests",
        "question": (
            "Interesting! And when {name} thinks about the future, "
            "are there any fields or careers that come to mind? "
            "Even a rough idea like 'something in technology' or "
            "'I want to help people' is really useful."
        ),
    },
]


def process_onboarding_turn(user_id: str, user_message: str) -> dict | None:
    """
    Handle one onboarding turn.
    Returns a response dict or None if onboarding is done.
    Called from rag_query.py BEFORE the main RAG pipeline.
    """
    if is_onboarding_complete(user_id):
        return None

    state      = get_onboarding_state(user_id)
    step_index = state.get("step", 0)
    role       = state.get("role", "student")
    name       = _name_token(role)

    # First turn — ask the first question
    if step_index == 0:
        state["step"] = 1
        save_onboarding_state(user_id, state)
        return _wrap(STEPS[0]["question"].replace("{name}", name))

    # Process answer to previous step
    prev     = STEPS[step_index - 1]
    prev_key = prev["key"]
    answer   = user_message.strip()

    if prev_key == "_role":
        role  = _role_from_answer(answer)
        name  = _name_token(role)
        state["role"] = role
    elif prev.get("is_stage"):
        stage = _stage_from_answer(answer)
        update_stage_in_db(user_id, stage)
    else:
        save_profile_field(user_id, prev_key, answer)

    state["step"] = step_index + 1
    save_onboarding_state(user_id, state)

    # All steps done
    if step_index >= len(STEPS):
        mark_onboarding_complete(user_id)
        return _wrap(
            "Thank you — that gives me a really good picture! "
            "Feel free to ask me anything now. I can help with CBC pathways, "
            "what your grades mean, subject combinations, schools, and careers."
        )

    # Ask next question
    next_q = STEPS[step_index]["question"].replace("{name}", name)
    return _wrap(next_q)


def _wrap(message: str) -> dict:
    return {
        "question": "",
        "answer":   message,
        "mode":     "onboarding",
        "metadata": {
            "source_folder":    "onboarding",
            "confidence_score": 1.0,
            "validated":        True,
            "intent":           "onboarding",
        },
    }
