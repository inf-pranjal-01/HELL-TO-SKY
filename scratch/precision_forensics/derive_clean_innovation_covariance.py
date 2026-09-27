"""
scratch/precision_forensics/derive_clean_innovation_covariance.py

Step 18: Computes the empirical 3D instantaneous innovation covariance and correlation matrix
from strictly clean historical training data (first 70% of all_stations.csv).
Channel ordering: [temperature_c, pressure_hpa, humidity_pct].
Audits:
- Positive definiteness
- Condition number
- Eigenvalues
- Channel correlations for consecutive steps (dt = 1h)
"""

import sys
import math
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from model.uncertainty_budget import SENSOR_QUANTIZATION_FLOORS

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]

def main():
    print("=" * 80)
    print("STEP 18: CLEAN INSTANTANEOUS INNOVATION COVARIANCE DERIVATION")
    print("=" * 80)

    df_raw = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"], utc=True)
    df_raw = df_raw.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    cutoff = int(len(df_raw) * 0.70)
    df_train = df_raw.iloc[:cutoff].copy().reset_index(drop=True)
    print(f"Training observations: {len(df_train)} across {df_train['station_id'].nunique()} stations.")

    # Compute consecutive step differences per station (dt = 1h strictly within station boundary)
    diff_records = []
    for st_id, grp in df_train.groupby("station_id"):
        grp = grp.sort_values("timestamp")
        # Check consecutive dt
        dt_s = grp["timestamp"].diff().dt.total_seconds() / 3600.0
        
        dy_t = grp["temperature_c"].diff()
        dy_p = grp["pressure_hpa"].diff()
        dy_h = grp["humidity_pct"].diff()

        for idx in range(1, len(grp)):
            if dt_s.iloc[idx] == 1.0:  # Exactly consecutive 1-hour step
                diff_records.append({
                    "station_id": st_id,
                    "temperature_c": dy_t.iloc[idx],
                    "pressure_hpa": dy_p.iloc[idx],
                    "humidity_pct": dy_h.iloc[idx],
                })

    df_diffs = pd.DataFrame(diff_records).dropna()
    print(f"Total clean consecutive 1-hour transitions: {len(df_diffs)}")

    # Raw Covariance Matrix
    cov_raw = df_diffs[PARAMS].cov().values
    corr_raw = df_diffs[PARAMS].corr().values

    print("\n--- EMPIRICAL INSTANTANEOUS CORRELATION MATRIX (Clean Data) ---")
    corr_df = pd.DataFrame(corr_raw, index=PARAMS, columns=PARAMS)
    print(corr_df.to_string())

    print("\n--- EMPIRICAL INSTANTANEOUS COVARIANCE MATRIX (Clean Data) ---")
    cov_df = pd.DataFrame(cov_raw, index=PARAMS, columns=PARAMS)
    print(cov_df.to_string())

    # Standardized Innovation Matrix (normalizing each channel by sigma_jump at dt = 1h)
    sigma_jumps = np.array([
        math.sqrt(2.0 * (SENSOR_QUANTIZATION_FLOORS[p]**2) + (SENSOR_QUANTIZATION_FLOORS[p]**2) * 1.0)
        for p in PARAMS
    ])
    print(f"\nTheoretical Sensor Jump Sigmas (dt=1h): T={sigma_jumps[0]:.4f}, P={sigma_jumps[1]:.4f}, H={sigma_jumps[2]:.4f}")

    # Eigenvalues and Condition Number of Correlation Matrix
    eigenvals = np.linalg.eigvalsh(corr_raw)
    cond_num = np.linalg.cond(corr_raw)
    print(f"\nCorrelation Matrix Eigenvalues: {eigenvals}")
    print(f"Is Positive Definite? {np.all(eigenvals > 0)}")
    print(f"Condition Number: {cond_num:.4f}")

    # Compare with the existing DEFAULT_CORRELATION_MATRIX in cross_channel_covariance.py
    # Existing was: [[1.00, -0.25, -0.65], [-0.25, 1.00, 0.15], [-0.65, 0.15, 1.00]]
    corr_df.to_csv(OUTPUT_DIR / "step18_clean_instantaneous_correlation.csv")
    cov_df.to_csv(OUTPUT_DIR / "step18_clean_instantaneous_covariance.csv")


if __name__ == "__main__":
    main()
