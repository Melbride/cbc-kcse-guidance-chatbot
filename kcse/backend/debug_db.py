import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def check_database():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cur = conn.cursor()
        
        # Check if tables exist and have data
        tables = ["degree_cutoffs", "diploma_programs", "artisan_programmes", "skillbuilding"]
        
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"{table}: {count} records")
                
                if count > 0:
                    cur.execute(f"SELECT * FROM {table} LIMIT 2")
                    rows = cur.fetchall()
                    print(f"  Sample data: {rows}")
                    
                    # Check if embedding column exists
                    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND column_name = 'embedding'")
                    embedding_exists = cur.fetchone()
                    print(f"  Has embedding column: {bool(embedding_exists)}")
                    
            except Exception as e:
                print(f"{table}: Error - {e}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Database connection error: {e}")

if __name__ == "__main__":
    check_database()
