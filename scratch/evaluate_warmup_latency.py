"""
scratch/evaluate_warmup_latency.py

Evaluates the exact empirical relationship between StationBuffer warmup duration
(number of history hours before evaluation) and detection metrics (Precision, Recall, F1).
Runs across the authoritative held-out test split over 7 seeds.
"""

import sys
import time
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

sys.path.append(str(Path(__file__).parent.parent))

from model.detect import score_reading, PARAMS
from model.state import StationBuffer
from model.peer_spatial_engine import PeerSpatialEngine
import data.anomaly_injector as injector
from evaluation.benchmark_contract import pooled_row_metrics

DATA_DIR = Path(__file__).parent.parent / "data"
ARTIFACTS_DIR = Path(__file__).parent.parent / "model_artifacts"
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
WARMUP_HORIZONS = [0, 1, 3, 6, 12, 24]  # in hours / readings


def load_test_split():
    stations_path = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(stations_path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    cutoff_date = df.iloc[cutoff_idx]["timestamp"]
    test_df = df[df["timestamp"] >= cutoff_date].copy().reset_index(drop=True)
    return test_df, cutoff_date


def evaluate_warmup_horizons():
    artifact = joblib.load(ARTIFACTS_DIR / "isolation_forest.pkl")
    test_raw_df, cutoff_date = load_test_split()
    
    results_by_horizon = {h: {"precisions": [], "recalls": [], "f1s": []} for h in WARMUP_HORIZONS}
    
    print("=" * 70)
    print("WARM-UP HORIZON EMPIRICAL DATA REPORT")
    print(f"Evaluating across 7 seeds and 28 stations (Test split: {len(test_raw_df)} readings)")
    print("=" * 70)
    
    t0_all = time.time()
    
    for seed in SEEDS:
        injected_frames = []
        for station_id, group in test_raw_df.groupby("station_id", sort=False):
            group_injected = injector.inject_anomalies(group.copy(), seed=seed, return_events=False)
            injected_frames.append(group_injected)
            
        eval_df = pd.concat(injected_frames, ignore_index=True)
        eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
        eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)
        
        station_ids = eval_df["station_id"].unique()
        buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
        
        # Track station reading counts
        st_reading_counts = {st_id: 0 for st_id in station_ids}
        
        # Collect predictions partitioned by station warmup age at moment of inference
        horizon_preds = {h: [] for h in WARMUP_HORIZONS}
        horizon_truths = {h: [] for h in WARMUP_HORIZONS}
        
        rows = eval_df.to_dict("records")
        for row in rows:
            st_id = row["station_id"]
            ts = row["timestamp"]
            buf = buffers[st_id]
            
            sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
            neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
            hist_df = buf.raw_history_df()
            
            raw_reading = {
                "station_id": st_id,
                "timestamp": ts,
                "temperature_c": row["temperature_c"],
                "pressure_hpa": row["pressure_hpa"],
                "humidity_pct": row["humidity_pct"],
            }
            
            verdict = score_reading(
                raw_reading=raw_reading,
                history_df=hist_df,
                artifact=artifact,
                neighbor_buffers=neighbor_bufs
            )
            
            is_pred = bool(verdict["is_anomaly"])
            is_true = bool(row.get("is_anomaly", False))
            
            age = st_reading_counts[st_id]
            for h in WARMUP_HORIZONS:
                if age >= h:
                    horizon_preds[h].append(is_pred)
                    horizon_truths[h].append(is_true)
                    
            buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)
            st_reading_counts[st_id] += 1
            
        # Compute metrics per horizon for this seed
        for h in WARMUP_HORIZONS:
            m = pooled_row_metrics(horizon_truths[h], horizon_preds[h])
            results_by_horizon[h]["precisions"].append(m["precision"])
            results_by_horizon[h]["recalls"].append(m["recall"])
            results_by_horizon[h]["f1s"].append(m["f1"])
            
    total_time = time.time() - t0_all
    
    print(f"\nCompleted in {total_time:.1f}s\n")
    print(f"{'Warmup Age':<18} | {'Mean Precision':<16} | {'Mean Recall':<16} | {'Mean F1':<14} | {'Notes'}")
    print("-" * 85)
    
    summary_table = []
    for h in WARMUP_HORIZONS:
        p_mean = np.mean(results_by_horizon[h]["precisions"]) * 100
        p_std = np.std(results_by_horizon[h]["precisions"]) * 100
        r_mean = np.mean(results_by_horizon[h]["recalls"]) * 100
        r_std = np.std(results_by_horizon[h]["recalls"]) * 100
        f1_mean = np.mean(results_by_horizon[h]["f1s"]) * 100
        f1_std = np.std(results_by_horizon[h]["f1s"]) * 100
        
        note = "Cold-start (all readings)" if h == 0 else f"After {h}h active history"
        print(f"{h:>2} hours ({h:>2} readings) | {p_mean:6.2f}% ± {p_std:4.2f}% | {r_mean:6.2f}% ± {r_std:4.2f}% | {f1_mean:6.2f}% ± {f1_std:4.2f}% | {note}")
        
        summary_table.append({
            "warmup_hours": h,
            "precision_mean": round(p_mean, 2),
            "precision_std": round(p_std, 2),
            "recall_mean": round(r_mean, 2),
            "recall_std": round(r_std, 2),
            "f1_mean": round(f1_mean, 2),
            "f1_std": round(f1_std, 2),
            "note": note
        })
        
    out_path = ARTIFACTS_DIR / "warmup_latency_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary_table, f, indent=2)
        
    print(f"\nDetailed report saved -> {out_path}")


if __name__ == "__main__":
    evaluate_warmup_horizons()
