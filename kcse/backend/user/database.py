# database.py
"""
Database and user management utilities for the KCSE backend.
Handles user CRUD, admin actions, and DB connection logic.
"""
import json
from typing import Optional
from backend.results import get_db_connection
import uuid
from fastapi import HTTPException
import bcrypt

def _column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name)
    )
    return cur.fetchone() is not None

def ensure_user_profiles_schema():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if not _column_exists(cur, "user_profiles", "created_at"):
                    cur.execute("""
                        ALTER TABLE user_profiles
                        ADD COLUMN created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    """)
                    conn.commit()
    except Exception:
        # Keep startup resilient if the database is unavailable or schema changes are restricted.
        pass

def create_user_profile(profile) -> str:
    user_id = str(uuid.uuid4())
    # Validate subjects
    if not profile.subjects or not (7 <= len(profile.subjects) <= 8):
        raise HTTPException(status_code=400, detail="You must provide 7 or 8 subjects.")
    extra_data = profile.extra_data or {}
    extra_data["subjects"] = profile.subjects
    # Hash the password before storing
    if not hasattr(profile, 'password') or not profile.password:
        raise HTTPException(status_code=400, detail="Password is required.")
    hashed_password = bcrypt.hashpw(profile.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if _column_exists(cur, "user_profiles", "created_at"):
                    cur.execute("""
                        INSERT INTO user_profiles (user_id, name, email, password, mean_grade, interests, career_goals, extra_data, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (user_id, profile.name, profile.email, hashed_password, profile.mean_grade, profile.interests, profile.career_goals, json.dumps(extra_data)))
                else:
                    cur.execute("""
                        INSERT INTO user_profiles (user_id, name, email, password, mean_grade, interests, career_goals, extra_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, profile.name, profile.email, hashed_password, profile.mean_grade, profile.interests, profile.career_goals, json.dumps(extra_data)))
                conn.commit()
        return user_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not create user: {e}")

def get_user_profile(user_id: str) -> Optional[dict]:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, name, email, mean_grade, interests, career_goals, extra_data FROM user_profiles WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "user_id": row[0], "name": row[1], "email": row[2], "mean_grade": row[3],
                        "interests": row[4], "career_goals": row[5], "extra_data": row[6]
                    }
                return None
    except Exception as e:
        return None

def get_user_profile_by_email(email: str) -> Optional[dict]:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, name, email, mean_grade, interests, career_goals, extra_data FROM user_profiles WHERE email = %s", (email,))
                row = cur.fetchone()
                if row:
                    return {
                        "user_id": row[0], "name": row[1], "email": row[2], "mean_grade": row[3],
                        "interests": row[4], "career_goals": row[5], "extra_data": row[6]
                    }
                return None
    except Exception as e:
        return None

def delete_user_profile(user_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_profiles WHERE user_id = %s", (user_id,))
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not delete user: {e}")

def list_all_users():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if _column_exists(cur, "user_profiles", "created_at"):
                    cur.execute("""
                        SELECT user_id, name, email, mean_grade, interests, career_goals, extra_data, created_at
                        FROM user_profiles
                    """)
                    users = [
                        {
                            "user_id": row[0],
                            "name": row[1],
                            "email": row[2],
                            "mean_grade": row[3],
                            "interests": row[4],
                            "career_goals": row[5],
                            "extra_data": row[6],
                            "created_at": row[7].isoformat() if row[7] else None
                        }
                        for row in cur.fetchall()
                    ]
                else:
                    cur.execute("SELECT user_id, name, email, mean_grade, interests, career_goals, extra_data FROM user_profiles")
                    users = [
                        {
                            "user_id": row[0],
                            "name": row[1],
                            "email": row[2],
                            "mean_grade": row[3],
                            "interests": row[4],
                            "career_goals": row[5],
                            "extra_data": row[6],
                            "created_at": None
                        }
                        for row in cur.fetchall()
                    ]
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list users: {e}")
