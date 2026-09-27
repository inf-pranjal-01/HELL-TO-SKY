"""
scratch/precision_forensics/run_offline_step2_experiments.py

Offline Peer / Context / Pre-Roll / Season Design Experiments for:
PATH 2 — PRECISION DEVELOPMENT STEP 2

PRODUCTION CODE IS UNTOUCHED / RESTORED.
NO THRESHOLD TUNING.
ALL EXPERIMENTS ARE OFFLINE DIAGNOSTICS.
"""

import sys
import os
from pathlib import Path
import time
import json
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(REPO_ROOT))

from model.detect import (
    score_reading,
    PARAMS,
    SENSOR_QUANTIZATION_FLOORS,
    WALD_UPPER_ALERT,
    WALD_LOWER_NORMAL,
    calculate_solar_hour
)
from model.state import StationBuffer
from model.features import build_features_for_history
from model.peer_spatial_engine import PeerSpatialEngine
from model.dynamic_expectation import compute_dynamic_expectation
from model.uncertainty_budget import UncertaintyBudget
from model.cross_channel_covariance import CrossChannelEngine
import data.anomaly_injector as injector
from evaluation.benchmark_contract import pooled_row_metrics, episodic_metrics
import joblib

DATA_DIR = REPO_ROOT / "data"
ARTIFACTS_DIR = REPO_ROOT / "model_artifacts"
OUTPUT_DIR = Path(__file__).parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]


def load_full_and_test_data():
    stations_path = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(stations_path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    cutoff_idx = int(len(df) * 0.7)
    cutoff_date = df.iloc[cutoff_idx]["timestamp"]
    
    test_df = df[df["timestamp"] >= cutoff_date].copy().reset_index(drop=True)
    train_df = df[df["timestamp"] < cutoff_date].copy().reset_index(drop=True)
    return df, train_df, test_df, cutoff_date


# =====================================================================
# 1. BASELINE REPRODUCTION (PART 1)
# =====================================================================
def run_baseline_reproduction(test_raw_df: pd.DataFrame, artifact: dict):
    print("==================================================================", flush=True)
    print("PART 1: VERIFYING RESTORED BASELINE ACROSS 7 SEEDS", flush=True)
    print("==================================================================", flush=True)

    seed_metrics = []
    all_raw_evals = []

    for seed in SEEDS:
        t0 = time.time()
        injected_frames = []
        for station_id, group in test_raw_df.groupby("station_id", sort=False):
            group_injected = injector.inject_anomalies(group.copy(), seed=seed)
            injected_frames.append(group_injected)

        eval_df = pd.concat(injected_frames, ignore_index=True)
        eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
        eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

        station_ids = eval_df["station_id"].unique()
        buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

        tp = 0
        fp = 0
        fn = 0
        tn = 0

        rows = eval_df.to_dict("records")
        n_rows = len(rows)

        for i, row in enumerate(rows):
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

            verdict = score_reading(raw_reading, hist_df, artifact, neighbor_bufs)
            is_pred_anom = bool(verdict["is_anomaly"])
            gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False

            if is_pred_anom and gt_is_anom:
                tp += 1
            elif is_pred_anom and not gt_is_anom:
                fp += 1
            elif not is_pred_anom and gt_is_anom:
                fn += 1
            else:
                tn += 1

            buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

        dt = time.time() - t0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        res = {
            "seed": seed,
            "total_samples": n_rows,
            "ground_truth_faults": tp + fn,
            "predicted_faults": tp + fp,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "duration_sec": dt,
            "latency_ms": (dt / n_rows) * 1000.0
        }
        seed_metrics.append(res)
        print(f"Seed {seed:12d} | TP: {tp:5d} | FP: {fp:5d} | FN: {fn:4d} | Prec: {prec*100:6.2f}% | Rec: {rec*100:6.2f}% | F1: {f1*100:6.2f}%", flush=True)

    base_df = pd.DataFrame(seed_metrics)
    base_df.to_csv(OUTPUT_DIR / "baseline_reproduction.csv", index=False)

    macro_p = float(np.mean(base_df["precision"]))
    macro_r = float(np.mean(base_df["recall"]))
    macro_f = float(np.mean(base_df["f1"]))
    print(f"\nRESTORED BASELINE MACRO: Precision = {macro_p*100:.2f}% | Recall = {macro_r*100:.2f}% | F1 = {macro_f*100:.2f}%")
    return base_df


# =====================================================================
# 2. CONTINUOUS PEER-CONTEXT EVIDENCE & PRESSURE/WEATHER FORENSICS (PARTS 2, 3, 4)
# =====================================================================
def run_continuous_peer_experiments(test_raw_df: pd.DataFrame, artifact: dict):
    print("\n==================================================================", flush=True)
    print("PARTS 2, 3, 4: CONTINUOUS PEER EVIDENCE & PRESSURE/WEATHER FORENSICS", flush=True)
    print("==================================================================", flush=True)

    # Use Seed 42 for rich continuous signal sampling across all 28 stations (18,144 readings)
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        group_injected = injector.inject_anomalies(group.copy(), seed=42)
        injected_frames.append(group_injected)

    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

    peer_events_records = []
    pressure_events_records = []
    weather_front_records = []

    rows = eval_df.to_dict("records")
    for i, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        buf = buffers[st_id]
        gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_fault = str(row["fault_type"]) if pd.notna(row["fault_type"]) else "normal"

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

        # Analyze each parameter for candidate jumps and continuous peer quantities
        for p in PARAMS:
            val = float(raw_reading[p])
            prior_val = None
            if not hist_df.empty and p in hist_df.columns:
                valid_pvals = pd.to_numeric(hist_df[p], errors="coerce").dropna()
                if not valid_pvals.empty:
                    prior_val = float(valid_pvals.iloc[-1])

            if prior_val is not None:
                d_target = val - prior_val
                floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                sigma_jump = math.sqrt(2.0 * (floor ** 2) + 0.25)
                z_target = d_target / max(1e-4, sigma_jump)

                # Collect sibling deltas
                sibling_deltas = []
                sibling_z = []
                sibling_1h_lag_deltas = []  # To evaluate phase lag effect

                for nid in sibling_ids:
                    if nid in neighbor_bufs:
                        nhist = neighbor_bufs[nid].raw_history_df()
                        if not nhist.empty and p in nhist.columns:
                            nv = pd.to_numeric(nhist[p], errors="coerce").dropna()
                            if len(nv) >= 2:
                                d_s = float(nv.iloc[-1]) - float(nv.iloc[-2])
                                sibling_deltas.append(d_s)
                                sibling_z.append(d_s / max(1e-4, sigma_jump))
                            if len(nv) >= 3:
                                d_s_lag = float(nv.iloc[-2]) - float(nv.iloc[-3])
                                sibling_1h_lag_deltas.append(d_s_lag)

                if len(sibling_deltas) >= 2:
                    s_arr = np.array(sibling_deltas, dtype=float)
                    # Continuous Peer Context Metrics
                    peer_median_d = float(np.median(s_arr))
                    peer_mad_d = float(np.median(np.abs(s_arr - peer_median_d)))
                    peer_dispersion = max(0.5 * sigma_jump, 1.4826 * peer_mad_d)
                    
                    # 1. Target Innovation minus Peer Common-Mode Innovation
                    residual_delta = d_target - peer_median_d
                    
                    # 2. Continuous Target-vs-Peer Standardized Surprise
                    z_surprise = residual_delta / max(1e-4, peer_dispersion)
                    
                    # 3. Directional Alignment Index: Dot-product normalized
                    dir_alignment = float(np.mean([np.sign(d_target) * np.sign(sd) for sd in sibling_deltas if abs(sd) > 0.5 * floor])) if sibling_deltas else 0.0
                    
                    # 4. Continuous Likelihood Ratio of Isolation vs Common Mode
                    # Under H_isolated: z_surprise is high, peer movement near 0
                    # Under H_common: z_surprise near 0, peer_median_d aligned with d_target
                    peer_common_mode_llr = float(0.5 * (z_target ** 2) - 0.5 * (z_surprise ** 2))

                    # Phase lag evaluation for pressure
                    lag_aligned = False
                    if p == "pressure_hpa" and sibling_1h_lag_deltas:
                        lag_median = float(np.median(sibling_1h_lag_deltas))
                        if np.sign(d_target) == np.sign(lag_median) and abs(lag_median) > 0.5:
                            lag_aligned = True

                    # Classify if candidate jump (|z_target| >= 2.5)
                    if abs(z_target) >= 2.5:
                        rec = {
                            "station_id": st_id,
                            "timestamp": ts.isoformat(),
                            "parameter": p,
                            "d_target": d_target,
                            "z_target": z_target,
                            "peer_median_d": peer_median_d,
                            "peer_dispersion": peer_dispersion,
                            "residual_delta": residual_delta,
                            "z_surprise": z_surprise,
                            "dir_alignment": dir_alignment,
                            "peer_common_mode_llr": peer_common_mode_llr,
                            "is_ground_truth_anomaly": gt_is_anom,
                            "ground_truth_fault_type": gt_fault,
                            "has_1h_phase_lag": lag_aligned
                        }
                        peer_events_records.append(rec)

                        if p == "pressure_hpa":
                            pressure_events_records.append(rec)
                        elif p in ["temperature_c", "humidity_pct"]:
                            weather_front_records.append(rec)

        verdict = score_reading(raw_reading, hist_df, artifact, neighbor_bufs)
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

    # Save CSV Artifacts
    peer_df = pd.DataFrame(peer_events_records)
    peer_df.to_csv(OUTPUT_DIR / "peer_context_distribution.csv", index=False)

    # Pressure Specific Analysis (Part 3)
    press_df = pd.DataFrame(pressure_events_records)
    if not press_df.empty:
        # Classify pressure jumps into categories
        # A: Strongly Common Mode (|z_surprise| < 1.5, |peer_median_d| > 0.8)
        # B: Likely Common Mode with Phase Lag (lag_aligned is True)
        # C: Mixed / Uncertain (1.5 <= |z_surprise| < 3.0)
        # D: Strongly Isolated (|z_surprise| >= 3.0, |peer_median_d| < 0.5)
        categories = []
        for _, r in press_df.iterrows():
            if abs(r["z_surprise"]) < 1.5 and abs(r["peer_median_d"]) >= 0.6:
                cat = "A_strongly_common_mode"
            elif r["has_1h_phase_lag"]:
                cat = "B_likely_common_mode_with_phase_lag"
            elif abs(r["z_surprise"]) >= 3.0:
                cat = "D_strongly_isolated_transducer_spike"
            else:
                cat = "C_mixed_uncertain"
            categories.append(cat)
        press_df["pressure_classification"] = categories
        press_df.to_csv(OUTPUT_DIR / "pressure_peer_analysis_v2.csv", index=False)

        print("\n--- Pressure Jump Classification by Continuous Peer Context ---")
        p_counts = press_df["pressure_classification"].value_counts(normalize=True) * 100.0
        for cat, pct in p_counts.items():
            print(f"  {cat:45s}: {pct:5.2f}%")

    # Weather Front Analysis (Part 4)
    weather_df = pd.DataFrame(weather_front_records)
    if not weather_df.empty:
        weather_df.to_csv(OUTPUT_DIR / "weather_peer_analysis_v2.csv", index=False)
        print(f"\nExtracted {len(weather_df)} multi-channel candidate weather front events for offline study.")


# =====================================================================
# 3. BENCHMARK PRE-ROLL / WARM-START EXPERIMENT (PART 5)
# =====================================================================
def run_warmstart_preroll_experiment(train_raw_df: pd.DataFrame, test_raw_df: pd.DataFrame, artifact: dict):
    print("\n==================================================================", flush=True)
    print("PART 5: BENCHMARK PRE-ROLL / CAUSAL WARM-START EXPERIMENT", flush=True)
    print("==================================================================", flush=True)

    # Pre-roll: Trailing 24 hours from train split (strictly prior to test cutoff date, clean history)
    cutoff_date = test_raw_df["timestamp"].min()
    preroll_start = cutoff_date - pd.Timedelta(hours=24)
    preroll_df = train_raw_df[train_raw_df["timestamp"] >= preroll_start].copy().reset_index(drop=True)
    print(f"Pre-roll window: {preroll_start} to {cutoff_date} ({len(preroll_df)} un-scored historical readings)")

    seed_preroll_results = []

    for seed in SEEDS:
        t0 = time.time()
        injected_frames = []
        for station_id, group in test_raw_df.groupby("station_id", sort=False):
            group_injected = injector.inject_anomalies(group.copy(), seed=seed)
            injected_frames.append(group_injected)

        eval_df = pd.concat(injected_frames, ignore_index=True)
        eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
        eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

        station_ids = eval_df["station_id"].unique()
        buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

        # Step 1: Pre-roll clean historical context into buffers (Un-scored!)
        for _, pr_row in preroll_df.iterrows():
            st_id = pr_row["station_id"]
            if st_id in buffers:
                r_dict = {
                    "station_id": st_id,
                    "timestamp": pr_row["timestamp"],
                    "temperature_c": pr_row["temperature_c"],
                    "pressure_hpa": pr_row["pressure_hpa"],
                    "humidity_pct": pr_row["humidity_pct"],
                }
                buffers[st_id].record_raw_reading(r_dict, timestamp=pr_row["timestamp"], verdict={"is_anomaly": False})

        # Step 2: Evaluate strictly scored test slice
        tp = 0
        fp = 0
        fn = 0
        tn = 0
        rows = eval_df.to_dict("records")
        n_rows = len(rows)

        for i, row in enumerate(rows):
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

            verdict = score_reading(raw_reading, hist_df, artifact, neighbor_bufs)
            is_pred_anom = bool(verdict["is_anomaly"])
            gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False

            if is_pred_anom and gt_is_anom:
                tp += 1
            elif is_pred_anom and not gt_is_anom:
                fp += 1
            elif not is_pred_anom and gt_is_anom:
                fn += 1
            else:
                tn += 1

            buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

        dt = time.time() - t0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        seed_preroll_results.append({
            "seed": seed,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "duration_sec": dt
        })
        print(f"Pre-Roll Seed {seed:12d} | TP: {tp:5d} | FP: {fp:5d} | FN: {fn:4d} | Prec: {prec*100:6.2f}% | Rec: {rec*100:6.2f}% | F1: {f1*100:6.2f}%", flush=True)

    preroll_res_df = pd.DataFrame(seed_preroll_results)
    preroll_res_df.to_csv(OUTPUT_DIR / "warmup_pre_roll_analysis.csv", index=False)

    print(f"\nPRE-ROLL EXPERIMENT MACRO: Precision = {np.mean(preroll_res_df['precision'])*100:.2f}% | Recall = {np.mean(preroll_res_df['recall'])*100:.2f}% | F1 = {np.mean(preroll_res_df['f1'])*100:.2f}%")


# =====================================================================
# 4. SEASONAL / REGIME CONTEXT INVESTIGATION (PART 6)
# =====================================================================
def run_seasonal_regime_investigation(df: pd.DataFrame):
    print("\n==================================================================", flush=True)
    print("PART 6: SEASONAL / REGIME CONTEXT INVESTIGATION", flush=True)
    print("==================================================================", flush=True)

    # Analyze physical variance across meteorological seasons in India
    # Winter: Dec, Jan, Feb
    # Pre-Monsoon (Summer): Mar, Apr, May
    # Monsoon: Jun, Jul, Aug, Sep
    # Post-Monsoon: Oct, Nov
    df["month"] = df["timestamp"].dt.month
    df["season"] = df["month"].apply(
        lambda m: "Winter" if m in [12, 1, 2] else "Pre-Monsoon (Summer)" if m in [3, 4, 5] else "Monsoon" if m in [6, 7, 8, 9] else "Post-Monsoon"
    )

    season_stats = []
    for s, grp in df.groupby("season"):
        season_stats.append({
            "season": s,
            "row_count": len(grp),
            "temp_mean": grp["temperature_c"].mean(),
            "temp_std": grp["temperature_c"].std(),
            "pressure_mean": grp["pressure_hpa"].mean(),
            "pressure_std": grp["pressure_hpa"].std(),
            "humidity_mean": grp["humidity_pct"].mean(),
            "humidity_std": grp["humidity_pct"].std(),
            "temp_diurnal_amplitude": grp.groupby(grp["timestamp"].dt.hour)["temperature_c"].mean().max() - grp.groupby(grp["timestamp"].dt.hour)["temperature_c"].mean().min(),
            "pressure_tide_amplitude": grp.groupby(grp["timestamp"].dt.hour)["pressure_hpa"].mean().max() - grp.groupby(grp["timestamp"].dt.hour)["pressure_hpa"].mean().min(),
        })

    season_df = pd.DataFrame(season_stats)
    season_df.to_csv(OUTPUT_DIR / "seasonal_context_analysis_v2.csv", index=False)
    print(season_df[["season", "temp_mean", "temp_std", "pressure_tide_amplitude", "temp_diurnal_amplitude"]].to_string(index=False))


def main():
    df, train_df, test_df, cutoff_date = load_full_and_test_data()
    artifact = joblib.load(ARTIFACTS_DIR / "isolation_forest.pkl")

    # 1. Baseline Reproduction
    run_baseline_reproduction(test_df, artifact)

    # 2. Continuous Peer Experiments
    run_continuous_peer_experiments(test_df, artifact)

    # 3. Pre-Roll Warm-Start Experiment
    run_warmstart_preroll_experiment(train_df, test_df, artifact)

    # 4. Seasonal Regime Investigation
    run_seasonal_regime_investigation(df)

    print("\n==================================================================", flush=True)
    print("ALL OFFLINE EXPERIMENTS COMPLETED SUCCESSFULLY!", flush=True)
    print("==================================================================", flush=True)


if __name__ == "__main__":
    main()
