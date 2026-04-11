"""
onboarding.py
-------------
Conversational profile and stage collection.

Design principles:
- New users are greeted warmly, then the bot naturally collects their
  situation through conversation — no form required.
- Profile data is saved to DB silently as the conversation progresses.
- The bot never says "according to your profile" — it just uses what it knows.
- Stage mismatches (e.g. user asks post-results question but is pre_exam)
  are handled by answering normally, then gently asking if their stage changed.
- Users can update their profile anytime on the profile page; the bot respects
  whatever is there and fills in gaps through conversation.

3 stages:
  pre_exam       → preparing for JSS exams, hasn't received results
  post_results   → has received results, choosing a pathway
  post_placement → placed in a school, navigating their pathway
"""

from config_loader import get_db

# ── Fields that define a "complete enough" profile for guidance ───────────────

_GUIDANCE_FIELDS = ["journey_stage", "favorite_subject", "career_interests"]

def profile_is_incomplete(profile_data: dict | None) -> bool:
    """True if the profile is missing too much to give meaningful guidance."""
    if not profile_data:
        return True
    filled = sum(1 for f in _GUIDANCE_FIELDS if profile_data.get(f))
    return filled < 1  # even 1 field filled is enough to start guiding


# ── Stage detection from free text ───────────────────────────────────────────

_POST_RESULTS_SIGNALS = [
    "got results", "got my results", "results are out", "results came out",
    "received results", "results back", "ee", "me", "ae", "grading",
    "what does ee", "what does me", "what does ae", "my grade", "my score",
    "passed", "failed", "results show",
]

_POST_PLACEMENT_SIGNALS = [
    "placed", "placement", "admitted", "got a school", "joined",
    "form one", "form 1", "reporting", "new school",
]

_PRE_EXAM_SIGNALS = [
    "preparing", "haven't done", "havent done", "not done", "upcoming exam",
    "next year", "still studying", "not yet", "waiting for", "grade 9", "grade9",
]

def detect_stage_from_question(question: str) -> str | None:
    """
    Detect if a question implies the user is in a different stage than recorded.
    Returns the detected stage or None if no strong signal.
    """
    q = question.lower()
    if any(s in q for s in _POST_PLACEMENT_SIGNALS):
        return "post_placement"
    if any(s in q for s in _POST_RESULTS_SIGNALS):
        return "post_results"
    if any(s in q for s in _PRE_EXAM_SIGNALS):
        return "pre_exam"
    return None

def stage_mismatch(recorded_stage: str | None, detected_stage: str | None) -> bool:
    """True if the detected stage is clearly different from the recorded one."""
    if not recorded_stage or not detected_stage:
        return False
    return recorded_stage != detected_stage

def stage_update_prompt(detected_stage: str) -> str:
    """
    A gentle, natural follow-up question to confirm a stage change.
    Appended to the bot's answer — not a separate message.
    """
    if detected_stage == "post_results":
        return " By the way, it sounds like results may have come out — have they? I can update my guidance for you."
    if detected_stage == "post_placement":
        return " It sounds like you may have already been placed in a school — is that right? Let me know so I can give you the most relevant advice."
    if detected_stage == "pre_exam":
        return " Are you still waiting for results, or have they come out?"
    return ""

def update_stage_in_db(user_id: str, stage: str) -> None:
    """Silently update the user's journey stage in the DB."""
    try:
        get_db().update_profile(user_id, {"journey_stage": stage})
        print(f"Stage updated to {stage} for user {user_id}", flush=True)
    except Exception as e:
        print(f"Warning: stage update failed: {e}", flush=True)


# ── Onboarding state ──────────────────────────────────────────────────────────

def is_onboarding_complete(user_id: str) -> bool:
    try:
        return bool(get_db().get_user_metadata(user_id, "onboarding_complete"))
    except Exception:
        return False

def mark_onboarding_complete(user_id: str) -> None:
    try:
        get_db().set_user_metadata(user_id, "onboarding_complete", True)
    except Exception as e:
        print(f"Warning: could not mark onboarding complete: {e}", flush=True)

def get_onboarding_state(user_id: str) -> dict:
    try:
        state = get_db().get_user_metadata(user_id, "onboarding_state")
        if state:
            return state
    except Exception:
        pass
    return {"step": 0, "role": "student"}

def save_onboarding_state(user_id: str, state: dict) -> None:
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


# ── Stage → question text ─────────────────────────────────────────────────────

def _stage_from_answer(answer: str) -> str:
    """Map a free-text stage answer to a DB stage value."""
    a = answer.lower()
    if any(w in a for w in ["placed", "school", "admitted", "joined", "form one", "form 1"]):
        return "post_placement"
    if any(w in a for w in ["out", "came", "got", "received", "have", "already", "back"]):
        return "post_results"
    return "pre_exam"

def _role_from_answer(answer: str) -> str:
    a = answer.lower()
    if any(w in a for w in ["parent", "mum", "mom", "dad", "father", "mother", "guardian", "helping my"]):
        return "parent"
    return "student"

def _name_token(role: str) -> str:
    return "you" if role == "student" else "your child"


# ── Onboarding conversation steps ────────────────────────────────────────────
# Each step: key (DB field to save), question to ask

STEPS = [
    # Step 0 → ask role (not saved to DB, used to personalise language)
    {
        "key": "_role",
        "question": (
            "To give you the most helpful guidance, I'd love to understand "
            "your situation a little. Are you a student, or are you a parent "
            "helping your child with CBC pathway choices?"
        ),
    },
    # Step 1 → stage
    {
        "key": "journey_stage",
        "question": (
            "Got it, thanks! Just so I know where {name} is in the journey — "
            "have CBC/JSS results come out yet, or are you still waiting? "
            "Or has {name} already been placed in a school?"
        ),
        "is_stage": True,
    },
    # Step 2 → favourite subject / strength
    {
        "key": "favorite_subject",
        "question": (
            "That helps a lot. What subjects does {name} enjoy the most, "
            "or feel strongest in? For example, Sciences, Maths, Arts, "
            "Languages, or something else?"
        ),
    },
    # Step 3 → career interests
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
    Returns a response dict (same shape as query_rag) or None if done.
    Call this from query_rag BEFORE the main RAG pipeline.
    """
    if is_onboarding_complete(user_id):
        return None

    state      = get_onboarding_state(user_id)
    step_index = state.get("step", 0)
    role       = state.get("role", "student")
    name       = _name_token(role)

    # First turn — just ask the first question, don't process any answer yet
    if step_index == 0:
        state["step"] = 1
        save_onboarding_state(user_id, state)
        return _wrap(STEPS[0]["question"].replace("{name}", name))

    # Process the answer to the previous step
    prev       = STEPS[step_index - 1]
    prev_key   = prev["key"]
    answer_raw = user_message.strip()

    if prev_key == "_role":
        role  = _role_from_answer(answer_raw)
        name  = _name_token(role)
        state["role"] = role
    elif prev.get("is_stage"):
        stage = _stage_from_answer(answer_raw)
        update_stage_in_db(user_id, stage)
    else:
        save_profile_field(user_id, prev_key, answer_raw)

    state["step"] = step_index + 1
    save_onboarding_state(user_id, state)

    # If we've exhausted all steps → done
    if step_index >= len(STEPS):
        mark_onboarding_complete(user_id)
        return _wrap(
            "Thank you — that gives me a really good picture! "
            "Feel free to ask me anything now. I can help with CBC pathways, "
            "what your grades mean, subject combinations, schools, careers — whatever's on your mind."
        )

    # Ask the next question
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
