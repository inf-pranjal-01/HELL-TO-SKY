"""
SkyGuard AI — Dedicated ESP32 First-Entry Anomaly Injector
----------------------------------------------------------
Injects first-entry sensor fault archetypes specifically targeted by the ESP32:
  - sensor_fail_low      : Electrical rail short / ground floor
  - frozen_value         : 1-hour continuous zero-variance physical freeze
  - impossible_jump      : Step jump discontinuity (>30°C, >50hPa, >50% RH)
  - dropout              : Missing sensor sample / NaN ADC conversion
  - physical_bounds      : Gross physical meteorological bounds violation

Operates on isolated pure CSV files in `data_esp32/` directory without affecting
the central system datasets in `data/`.
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_ESP32_DIR = ROOT_DIR / "data_esp32"

def inject_esp32_faults(df: pd.DataFrame, seed: int = 999) -> tuple[pd.DataFrame, list]:
    rng = np.random.default_rng(seed)
    df_out = df.copy()
    
    if "is_anomaly" not in df_out.columns:
        df_out["is_anomaly"] = False
    if "fault_type" not in df_out.columns:
        df_out["fault_type"] = None

    n_rows = len(df_out)
    events = []

    # 1. Inject sensor_fail_low (10 episodes of 3 rows)
    for _ in range(10):
        start_idx = rng.integers(10, n_rows - 20)
        param = rng.choice(["temperature_c", "pressure_hpa", "humidity_pct"])
        fail_val = -35.0 if param == "temperature_c" else (150.0 if param == "pressure_hpa" else 0.0)
        
        for i in range(3):
            idx = start_idx + i
            df_out.loc[idx, param] = fail_val
            df_out.loc[idx, "is_anomaly"] = True
            df_out.loc[idx, "fault_type"] = "sensor_fail_low"
        
        events.append({
            "fault_type": "sensor_fail_low",
            "parameter": param,
            "start_idx": start_idx,
            "end_idx": start_idx + 2
        })

    # 2. Inject frozen_value (5 episodes of 3600s / 180 rows assuming 20s/60s steps)
    for _ in range(5):
        start_idx = rng.integers(50, n_rows - 60)
        freeze_t = df_out.loc[start_idx, "temperature_c"]
        freeze_p = df_out.loc[start_idx, "pressure_hpa"]
        freeze_h = df_out.loc[start_idx, "humidity_pct"]

        # Freeze for 30 consecutive readings (simulated long freeze)
        for i in range(30):
            idx = start_idx + i
            df_out.loc[idx, "temperature_c"] = freeze_t
            df_out.loc[idx, "pressure_hpa"] = freeze_p
            df_out.loc[idx, "humidity_pct"] = freeze_h
            df_out.loc[idx, "is_anomaly"] = True
            df_out.loc[idx, "fault_type"] = "frozen_value"

        events.append({
            "fault_type": "frozen_value",
            "parameter": "all_sensors",
            "start_idx": start_idx,
            "end_idx": start_idx + 29
        })

    # 3. Inject impossible_jump (15 single-point transients)
    for _ in range(15):
        idx = rng.integers(10, n_rows - 10)
        param = rng.choice(["temperature_c", "pressure_hpa", "humidity_pct"])
        curr_val = df_out.loc[idx, param] if pd.notna(df_out.loc[idx, param]) else 25.0
        jump_offset = 40.0 if param == "temperature_c" else (60.0 if param == "pressure_hpa" else 55.0)
        
        df_out.loc[idx, param] = curr_val + jump_offset
        df_out.loc[idx, "is_anomaly"] = True
        df_out.loc[idx, "fault_type"] = "impossible_jump"

        events.append({
            "fault_type": "impossible_jump",
            "parameter": param,
            "start_idx": idx,
            "end_idx": idx
        })

    # 4. Inject dropout / NaN (10 single points)
    for _ in range(10):
        idx = rng.integers(10, n_rows - 10)
        param = rng.choice(["temperature_c", "pressure_hpa", "humidity_pct"])
        df_out.loc[idx, param] = np.nan
        df_out.loc[idx, "is_anomaly"] = True
        df_out.loc[idx, "fault_type"] = "dropout"

        events.append({
            "fault_type": "dropout",
            "parameter": param,
            "start_idx": idx,
            "end_idx": idx
        })

    # 5. Inject physical_bounds violation (10 single points)
    for _ in range(10):
        idx = rng.integers(10, n_rows - 10)
        param = rng.choice(["temperature_c", "pressure_hpa", "humidity_pct"])
        bound_val = 75.0 if param == "temperature_c" else (1200.0 if param == "pressure_hpa" else 115.0)
        
        df_out.loc[idx, param] = bound_val
        df_out.loc[idx, "is_anomaly"] = True
        df_out.loc[idx, "fault_type"] = "physical_bounds"

        events.append({
            "fault_type": "physical_bounds",
            "parameter": param,
            "start_idx": idx,
            "end_idx": idx
        })

    return df_out, events

def main():
    print("=" * 70)
    print("  SkyGuard AI — Dedicated ESP32 Anomaly Injector")
    print("=" * 70)

    if not DATA_ESP32_DIR.exists():
        print(f"Error: Directory {DATA_ESP32_DIR} does not exist.")
        sys.exit(1)

    raw_files = sorted([p for p in DATA_ESP32_DIR.glob("AWS-*.csv") if "_esp32_labeled" not in p.name])
    print(f"Found {len(raw_files)} pure raw CSV files in data_esp32/\n")

    for csv_file in raw_files:
        df_raw = pd.read_csv(csv_file)
        # Use station-specific seed derived from file index
        seed = 999 + raw_files.index(csv_file)
        df_injected, events = inject_esp32_faults(df_raw, seed=seed)
        
        out_name = csv_file.name.replace(".csv", "_esp32_labeled.csv")
        out_path = DATA_ESP32_DIR / out_name
        df_injected.to_csv(out_path, index=False)
        
        n_anom = df_injected["is_anomaly"].sum()
        print(f"[OK] Injected ESP32 faults into {csv_file.name} -> {out_name}")
        print(f"  Total Anomalous Rows: {n_anom} / {len(df_injected)}")
        print("  Fault Type Breakdown:")
        print(df_injected[df_injected["is_anomaly"]]["fault_type"].value_counts().to_string())
        print("-" * 50)

    print("\nSuccessfully generated dedicated ESP32 labeled CSV datasets in data_esp32/!")

if __name__ == "__main__":
    main()
