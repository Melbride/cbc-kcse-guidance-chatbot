"""
history_utils.py
----------------
Conversation history: saving turns and building recent-context strings.
save_conversation_history_safe() is the only function called externally —
build_recent_history_context() has been moved to profile_utils.py so that
utils.py consumers can get both from one place.
"""

import numpy as np
from config_loader import get_db


def save_conversation_history_safe(
    embeddings,
    user_id: str | None,
    question: str,
    answer: str,
    mode: str,
    metadata: dict | None = None,
) -> None:
    """
    Persist a conversation turn to the DB without ever failing the response path.
    embeddings is passed in from rag_query.py (owned by document_search.py).
    """
    if not user_id:
        return

    try:
        allowed_modes = {"general", "personalized"}
        safe_mode = mode if mode in allowed_modes else "general"

        if not get_db().get_user(user_id):
            get_db().create_user(user_id=user_id)

        question_embedding = np.array(embeddings.embed_query(question))
        get_db().save_conversation(
            user_id=user_id,
            question=question,
            question_embedding=question_embedding,
            answer=answer,
            mode=safe_mode,
            metadata=metadata or {},
        )
    except Exception as e:
        print(f"Warning: failed to save conversation history: {e}")
