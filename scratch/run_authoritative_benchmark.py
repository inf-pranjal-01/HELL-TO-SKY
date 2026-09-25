"""
scratch/run_authoritative_benchmark.py

Path 2 — Authoritative Benchmark Runner.
Executes the locked benchmark protocol strictly ONCE across the 7 predetermined seeds:
[42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]

Strict causality:
- Evaluates strictly chronologically on the held-out test split (last 30% of historical data).
- Station state updated causally (clean observations to trusted buffer; anomalies quarantined).
- Ground truth is completely hidden from detection inference.
- Exact pooled row metrics & episodic evaluation metrics.
"""

import sys
from pathlib import Path
import time
import json
import joblib
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

from model.detect import score_reading, PARAMS
from model.state import StationBuffer
from model.features import build_features_for_history
from model.peer_spatial_engine import PeerSpatialEngine
import data.anomaly_injector as injector
from evaluation.benchmark_contract import pooled_row_metrics, episodic_metrics

DATA_DIR = Path(__file__).parent.parent / "data"
ARTIFACTS_DIR = Path(__file__).parent.parent / "model_artifacts"
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]


def load_test_split():
    stations_path = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(stations_path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Use the 30% chronological held-out test split (after cutoff)
    cutoff_idx = int(len(df) * 0.7)
    cutoff_date = df.iloc[cutoff_idx]["timestamp"]
    test_df = df[df["timestamp"] >= cutoff_date].copy().reset_index(drop=True)
    return test_df, cutoff_date


def run_single_seed_benchmark(test_raw_df: pd.DataFrame, seed: int, artifact: dict):
    # 1. Inject low-stress anomalies into test slice
    injected_frames = []
    all_events = []
    
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        group_injected, events = injector.inject_anomalies(group.copy(), seed=seed, return_events=True)
        injected_frames.append(group_injected)
        for _, ev in events.iterrows():
            ev_dict = ev.to_dict()
            ev_dict["station_id"] = station_id
            all_events.append(ev_dict)
            
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)
    
    # 2. Initialize causal station buffers for all stations
    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    
    predictions = []
    pred_fault_types = []
    pred_events = []
    active_episodes = {st_id: {} for st_id in station_ids}  # param -> episode tracker
    
    # 3. Stream chronologically through all readings
    # Pre-extract values for high execution throughput
    rows = eval_df.to_dict("records")
    n_rows = len(rows)
    
    for i, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        buf = buffers[st_id]
        
        # Build neighbor buffers for spatial peer consensus (strictly 3 cluster siblings)
        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
        
        # History DataFrame from trusted physical buffer
        hist_df = buf.raw_history_df()
        
        # Strict Causal Inference (zero future information / zero ground-truth leakage)
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
        
        is_pred_anom = bool(verdict["is_anomaly"])
        pred_fault = verdict.get("fault_type")
        
        predictions.append(is_pred_anom)
        pred_fault_types.append(pred_fault)
        
        # Causal State Update
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)
        
        # Track continuous episodic events
        faulty_sensors = verdict.get("likely_faulty_sensors", [])
        for p in PARAMS:
            if is_pred_anom and (p in faulty_sensors or "multivariate" in str(pred_fault)):
                if p not in active_episodes[st_id]:
                    active_episodes[st_id][p] = {
                        "station_id": st_id,
                        "fault_type": pred_fault,
                        "parameters": [p],
                        "start_timestamp": ts,
                        "end_timestamp": ts,
                        "first_detect_timestamp": ts,
                    }
                else:
                    active_episodes[st_id][p]["end_timestamp"] = ts
            else:
                if p in active_episodes[st_id]:
                    # Episode closure
                    pred_events.append(active_episodes[st_id][p])
                    del active_episodes[st_id][p]
                    
    # Flush remaining active episodes
    for st_id in station_ids:
        for p, ev in active_episodes[st_id].items():
            pred_events.append(ev)
            
    # 4. Compute Metrics
    ground_truth = eval_df["is_anomaly"].fillna(False).astype(bool).tolist()
    gt_fault_types = eval_df["fault_type"].fillna("").tolist()
    
    # Pooled row metrics
    row_metrics = pooled_row_metrics(ground_truth, predictions)
    
    # Fault-wise breakdown
    fault_categories = ["spike", "frozen_value", "drift", "multivariate_inconsistency", "sensor_fail_low", "dropout"]
    fault_breakdown = {}
    
    for ftype in fault_categories:
        mask = [gt == ftype for gt in gt_fault_types]
        if sum(mask) > 0:
            tp_f = sum(p and m for p, m in zip(predictions, mask))
            fn_f = sum((not p) and m for p, m in zip(predictions, mask))
            rec_f = tp_f / (tp_f + fn_f) if (tp_f + fn_f) > 0 else 0.0
            fault_breakdown[ftype] = {
                "total_rows": sum(mask),
                "tp": tp_f,
                "fn": fn_f,
                "recall": rec_f
            }
            
    # Episodic metrics for drift & frozen
    drift_episodic = episodic_metrics(all_events, pred_events, "drift")
    frozen_episodic = episodic_metrics(all_events, pred_events, "frozen_value")
    
    return {
        "seed": seed,
        "row_metrics": row_metrics,
        "fault_breakdown": fault_breakdown,
        "drift_episodic": drift_episodic,
        "frozen_episodic": frozen_episodic,
        "pred_events": pred_events[:10],
        "true_events": all_events[:10]
    }


def main():
    print("==================================================================", flush=True)
    print("PATH 2 AUTHORITATIVE BENCHMARK EXECUTION", flush=True)
    print("==================================================================", flush=True)
    
    artifact_path = ARTIFACTS_DIR / "isolation_forest.pkl"
    assert artifact_path.exists(), "Model artifact missing"
    artifact = joblib.load(artifact_path)
    
    test_raw_df, cutoff_date = load_test_split()
    print(f"Loaded held-out test split: {len(test_raw_df)} rows from {cutoff_date} across 28 stations.\n", flush=True)
    
    seed_results = []
    
    start_time = time.time()
    for seed in SEEDS:
        t0 = time.time()
        print(f"--- Running Benchmark Seed: {seed} ---", flush=True)
        res = run_single_seed_benchmark(test_raw_df, seed, artifact)
        dt = time.time() - t0
        rm = res["row_metrics"]
        print(f"Seed {seed:12d} | Precision: {rm['precision']*100:6.2f}% | Recall: {rm['recall']*100:6.2f}% | F1: {rm['f1']*100:6.2f}% | Time: {dt:.1f}s", flush=True)
        seed_results.append(res)
        
    total_time = time.time() - start_time
    
    # Aggregate Metrics
    precisions = [r["row_metrics"]["precision"] for r in seed_results]
    recalls = [r["row_metrics"]["recall"] for r in seed_results]
    f1s = [r["row_metrics"]["f1"] for r in seed_results]
    
    print("\n==================================================================", flush=True)
    print("AGGREGATE BENCHMARK RESULTS (7 SEEDS)", flush=True)
    print("==================================================================", flush=True)
    print(f"Mean Precision : {np.mean(precisions)*100:6.2f}%  (std: {np.std(precisions)*100:4.2f}%)", flush=True)
    print(f"Mean Recall    : {np.mean(recalls)*100:6.2f}%  (std: {np.std(recalls)*100:4.2f}%)", flush=True)
    print(f"Mean F1 Score  : {np.mean(f1s)*100:6.2f}%  (std: {np.std(f1s)*100:4.2f}%)", flush=True)
    print(f"Total Runtime  : {total_time:.1f}s", flush=True)
    print("==================================================================", flush=True)
    
    # Save benchmark summary
    out_summary = {
        "seeds": SEEDS,
        "mean_precision": float(np.mean(precisions)),
        "std_precision": float(np.std(precisions)),
        "mean_recall": float(np.mean(recalls)),
        "std_recall": float(np.std(recalls)),
        "mean_f1": float(np.mean(f1s)),
        "std_f1": float(np.std(f1s)),
        "seed_details": seed_results
    }
    
    out_path = ARTIFACTS_DIR / "authoritative_benchmark_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_summary, f, indent=2, default=str)
    print(f"Saved full benchmark results -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
