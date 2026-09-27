"""
SkyGuard AI — Parallel Multi-Cluster Benchmark Engine.
Evaluates all 28 stations with live unbuffered progress and ETA estimation.
"""

from __future__ import annotations
import sys
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np

from model.detect import score_reading
from model.state import StateManager

DATA_DIR = Path("data")
ARTIFACTS_PATH = Path("model_artifacts/isolation_forest.pkl")

class _NullHistoryStore:
    def append(self, *args, **kwargs): pass
    def append_batch(self, *args, **kwargs): pass
    def get_recent(self, *args, **kwargs): return pd.DataFrame()
    def get_all(self, *args, **kwargs): return pd.DataFrame()

def _eval_single_cluster(cluster_id: str, station_ids: list[str], metadata_df: pd.DataFrame, artifact_dict: dict):
    cluster_start = time.perf_counter()
    cluster_meta = metadata_df[metadata_df["station_id"].isin(station_ids)].copy()
    frames = []
    for sid in station_ids:
        p = DATA_DIR / f"{sid}_labeled.csv"
        if p.exists():
            df = pd.read_csv(p, parse_dates=["timestamp"])
            frames.append(df)
            
    if not frames:
        return []
        
    full = pd.concat(frames, ignore_index=True)
    full["timestamp"] = pd.to_datetime(full["timestamp"], utc=True)
    full = full.sort_values(["timestamp", "station_id"]).reset_index(drop=True)
    
    manager = StateManager(cluster_meta, artifact_dict, history_store=_NullHistoryStore())
    manager.explainer = None
    
    records = []
    unique_ts = full["timestamp"].unique()
    total_ts = len(unique_ts)
    
    print(f"[{cluster_id}] Starting evaluation for {len(station_ids)} stations ({len(full):,} readings across {total_ts} timestamps)...", flush=True)
    
    step = 0
    for timestamp, group in full.groupby("timestamp", sort=True):
        step += 1
        network_snapshot = {}
        rows_to_score = []
        for row in group.to_dict("records"):
            sid = str(row["station_id"])
            raw = {k: v for k, v in row.items() if k not in ["is_anomaly", "fault_type", "episode_id", "fault_parameter", "fault_parameters", "fault_events", "__source_file"]}
            r_time = pd.to_datetime(row["timestamp"], utc=True)
            network_snapshot[sid] = (raw, r_time)
            rows_to_score.append((row, sid, raw, r_time))
            
        for row, sid, raw, r_time in rows_to_score:
            verdict = manager.ingest_reading(sid, raw, r_time, network_snapshot, include_evaluation_diagnostics=False)
            is_pred = bool(verdict.get("is_anomaly", False))
            is_gt = bool(row.get("is_anomaly", False))
            fault_gt = str(row.get("fault_type", "none") or "none")
            fault_pred = str(verdict.get("fault_type", "none") or "none")
            
            records.append({
                "station_id": sid,
                "timestamp": r_time,
                "is_gt": is_gt,
                "is_pred": is_pred,
                "fault_gt": fault_gt,
                "fault_pred": fault_pred
            })
            
        if step % 500 == 0 or step == total_ts:
            c_elapsed = time.perf_counter() - cluster_start
            c_rate = (step * len(station_ids)) / max(0.01, c_elapsed)
            c_eta = (total_ts - step) / max(1, (step / c_elapsed))
            pct = (step / total_ts) * 100
            print(f"[{cluster_id}] Progress: {pct:5.1f}% ({step}/{total_ts} ticks) | Rate: {c_rate:.0f} rows/s | ETA: {c_eta:.1f}s", flush=True)
            
    c_total_time = time.perf_counter() - cluster_start
    print(f"[{cluster_id}] COMPLETED in {c_total_time:.2f}s ({len(records):,} rows)", flush=True)
    return records

def run_benchmark():
    import joblib
    metadata = pd.read_csv(DATA_DIR / "stations_metadata.csv")
    artifact = joblib.load(ARTIFACTS_PATH) if ARTIFACTS_PATH.exists() else None
    
    clusters = {}
    for _, row in metadata.iterrows():
        clusters.setdefault(row["cluster_id"], []).append(row["station_id"])
        
    print(f"[BENCHMARK] Starting Parallel Multi-Cluster Benchmark across {len(clusters)} clusters ({len(metadata)} stations)...", flush=True)
    start = time.perf_counter()
    
    tasks = [(cid, sids, metadata, artifact) for cid, sids in sorted(clusters.items())]
    all_results = []
    
    with ThreadPoolExecutor(max_workers=min(7, len(tasks))) as pool:
        futures = [pool.submit(_eval_single_cluster, *t) for t in tasks]
        for f in futures:
            all_results.extend(f.result())
            
    elapsed = time.perf_counter() - start
    df_eval = pd.DataFrame(all_results)
    
    tp = int(((df_eval["is_gt"] == True) & (df_eval["is_pred"] == True)).sum())
    fp = int(((df_eval["is_gt"] == False) & (df_eval["is_pred"] == True)).sum())
    fn = int(((df_eval["is_gt"] == True) & (df_eval["is_pred"] == False)).sum())
    tn = int(((df_eval["is_gt"] == False) & (df_eval["is_pred"] == False)).sum())
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    print("\n" + "="*60, flush=True)
    print("SKYGUARD AI - PRODUCTION BENCHMARK SCORECARD", flush=True)
    print("="*60, flush=True)
    print(f"Total Rows Evaluated : {len(df_eval):,}", flush=True)
    print(f"Total Execution Time : {elapsed:.2f} seconds ({len(df_eval)/elapsed:.1f} rows/s)", flush=True)
    print(f"True Positives (TP)  : {tp:,}", flush=True)
    print(f"False Positives (FP) : {fp:,}", flush=True)
    print(f"False Negatives (FN) : {fn:,}", flush=True)
    print(f"True Negatives (TN)  : {tn:,}", flush=True)
    print("-"*60, flush=True)
    print(f"ROW PRECISION        : {precision:.2%}", flush=True)
    print(f"ROW RECALL           : {recall:.2%}", flush=True)
    print(f"ROW F1-SCORE         : {f1:.2%}", flush=True)
    print("="*60, flush=True)

if __name__ == "__main__":
    run_benchmark()
