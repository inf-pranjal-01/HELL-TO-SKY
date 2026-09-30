
import os
import sys
from dotenv import load_dotenv
import pandas as pd
load_dotenv()
db_url = os.environ.get("DATABASE_URL") or os.environ.get("TIMESCALE_SERVICE_URL")
if not db_url:
    print("[ERROR] DATABASE_URL is missing in .env")
    sys.exit(1)
try:
    import psycopg2
    print("Connecting to Tiger Cloud TimescaleDB...")
    conn = psycopg2.connect(db_url)
    query = 
    print("Exporting readings to CSV...")
    df = pd.read_sql_query(query, conn)
    conn.close()
    output_file = "cloud_telemetry_export.csv"
    df.to_csv(output_file, index=False)
    print("=" * 65)
    print(f"[SUCCESS] Exported {len(df)} rows to {output_file}")
    print("You can now open 'cloud_telemetry_export.csv' in Excel or VS Code!")
    print("=" * 65)
except Exception as e:
    print(f"[ERROR] Failed to export: {e}")
