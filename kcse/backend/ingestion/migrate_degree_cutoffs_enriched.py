import os
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

from backend.results import get_db_connection


DATA_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "DEGREE_CUTOFFS_ENRICHED_CLEAN.xlsx")
)

NEW_TEXT_COLUMNS = [
    "qualification_type",
    "minimum_mean_grade",
    "subject_requirements",
    "cluster_or_points_info",
    "course_description",
    "career_paths",
    "notes",
    "source_reference",
]

INSERT_COLUMNS = [
    "prog_code",
    "institution_name",
    "programme_name",
    "cutoff_2018",
    "cutoff_2019",
    "cutoff_2020",
    "cutoff_2021",
    "cutoff_2022",
    "cutoff_2023",
    "cutoff_2024",
    "qualification_type",
    "minimum_mean_grade",
    "subject_requirements",
    "cluster_or_points_info",
    "course_description",
    "career_paths",
    "notes",
    "source_reference",
]


def load_dataset():
    df = pd.read_excel(DATA_FILE)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.where(pd.notna(df), None)
    return df


def ensure_columns(cur):
    for column in NEW_TEXT_COLUMNS:
        cur.execute(
            f"ALTER TABLE degree_cutoffs ADD COLUMN IF NOT EXISTS {column} TEXT"
        )


def backup_existing_table(cur):
    backup_name = f"degree_cutoffs_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cur.execute(f"CREATE TABLE {backup_name} AS TABLE degree_cutoffs")
    return backup_name


def migrate():
    df = load_dataset()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            backup_name = backup_existing_table(cur)
            ensure_columns(cur)
            cur.execute("DELETE FROM degree_cutoffs")

            insert_sql = f"""
                INSERT INTO degree_cutoffs ({", ".join(INSERT_COLUMNS)})
                VALUES ({", ".join(["%s"] * len(INSERT_COLUMNS))})
            """

            rows = []
            for _, row in df.iterrows():
                rows.append(tuple(row.get(column) for column in INSERT_COLUMNS))

            execute_batch(cur, insert_sql, rows, page_size=200)
            conn.commit()

    print(f"Migration complete from: {DATA_FILE}")
    print(f"Inserted rows: {len(df)}")
    print(f"Backup table created: {backup_name}")


if __name__ == "__main__":
    migrate()
