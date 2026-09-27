"""
scratch/precision_forensics/run_step13_fp_autopsy.py

Step 13: False-Positive Autopsy + Non-Destructive Environmental Disambiguation Study.
Exact reproduction and forensic analysis across 7 locked seeds.
"""

import sys
import math
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import data.anomaly_injector as injector
import model.detect as baseline_detect
from model.peer_spatial_engine import PeerSpatialEngine
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS
from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.sequential_sprt import SequentialSPRT
from model.cross_channel_covariance import CrossChannelEngine
from model.state import StationBuffer
from scratch.precision_forensics.run_step12_experiment import score_variant, compute_channel_scaled_sigma_jump

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]


def process_seed_forensics(seed_args):
    seed, test_raw_df = seed_args
    print(f"[Seed {seed}] Starting dual evaluation...")
    t0 = time.time()

    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers_base = {st_id: StationBuffer(st_id) for st_id in station_ids}
    buffers_s12 = {st_id: StationBuffer(st_id) for st_id in station_ids}
    trusted_priors = {st_id: {p: None for p in PARAMS} for st_id in station_ids}

    base_tp = base_fp = base_fn = 0
    s12_tp = s12_fp = s12_fn = 0

    new_fps_list = []
    base_fps_list = []
    base_tps_list = []
    s12_tps_list = []

    rows = eval_df.to_dict("records")
    for row_idx, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        fault_type = row.get("fault_type", "normal") if gt_is_anom else "normal"

        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        
        # Base buffers
        buf_base = buffers_base[st_id]
        neighbor_bufs_base = {nid: buffers_base[nid] for nid in sibling_ids if nid in buffers_base}
        hist_df_base = buf_base.raw_history_df()

        # Step 12 buffers
        buf_s12 = buffers_s12[st_id]
        neighbor_bufs_s12 = {nid: buffers_s12[nid] for nid in sibling_ids if nid in buffers_s12}
        hist_df_s12 = buf_s12.raw_history_df()

        raw_reading = {
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }

        # 1. Base score
        res_base = score_variant(
            variant_id=0,
            raw_reading=raw_reading,
            history_df=hist_df_base,
            artifact={},
            neighbor_buffers=neighbor_bufs_base,
            trusted_prior_vals=None
        )
        base_flag = bool(res_base["is_anomaly"])

        # 2. Step 12 score (Variant 1 Channel Scaled)
        res_s12 = score_variant(
            variant_id=1,
            raw_reading=raw_reading,
            history_df=hist_df_s12,
            artifact={},
            neighbor_buffers=neighbor_bufs_s12,
            trusted_prior_vals=None
        )
        s12_flag = bool(res_s12["is_anomaly"])

        # Update buffers
        buf_base.record_raw_reading(raw_reading, timestamp=ts, verdict=res_base)
        buf_s12.record_raw_reading(raw_reading, timestamp=ts, verdict=res_s12)

        # Metrics
        if base_flag and gt_is_anom:
            base_tp += 1
        elif base_flag and not gt_is_anom:
            base_fp += 1
        elif not base_flag and gt_is_anom:
            base_fn += 1

        if s12_flag and gt_is_anom:
            s12_tp += 1
        elif s12_flag and not gt_is_anom:
            s12_fp += 1
        elif not s12_flag and gt_is_anom:
            s12_fn += 1

        # Extract per-channel jump/evidence for forensic analysis
        prior_time = None
        if not hist_df_s12.empty and "timestamp" in hist_df_s12.columns:
            valid_ts = pd.to_datetime(hist_df_s12["timestamp"], utc=True, errors="coerce").dropna()
            if not valid_ts.empty:
                prior_time = valid_ts.iloc[-1]
        dt_hours = max(0.1, (ts - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
        solar_hour = calculate_solar_hour(ts, st_id)

        # Collect channel forensics
        channel_details = {}
        for p in PARAMS:
            val = float(row[p])
            floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
            base_sigma = math.sqrt(2.0 * (floor ** 2) + 0.25 * max(0.5, dt_hours))
            s12_sigma = compute_channel_scaled_sigma_jump(p, dt_hours)

            prior_val = None
            if not hist_df_s12.empty and p in hist_df_s12.columns:
                valid_pvals = pd.to_numeric(hist_df_s12[p], errors="coerce").dropna()
                if not valid_pvals.empty:
                    prior_val = float(valid_pvals.iloc[-1])

            delta = abs(val - prior_val) if prior_val is not None else 0.0
            z_base = delta / (base_sigma + 1e-6)
            z_s12 = delta / (s12_sigma + 1e-6)

            peer_med, peer_disp, n_peers = PeerSpatialEngine.compute_robust_peer_consensus(
                st_id, p, ts, neighbor_bufs_s12
            )
            exp_val, _ = compute_dynamic_expectation(st_id, p, ts, hist_df_s12)

            channel_details[p] = {
                "val": val, "prior_val": prior_val, "delta": delta,
                "dt": dt_hours, "base_sigma": base_sigma, "s12_sigma": s12_sigma,
                "z_base": z_base, "z_s12": z_s12,
                "peer_med": peer_med, "peer_disp": peer_disp, "n_peers": n_peers,
                "exp_val": exp_val, "solar_hour": solar_hour, "day_of_year": ts.dayofyear
            }

        # Save record populations
        if s12_flag and gt_is_anom:
            s12_tps_list.append({
                "seed": seed, "station_id": st_id, "timestamp": ts, "fault_type": fault_type,
                "max_z_s12": max(c["z_s12"] for c in channel_details.values()),
                "max_delta": max(c["delta"] for c in channel_details.values()),
                "details": channel_details
            })
        if base_flag and gt_is_anom:
            base_tps_list.append({
                "seed": seed, "station_id": st_id, "timestamp": ts, "fault_type": fault_type,
                "max_z_base": max(c["z_base"] for c in channel_details.values()),
                "max_delta": max(c["delta"] for c in channel_details.values()),
                "details": channel_details
            })
        if base_flag and not gt_is_anom:
            base_fps_list.append({
                "seed": seed, "station_id": st_id, "timestamp": ts,
                "max_z_base": max(c["z_base"] for c in channel_details.values()),
                "details": channel_details
            })

        # Check if NEW FP in Step 12
        if s12_flag and not base_flag and not gt_is_anom:
            # Find trigger channel
            trig_p = max(channel_details.keys(), key=lambda k: channel_details[k]["z_s12"])
            trig_info = channel_details[trig_p]

            new_fps_list.append({
                "seed": seed,
                "station": st_id,
                "cluster": row.get("cluster_id", "default"),
                "timestamp": ts.isoformat(),
                "channel": trig_p,
                "value": trig_info["val"],
                "raw_previous_value": trig_info["prior_val"],
                "raw_delta": trig_info["delta"],
                "dt": trig_info["dt"],
                "z_raw_base": trig_info["z_base"],
                "z_raw_s12": trig_info["z_s12"],
                "sigma_jump_base": trig_info["base_sigma"],
                "sigma_jump_s12": trig_info["s12_sigma"],
                "baseline_verdict": False,
                "step12_verdict": True,
                "baseline_evidence": trig_info["z_base"],
                "step12_evidence": trig_info["z_s12"],
                "fault_type_if_any": fault_type,
                "diurnal_expectation": trig_info["exp_val"],
                "local_trend": trig_info["val"] - trig_info["exp_val"] if trig_info["exp_val"] else 0.0,
                "peer_movement": trig_info["peer_med"],
                "peer_dispersion": trig_info["peer_disp"],
                "time_of_day": ts.strftime("%H:%M:%S"),
                "day_of_year": ts.dayofyear,
                "solar_hour": trig_info["solar_hour"],
                "temperature": row.get("temperature_c", np.nan),
                "pressure": row.get("pressure_hpa", np.nan),
                "humidity": row.get("humidity_pct", np.nan),
                "cross_channel_evidence": f"T={row.get('temperature_c'):.1f},P={row.get('pressure_hpa'):.1f},H={row.get('humidity_pct'):.1f}",
                "model_evidence": "RULE_SPECIALIST_SPIKE",
                "state_status": "NORMAL_HISTORY",
                "history_length": len(hist_df_s12),
                "gap_duration": trig_info["dt"],
                "episode_context": "ISOLATED_TRANSIENT",
                "sunrise_sunset_indicator": "DAWN_DUSK" if (5.5 <= trig_info["solar_hour"] <= 8.5 or 16.5 <= trig_info["solar_hour"] <= 19.5) else "DAY_NIGHT",
                "weather_front_indicator": "PRESSURE_ACTIVE" if abs(channel_details["pressure_hpa"]["delta"]) >= 0.5 else "CALM",
            })

    p_base = base_tp / (base_tp + base_fp) * 100
    r_base = base_tp / (base_tp + base_fn) * 100
    f1_base = 2 * p_base * r_base / (p_base + r_base)

    p_s12 = s12_tp / (s12_tp + s12_fp) * 100
    r_s12 = s12_tp / (s12_tp + s12_fn) * 100
    f1_s12 = 2 * p_s12 * r_s12 / (p_s12 + r_s12)

    print(f"[Seed {seed}] Done in {time.time()-t0:.1f}s | Base: P={p_base:.2f}% R={r_base:.2f}% F1={f1_base:.2f}% | Step 12: P={p_s12:.2f}% R={r_s12:.2f}% F1={f1_s12:.2f}% | New FPs: {len(new_fps_list)}")

    return {
        "seed": seed,
        "base_tp": base_tp, "base_fp": base_fp, "base_fn": base_fn,
        "base_p": p_base, "base_r": r_base, "base_f1": f1_base,
        "s12_tp": s12_tp, "s12_fp": s12_fp, "s12_fn": s12_fn,
        "s12_p": p_s12, "s12_r": r_s12, "s12_f1": f1_s12,
        "new_fps": new_fps_list,
        "base_fps": base_fps_list,
        "base_tps": base_tps_list,
        "s12_tps": s12_tps_list,
    }


def main():
    print("=" * 80)
    print("STEP 13 FORENSIC BENCHMARK RUNNER")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)
    print(f"Loaded {len(df_test_raw)} test rows across {df_test_raw['station_id'].nunique()} stations.")

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(process_seed_forensics, tasks))

    # Aggregate metrics
    summary_rows = []
    all_new_fps = []
    all_base_fps = []
    all_base_tps = []
    all_s12_tps = []

    for r in results:
        summary_rows.append({
            "seed": r["seed"],
            "base_tp": r["base_tp"], "base_fp": r["base_fp"], "base_fn": r["base_fn"],
            "base_p": r["base_p"], "base_r": r["base_r"], "base_f1": r["base_f1"],
            "s12_tp": r["s12_tp"], "s12_fp": r["s12_fp"], "s12_fn": r["s12_fn"],
            "s12_p": r["s12_p"], "s12_r": r["s12_r"], "s12_f1": r["s12_f1"],
        })
        all_new_fps.extend(r["new_fps"])
        all_base_fps.extend(r["base_fps"])
        all_base_tps.extend(r["base_tps"])
        all_s12_tps.extend(r["s12_tps"])

    df_summary = pd.DataFrame(summary_rows)
    macro_base_p = df_summary["base_p"].mean()
    macro_base_r = df_summary["base_r"].mean()
    macro_base_f1 = df_summary["base_f1"].mean()

    macro_s12_p = df_summary["s12_p"].mean()
    macro_s12_r = df_summary["s12_r"].mean()
    macro_s12_f1 = df_summary["s12_f1"].mean()

    print("\n" + "=" * 80)
    print("STEP 12 EXACT REPRODUCTION RESULTS:")
    print(f"BASELINE: P = {macro_base_p:.2f}% | R = {macro_base_r:.2f}% | F1 = {macro_base_f1:.2f}%")
    print(f"STEP 12:  P = {macro_s12_p:.2f}% | R = {macro_s12_r:.2f}% | F1 = {macro_s12_f1:.2f}%")
    print("=" * 80)
    print(df_summary[["seed", "base_p", "s12_p", "base_r", "s12_r", "base_f1", "s12_f1"]].to_string(index=False))

    # 1. Save new FP dataset
    df_new_fps = pd.DataFrame(all_new_fps)
    new_fp_path = OUTPUT_DIR / "step12_new_fp_dataset.csv"
    df_new_fps.to_csv(new_fp_path, index=False)
    print(f"\nSaved {len(df_new_fps)} records to {new_fp_path} (Mean {len(df_new_fps)/len(SEEDS):.1f} per seed)")

    # 2. Classification of New FPs
    def classify_fp(row):
        ch = row["channel"]
        sh = row["solar_hour"]
        delta = row["raw_delta"]
        z = row["z_raw_s12"]
        hlen = row["history_length"]

        if hlen < 5:
            return "G. Cold-start / insufficient-context artifact"
        if ch == "temperature_c" and (5.5 <= sh <= 8.5 or 16.5 <= sh <= 19.5):
            return "C. Dawn / dusk transition"
        if ch == "humidity_pct" and delta >= 2.5:
            return "E. Humidity surge / rainfall-related movement"
        if ch == "pressure_hpa" and delta >= 0.5:
            return "D. Pressure front / common-mode regional movement"
        if 3.0 <= z < 4.0:
            return "B. Normal high-frequency weather variability"
        if z >= 4.0:
            return "A. Genuine atmospheric transition"
        return "J. Genuine ambiguity"

    df_new_fps["category"] = df_new_fps.apply(classify_fp, axis=1)
    cat_summary = df_new_fps["category"].value_counts().reset_index()
    cat_summary.columns = ["category", "count"]
    cat_summary["percentage"] = (cat_summary["count"] / len(df_new_fps)) * 100.0
    cat_summary["per_seed_mean"] = cat_summary["count"] / len(SEEDS)
    cat_summary.to_csv(OUTPUT_DIR / "step13_fp_classification.csv", index=False)
    print("\n--- NEW FALSE POSITIVE CLASSIFICATION ---")
    print(cat_summary.to_string(index=False))

    # Channel breakdown
    ch_summary = df_new_fps["channel"].value_counts().reset_index()
    ch_summary.columns = ["channel", "count"]
    ch_summary["percentage"] = (ch_summary["count"] / len(df_new_fps)) * 100.0
    ch_summary["per_seed_mean"] = ch_summary["count"] / len(SEEDS)
    ch_summary.to_csv(OUTPUT_DIR / "step13_fp_by_channel.csv", index=False)
    print("\n--- NEW FALSE POSITIVES BY CHANNEL ---")
    print(ch_summary.to_string(index=False))

    # 3. Raw-Z Percentile Distribution Analysis
    z_new_fps = df_new_fps["z_raw_s12"].values
    z_base_fps = np.array([r["max_z_base"] for r in all_base_fps])
    z_base_tps = np.array([r["max_z_base"] for r in all_base_tps])
    z_s12_tps = np.array([r["max_z_s12"] for r in all_s12_tps])

    def calc_stats(arr, name):
        return {
            "population": name,
            "count": len(arr),
            "P50": np.percentile(arr, 50),
            "P75": np.percentile(arr, 75),
            "P90": np.percentile(arr, 90),
            "P95": np.percentile(arr, 95),
            "P99": np.percentile(arr, 99),
            "max": np.max(arr),
        }

    z_dist_df = pd.DataFrame([
        calc_stats(z_new_fps, "New Step-12 False Positives"),
        calc_stats(z_base_fps, "Baseline False Positives"),
        calc_stats(z_base_tps, "Baseline True Positives"),
        calc_stats(z_s12_tps, "Step-12 True Positives"),
    ])
    z_dist_df.to_csv(OUTPUT_DIR / "step13_raw_z_distribution.csv", index=False)
    print("\n--- RAW-Z DISTRIBUTIONS ---")
    print(z_dist_df.to_string(index=False))

    # 4. Offline FP Pruning & Environmental Context Separability Experiment
    # Test a non-destructive contextual filter:
    # If 3.0 <= z_raw < 4.5 AND environmental context (diurnal transition or peer agreement) explains the delta,
    # classify as natural transition rather than sensor jump.
    # CRITICAL: Verify effect on Baseline TPs and Step 12 TPs!
    
    pruned_new_fps = 0
    for _, row in df_new_fps.iterrows():
        z = row["z_raw_s12"]
        delta = row["raw_delta"]
        sh = row["solar_hour"]
        ch = row["channel"]
        if 3.0 <= z < 4.2:
            if ch == "temperature_c" and (5.5 <= sh <= 8.5 or 16.5 <= sh <= 19.5) and delta < 0.65:
                pruned_new_fps += 1
            elif ch == "humidity_pct" and delta < 3.2:
                pruned_new_fps += 1
            elif ch == "pressure_hpa" and delta < 0.65:
                pruned_new_fps += 1

    pruned_base_tps = 0
    for r in all_base_tps:
        z = r["max_z_base"]
        delta = r["max_delta"]
        # Check if temperature channel in details satisfies pruning
        t_det = r["details"].get("temperature_c", {})
        sh = t_det.get("solar_hour", 12.0)
        if 3.0 <= z < 4.2 and (5.5 <= sh <= 8.5 or 16.5 <= sh <= 19.5) and delta < 0.65:
            pruned_base_tps += 1

    pruned_s12_tps = 0
    for r in all_s12_tps:
        z = r["max_z_s12"]
        delta = r["max_delta"]
        t_det = r["details"].get("temperature_c", {})
        sh = t_det.get("solar_hour", 12.0)
        if 3.0 <= z < 4.2 and (5.5 <= sh <= 8.5 or 16.5 <= sh <= 19.5) and delta < 0.65:
            pruned_s12_tps += 1

    pruning_summary = pd.DataFrame([{
        "new_fps_evaluated": len(df_new_fps),
        "new_fps_pruned": pruned_new_fps,
        "new_fps_pruned_pct": (pruned_new_fps / len(df_new_fps)) * 100.0,
        "mean_fps_removed_per_seed": pruned_new_fps / len(SEEDS),
        "total_base_tps": len(all_base_tps),
        "base_tps_lost": pruned_base_tps,
        "base_tps_lost_pct": (pruned_base_tps / len(all_base_tps)) * 100.0,
        "total_s12_tps": len(all_s12_tps),
        "s12_tps_lost": pruned_s12_tps,
        "s12_tps_lost_pct": (pruned_s12_tps / len(all_s12_tps)) * 100.0,
    }])
    pruning_summary.to_csv(OUTPUT_DIR / "step13_offline_pruning_results.csv", index=False)
    print("\n--- OFFLINE FP-PRUNING EXPERIMENT SUMMARY ---")
    print(pruning_summary.to_string(index=False))

    print("\nStep 13 execution finished successfully.")

if __name__ == "__main__":
    main()
