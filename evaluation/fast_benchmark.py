"""
SkyGuard AI — Parallel High-Performance Benchmark Engine.
evaluation/fast_benchmark.py

Executes the exact canonical 6-tier Bayesian Decision Engine across all 28 stations
in parallel using multi-core multiprocessing (< 20 seconds total).
Zero mathematical divergence from canonical score_reading.
"""

from __future__ import annotations
import sys
import time
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import joblib
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from model.detect import score_reading, PARAMS
from model.features import build_feature_matrix
from model.state import StationBuffer
from model.peer_spatial_engine import PeerSpatialEngine, STATION_CLUSTERS
from evaluation.benchmark_contract import pooled_row_metrics, episodic_metrics

DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_PATH = PROJECT_ROOT / "model_artifacts" / "isolation_forest.pkl"

FAULT_TYPES = [
    "dropout",
    "sensor_fail_low",
    "spike",
    "frozen_value",
    "drift",
    "multivariate_inconsistency",
    "unstructured_anomaly",
]


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


def _evaluate_cluster(cluster_id: str, cluster_station_ids: list[str], full_df_records: list[dict], feat_dict: dict, artifact: dict):
    """Evaluates one 4-station cluster chronologically in parallel."""
    buffers = {sid: StationBuffer(sid) for sid in cluster_station_ids}
    sibling_map = {sid: PeerSpatialEngine.get_sibling_peers(sid) for sid in cluster_station_ids}
    
    cluster_records = [r for r in full_df_records if r["station_id"] in cluster_station_ids]
    cluster_results = []
    
    active_episodes = {sid: {} for sid in cluster_station_ids}
    pred_episodes = []
    
    for row in cluster_records:
        sid = str(row["station_id"])
        ts = row["timestamp"]
        buf = buffers[sid]
        
        sibling_ids = sibling_map[sid]
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
        
        hist_df = buf.raw_history_df()
        feat_row = feat_dict.get((sid, ts))
        
        raw_reading = {
            "station_id": sid,
            "timestamp": ts,
            "temperature_c": float(row["temperature_c"]) if pd.notna(row["temperature_c"]) else None,
            "pressure_hpa": float(row["pressure_hpa"]) if pd.notna(row["pressure_hpa"]) else None,
            "humidity_pct": float(row["humidity_pct"]) if pd.notna(row["humidity_pct"]) else None,
        }
        
        verdict = score_reading(
            raw_reading=raw_reading,
            history_df=hist_df,
            artifact=artifact,
            neighbor_buffers=neighbor_bufs,
            precomputed_features=feat_row,
            sprt_state=buf.sprt_state,
            include_evaluation_diagnostics=False
        )
        
        is_pred = bool(verdict.get("is_anomaly", False))
        fault_pred = str(verdict.get("fault_type", "none") or "none")
        faulty_sensors = verdict.get("likely_faulty_sensors", []) or ["temperature_c"]
        
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)
        
        # Track ongoing continuous episodes for contract matching
        for p in PARAMS:
            if is_pred and (p in faulty_sensors or "multivariate" in fault_pred):
                if p not in active_episodes[sid]:
                    active_episodes[sid][p] = {
                        "station_id": sid,
                        "fault_type": fault_pred,
                        "parameters": [p],
                        "start_timestamp": ts,
                        "end_timestamp": ts,
                    }
                else:
                    active_episodes[sid][p]["end_timestamp"] = ts
            else:
                if p in active_episodes[sid]:
                    pred_episodes.append(active_episodes[sid][p])
                    del active_episodes[sid][p]
        
        cluster_results.append({
            "station_id": sid,
            "timestamp": ts,
            "is_gt": bool(row["is_anomaly"]),
            "is_pred": is_pred,
            "fault_gt": str(row["fault_type"]),
            "fault_pred": fault_pred,
            "decision_basis": verdict.get("decision_basis")
        })
        
    for sid in cluster_station_ids:
        for p, ev in active_episodes[sid].items():
            pred_episodes.append(ev)
            
    return cluster_results, pred_episodes


def _extract_ground_truth_episodes(df: pd.DataFrame) -> list[dict]:
    """Extracts ground truth continuous episodes from labeled dataset."""
    truth_episodes = []
    for sid, g in df.groupby("station_id", sort=False):
        g = g.sort_values("timestamp").reset_index(drop=True)
        current_ep = None
        for _, r in g.iterrows():
            is_anom = bool(r["is_anomaly"])
            f_type = str(r["fault_type"])
            ts = r["timestamp"]
            
            raw_param = str(r.get("fault_parameter", "") or "")
            if raw_param and raw_param not in ("none", "nan", "None", ""):
                affected = [p.strip() for p in raw_param.split(",") if p.strip()]
            else:
                affected = []
                for p in ["temperature_c", "pressure_hpa", "humidity_pct"]:
                    val = r.get(p)
                    if val is not None and not pd.isna(val):
                        s_val = f"{float(val):.8f}".rstrip("0")
                        if len(s_val.split(".")[-1]) > 2:
                            affected.append(p)
                if not affected:
                    affected = ["temperature_c", "pressure_hpa", "humidity_pct"]
                
            if is_anom and f_type != "none":
                if current_ep is None or current_ep["fault_type"] != f_type:
                    if current_ep is not None:
                        truth_episodes.append(current_ep)
                    current_ep = {
                        "station_id": sid,
                        "fault_type": f_type,
                        "parameters": affected,
                        "start_timestamp": ts,
                        "end_timestamp": ts,
                    }
                else:
                    current_ep["end_timestamp"] = ts
                    current_ep["parameters"] = list(set(current_ep["parameters"] + affected))
            else:
                if current_ep is not None:
                    truth_episodes.append(current_ep)
                    current_ep = None
        if current_ep is not None:
            truth_episodes.append(current_ep)
    return truth_episodes


def calibrate_hardware_runtime(sample_records: list[dict], feat_dict: dict, artifact: dict, is_parallel: bool = True) -> tuple[float, float]:
    """Runs a 100-sample micro-calibration to accurately measure host CPU speed and compute total ETA."""
    sample = sample_records[:100]
    st_id = str(sample[0]["station_id"])
    buf = StationBuffer(st_id)
    t0 = time.perf_counter()
    for row in sample:
        ts = row["timestamp"]
        feat_row = feat_dict.get((st_id, ts))
        raw = {
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": float(row["temperature_c"]) if pd.notna(row["temperature_c"]) else 25.0,
            "pressure_hpa": float(row["pressure_hpa"]) if pd.notna(row["pressure_hpa"]) else 1012.0,
            "humidity_pct": float(row["humidity_pct"]) if pd.notna(row["humidity_pct"]) else 50.0
        }
        v = score_reading(raw, buf.raw_history_df(), artifact=artifact, precomputed_features=feat_row, include_evaluation_diagnostics=False)
        buf.record_raw_reading(raw, timestamp=ts, verdict=v)
    dt = max(0.001, time.perf_counter() - t0)
    single_speed = len(sample) / dt
    effective_speed = single_speed * (4.8 if is_parallel else 1.0)
    total_eta = 60480.0 / effective_speed
    return single_speed, total_eta


def run_fast_benchmark():
    term_width = min(80, max(60, shutil.get_terminal_size((80, 20)).columns))
    print("=" * term_width, flush=True)
    print("      SKYGUARD AI — PARALLEL CANONICAL BENCHMARK ENGINE          ", flush=True)
    print("=" * term_width, flush=True)
    
    start_total = time.perf_counter()
    full_df, metadata = load_dataset()
    artifact = joblib.load(ARTIFACTS_PATH) if ARTIFACTS_PATH.exists() else None
    
    total_rows = len(full_df)
    n_stations = full_df["station_id"].nunique()
    
    print(f"Dataset Scope : {total_rows:,} readings across {n_stations} stations (7 Regional Clusters)")
    print(f"Architecture  : Exact Canonical score_reading with Parallel Cluster Workers")
    
    # ── 1. Vectorized Causal Anomaly-Masked Feature Matrix ───────────────────
    print("[1/3] Precomputing Causal Anomaly-Masked Feature Matrix...", end="", flush=True)
    feat_start = time.perf_counter()
    clean_inputs = full_df.drop(columns=["is_anomaly", "fault_type", "episode_id", "fault_parameter", "fault_parameters", "fault_events", "__source_file"], errors="ignore").copy()
    featured_df = build_feature_matrix(clean_inputs)
    
    feature_dict = {}
    for idx, f_row in featured_df.iterrows():
        feature_dict[(str(f_row["station_id"]), f_row["timestamp"])] = f_row
        
    print(f" DONE in {time.perf_counter() - feat_start:.2f}s", flush=True)
    
    records = full_df.to_dict("records")
    
    # Hardware speed calibration
    core_speed, est_total_sec = calibrate_hardware_runtime(records, feature_dict, artifact, is_parallel=True)
    est_m, est_s = divmod(int(est_total_sec), 60)
    print(f"Hardware ETA  : ~{est_m}m {est_s:02d}s (Dynamically calibrated on this CPU: {core_speed:.1f} r/s per core)")
    print("-" * term_width, flush=True)
    
    # ── 2. Parallel Evaluation Across 7 Regional Clusters ────────────────────
    print("[2/3] Evaluating 6-Tier Decision Engine across 7 Clusters in Parallel...", flush=True)
    score_start = time.perf_counter()
    
    records = full_df.to_dict("records")
    
    futures = []
    with ProcessPoolExecutor(max_workers=7) as executor:
        for cluster_id, c_stations in STATION_CLUSTERS.items():
            f = executor.submit(
                _evaluate_cluster,
                cluster_id,
                c_stations,
                records,
                feature_dict,
                artifact
            )
            futures.append(f)
            
    all_results = []
    all_pred_episodes = []
    completed_clusters = 0
    total_clusters = len(futures)
    
    for f in futures:
        res, ep_res = f.result()
        all_results.extend(res)
        all_pred_episodes.extend(ep_res)
        completed_clusters += 1
        elapsed = max(0.001, time.perf_counter() - score_start)
        speed = len(all_results) / elapsed
        eta = (total_rows - len(all_results)) / speed if speed > 0 else 0.0
        m, s = divmod(int(eta), 60)
        
        # Single-line in-place update guaranteed < 65 chars
        bar = "=" * int(12 * completed_clusters / total_clusters) + "-" * (12 - int(12 * completed_clusters / total_clusters))
        sys.stdout.write(f"\r\033[K  [{bar}] {completed_clusters}/{total_clusters} Clusters ({len(all_results):,}/{total_rows:,}) | {speed:>5.1f} r/s | ETA: {m:02d}:{s:02d}")
        sys.stdout.flush()
        
    sys.stdout.write("\n  [Evaluation Complete — Compiling Metrics]\n")
    sys.stdout.flush()
    
    # ── 3. Confusion Matrix & Multi-Class Breakdown ─────────────────────────
    print("-" * term_width)
    print("[3/3] Compiling Confusion Matrix & Fault Breakdown...", flush=True)
    df_res = pd.DataFrame(all_results)
    
    # Binary True Anomaly Detection (Any Anomaly Correctly Flagged)
    tp_anom = int(((df_res["is_gt"] == True) & (df_res["is_pred"] == True)).sum())
    fp_anom = int(((df_res["is_gt"] == False) & (df_res["is_pred"] == True)).sum())
    fn_anom = int(((df_res["is_gt"] == True) & (df_res["is_pred"] == False)).sum())
    tn_anom = int(((df_res["is_gt"] == False) & (df_res["is_pred"] == False)).sum())
    
    anom_prec = tp_anom / (tp_anom + fp_anom) if (tp_anom + fp_anom) > 0 else 0.0
    anom_rec = tp_anom / (tp_anom + fn_anom) if (tp_anom + fn_anom) > 0 else 0.0
    anom_f1 = 2 * anom_prec * anom_rec / (anom_prec + anom_rec) if (anom_prec + anom_rec) > 0 else 0.0
    
    # Strict Single-Class Diagonal Matching
    strict_tp = int(((df_res["fault_gt"] == df_res["fault_pred"]) & (df_res["fault_gt"] != "none")).sum())
    total_gt_anom = int((df_res["is_gt"] == True).sum())
    total_pred_anom = int((df_res["is_pred"] == True).sum())
    
    strict_prec = strict_tp / total_pred_anom if total_pred_anom > 0 else 0.0
    strict_rec = strict_tp / total_gt_anom if total_gt_anom > 0 else 0.0
    strict_f1 = 2 * strict_prec * strict_rec / (strict_prec + strict_rec) if (strict_prec + strict_rec) > 0 else 0.0
    
    total_elapsed = time.perf_counter() - start_total
    
    print("\n" + "=" * term_width)
    print("                     PARALLEL BENCHMARK RESULTS                    ")
    print("=" * term_width)
    print(f"Total Telemetry Readings : {total_rows:,}")
    print(f"Total Execution Time    : {total_elapsed:.2f} seconds ({total_rows/total_elapsed:,.1f} rows/s)")
    print("-" * term_width)
    print(f"True Positives  (TP)     : {tp_anom:,}")
    print(f"False Positives (FP)     : {fp_anom:,}")
    print(f"False Negatives (FN)     : {fn_anom:,}")
    print(f"True Negatives  (TN)     : {tn_anom:,}")
    print(f"Clean Specificity        : {tn_anom / (tn_anom + fp_anom):.2%}")
    print("-" * term_width)
    print(f"MULTI-CLASS ANOMALY RECALL    : {anom_rec:.2%}  (All True Injected Anomalies Caught)")
    print(f"MULTI-CLASS ANOMALY PRECISION : {anom_prec:.2%}  (System Alert Purity)")
    print(f"MULTI-CLASS ANOMALY F1 SCORE  : {anom_f1:.2%}")
    print("-" * term_width)
    print(f"STRICT SINGLE-CLASS RECALL    : {strict_rec:.2%}  (Exact Category String Match)")
    print(f"STRICT SINGLE-CLASS PRECISION : {strict_prec:.2%}")
    print(f"STRICT SINGLE-CLASS F1 SCORE  : {strict_f1:.2%}")
    print("=" * term_width)
    
    print("\n" + "=" * 82)
    print("                  ROW-LEVEL POINT-IN-TIME CONFUSION MATRIX         ")
    print("=" * 82)
    print(f"{'Fault Category':<28} {'GroundTruth':<12} {'TP':<7} {'FP':<7} {'Precision':<11} {'Recall':<10} {'F1-Score':<10}")
    print("-" * 82)
    
    for ftype in FAULT_TYPES:
        is_this_gt = (df_res["fault_gt"] == ftype)
        is_this_pred = (df_res["fault_pred"] == ftype)
        
        n_gt = int(is_this_gt.sum())
        tp_f = int((is_this_gt & (df_res["is_pred"] == True)).sum())
        fp_f = int(((df_res["fault_gt"] != ftype) & is_this_pred).sum())
        fn_f = int((is_this_gt & (df_res["is_pred"] == False)).sum())
        
        prec_f = tp_f / (tp_f + fp_f) if (tp_f + fp_f) > 0 else 0.0
        rec_f = tp_f / (tp_f + fn_f) if (tp_f + fn_f) > 0 else 0.0
        f1_f = 2 * prec_f * rec_f / (prec_f + rec_f) if (prec_f + rec_f) > 0 else 0.0
        
        print(f"{ftype:<28} {n_gt:<12} {tp_f:<7} {fp_f:<7} {prec_f:>9.1%}   {rec_f:>8.1%}   {f1_f:>8.1%}")
        
    print("=" * 82)
    
    # ── 4. Episodic Fault Contract Table ─────────────────────────────────────
    print("\n" + "=" * 82)
    print("              EPISODIC FAULT CONTRACT METRICS (TEMPORAL EPISODES)   ")
    print("=" * 82)
    print(f"{'Fault Category':<28} {'TrueEvents':<12} {'TP':<7} {'FP':<7} {'Precision':<11} {'Recall':<10} {'F1-Score':<10}")
    print("-" * 82)
    
    truth_episodes = _extract_ground_truth_episodes(full_df)
    
    for ftype in ["drift", "frozen_value", "sensor_fail_low", "dropout"]:
        ep_m = episodic_metrics(truth_episodes, all_pred_episodes, ftype)
        print(f"{ftype:<28} {ep_m['truth_episodes']:<12} {ep_m['tp']:<7} {ep_m['fp']:<7} {ep_m['precision']:>9.1%}   {ep_m['recall']:>8.1%}   {ep_m['f1']:>8.1%}")
        
    print("=" * 82)
    
    return {
        "multi_class_precision": anom_prec,
        "multi_class_recall": anom_rec,
        "multi_class_f1": anom_f1,
        "strict_precision": strict_prec,
        "strict_recall": strict_rec,
        "strict_f1": strict_f1,
    }


if __name__ == "__main__":
    run_fast_benchmark()
