"""
scratch/precision_forensics/inspect_lost_tps_step14.py

Investigates why Variant A and Variant C lost TPs when dt_hours <= 2.5 was checked.
"""

import sys
import math
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import data.anomaly_injector as injector
from model.state import StationBuffer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

all_stations_file = DATA_DIR / "all_stations.csv"
df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp").reset_index(drop=True)
cutoff_idx = int(len(df) * 0.7)
df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

# Run seed 42 injection
injected_frames = []
for station_id, group in df_test_raw.groupby("station_id", sort=False):
    injected_frames.append(injector.inject_anomalies(group.copy(), seed=42))
eval_df = pd.concat(injected_frames, ignore_index=True)
eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

station_ids = eval_df["station_id"].unique()
buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

print("=" * 80)
print("INSPECTING dt DISTRIBUTION FOR TRUE ANOMALIES IN TEST SET")
print("=" * 80)

dt_anomalies = []
dt_normals = []

for row_idx, row in eval_df.iterrows():
    st_id = row["station_id"]
    ts = row["timestamp"]
    gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
    ftype = row.get("fault_type", "normal") if gt else "normal"

    buf = buffers[st_id]
    hist_df = buf.raw_history_df()

    prior_time = None
    if not hist_df.empty and "timestamp" in hist_df.columns:
        valid_ts = pd.to_datetime(hist_df["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]

    dt_hours = (ts - prior_time).total_seconds() / 3600.0 if prior_time is not None else np.nan

    raw_reading = {
        "station_id": st_id, "timestamp": ts,
        "temperature_c": row["temperature_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"],
    }
    buf.record_raw_reading(raw_reading, timestamp=ts, verdict={"is_anomaly": False})

    if gt:
        dt_anomalies.append({"station": st_id, "timestamp": ts, "fault_type": ftype, "dt": dt_hours})
    else:
        dt_normals.append({"station": st_id, "timestamp": ts, "dt": dt_hours})

df_anom_dt = pd.DataFrame(dt_anomalies)
df_norm_dt = pd.DataFrame(dt_normals)

print(f"Total Anomaly Points: {len(df_anom_dt)}")
print("Anomaly dt quantiles:")
print(df_anom_dt["dt"].describe())

print("\nAnomaly dt buckets:")
print(pd.cut(df_anom_dt["dt"], bins=[-1, 0.5, 1.5, 2.5, 6.0, 24.0, 1000.0]).value_counts(sort=False))

print("\nNormal dt quantiles:")
print(df_norm_dt["dt"].describe())

print("\nNormal dt buckets:")
print(pd.cut(df_norm_dt["dt"], bins=[-1, 0.5, 1.5, 2.5, 6.0, 24.0, 1000.0]).value_counts(sort=False))
