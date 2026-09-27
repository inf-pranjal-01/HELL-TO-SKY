"""
SkyGuard AI — Production Benchmark Engine.
Vectorized 1-pass causal feature pipeline with full train/serve mathematical parity.
Runs across all 28 stations and 60,480 rows with upfront ETA and detailed metrics.
"""

from __future__ import annotations
import sys
import time
import json
from pathlib import Path
import joblib
import pandas as pd
import numpy as np

from model.detect import score_reading, PARAM_PREFIXES
from model.features import build_feature_matrix, FEATURE_COLUMNS
from model.state import RAW_HISTORY_MAXLEN_HOURS

DATA_DIR = Path("data")
ARTIFACTS_PATH = Path("model_artifacts/isolation_forest.pkl")

LABEL_COLUMNS = {
    "is_anomaly", "fault_type", "episode_id", "fault_parameter",
    "fault_parameters", "fault_events", "__source_file",
}

def load_dataset():
    metadata = pd.read_csv(DATA_DIR / "stations_metadata.csv")
    frames = []
    for sid in sorted(metadata["station_id"]):
        p = DATA_DIR / f"{sid}_labeled.csv"
        if p.exists():
            df = pd.read_csv(p, parse_dates=["timestamp"])
            df["station_id"] = sid
            frames.append(df)
            
    full = pd.concat(frames, ignore_index=True)
    full["timestamp"] = pd.to_datetime(full["timestamp"], utc=True)
    full["is_anomaly"] = full["is_anomaly"].fillna(False).astype(bool)
    full["fault_type"] = full["fault_type"].fillna("none").astype(str)
    return full.sort_values(["timestamp", "station_id"]).reset_index(drop=True), metadata

def run_benchmark():
    print("="*65, flush=True)
    print("SKYGUARD AI - PRODUCTION BENCHMARK RUNNER", flush=True)
    print("="*65, flush=True)
    
    total_start = time.perf_counter()
    full_df, metadata = load_dataset()
    artifact = joblib.load(ARTIFACTS_PATH) if ARTIFACTS_PATH.exists() else None
    
    total_rows = len(full_df)
    n_stations = full_df["station_id"].nunique()
    
    print(f"Loaded {total_rows:,} readings across {n_stations} stations.", flush=True)
    print(f"Estimated Execution Time: ~2.5 to 3.5 seconds", flush=True)
    print("-"*65, flush=True)
    
    feat_start = time.perf_counter()
    print("[1/3] Precomputing vectorized causal feature matrix (1-pass)...", end="", flush=True)
    clean_inputs = full_df.drop(columns=list(LABEL_COLUMNS), errors="ignore").copy()
    featured_df = build_feature_matrix(clean_inputs)
    print(f" DONE in {time.perf_counter() - feat_start:.2f}s", flush=True)
    
    # Organize features and raw readings by station
    feature_groups = {}
    positions = {}
    for station_id, group in featured_df.groupby("station_id", sort=False):
        group = group.reset_index(drop=True)
        group["timestamp"] = pd.to_datetime(group["timestamp"], utc=True)
        station_id = str(station_id)
        feature_groups[station_id] = group
        for pos, ts in enumerate(group["timestamp"]):
            positions[(station_id, ts)] = pos
            
    raw_groups = {}
    for station_id, group in full_df.groupby("station_id", sort=False):
        station_id = str(station_id)
        raw_groups[station_id] = group.reset_index(drop=True)
        
    print("[2/3] Evaluating 6-Tier Bayesian Decision Engine across all rows...", end="", flush=True)
    score_start = time.perf_counter()
    
    results = []
    for idx, row in full_df.iterrows():
        sid = str(row["station_id"])
        ts = row["timestamp"]
        pos = positions.get((sid, ts), 0)
        
        feat_grp = feature_groups.get(sid)
        feat_row = feat_grp.iloc[pos] if feat_grp is not None else None
        
        hist_start = max(0, pos + 1 - RAW_HISTORY_MAXLEN_HOURS)
        raw_hist = raw_groups[sid].iloc[hist_start:pos + 1].drop(columns=list(LABEL_COLUMNS), errors="ignore")
        
        raw_reading = {
            "station_id": sid,
            "timestamp": ts,
            "temperature_c": float(row["temperature_c"]) if pd.notna(row["temperature_c"]) else None,
            "pressure_hpa": float(row["pressure_hpa"]) if pd.notna(row["pressure_hpa"]) else None,
            "humidity_pct": float(row["humidity_pct"]) if pd.notna(row["humidity_pct"]) else None,
        }
        
        verdict = score_reading(
            raw_reading=raw_reading,
            history_df=raw_hist,
            artifact=artifact,
            neighbor_buffers={},
            precomputed_features=feat_row,
            include_evaluation_diagnostics=False
        )
        
        is_pred = bool(verdict.get("is_anomaly", False))
        fault_pred = str(verdict.get("fault_type", "none") or "none")
        
        results.append({
            "is_gt": bool(row["is_anomaly"]),
            "is_pred": is_pred,
            "fault_gt": str(row["fault_type"]),
            "fault_pred": fault_pred,
            "basis": verdict.get("decision_basis")
        })
        
    print(f" DONE in {time.perf_counter() - score_start:.2f}s", flush=True)
    
    # Calculate Metrics
    print("[3/3] Compiling Confusion Matrix & Fault Breakdown...", flush=True)
    df_res = pd.DataFrame(results)
    
    tp = int(((df_res["is_gt"] == True) & (df_res["is_pred"] == True)).sum())
    fp = int(((df_res["is_gt"] == False) & (df_res["is_pred"] == True)).sum())
    fn = int(((df_res["is_gt"] == True) & (df_res["is_pred"] == False)).sum())
    tn = int(((df_res["is_gt"] == False) & (df_res["is_pred"] == False)).sum())
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    total_elapsed = time.perf_counter() - total_start
    
    print("\n" + "="*65)
    print("           SKYGUARD AI BENCHMARK RESULTS           ")
    print("="*65)
    print(f"Total Telemetry Readings : {total_rows:,}")
    print(f"Total Evaluation Time    : {total_elapsed:.2f} seconds ({total_rows/total_elapsed:.1f} rows/s)")
    print("-"*65)
    print(f"True Positives  (TP)     : {tp:,}")
    print(f"False Positives (FP)     : {fp:,}")
    print(f"False Negatives (FN)     : {fn:,}")
    print(f"True Negatives  (TN)     : {tn:,}")
    print("-"*65)
    print(f"PRECISION                : {precision:.2%}")
    print(f"RECALL                   : {recall:.2%}")
    print(f"F1 SCORE                 : {f1:.2%}")
    print("="*65)
    
    # Breakdown by fault type
    print("\nBreakdown by Ground-Truth Fault Type:")
    print(f"{'Fault Type':<25} {'Total':<8} {'Detected':<10} {'Recall':<10}")
    print("-"*55)
    for ftype, grp in df_res[df_res["is_gt"] == True].groupby("fault_gt"):
        f_total = len(grp)
        f_det = int((grp["is_pred"] == True).sum())
        f_rec = (f_det / f_total) if f_total > 0 else 0.0
        print(f"{ftype:<25} {f_total:<8} {f_det:<10} {f_rec:.1%}")
    print("="*65)

if __name__ == "__main__":
    run_benchmark()
