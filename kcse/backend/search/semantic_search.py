import psycopg2
from dotenv import load_dotenv
import os
import sys

# Load environment variables
load_dotenv()
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")


def get_table_columns(cur, table):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row[0] for row in cur.fetchall()]


def search_table_text(cur, table, columns, search_term, extra_label=None, limit=5):
    """Simple text-based search for tables with aligned selected/searchable columns."""
    try:
        search_columns = columns.split(", ")
        raw_keywords = [part.strip().lower() for part in str(search_term).replace("/", " ").split() if len(part.strip()) > 2]
        keywords = raw_keywords or [str(search_term).strip().lower()]
        keyword_groups = []
        params = []

        for keyword in keywords:
            per_keyword_conditions = []
            for col in search_columns:
                per_keyword_conditions.append(f"LOWER({col}) LIKE %s")
                params.append(f"%{keyword}%")
            keyword_groups.append(f"({' OR '.join(per_keyword_conditions)})")

        sql = f"""
        SELECT {columns}
        FROM {table}
        WHERE {' AND '.join(keyword_groups)}
        LIMIT {limit};
        """

        cur.execute(sql, tuple(params))
        results = cur.fetchall()
        return [(table if not extra_label else extra_label, row) for row in results]
    except Exception as e:
        print(f"Table {table} text search failed: {e}")
        return []


def search_table_text_custom(cur, table, select_columns, search_columns, search_term, extra_label=None, limit=5):
    """Text search where the displayed columns differ from searchable columns."""
    try:
        raw_keywords = [part.strip().lower() for part in str(search_term).replace("/", " ").split() if len(part.strip()) > 2]
        keywords = raw_keywords or [str(search_term).strip().lower()]
        keyword_groups = []
        params = []

        for keyword in keywords:
            per_keyword_conditions = []
            for col in search_columns:
                per_keyword_conditions.append(f"LOWER({col}) LIKE %s")
                params.append(f"%{keyword}%")
            keyword_groups.append(f"({' OR '.join(per_keyword_conditions)})")

        sql = f"""
        SELECT {", ".join(select_columns)}
        FROM {table}
        WHERE {' AND '.join(keyword_groups)}
        LIMIT {limit};
        """
        cur.execute(sql, tuple(params))
        results = cur.fetchall()
        return [(table if not extra_label else extra_label, row) for row in results]
    except Exception as e:
        print(f"Table {table} custom text search failed: {e}")
        return []


def main():
    if len(sys.argv) > 1:
        query = sys.argv[1]
    else:
        query = sys.stdin.read().strip()

    if not query:
        return

    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cur = conn.cursor()

    all_results = []

    degree_columns = get_table_columns(cur, "degree_cutoffs")
    extra_degree_columns = [
        "qualification_type",
        "minimum_mean_grade",
        "subject_requirements",
        "cluster_or_points_info",
        "course_description",
        "career_paths",
        "notes",
        "source_reference",
    ]
    available_degree_extra_columns = [col for col in extra_degree_columns if col in degree_columns]
    degree_select_columns = ["prog_code", "institution_name", "programme_name", "cutoff_2024"] + available_degree_extra_columns
    degree_search_columns = ["prog_code", "institution_name", "programme_name"] + available_degree_extra_columns

    all_results += search_table_text_custom(
        cur,
        "degree_cutoffs",
        degree_select_columns,
        degree_search_columns,
        query,
        extra_label="Degree"
    )

    all_results += search_table_text(
        cur,
        "diploma_programs",
        "programme_code, institution_name, programme_name, mean_grade, subject_requirements",
        query,
        extra_label="Diploma"
    )

    all_results += search_table_text(
        cur,
        "artisan_programmes",
        "level, institution, programme, mean_grade, requirements",
        query,
        extra_label="Artisan"
    )

    try:
        all_results += search_table_text(
            cur,
            "skillbuilding",
            "company, programme_name, pathway, duration, cost, link",
            query,
            extra_label="SkillBuilding"
        )
    except Exception:
        print("SkillBuilding search skipped (table not present).")

    cur.close()
    conn.close()

    for label, row in all_results:
        print(f"[{label}] {row}")


if __name__ == "__main__":
    main()
