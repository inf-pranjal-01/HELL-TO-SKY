"""
scratch/precision_forensics/study_clean_gap_variance.py

Step 15 Empirical Gap Variance Model Study.
Estimates Var(Δy | Δt) directly from clean training data (first 70% of all_stations.csv).
Analyzes:
1. Empirical scaling of Var(Δy | Δt) vs Δt for Temperature, Pressure, Humidity.
2. Functional form: linear in dt, sqrt(dt), power law, or non-parametric.
3. Cadence distribution per station.
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
    print("STEP 15: CLEAN TELEMETRY GAP VARIANCE STUDY")
    print("=" * 80)

    df_raw = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"], utc=True)
    df_raw = df_raw.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    # Use strictly clean training split (first 70%)
    cutoff = int(len(df_raw) * 0.70)
    df_train = df_raw.iloc[:cutoff].copy().reset_index(drop=True)
    print(f"Training observations: {len(df_train)} across {df_train['station_id'].nunique()} stations.")

    # 1. Auditing inter-arrival cadence per station
    station_cadences = []
    for st_id, grp in df_train.groupby("station_id"):
        grp = grp.sort_values("timestamp")
        dt_vals = grp["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
        station_cadences.append({
            "station_id": st_id,
            "median_dt": dt_vals.median(),
            "mad_dt": (dt_vals - dt_vals.median()).abs().median(),
            "p90_dt": dt_vals.quantile(0.90),
            "p95_dt": dt_vals.quantile(0.95),
            "p99_dt": dt_vals.quantile(0.99),
            "max_dt": dt_vals.max(),
            "total_records": len(grp)
        })
    df_cadence = pd.DataFrame(station_cadences)
    print("\n--- PER-STATION CADENCE SUMMARY ---")
    print(df_cadence.to_string(index=False))
    df_cadence.to_csv(OUTPUT_DIR / "step15_station_cadence_summary.csv", index=False)

    # 2. Extracting delta y across various lag horizons (dt = 1h to 72h) from clean history
    clean_lags = []
    lags_hours = [1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 48, 72]

    for st_id, grp in df_train.groupby("station_id"):
        grp = grp.sort_values("timestamp").set_index("timestamp")
        # Ensure regular resampling or forward differences
        for lag_h in lags_hours:
            # Shift by lag_h
            shifted = grp[PARAMS].shift(lag_h)
            diffs = (grp[PARAMS] - shifted).dropna()
            for p in PARAMS:
                vals = diffs[p].values
                clean_lags.append({
                    "station_id": st_id,
                    "channel": p,
                    "dt_hours": lag_h,
                    "std_delta": np.std(vals),
                    "mad_delta": np.median(np.abs(vals - np.median(vals))) * 1.4826,
                    "var_delta": np.var(vals),
                    "p95_abs_delta": np.percentile(np.abs(vals), 95),
                    "p99_abs_delta": np.percentile(np.abs(vals), 99),
                    "count": len(vals)
                })

    df_lags = pd.DataFrame(clean_lags)
    # Aggregate across stations per channel and dt
    agg_lags = df_lags.groupby(["channel", "dt_hours"]).agg({
        "std_delta": "mean",
        "mad_delta": "mean",
        "var_delta": "mean",
        "p95_abs_delta": "mean",
        "p99_abs_delta": "mean"
    }).reset_index()

    print("\n--- EMPIRICAL CLEAN TRANSITION DISPERSION vs ELAPSED TIME (dt) ---")
    print(agg_lags.to_string(index=False))
    agg_lags.to_csv(OUTPUT_DIR / "step15_empirical_gap_dispersion.csv", index=False)

    # Fit scaling models:
    # Var(dy | dt) = 2*sigma_floor^2 + sigma_rate^2 * (dt)^gamma
    print("\n--- ESTIMATED EMPIRICAL PROCESS RATES PER CHANNEL ---")
    rate_models = []
    for p in PARAMS:
        floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
        sub = agg_lags[agg_lags["channel"] == p]
        dt = sub["dt_hours"].values
        var_obs = sub["var_delta"].values
        
        # Fit linear diffusion: Var = 2*floor^2 + beta * dt
        y_adj = np.maximum(0, var_obs - 2 * (floor**2))
        beta, _ = np.polyfit(dt, y_adj, 1)
        sigma_rate = math.sqrt(max(1e-6, beta))

        # Check sublinear fit: Var = 2*floor^2 + beta_sub * sqrt(dt)
        beta_sqrt, _ = np.polyfit(np.sqrt(dt), y_adj, 1)

        rate_models.append({
            "channel": p,
            "sensor_floor": floor,
            "2_floor_sq": 2 * (floor**2),
            "linear_rate_beta": beta,
            "sigma_rate_per_sqrt_hr": sigma_rate,
            "sqrt_rate_beta": beta_sqrt,
            "1h_std": sub[sub["dt_hours"] == 1]["std_delta"].values[0],
            "24h_std": sub[sub["dt_hours"] == 24]["std_delta"].values[0],
        })

    df_rates = pd.DataFrame(rate_models)
    print(df_rates.to_string(index=False))
    df_rates.to_csv(OUTPUT_DIR / "step15_channel_rate_models.csv", index=False)


if __name__ == "__main__":
    main()
