import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

EXCEL_PATH = r"C:/Users/VORN/Desktop/BDS/Project proposal/cbc-kcse-guidance-chatbot/cbc-guidance-chatbot/documents/cbc/subject_combinations/kenya_senior_schools_pathways.xlsx"

print(f"Connecting to database with:")
print(f"Host: {DB_HOST}")
print(f"Database: {DB_NAME}")
print(f"User: {DB_USER}")
print(f"Port: {DB_PORT}")

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
    )
    print("Database connection successful!")
except Exception as e:
    print(f"Database connection failed: {e}")
    exit(1)

cur = conn.cursor()

df = pd.read_excel(EXCEL_PATH)
df = df.fillna("")  # IMPORTANT FIX

for _, row in df.iterrows():
    try:
        knec_code = row.get("KNEC CODE")
        knec_code = "" if pd.isna(knec_code) else str(knec_code)

        cur.execute("""
            INSERT INTO kenya_senior_schools_pathways (
                region, county, sub_county, knec_code, school_name, cluster, type,
                accomodation, gender, pathway_type, pathways_offered, combo_pathway,
                combo_track, subject_1, subject_2, subject_3
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            row.get("REGION"),
            row.get("COUNTY"),
            row.get("SUB-COUNTY"),
            knec_code,
            row.get("SCHOOL NAME"),
            row.get("CLUSTER"),
            row.get("TYPE"),
            row.get("ACCOMMODATION"),
            row.get("GENDER"),
            row.get("PATHWAY TYPE"),
            row.get("PATHWAYS OFFERED"),
            row.get("COMBO PATHWAY"),
            row.get("COMBO TRACK"),
            row.get("SUBJECT 1"),
            row.get("SUBJECT 2"),
            row.get("SUBJECT 3"),
        ))

    except Exception as e:
        print("Error on row:", e)

conn.commit()
cur.close()
conn.close()

print("Ingestion complete.")
