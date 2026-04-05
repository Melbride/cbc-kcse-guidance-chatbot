"""
config_loader.py
----------------
Shared config, database singleton, and runtime data loaders.
Imported by all other utility modules to avoid circular imports.

Responsibilities:
  - DB singleton
  - JSON config loading (scoring weights, career hints, keyword routing)
  - DB-backed loaders for counties and subjects (called once at startup)

PostgreSQL schema (from kenya_senior_schools_pathways_v3.xlsx):
  Table: schools
    no, region, county, sub_county, knec_code, school_name,
    cluster, type, accommodation, gender, pathway_type,
    pathways_offered, combo_pathway, combo_track,
    subject_1, subject_2, subject_3
"""

import os
import json
from database.db_manager import DatabaseManager

# ── Database singleton ────────────────────────────────────────────────────────

db = None

def get_db() -> DatabaseManager:
    """Get (or lazily create) the shared DatabaseManager instance."""
    global db
    if db is None:
        db = DatabaseManager()
    return db


# ── JSON config loading ───────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_BASE_DIR, 'config', 'pathway_subject_priority.json'), 'r', encoding='utf-8') as f:
    PATHWAY_SUBJECT_PRIORITY: dict = json.load(f)

with open(os.path.join(_BASE_DIR, 'config', 'career_subject_hints.json'), 'r', encoding='utf-8') as f:
    CAREER_SUBJECT_HINTS: dict = json.load(f)

with open(os.path.join(_BASE_DIR, 'config', 'query_keywords.json'), 'r', encoding='utf-8') as f:
    QUERY_KEYWORDS: dict = json.load(f)


# ── DB-backed data loaders ────────────────────────────────────────────────────
# Load reference data whose source of truth is PostgreSQL, not config files.
# Called once at startup by query_analyzer.py.
# Falls back to empty list on error so startup never crashes.

def load_counties_from_db() -> list[str]:
    """
    Load distinct county names from schools.county.
    Returns lowercase strings for case-insensitive matching in query_analyzer.
    """
    try:
        rows = get_db().fetch_all(
                "SELECT DISTINCT LOWER(county) AS county "
                "FROM kenya_senior_schools_pathways WHERE county IS NOT NULL ORDER BY county"
        )
        return [row["county"] for row in rows if row.get("county")]
    except Exception as e:
        print(f"Warning: could not load counties from DB: {e}")
        return []


def load_subjects_from_db() -> list[str]:
    """
    Load all unique subject names from schools.subject_1, subject_2, subject_3.
    Returns lowercase strings sorted longest-first so that multi-word subjects
    (e.g. 'advanced mathematics') match before shorter ones ('mathematics').
    """
    try:
        rows = get_db().fetch_all("""
            SELECT DISTINCT LOWER(subject) AS subject FROM (
                SELECT subject_1 AS subject FROM kenya_senior_schools_pathways WHERE subject_1 IS NOT NULL
                UNION
                SELECT subject_2 AS subject FROM kenya_senior_schools_pathways WHERE subject_2 IS NOT NULL
                UNION
                SELECT subject_3 AS subject FROM kenya_senior_schools_pathways WHERE subject_3 IS NOT NULL
            ) all_subjects
            ORDER BY subject
        """)
        subjects = [row["subject"] for row in rows if row.get("subject")]
        return sorted(subjects, key=len, reverse=True)
    except Exception as e:
        print(f"Warning: could not load subjects from DB: {e}")
        return []