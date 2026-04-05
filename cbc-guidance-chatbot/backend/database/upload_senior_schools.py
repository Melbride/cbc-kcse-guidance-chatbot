import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "cbc_chatbot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_PORT = os.getenv("DB_PORT", "5432")

EXCEL_PATH = r"C:/Users/VORN/Desktop/BDS/Project proposal/cbc-kcse-guidance-chatbot/documents/cbc/subject_combinations/kenya_senior_schools_pathways.xlsx"

conn = psycopg2.connect(
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    port=DB_PORT
)
cur = conn.cursor()

df = pd.read_excel(EXCEL_PATH)

for _, row in df.iterrows():
    cur.execute("""
        INSERT INTO kenya_senior_schools_pathways (
            region, county, sub_county, knec_code, school_name, cluster, type,
            accomodation, gender, pathway_type, pathways_offered, combo_pathway,
            combo_track, subject_1, subject_2, subject_3
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        row.get('REGION'),
        row.get('COUNTY'),
        row.get('SUB-COUNTY'),
        str(row.get('KNEC CODE')),
        row.get('SCHOOL NAME'),
        row.get('CLUSTER'),
        row.get('TYPE'),
        row.get('ACCOMMODATION'),
        row.get('GENDER'),
        row.get('PATHWAY TYPE'),
        row.get('PATHWAYS OFFERED'),
        row.get('COMBO PATHWAY'),
        row.get('COMBO TRACK'),
        row.get('SUBJECT 1'),
        row.get('SUBJECT 2'),
        row.get('SUBJECT 3'),
    ))

conn.commit()
cur.close()
conn.close()
print("Ingestion complete.")