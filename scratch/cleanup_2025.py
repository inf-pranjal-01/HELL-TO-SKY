import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("DATABASE_URL")
if db_url:
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_readings WHERE EXTRACT(YEAR FROM time) <= 2025;")
        deleted = cur.rowcount
        cur.execute("SELECT COUNT(*), MIN(time), MAX(time) FROM sensor_readings;")
        total, min_t, max_t = cur.fetchone()
    conn.commit()
    conn.close()
    print(f"Purged {deleted} legacy 2025 rows. DB now has {total} rows from {min_t} to {max_t}.")
else:
    print("No DB URL")
