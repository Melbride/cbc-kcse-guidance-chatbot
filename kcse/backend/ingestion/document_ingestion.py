import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

#Load environment variables
load_dotenv()
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def main():
    # Uncomment when you are ready to reload the cleaned enriched degree dataset.
    # ingest_degree_cutoffs()

    # Ingest Diploma programs
    ingest_diploma_programs()
    # Ingest Artisan Programmes
    ingest_artisan_programmes()
    # Ingest SkillBuilding
    ingest_skillbuilding()


def get_data_path(filename):
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", filename))


def get_table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [row[0] for row in cur.fetchall()]


def ingest_degree_cutoffs(filename="DEGREE_CUTOFFS_ENRICHED_CLEAN.xlsx", replace_existing=False):
    excel_path = get_data_path(filename)
    df = pd.read_excel(excel_path)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df = df.where(pd.notna(df), None)
    print("Degree columns from file:", df.columns.tolist())

    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cur = conn.cursor()

    table_columns = get_table_columns(cur, "degree_cutoffs")
    insert_columns = [column for column in df.columns if column in table_columns]
    if not insert_columns:
        cur.close()
        conn.close()
        raise RuntimeError("No matching columns found between the cleaned degree file and degree_cutoffs table.")

    if replace_existing:
        cur.execute("DELETE FROM degree_cutoffs")

    placeholders = ", ".join(["%s"] * len(insert_columns))
    insert_sql = f"""
        INSERT INTO degree_cutoffs ({", ".join(insert_columns)})
        VALUES ({placeholders})
    """

    for _, row in df.iterrows():
        values = [row[column] for column in insert_columns]
        cur.execute(insert_sql, values)

    conn.commit()
    cur.close()
    conn.close()
    print(f"Degree cutoffs ingestion complete from {filename} using columns: {insert_columns}")


def ingest_skillbuilding():
    # Path to SkillBuilding Excel file
    excel_path = get_data_path("SkillBuilding.xlsx")
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    print("SkillBuilding columns:", df.columns.tolist())

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cur = conn.cursor()

    for idx, row in df.iterrows():
        cur.execute("""
            INSERT INTO skillbuilding (
                company, programme_name, pathway, duration, cost, link
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            row['Company'], row['Programme Name'], row['Pathway'],
            row['Duration'], row['Cost'], row['Link']
        ))

    conn.commit()
    cur.close()
    conn.close()
    print("SkillBuilding ingestion complete!")
def ingest_artisan_programmes():
    # Path to Artisan Programmes Excel file
    excel_path = get_data_path("Artisan Programmes.xlsx")
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    print("Artisan columns:", df.columns.tolist())

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cur = conn.cursor()

    for idx, row in df.iterrows():
        cur.execute("""
            INSERT INTO artisan_programmes (
                level, institution, programme, mean_grade, requirements
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            row['Level'], row['Institution'], row['Programme'],
            row['Mean Grade'], row['Requirements']
        ))

    conn.commit()
    cur.close()
    conn.close()
    print("Artisan programmes ingestion complete!")

def ingest_diploma_programs():
    # Path to Diploma programs Excel file
    excel_path = get_data_path("Diploma Programmes.xlsx")
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    print("Diploma columns:", df.columns.tolist())

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cur = conn.cursor()

    for idx, row in df.iterrows():
        cur.execute("""
            INSERT INTO diploma_programs (
                programme_code, institution_name, programme_name, mean_grade, subject_requirements
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            row['Programme Code'], row['Institution Name'], row['Programme Name'],
            row['Mean Grade'], row['Subject Requirements']
        ))

    conn.commit()
    cur.close()
    conn.close()
    print("Diploma programs ingestion complete!")

if __name__ == "__main__":
    main()



