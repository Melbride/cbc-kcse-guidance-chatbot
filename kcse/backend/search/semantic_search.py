import psycopg2
from dotenv import load_dotenv
import os
import sys

load_dotenv()
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")


def get_keywords(search_term: str) -> list[str]:
    """Split search term into meaningful keywords, filtering noise words."""
    STOP_WORDS = {"in", "of", "the", "and", "or", "for", "a", "an", "to", "at", "by", "is", "kenya", "course", "courses"}
    parts = str(search_term).replace("/", " ").replace(",", " ").split()
    return [p.lower() for p in parts if len(p) > 2 and p.lower() not in STOP_WORDS] or [search_term.strip().lower()]


def search_table_scored(cur, table, select_columns, search_columns, search_term, extra_label=None, limit=6):
    """
    OR-based search: a row matches if ANY keyword appears in ANY search column.
    Rows are then ranked by how many keywords matched (most relevant first).
    This replaces the old AND logic that caused empty results for multi-word queries.
    """
    keywords = get_keywords(search_term)

    # Build one big OR block across all keywords × all columns
    conditions = []
    params = []
    for keyword in keywords:
        for col in search_columns:
            conditions.append(f"LOWER({col}) LIKE %s")
            params.append(f"%{keyword}%")

    # Score = number of keywords that matched (for ranking)
    score_cases = []
    score_params = []
    for keyword in keywords:
        col_conditions = " OR ".join([f"LOWER({col}) LIKE %s" for col in search_columns])
        score_cases.append(f"CASE WHEN ({col_conditions}) THEN 1 ELSE 0 END")
        score_params.extend([f"%{keyword}%"] * len(search_columns))

    select_str = ", ".join(select_columns)
    score_expr = " + ".join(score_cases) if score_cases else "1"

    sql = f"""
    SELECT {select_str}, ({score_expr}) AS _score
    FROM {table}
    WHERE {" OR ".join(conditions)}
    ORDER BY _score DESC
    LIMIT {limit};
    """

    try:
        cur.execute(sql, tuple(params + score_params))
        results = cur.fetchall()
        label = extra_label or table
        # Strip the _score column before returning
        return [(label, row[:-1]) for row in results]
    except Exception as e:
        print(f"Table {table} search failed: {e}", file=sys.stderr)
        return []


def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = sys.stdin.read().strip()

    if not query:
        return

    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
    except Exception as e:
        print(f"DB connection failed: {e}", file=sys.stderr)
        return

    cur = conn.cursor()
    all_results = []

    # Smart table selection based on query keywords
    query_lower = query.lower()
    short_course_keywords = ['short course', 'short courses', 'course', 'courses', 'bootcamp', 'bootcamps', 'coding', 'programming', 'it', 'tech', 'digital', 'online', 'certificate', 'certification']
    degree_keywords = ['degree', 'bachelor', 'masters', 'phd', 'university', 'undergraduate', 'postgraduate']
    diploma_keywords = ['diploma', 'certificate']
    artisan_keywords = ['artisan', 'craft', 'trade', 'technical', 'vocational']

    # --- SkillBuilding (short courses / online platforms) ---
    # Search for short courses when relevant keywords are found
    if any(keyword in query_lower for keyword in short_course_keywords):
        try:
            all_results += search_table_scored(
                cur,
                table="skillbuilding",
                select_columns=["company", "programme_name", "pathway", "duration", "cost", "link"],
                search_columns=["company", "programme_name", "pathway"],
                search_term=query,
                extra_label="SkillBuilding",
                limit=50,
            )
        except Exception:
            pass  # Table may not exist yet

    # --- Degree cutoffs ---
    # Only search for degrees when specifically requested
    if any(keyword in query_lower for keyword in degree_keywords):
        all_results += search_table_scored(
            cur,
            table="degree_cutoffs",
            select_columns=[
                "prog_code", "institution_name", "programme_name", "cutoff_2024",
                "qualification_type", "minimum_mean_grade", "subject_requirements",
                "cluster_or_points_info", "course_description", "career_paths",
                "notes",
            ],
            search_columns=[
                "institution_name", "programme_name", "course_description",
                "career_paths", "cluster_or_points_info"
            ],
            search_term=query,
            extra_label="Degree",
            limit=15,
        )

    # --- Diploma programmes ---
    # Only search for diplomas when specifically requested
    if any(keyword in query_lower for keyword in diploma_keywords):
        all_results += search_table_scored(
            cur,
            table="diploma_programs",
            select_columns=[
                "programme_code", "institution_name", "programme_name",
                "mean_grade", "subject_requirements",
            ],
            search_columns=["institution_name", "programme_name", "subject_requirements"],
            search_term=query,
            extra_label="Diploma",
            limit=15,
        )

    # --- Artisan programmes ---
    # Only search for artisan programmes when specifically requested
    if any(keyword in query_lower for keyword in artisan_keywords):
        all_results += search_table_scored(
            cur,
            table="artisan_programmes",
            select_columns=["level", "institution", "programme", "mean_grade", "requirements"],
            search_columns=["institution", "programme", "requirements"],
            search_term=query,
            extra_label="Artisan",
            limit=10,
        )

    # If no specific keywords found, search all tables (fallback)
    if not any(keyword in query_lower for keyword in short_course_keywords + degree_keywords + diploma_keywords + artisan_keywords):
        # Search all tables as fallback
        all_results += search_table_scored(
            cur,
            table="skillbuilding",
            select_columns=["company", "programme_name", "pathway", "duration", "cost", "link"],
            search_columns=["company", "programme_name", "pathway"],
            search_term=query,
            extra_label="SkillBuilding",
            limit=50,
        )
        all_results += search_table_scored(
            cur,
            table="degree_cutoffs",
            select_columns=[
                "prog_code", "institution_name", "programme_name", "cutoff_2024",
                "qualification_type", "minimum_mean_grade", "subject_requirements",
                "cluster_or_points_info", "course_description", "career_paths",
                "notes",
            ],
            search_columns=[
                "institution_name", "programme_name", "course_description",
                "career_paths", "cluster_or_points_info"
            ],
            search_term=query,
            extra_label="Degree",
            limit=15,
        )
        all_results += search_table_scored(
            cur,
            table="diploma_programs",
            select_columns=[
                "programme_code", "institution_name", "programme_name",
                "mean_grade", "subject_requirements",
            ],
            search_columns=["institution_name", "programme_name", "subject_requirements"],
            search_term=query,
            extra_label="Diploma",
            limit=15,
        )
        all_results += search_table_scored(
            cur,
            table="artisan_programmes",
            select_columns=["level", "institution", "programme", "mean_grade", "requirements"],
            search_columns=["institution", "programme", "requirements"],
            search_term=query,
            extra_label="Artisan",
            limit=10,
        )

    cur.close()
    conn.close()

    for label, row in all_results:
        print(f"[{label}] {row}")


if __name__ == "__main__":
    main()