import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.anomaly_injector import inject_anomalies, RANDOM_SEED

DATA_DIR = PROJECT_ROOT / "data"

def regenerate_all():
    station_files = sorted(p for p in DATA_DIR.glob("AWS-*.csv") if "_labeled" not in p.name and "_esp32" not in p.name)
    print(f"Found {len(station_files)} raw station files to regenerate.")
    
    # Regional cluster centers that receive faults
    CENTER_STATION_IDS = {
        "AWS-DEL-011", "AWS-CHN-024", "AWS-MUM-007", "AWS-KOL-015",
        "AWS-BHO-030", "AWS-RAN-067", "AWS-VAR-052",
    }
    
    total_injected_rows = 0
    total_clean_rows = 0
    
    for i, csv_path in enumerate(station_files):
        df_raw = pd.read_csv(csv_path, parse_dates=["timestamp"])
        sid = csv_path.stem
        out_path = DATA_DIR / f"{sid}_labeled.csv"
        
        if sid in CENTER_STATION_IDS:
            seed = RANDOM_SEED + i * 10007
            df_injected, events = inject_anomalies(df_raw, seed=seed, return_events=True)
            df_injected.to_csv(out_path, index=False)
            n_anom = int(df_injected["is_anomaly"].sum())
            total_injected_rows += n_anom
            total_clean_rows += len(df_injected) - n_anom
            print(f"[{sid}] Injected {n_anom} anomalous rows across {len(events)} events -> {out_path.name}")
        else:
            # Sibling peer station: clean baseline with no injected faults
            df_clean = df_raw.copy()
            df_clean["is_anomaly"] = False
            df_clean["fault_type"] = "none"
            df_clean.to_csv(out_path, index=False)
            total_clean_rows += len(df_clean)
            print(f"[{sid}] Clean sibling peer baseline -> {out_path.name}")
            
    print(f"\nRegeneration Complete: {total_injected_rows} anomalous rows, {total_clean_rows} clean rows.")

if __name__ == "__main__":
    regenerate_all()
