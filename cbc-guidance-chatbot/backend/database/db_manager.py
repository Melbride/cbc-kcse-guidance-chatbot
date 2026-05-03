#import required libraries for database management
import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.extensions import TRANSACTION_STATUS_INERROR
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional, List, Dict
import numpy as np
import uuid
from threading import Lock

#load environment variables
load_dotenv()  

_db_singleton = None  
_db_lock = Lock  

"""
========================================================
Database Manager Class
========================================================
This class manages all database operations for the CBC Guidance System.
It handles user management, conversation history, CBC results, and school placements.
It also provides caching for query optimization.
"""

class DatabaseManager:
    """
    =====================================================
    Connection Management
    =====================================================
    The following methods manage the database connection.
    """
    def _connect(self):
        """Create a fresh PostgreSQL connection using current environment settings."""
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return psycopg2.connect(
                database_url,
                connect_timeout=10
            )

        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "cbc_chatbot"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            port=os.getenv("DB_PORT", "5432"),
            connect_timeout=10
        )

    def _ensure_connection(self):
        """Reconnect if the shared connection was closed or dropped."""
        if getattr(self, "conn", None) is None or self.conn.closed:
            self.conn = self._connect()

    def _safe_rollback(self):
        """Rollback only when the connection is still open."""
        try:
            if self.conn and not self.conn.closed:
                self.conn.rollback()
        except Exception as e:
            print(f"Warning: rollback skipped: {e}")

    def _reset_failed_transaction(self):
        """Clear aborted transactions so later requests can use the shared connection."""
        try:
            self._ensure_connection()
            if self.conn and not self.conn.closed:
                status = self.conn.get_transaction_status()
                if status == TRANSACTION_STATUS_INERROR:
                    self.conn.rollback()
        except Exception as e:
            print(f"Warning: failed to reset transaction state: {e}")

    def close(self):
        """Close the underlying database connection if it is open."""
        try:
            if self.conn and not self.conn.closed:
                self.conn.close()
        except Exception as e:
            print(f"Warning: failed to close database connection: {e}")

    def get_all_users(self):
        """Return all users for admin dashboard"""
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT user_id, name, email, role, active, created_at, last_active
                    FROM users
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            self._safe_rollback()
            print(f"Error getting all users: {e}")
            return []

    def fetch_all(self, query: str, params: tuple = ()):
        """
        Generic fetch_all method for running SELECT queries and returning all results as a list of dicts.
        Used by config_loader.py for loading counties and subjects.
        """
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchall()
        except Exception as e:
            self._safe_rollback()
            print(f"Error in fetch_all: {e}")
            return []

    """
    Manages all database operations for CBC Guidance System.

    Purpose:
    - Handles user management and profiles
    - Manages conversation history
    - Stores CBC results and school placements
    - Provides caching for query optimization
    """

    def __init__(self):
        #initialize database connection
        self.conn = self._connect()
        self._ensure_user_columns()
        self._ensure_profile_columns()
        self._ensure_analytics_constraints()
        self._promote_configured_admins()

    def _ensure_user_columns(self):
        """Ensure user admin/status columns exist for dashboard management."""
        alter_statements = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'student'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE",
            "UPDATE users SET role = COALESCE(role, 'student')",
            "UPDATE users SET active = COALESCE(active, TRUE)",
        ]
        try:
            with self.conn.cursor() as cur:
                for stmt in alter_statements:
                    cur.execute(stmt)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"Warning: user column migration skipped due to error: {e}")

    def _ensure_profile_columns(self):
        """Ensure profile columns exist for cross-device continuity and incremental schema updates."""
        alter_statements = [
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS favorite_subject VARCHAR(100)",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS interests TEXT",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS strengths TEXT",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS career_interests TEXT",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS learning_style VARCHAR(50)",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS explore_goals TEXT",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS placed_school VARCHAR(255)",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS placed_pathway VARCHAR(100)",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS journey_stage VARCHAR(50)",
            # metadata column for onboarding state and feature flags
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb",
        ]
        try:
            with self.conn.cursor() as cur:
                for stmt in alter_statements:
                    cur.execute(stmt)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"Warning: profile column migration skipped due to error: {e}")

    def _ensure_analytics_constraints(self):
        """Add unique indexes required by analytics upsert queries."""
        self._ensure_analytics_tables()

        statements = [
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_document_usage_hash_unique
            ON document_usage(document_hash)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_gap_hash_unique
            ON knowledge_gap_log(query_hash)
            """,
        ]
        try:
            with self.conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"Warning: analytics index migration skipped due to error: {e}")

    def _ensure_analytics_tables(self):
        """Ensure analytics tables exist with correct schema."""
        statements = [
            """
            CREATE TABLE IF NOT EXISTS document_usage (
                id SERIAL PRIMARY KEY,
                document_name VARCHAR(255) NOT NULL,
                document_hash VARCHAR(64) UNIQUE NOT NULL,
                retrieval_count INTEGER DEFAULT 1,
                avg_confidence_score DECIMAL(3,2) DEFAULT 0.0,
                last_used_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_gap_log (
                id SERIAL PRIMARY KEY,
                query_hash VARCHAR(64) UNIQUE NOT NULL,
                topic_category VARCHAR(100),
                fallback_reason TEXT,
                suggested_document_topic VARCHAR(255),
                count INTEGER DEFAULT 1,
                last_occurred_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS feedback_log (
                id SERIAL PRIMARY KEY,
                query_hash VARCHAR(64) NOT NULL,
                topic_category VARCHAR(100),
                feedback_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id SERIAL PRIMARY KEY,
                admin_id VARCHAR(255) NOT NULL,
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id VARCHAR(255),
                reason TEXT,
                ip_address INET,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        ]
        try:
            with self.conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            self.conn.commit()
            print("Analytics tables ensured successfully")
        except Exception as e:
            self.conn.rollback()
            print(f"Warning: analytics table creation skipped due to error: {e}")

    def _promote_configured_admins(self):
        """Promote configured admin emails to the admin role."""
        raw_admin_emails = os.getenv("ADMIN_EMAILS", "")
        admin_emails = [email.strip().lower() for email in raw_admin_emails.split(",") if email.strip()]
        if not admin_emails:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET role = 'admin'
                    WHERE email IS NOT NULL AND LOWER(email) = ANY(%s)
                    """,
                    (admin_emails,),
                )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"Warning: admin promotion skipped due to error: {e}")


    # ── County validation ─────────────────────────────────────────────────────

    def _validate_school_county_match(self, school_name: str, listed_county: str) -> str:
        if not school_name or not listed_county:
            return listed_county

        school_upper = school_name.upper()
        listed_upper = listed_county.upper()

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT DISTINCT county FROM kenya_senior_schools_pathways WHERE county IS NOT NULL")
                all_counties = [row['county'].upper().strip() for row in cur.fetchall()]

            for county in all_counties:
                if county == listed_upper:
                    continue
                if county in school_upper and county not in listed_upper:
                    return county.title()

        except Exception as e:
            print(f"Warning: county validation failed: {e}")

        return listed_county

    # ── Normalization helpers ─────────────────────────────────────────────────

    def _normalize_county(self, county: str) -> str:
        if not county:
            return None
        normalized = county.strip().upper()
        county_mappings = {
            'NAIROBI': 'NAIROBI',
            'MOMBASA': 'MOMBASA',
            'KISUMU': 'KISUMU',
            'NAKURU': 'NAKURU',
            'ELDORET': 'ELDORET',
        }
        return county_mappings.get(normalized, normalized)

    def _normalize_pathway(self, pathway: str) -> str:
        if not pathway:
            return None
        pathway_lower = pathway.strip().lower()
        pathway_mappings = {
            'stem': 'STEM',
            'social sciences': 'SOCIAL SCIENCES',
            'social science': 'SOCIAL SCIENCES',
            'arts & sports': 'ARTS & SPORTS',
            'arts and sports': 'ARTS & SPORTS',
            'arts': 'ARTS & SPORTS',
            'sports': 'ARTS & SPORTS',
        }
        if pathway_lower in pathway_mappings:
            return pathway_mappings[pathway_lower]
        if any(k in pathway_lower for k in ['science', 'technology', 'engineering', 'mathematics']):
            return 'STEM'
        elif any(k in pathway_lower for k in ['humanities', 'business', 'social', 'economics']):
            return 'SOCIAL SCIENCES'
        elif any(k in pathway_lower for k in ['music', 'dance', 'drama', 'art', 'sport']):
            return 'ARTS & SPORTS'
        return pathway.upper()

    def _normalize_subject(self, subject: str) -> str:
        if not subject:
            return None
        subject_lower = subject.strip().lower()
        subject_mappings = {
            'physics': 'Physics',
            'chemistry': 'Chemistry',
            'biology': 'Biology',
            'mathematics': 'Mathematics',
            'advanced mathematics': 'Advanced Mathematics',
            'english': 'English',
            'kiswahili': 'Kiswahili',
            'fasihi': 'Fasihi',
            'history': 'History',
            'geography': 'Geography',
            'business studies': 'Business Studies',
            'business': 'Business Studies',
            'computer studies': 'Computer Studies',
            'agriculture': 'Agriculture',
            'cre': 'CRE',
            'religious education': 'CRE',
        }
        if subject_lower in subject_mappings:
            return subject_mappings[subject_lower]
        return subject.title()

    # ── School query methods ──────────────────────────────────────────────────

    def get_schools_by_pathway(self, pathway: str, county: str = None, limit: int = 50, gender: str = None) -> List[Dict]:
        self._reset_failed_transaction()
        try:
            pathway_upper = self._normalize_pathway(pathway)
            county_upper = self._normalize_county(county)

            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                pathway_pattern = f"%{pathway_upper}%"

                if county:
                    query = """
                        SELECT DISTINCT school_name, county, sub_county, type, gender,
                               accomodation, pathways_offered, pathway_type
                        FROM kenya_senior_schools_pathways
                        WHERE pathways_offered ILIKE %s AND county = %s
                    """
                    params = [pathway_pattern, county_upper]
                    if gender:
                        query += " AND gender = %s"
                        params.append(gender.upper())
                    query += " ORDER BY school_name LIMIT %s"
                    params.append(limit)

                    cursor.execute(query, params)
                    raw_results = cursor.fetchall()

                    validated_results = []
                    for result in raw_results:
                        result = dict(result)
                        original_county = result['county']
                        corrected_county = self._validate_school_county_match(result['school_name'], original_county)

                        if corrected_county != original_county:
                            result['county'] = corrected_county
                            if corrected_county.upper() == county_upper:
                                validated_results.append(result)
                        else:
                            validated_results.append(result)

                    results = validated_results

                else:
                    query = """
                        SELECT DISTINCT school_name, county, sub_county, type, gender,
                               accomodation, pathways_offered, pathway_type
                        FROM kenya_senior_schools_pathways
                        WHERE pathways_offered ILIKE %s
                    """
                    params = [pathway_pattern]
                    if gender:
                        query += " AND gender = %s"
                        params.append(gender.upper())
                    query += " ORDER BY school_name LIMIT %s"
                    params.append(limit)

                    cursor.execute(query, params)
                    results = cursor.fetchall()

                return results

        except Exception as e:
            self.conn.rollback()
            print(f"Error getting schools by pathway: {e}")
            return []

    def get_schools_by_county(self, county: str, limit: int = 50, gender: str = None) -> List[Dict]:
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT DISTINCT school_name, county, sub_county, type, gender,
                           accomodation, pathways_offered, combo_pathway
                    FROM kenya_senior_schools_pathways
                    WHERE county = %s
                """
                params = [county.upper()]
                if gender:
                    query += " AND gender = %s"
                    params.append(gender.upper())
                query += " ORDER BY school_name LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                raw_results = cursor.fetchall()

                validated_results = []
                for result in raw_results:
                    result = dict(result)
                    original_county = result['county']
                    corrected_county = self._validate_school_county_match(result['school_name'], original_county)

                    if corrected_county != original_county:
                        result['county'] = corrected_county
                        if corrected_county.upper() == county.upper():
                            validated_results.append(result)
                    else:
                        validated_results.append(result)

                schools = []
                for row in validated_results:
                    school = dict(row)
                    if isinstance(school.get('pathways_offered'), str):
                        import ast
                        try:
                            school['pathways_offered'] = ast.literal_eval(school['pathways_offered'])
                        except:
                            school['pathways_offered'] = []
                    elif school.get('pathways_offered') is None:
                        school['pathways_offered'] = []
                    schools.append(school)

                return schools

        except Exception as e:
            print(f"Error getting schools by county: {e}")
            return []

    def get_subject_combinations_by_pathway(self, pathway: str, county: str = None) -> List[str]:
        try:
            pathway_upper = self._normalize_pathway(pathway)
            county_upper = self._normalize_county(county)

            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                pathway_pattern = f"%{pathway_upper}%"
                if county_upper:
                    query = """
                        SELECT DISTINCT
                            CASE
                                WHEN subject_1 IS NOT NULL AND subject_2 IS NOT NULL AND subject_3 IS NOT NULL
                                THEN subject_1 || ', ' || subject_2 || ', ' || subject_3
                                WHEN subject_1 IS NOT NULL AND subject_2 IS NOT NULL
                                THEN subject_1 || ', ' || subject_2
                                WHEN subject_1 IS NOT NULL
                                THEN subject_1
                                ELSE 'No subjects specified'
                            END as combination
                        FROM kenya_senior_schools_pathways
                        WHERE pathways_offered ILIKE %s
                            AND county = %s
                            AND subject_1 IS NOT NULL
                        ORDER BY combination
                    """
                    cursor.execute(query, (pathway_pattern, county_upper))
                else:
                    query = """
                        SELECT DISTINCT
                            CASE
                                WHEN subject_1 IS NOT NULL AND subject_2 IS NOT NULL AND subject_3 IS NOT NULL
                                THEN subject_1 || ', ' || subject_2 || ', ' || subject_3
                                WHEN subject_1 IS NOT NULL AND subject_2 IS NOT NULL
                                THEN subject_1 || ', ' || subject_2
                                WHEN subject_1 IS NOT NULL
                                THEN subject_1
                                ELSE 'No subjects specified'
                            END as combination
                        FROM kenya_senior_schools_pathways
                        WHERE pathways_offered ILIKE %s
                            AND subject_1 IS NOT NULL
                        ORDER BY combination
                    """
                    cursor.execute(query, (pathway_pattern,))

                results = cursor.fetchall()
                combinations = []
                for row in results:
                    combination = row.get('combination')
                    if combination and combination != 'No subjects specified':
                        combinations.append(combination)

                return combinations

        except Exception as e:
            print(f"Error getting subject combinations: {e}")
            return []

    def get_schools_by_subjects(self, subjects: List[str], county: str = None, limit: int = 50) -> List[Dict]:
        try:
            county_upper = self._normalize_county(county)
            normalized_subjects = [self._normalize_subject(subject) for subject in subjects]

            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                placeholders = " OR ".join(["combo_pathway ILIKE %s"] * len(normalized_subjects))
                search_patterns = [f"%{subject}%" for subject in normalized_subjects]

                if county:
                    query = f"""
                        SELECT school_name, county, type, gender, accomodation, pathways_offered, combo_pathway
                        FROM kenya_senior_schools_pathways
                        WHERE county = %s AND ({placeholders})
                        ORDER BY school_name
                        LIMIT %s
                    """
                    cursor.execute(query, (county_upper, *search_patterns, limit))
                else:
                    query = f"""
                        SELECT school_name, county, type, gender, accomodation, pathways_offered, combo_pathway
                        FROM kenya_senior_schools_pathways
                        WHERE ({placeholders})
                        ORDER BY school_name
                        LIMIT %s
                    """
                    cursor.execute(query, (*search_patterns, limit))

                results = cursor.fetchall()
                return results

        except Exception as e:
            print(f"Error getting schools by subjects: {e}")
            return []

    def get_pathway_statistics(self) -> Dict:
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT pathway_type, COUNT(*) as count
                    FROM kenya_senior_schools_pathways
                    GROUP BY pathway_type
                    ORDER BY count DESC
                """)
                pathway_types = cursor.fetchall()

                cursor.execute("""
                    SELECT unnest(string_to_array(pathways_offered, ',')) as pathway, COUNT(*) as count
                    FROM kenya_senior_schools_pathways
                    GROUP BY pathway
                    ORDER BY count DESC
                """)
                pathways_offered = cursor.fetchall()

                cursor.execute("""
                    SELECT county, COUNT(*) as count
                    FROM kenya_senior_schools_pathways
                    GROUP BY county
                    ORDER BY count DESC
                    LIMIT 10
                """)
                top_counties = cursor.fetchall()

                return {
                    "pathway_types": pathway_types,
                    "pathways_offered": pathways_offered,
                    "top_counties": top_counties,
                }

        except Exception as e:
            self._safe_rollback()
            print(f"Error getting pathway statistics: {e}")
            return {}

    def search_schools(self, query: str, limit: int = 50) -> List[Dict]:
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                search_query = """
                    SELECT school_name, county, sub_county, type, gender, pathways_offered
                    FROM kenya_senior_schools_pathways
                    WHERE school_name ILIKE %s OR county ILIKE %s
                    ORDER BY school_name
                    LIMIT %s
                """
                search_term = f"%{query}%"
                cursor.execute(search_query, (search_term, search_term, limit))
                return cursor.fetchall()
        except Exception as e:
            self._safe_rollback()
            print(f"Error searching schools: {e}")
            return []

    def get_schools_catalog(
        self,
        pathway: Optional[str] = None,
        county: Optional[str] = None,
        school_type: Optional[str] = None,
        gender: Optional[str] = None,
        search_query: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
    ) -> Dict:
        self._reset_failed_transaction()
        try:
            safe_page = max(1, int(page or 1))
            safe_page_size = max(1, min(100, int(page_size or 30)))
            offset = (safe_page - 1) * safe_page_size

            where_clauses = []
            params = []

            if pathway:
                pathway_upper = self._normalize_pathway(pathway)
                where_clauses.append("pathways_offered ILIKE %s")
                params.append(f"%{pathway_upper}%")

            if county:
                county_upper = self._normalize_county(county)
                where_clauses.append("county = %s")
                params.append(county_upper)

            if school_type:
                where_clauses.append("type = %s")
                params.append(str(school_type).upper())

            if gender:
                where_clauses.append("gender = %s")
                params.append(str(gender).upper())

            if search_query:
                where_clauses.append("(school_name ILIKE %s OR county ILIKE %s)")
                search_term = f"%{search_query.strip()}%"
                params.extend([search_term, search_term])

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                count_query = f"""
                    SELECT COUNT(*) AS total
                    FROM kenya_senior_schools_pathways
                    {where_sql}
                """
                cursor.execute(count_query, params)
                total = int(cursor.fetchone()["total"])

                data_query = f"""
                    SELECT school_name, county, sub_county, type, gender,
                           accomodation, pathways_offered
                    FROM kenya_senior_schools_pathways
                    {where_sql}
                    ORDER BY school_name
                    LIMIT %s OFFSET %s
                """
                data_params = [*params, safe_page_size, offset]
                cursor.execute(data_query, data_params)
                rows = cursor.fetchall()

            schools = []
            for row in rows:
                school = dict(row)
                if school.get("pathways_offered") is None:
                    school["pathways_offered"] = []
                elif isinstance(school.get("pathways_offered"), str):
                    import ast
                    try:
                        school["pathways_offered"] = ast.literal_eval(school["pathways_offered"])
                    except Exception:
                        school["pathways_offered"] = [school["pathways_offered"]]
                schools.append(school)

            total_pages = (total + safe_page_size - 1) // safe_page_size if total > 0 else 0

            return {
                "schools": schools,
                "total": total,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": total_pages,
            }

        except Exception as e:
            self._safe_rollback()
            print(f"Error getting schools catalog: {e}")
            return {
                "schools": [],
                "total": 0,
                "page": 1,
                "page_size": 30,
                "total_pages": 0,
            }

    # ── User management ───────────────────────────────────────────────────────

    def create_user(self, user_id: str = None, email: str = None, name: str = None):
        """Create new user or return existing"""
        if not user_id:
            user_id = str(uuid.uuid4())
        normalized_email = email.strip().lower() if isinstance(email, str) else email
        configured_admins = {
            item.strip().lower()
            for item in os.getenv("ADMIN_EMAILS", "").split(",")
            if item.strip()
        }
        resolved_role = "admin" if normalized_email and normalized_email in configured_admins else "student"
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO users (user_id, email, name, role, active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (user_id) DO UPDATE
                SET last_active = NOW(),
                    email = COALESCE(EXCLUDED.email, users.email),
                    name = COALESCE(EXCLUDED.name, users.name),
                    role = COALESCE(users.role, EXCLUDED.role)
                RETURNING user_id, email, name, role, active, created_at
            """, (user_id, normalized_email, name, resolved_role))
            self.conn.commit()
            return cur.fetchone()

    def get_user(self, user_id: str):
        """Get user by id"""
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            self._safe_rollback()
            print(f"Error getting user {user_id}: {e}")
            return None

    def get_user_by_email(self, email: str):
        """Get user by email"""
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            self._safe_rollback()
            print(f"Error getting user by email: {e}")
            return None

    # ── Profile management ────────────────────────────────────────────────────

    def save_profile(self, user_id: str, profile_data: dict):
        """Save or update user profile"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_profiles (
                    user_id, favorite_subject, interests, strengths, career_interests,
                    learning_style, explore_goals, placed_school, placed_pathway,
                    mathematics_avg, science_avg, english_avg,
                    kiswahili_avg, social_studies_avg, business_studies_avg,
                    problem_solving_level, scientific_reasoning_level,
                    collaboration_level, communication_level,
                    interest_stem, interest_arts, interest_social,
                    career_goals, interest_creative, interest_sports, interest_dance,
                    overall_performance, journey_stage
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    favorite_subject = EXCLUDED.favorite_subject,
                    interests = EXCLUDED.interests,
                    strengths = EXCLUDED.strengths,
                    career_interests = EXCLUDED.career_interests,
                    learning_style = EXCLUDED.learning_style,
                    explore_goals = EXCLUDED.explore_goals,
                    placed_school = EXCLUDED.placed_school,
                    placed_pathway = EXCLUDED.placed_pathway,
                    mathematics_avg = EXCLUDED.mathematics_avg,
                    science_avg = EXCLUDED.science_avg,
                    english_avg = EXCLUDED.english_avg,
                    kiswahili_avg = EXCLUDED.kiswahili_avg,
                    social_studies_avg = EXCLUDED.social_studies_avg,
                    business_studies_avg = EXCLUDED.business_studies_avg,
                    problem_solving_level = EXCLUDED.problem_solving_level,
                    scientific_reasoning_level = EXCLUDED.scientific_reasoning_level,
                    collaboration_level = EXCLUDED.collaboration_level,
                    communication_level = EXCLUDED.communication_level,
                    interest_stem = EXCLUDED.interest_stem,
                    interest_arts = EXCLUDED.interest_arts,
                    interest_social = EXCLUDED.interest_social,
                    career_goals = EXCLUDED.career_goals,
                    interest_creative = EXCLUDED.interest_creative,
                    interest_sports = EXCLUDED.interest_sports,
                    interest_dance = EXCLUDED.interest_dance,
                    overall_performance = EXCLUDED.overall_performance,
                    journey_stage = EXCLUDED.journey_stage,
                    updated_at = NOW()
            """, (
                user_id,
                profile_data.get('favorite_subject'),
                profile_data.get('interests'),
                profile_data.get('strengths'),
                profile_data.get('career_interests'),
                profile_data.get('learning_style'),
                profile_data.get('explore_goals'),
                profile_data.get('placed_school'),
                profile_data.get('placed_pathway'),
                profile_data.get('mathematics_avg'),
                profile_data.get('science_avg'),
                profile_data.get('english_avg'),
                profile_data.get('kiswahili_avg'),
                profile_data.get('social_studies_avg'),
                profile_data.get('business_studies_avg'),
                profile_data.get('problem_solving_level'),
                profile_data.get('scientific_reasoning_level'),
                profile_data.get('collaboration_level'),
                profile_data.get('communication_level'),
                profile_data.get('interest_stem'),
                profile_data.get('interest_arts'),
                profile_data.get('interest_social'),
                Json(profile_data.get('career_goals', [])),
                profile_data.get('interest_creative'),
                profile_data.get('interest_sports'),
                profile_data.get('interest_dance'),
                profile_data.get('overall_performance'),
                profile_data.get('journey_stage'),
            ))
            self.conn.commit()
            return {"status": "success", "message": "Profile saved successfully"}

    def get_profile(self, user_id: str):
        """Get user profile combined with user info"""
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        u.user_id, u.name, u.email, u.created_at, u.last_active,
                        p.*,
                        cps.stem_score,
                        cps.social_sciences_score,
                        cps.arts_sports_score,
                        cps.knec_recommended_pathway,
                        COALESCE(csr.subject_count, 0) AS cbc_subject_count,
                        COALESCE(csr.subjects_json, '[]'::jsonb) AS cbc_subject_results
                    FROM users u
                    LEFT JOIN user_profiles p ON u.user_id = p.user_id
                    LEFT JOIN cbc_pathway_scores cps ON u.user_id = cps.user_id
                    LEFT JOIN (
                        SELECT
                            user_id,
                            COUNT(*) AS subject_count,
                            jsonb_agg(
                                jsonb_build_object(
                                    'subject_code', subject_code,
                                    'subject_name', subject_name,
                                    'performance_level', performance_level,
                                    'points', points
                                )
                                ORDER BY subject_code
                            ) AS subjects_json
                        FROM cbc_subject_results
                        GROUP BY user_id
                    ) csr ON u.user_id = csr.user_id
                    WHERE u.user_id = %s
                """, (user_id,))
                result = cur.fetchone()
                return result

        except Exception as e:
            self._safe_rollback()
            print(f"Error getting profile: {e}")
            return None

    def get_user_stage(self, user_id: str):
        """Get user's current stage from database"""
        profile = self.get_profile(user_id)
        if not profile:
            return "pre_exam"
        stage = profile.get('journey_stage')
        if stage:
            return stage
        return "pre_exam"

    def should_prompt_for_stage_update(self, user_id: str) -> dict:
        """Check if user should be prompted to update their stage"""
        profile = self.get_profile(user_id)
        if not profile:
            return {"should_prompt": False}
        current_stage = profile.get('journey_stage', 'pre_exam')
        created_at = profile.get('created_at')
        if not created_at:
            return {"should_prompt": False}

        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except:
                return {"should_prompt": False}

        days_since_signup = (datetime.now() - created_at).days
        EXAM_RESULTS_DAYS = 30
        PLACEMENT_DAYS = 50

        if current_stage == "pre_exam" and days_since_signup >= EXAM_RESULTS_DAYS:
            return {
                "should_prompt": True,
                "reason": "exam_results",
                "message": "Have you received your Grade 9 results yet?",
            }
        if current_stage == "post_results" and days_since_signup >= PLACEMENT_DAYS:
            return {
                "should_prompt": True,
                "reason": "placement",
                "message": "Have you been placed in a school yet?",
            }
        return {"should_prompt": False}

    def update_profile(self, user_id: str, profile_data: dict):
        """Update existing user profile"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE user_profiles SET
                    favorite_subject = COALESCE(%s, favorite_subject),
                    interests = COALESCE(%s, interests),
                    strengths = COALESCE(%s, strengths),
                    career_interests = COALESCE(%s, career_interests),
                    learning_style = COALESCE(%s, learning_style),
                    explore_goals = COALESCE(%s, explore_goals),
                    placed_school = COALESCE(%s, placed_school),
                    placed_pathway = COALESCE(%s, placed_pathway),
                    mathematics_avg = COALESCE(%s, mathematics_avg),
                    science_avg = COALESCE(%s, science_avg),
                    english_avg = COALESCE(%s, english_avg),
                    kiswahili_avg = COALESCE(%s, kiswahili_avg),
                    social_studies_avg = COALESCE(%s, social_studies_avg),
                    business_studies_avg = COALESCE(%s, business_studies_avg),
                    problem_solving_level = COALESCE(%s, problem_solving_level),
                    scientific_reasoning_level = COALESCE(%s, scientific_reasoning_level),
                    collaboration_level = COALESCE(%s, collaboration_level),
                    communication_level = COALESCE(%s, communication_level),
                    interest_stem = COALESCE(%s, interest_stem),
                    interest_arts = COALESCE(%s, interest_arts),
                    interest_social = COALESCE(%s, interest_social),
                    career_goals = COALESCE(%s, career_goals),
                    interest_creative = COALESCE(%s, interest_creative),
                    interest_sports = COALESCE(%s, interest_sports),
                    interest_dance = COALESCE(%s, interest_dance),
                    overall_performance = COALESCE(%s, overall_performance),
                    journey_stage = COALESCE(%s, journey_stage),
                    updated_at = NOW()
                WHERE user_id = %s
            """, (
                profile_data.get('favorite_subject'),
                profile_data.get('interests'),
                profile_data.get('strengths'),
                profile_data.get('career_interests'),
                profile_data.get('learning_style'),
                profile_data.get('explore_goals'),
                profile_data.get('placed_school'),
                profile_data.get('placed_pathway'),
                profile_data.get('mathematics_avg'),
                profile_data.get('science_avg'),
                profile_data.get('english_avg'),
                profile_data.get('kiswahili_avg'),
                profile_data.get('social_studies_avg'),
                profile_data.get('business_studies_avg'),
                profile_data.get('problem_solving_level'),
                profile_data.get('scientific_reasoning_level'),
                profile_data.get('collaboration_level'),
                profile_data.get('communication_level'),
                profile_data.get('interest_stem'),
                profile_data.get('interest_arts'),
                profile_data.get('interest_social'),
                Json(profile_data.get('career_goals', [])) if profile_data.get('career_goals') else None,
                profile_data.get('interest_creative'),
                profile_data.get('interest_sports'),
                profile_data.get('interest_dance'),
                profile_data.get('overall_performance'),
                profile_data.get('journey_stage'),
                user_id,
            ))

            if profile_data.get('name') or profile_data.get('email'):
                cur.execute("""
                    UPDATE users SET
                        name = COALESCE(%s, name),
                        email = COALESCE(%s, email),
                        last_active = NOW()
                    WHERE user_id = %s
                """, (profile_data.get('name'), profile_data.get('email'), user_id))

            self.conn.commit()
            return {"status": "success", "message": "Profile updated successfully"}

    # ── User metadata (onboarding state, feature flags) ──────────────────────

    def get_user_metadata(self, user_id: str, key: str):
        """
        Get a metadata value for a user by key.
        Stored as a JSONB column on user_profiles.
        Returns the value or None if not found.
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT metadata
                    FROM user_profiles
                    WHERE user_id = %s
                """, (user_id,))
                row = cur.fetchone()
                if not row or not row.get('metadata'):
                    return None
                return row['metadata'].get(key)
        except Exception as e:
            print(f"Warning: get_user_metadata failed for key '{key}': {e}", flush=True)
            return None

    def set_user_metadata(self, user_id: str, key: str, value) -> None:
        """
        Set a metadata value for a user by key.
        Stored as a JSONB column on user_profiles.
        Creates the profile row if it doesn't exist.
        """
        try:
            with self.conn.cursor() as cur:
                # Ensure profile row exists
                cur.execute("""
                    INSERT INTO user_profiles (user_id, metadata)
                    VALUES (%s, '{}'::jsonb)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id,))
                # Merge new key into existing metadata
                cur.execute("""
                    UPDATE user_profiles
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE user_id = %s
                """, (Json({key: value}), user_id))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"Warning: set_user_metadata failed for key '{key}': {e}", flush=True)

    # ── Conversation history ──────────────────────────────────────────────────

    def save_conversation(self, user_id: str, question: str, question_embedding: np.ndarray,
                          answer: str, mode: str, metadata: dict):
        """Save conversation to history"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO conversations (
                        user_id, question, question_embedding, answer, mode,
                        source_folder, confidence_score, validated, from_cache,
                        recommended_pathway, match_score
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    question,
                    question_embedding.tolist(),
                    answer,
                    mode,
                    metadata.get('source_folder'),
                    metadata.get('confidence_score'),
                    metadata.get('validated', False),
                    metadata.get('from_cache', False),
                    metadata.get('recommended_pathway'),
                    metadata.get('match_score'),
                ))
                self.conn.commit()
                return {"status": "success", "message": "Chat saved successfully"}
        except Exception as e:
            self.conn.rollback()
            print(f"Error saving conversation: {e}")
            return {"status": "error", "message": str(e)}

    # ── CBC results & placement ───────────────────────────────────────────────

    def save_cbc_results(self, user_id: str, cbc_results: dict):
        """Save official CBC Grade 9 results"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_profiles (user_id, journey_stage)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    journey_stage = EXCLUDED.journey_stage,
                    updated_at = NOW()
            """, (user_id, 'post_results'))

            cur.execute("""
                INSERT INTO cbc_pathway_scores
                (user_id, stem_score, social_sciences_score, arts_sports_score, knec_recommended_pathway)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    stem_score = EXCLUDED.stem_score,
                    social_sciences_score = EXCLUDED.social_sciences_score,
                    arts_sports_score = EXCLUDED.arts_sports_score,
                    knec_recommended_pathway = EXCLUDED.knec_recommended_pathway
            """, (
                user_id,
                cbc_results.get('stem_pathway_score'),
                cbc_results.get('social_sciences_pathway_score'),
                cbc_results.get('arts_sports_pathway_score'),
                cbc_results.get('recommended_pathway'),
            ))

            cur.execute("DELETE FROM cbc_subject_results WHERE user_id = %s", (user_id,))

            for subject in cbc_results.get('subjects', []):
                cur.execute("""
                    INSERT INTO cbc_subject_results
                    (user_id, subject_code, subject_name, performance_level, points)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    user_id,
                    subject.get('subject_code'),
                    subject.get('subject_name'),
                    subject.get('performance_level'),
                    subject.get('points'),
                ))
            self.conn.commit()
            return {"status": "success", "message": "CBC results saved successfully"}

    def save_school_placement(self, user_id: str, placement: dict):
        """Save school placement information"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO school_placements
                (user_id, school_name, pathway, reporting_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    school_name = EXCLUDED.school_name,
                    pathway = EXCLUDED.pathway,
                    reporting_date = EXCLUDED.reporting_date
            """, (
                user_id,
                placement.get('school_name'),
                placement.get('pathway'),
                placement.get('reporting_date'),
            ))
            self.conn.commit()
            return {"status": "success", "message": "School placement saved successfully"}

    def get_user_history(self, user_id: str, limit: int = 10):
        """Get user's conversation history"""
        self._reset_failed_transaction()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT question, answer, mode, created_at
                    FROM conversations
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            self.conn.rollback()
            print(f"Error getting user history for {user_id}: {e}")
            return []

    # ── Caching ───────────────────────────────────────────────────────────────

    def search_cache(self, question_embedding: np.ndarray, similarity_threshold: float = 0.95, mode: str = 'general'):
        """Search for similar questions in cache"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        id, question_text, answer, source_folder,
                        confidence_score, validated, times_requested,
                        1 - (question_embedding <=> %s::vector) as similarity
                    FROM cached_qa
                    WHERE mode = %s
                      AND 1 - (question_embedding <=> %s::vector) > %s
                    ORDER BY similarity DESC
                    LIMIT 1
                """, (question_embedding.tolist(), mode, question_embedding.tolist(), similarity_threshold))

                result = cur.fetchone()
                if result:
                    cur.execute("""
                        UPDATE cached_qa
                        SET times_requested = times_requested + 1,
                            last_requested_at = NOW()
                        WHERE id = %s
                    """, (result['id'],))
                    self.conn.commit()
                return result

        except Exception as e:
            self.conn.rollback()
            print(f"Error searching cache: {e}")
            return None

    def save_to_cache(self, question: str, question_embedding: np.ndarray,
                      answer: str, mode: str, metadata: dict):
        """Save Q&A to cache"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cached_qa
                (question_text, question_embedding, answer, mode, source_folder,
                 confidence_score, validated)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                question,
                question_embedding.tolist(),
                answer,
                mode,
                metadata.get('source_folder'),
                metadata.get('confidence_score'),
                metadata.get('validated', True),
            ))
            self.conn.commit()

    # ── Recommendations ───────────────────────────────────────────────────────

    def save_recommendation(self, user_id: str, recommendation: dict):
        """Save pathway recommendation"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO recommendations
                (user_id, pathway, match_score, reasoning, subjects, careers)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                recommendation.get('pathway'),
                recommendation.get('match_score'),
                recommendation.get('reasoning'),
                Json(recommendation.get('subjects', [])),
                Json(recommendation.get('careers', [])),
            ))
            self.conn.commit()

    def get_user_recommendations(self, user_id: str):
        """Get user's recommendation history"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM recommendations
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            return cur.fetchall()

    def get_pathway_scores(self, user_id: str):
        """Get user's pathway scores from CBC results or calculate from profile"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT stem_score, social_sciences_score, arts_sports_score
                FROM cbc_pathway_scores
                WHERE user_id = %s
            """, (user_id,))
            result = cur.fetchone()

            if result and (
                result.get('stem_score') is not None
                or result.get('social_sciences_score') is not None
                or result.get('arts_sports_score') is not None
            ):
                return {
                    "STEM": result.get('stem_score') or 0,
                    "Social Sciences": result.get('social_sciences_score') or 0,
                    "Arts and Sports Science": result.get('arts_sports_score') or 0,
                }

            cur.execute("""
                SELECT mathematics_avg, science_avg, english_avg, kiswahili_avg,
                       social_studies_avg, interest_stem, interest_arts, interest_social
                FROM user_profiles
                WHERE user_id = %s
            """, (user_id,))
            profile = cur.fetchone()
            if not profile:
                return None

            stem_score = (
                (profile.get('mathematics_avg') or 0) * 0.4
                + (profile.get('science_avg') or 0) * 0.4
                + (profile.get('english_avg') or 0) * 0.2
            )
            social_score = (
                (profile.get('english_avg') or 0) * 0.3
                + (profile.get('kiswahili_avg') or 0) * 0.3
                + (profile.get('social_studies_avg') or 0) * 0.4
            )
            arts_score = (
                (profile.get('social_studies_avg') or 0) * 0.3
                + (profile.get('interest_arts') or 3) * 2
                + (profile.get('interest_social') or 3) * 1
            )
            return {
                "STEM": round(stem_score, 2),
                "Social Sciences": round(social_score, 2),
                "Arts and Sports Science": round(arts_score, 2),
            }


def get_shared_db() -> DatabaseManager:
    """Process-wide shared DatabaseManager instance."""
    global _db_singleton
    if _db_singleton is None or getattr(_db_singleton, "conn", None) is None or _db_singleton.conn.closed:
        with _db_lock:
            if _db_singleton is None or getattr(_db_singleton, "conn", None) is None or _db_singleton.conn.closed:
                _db_singleton = DatabaseManager()
    return _db_singleton


def close_shared_db() -> None:
    """Close and clear the process-wide shared DatabaseManager instance."""
    global _db_singleton
    with _db_lock:
        if _db_singleton is not None:
            _db_singleton.close()
            _db_singleton = None
