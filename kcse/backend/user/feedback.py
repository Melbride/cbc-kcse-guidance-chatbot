# feedback.py
"""
Feedback management utilities for the KCSE backend.
Handles feedback CRUD and related DB logic.
"""
from backend.results import get_db_connection
from fastapi import HTTPException

def store_feedback(user_id, recommendation_id, feedback_text, rating):
    """
    Stores user feedback for a recommendation in the feedback table.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO recommendation_feedback (user_id, recommendation_id, feedback_text, rating)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, recommendation_id, feedback_text, rating))
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not store feedback: {e}")

def list_feedback():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id, recommendation_id, feedback_text, rating
                    FROM recommendation_feedback
                    ORDER BY recommendation_id DESC
                """)
                return [
                    {
                        "user_id": row[0],
                        "recommendation_id": row[1],
                        "feedback_text": row[2],
                        "rating": row[3]
                    }
                    for row in cur.fetchall()
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list feedback: {e}")
