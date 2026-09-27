"""
scratch/precision_forensics/diagnose_lost_tps.py

Diagnoses the exact lost TPs in Variant C vs Step 12.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import data.anomaly_injector as injector
import model.detect as baseline_detect
from model.state import StationBuffer
from scratch.precision_forensics.run_step14_study import score_observation_step14, SEEDS, PARAMS, DATA_DIR

all_stations_file = DATA_DIR / "all_stations.csv"
df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp").reset_index(drop=True)
cutoff_idx = int(len(df) * 0.7)
df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

# Run seed 42
injected_frames = []
for station_id, group in df_test_raw.groupby("station_id", sort=False):
    injected_frames.append(injector.inject_anomalies(group.copy(), seed=42))
eval_df = pd.concat(injected_frames, ignore_index=True)
eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

station_ids = eval_df["station_id"].unique()
buffers_s12 = {st_id: StationBuffer(st_id) for st_id in station_ids}
buffers_vc = {st_id: StationBuffer(st_id) for st_id in station_ids}

lost_in_vc = []

for row_idx, row in eval_df.iterrows():
    st_id = row["station_id"]
    ts = row["timestamp"]
    gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
    ftype = row.get("fault_type", "normal") if gt else "normal"

    buf_s12 = buffers_s12[st_id]
    buf_vc = buffers_vc[st_id]

    raw_reading = {
        "station_id": st_id, "timestamp": ts,
        "temperature_c": row["temperature_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"],
    }

    res_s12 = score_observation_step14(raw_reading, buf_s12.raw_history_df(), {}, mode="step12")
    res_vc = score_observation_step14(raw_reading, buf_vc.raw_history_df(), {}, mode="variant_c")

    flag_s12 = bool(res_s12["is_anomaly"])
    flag_vc = bool(res_vc["is_anomaly"])

    buf_s12.record_raw_reading(raw_reading, timestamp=ts, verdict=res_s12)
    buf_vc.record_raw_reading(raw_reading, timestamp=ts, verdict=res_vc)

    if gt and flag_s12 and not flag_vc:
        lost_in_vc.append({
            "station": st_id, "timestamp": ts, "fault_type": ftype,
            "s12_basis": res_s12.get("decision_basis"),
            "vc_basis": res_vc.get("decision_basis"),
            "hist_len": len(buf_vc.raw_history_df()),
        })

df_lost = pd.DataFrame(lost_in_vc)
print("=" * 80)
print(f"Total TPs flagged by Step 12 but missed by Variant C on Seed 42: {len(df_lost)}")
print("=" * 80)
if not df_lost.empty:
    print("\nBreakdown by fault type:")
    print(df_lost["fault_type"].value_counts())
    print("\nSample lost TPs:")
    print(df_lost.head(20).to_string())
