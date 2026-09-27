import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("TIMESCALE_URL", "postgresql://postgres:postgres@localhost:5432/skyguard")
try:
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM sensor_readings
            WHERE source = 'live' AND (temperature_c < -10 OR temperature_c > 60 OR fault_type = 'sensor_fail_low' OR fault_type = 'physical_bounds');
        """)
        deleted = cur.rowcount
        conn.commit()
    conn.close()
    print(f"Deleted {deleted} test injection rows from TimescaleDB sensor_readings table.")
except Exception as e:
    print("DB error:", e)
