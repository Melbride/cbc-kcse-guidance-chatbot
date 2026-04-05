"""
Handles conversation context storage and retrieval for recommendations.
"""
from backend.results import get_db_connection
from fastapi import HTTPException

def update_conversation_context(conversation_id, user_input, system_response):
    """
    Store the latest user input and system response for a conversation in PostgreSQL.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO conversation_context (conversation_id, user_input, system_response)
                    VALUES (%s, %s, %s)
                """, (conversation_id, user_input, system_response))
                conn.commit()
    except Exception as e:
        raise e

def get_conversation_context(conversation_id):
    """
    Retrieve the last user input and system response for a conversation from PostgreSQL.
    Returns a dict with 'last_user_input' and 'last_system_response'.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_input, system_response FROM conversation_context
                    WHERE conversation_id = %s
                    ORDER BY timestamp DESC LIMIT 1
                """, (conversation_id,))
                row = cur.fetchone()
                if row:
                    return {"last_user_input": row[0], "last_system_response": row[1]}
                return {}
    except Exception:
        return {}

def list_recent_questions(limit=20):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT conversation_id, user_input, system_response, timestamp
                    FROM conversation_context
                    WHERE user_input IS NOT NULL AND TRIM(user_input) <> ''
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
                return [
                    {
                        "conversation_id": row[0],
                        "question": row[1],
                        "response": row[2],
                        "timestamp": row[3].isoformat() if row[3] else None
                    }
                    for row in rows
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load recent questions: {e}")

def list_top_questions(limit=10):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT LOWER(TRIM(user_input)) AS normalized_question, COUNT(*) AS question_count
                    FROM conversation_context
                    WHERE user_input IS NOT NULL AND TRIM(user_input) <> ''
                    GROUP BY LOWER(TRIM(user_input))
                    ORDER BY question_count DESC, normalized_question ASC
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
                return [
                    {
                        "question": row[0],
                        "count": row[1]
                    }
                    for row in rows
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load top questions: {e}")
