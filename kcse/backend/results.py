
import os
import psycopg2

# --- Ensure .env is loaded for all entry points ---
def _load_dotenv():
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for env_path in candidate_paths:
        env_path = os.path.normpath(env_path)
        if not os.path.exists(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value

_load_dotenv()

# GRADE CONVERSION
GRADE_POINTS = {
    "A": 12, "A-": 11,
    "B+": 10, "B": 9, "B-": 8,
    "C+": 7, "C": 6, "C-": 5,
    "D+": 4, "D": 3, "D-": 2,
    "E": 1,
}
#DATABASE CONNECTION
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "kcse"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )

#FETCH COURSES
def fetch_courses(cur):
    cur.execute("SELECT id, name, level, min_mean_grade FROM courses")
    rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "level": r[2], "min_mean_grade": r[3]}
        for r in rows
    ]
#FETCH REQUIREMENTS
def fetch_requirements(cur, course_id):
    cur.execute(
        "SELECT subject, min_grade FROM course_requirements WHERE course_id = %s",
        (course_id,),
    )
    rows = cur.fetchall()
    return [{"subject": r[0], "min_grade": r[1]} for r in rows]

#FETCH INSTITUTIONS
def fetch_institutions(cur, course_id):
    cur.execute(
        """
        SELECT i.name
        FROM institutions i
        JOIN course_institutions ci ON i.id = ci.institution_id
        WHERE ci.course_id = %s
        """,
        (course_id,),
    )
    rows = cur.fetchall()
    return [r[0] for r in rows]
