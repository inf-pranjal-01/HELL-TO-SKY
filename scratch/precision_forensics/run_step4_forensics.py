"""
scratch/precision_forensics/run_step4_forensics.py

Path 2 — Precision Step 4:
High-Performance Parallel Deep Causal Spike-Statistic Forensics, Uncertainty Decomposition,
Temporal Shape Analysis, and Sampling Assumptions Audit.
"""

import sys
import os
import re
import math
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from model.dynamic_expectation import (
    compute_dynamic_expectation,
    calculate_solar_hour,
    STATION_COORDS
)
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS
from model.sequential_sprt import SequentialSPRT
from model.peer_spatial_engine import (
    PeerSpatialEngine,
    STATION_CLUSTERS,
    STATION_TO_CLUSTER,
    STATION_SIBLING_PEERS,
    STATION_ELEVATIONS
)
from model.detect import (
    PARAMS,
    PARAM_PREFIXES,
    WALD_UPPER_ALERT,
    WALD_LOWER_NORMAL,
    evaluate_spike_evidence
)
from model.state import StationBuffer
import data.anomaly_injector as injector

DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]


# =====================================================================
# 1. PARALLEL POPULATION EXTRACTION WORKER
# =====================================================================
def extract_single_seed_records(args: Tuple) -> List[Dict[str, Any]]:
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

    seed_records = []
    rows = eval_df.to_dict("records")

    for i, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        buf = buffers[st_id]
        gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_fault = str(row["fault_type"]) if pd.notna(row["fault_type"]) else "normal"

        sibling_ids = STATION_SIBLING_PEERS.get(st_id, [])
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}

        prior_vals = {}
        prior2_vals = {}
        if buf and hasattr(buf, "_raw_rows") and len(buf._raw_rows) >= 1:
            prior_vals = {p: buf._raw_rows[-1].get(p) for p in PARAMS}
        if buf and hasattr(buf, "_raw_rows") and len(buf._raw_rows) >= 2:
            prior2_vals = {p: buf._raw_rows[-2].get(p) for p in PARAMS}

        hist_df_cached = None

        for p in PARAMS:
            val = float(row[p])
            prior_v = prior_vals.get(p)
            prior2_v = prior2_vals.get(p)

            if prior_v is not None:
                delta_actual = val - prior_v
                accel_actual = (val - 2.0 * prior_v + prior2_v) if prior2_v is not None else 0.0

                floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                sigma_jump = math.sqrt(2.0 * (floor ** 2) + 0.25)
                z_jump = abs(delta_actual) / max(1e-4, sigma_jump)
                jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / floor)))

                # Peer consensus delta
                sibling_deltas = []
                for nid in sibling_ids:
                    if nid in neighbor_bufs:
                        nb = neighbor_bufs[nid]
                        if hasattr(nb, "_raw_rows") and len(nb._raw_rows) >= 2:
                            nv1 = nb._raw_rows[-1].get(p)
                            nv0 = nb._raw_rows[-2].get(p)
                            if nv1 is not None and nv0 is not None:
                                sibling_deltas.append(float(nv1) - float(nv0))

                peer_median_d = float(np.median(sibling_deltas)) if sibling_deltas else 0.0
                peer_residual_delta = delta_actual - peer_median_d

                # Only compute heavy dynamic expectation for candidate movements
                if abs(delta_actual) >= 1.5 * floor:
                    if hist_df_cached is None:
                        hist_df_cached = buf.raw_history_df() if buf else pd.DataFrame()
                    exp_val, exp_roc = compute_dynamic_expectation(st_id, p, ts, hist_df_cached)
                    expected_delta = exp_roc
                    residual_delta = delta_actual - expected_delta

                    seed_records.append({
                        "seed": seed,
                        "station_id": st_id,
                        "timestamp": ts.isoformat(),
                        "parameter": p,
                        "val": val,
                        "prior_val": prior_v,
                        "delta_actual": delta_actual,
                        "accel_actual": accel_actual,
                        "expected_delta": expected_delta,
                        "residual_delta": residual_delta,
                        "peer_median_delta": peer_median_d,
                        "peer_residual_delta": peer_residual_delta,
                        "sigma_jump": sigma_jump,
                        "z_jump": z_jump,
                        "jump_llr": jump_llr,
                        "is_spike_predicted": (jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0),
                        "is_ground_truth_anomaly": gt_is_anom,
                        "ground_truth_fault_type": gt_fault,
                        "is_true_spike": (gt_fault == "spike"),
                        "is_clean_weather": (not gt_is_anom)
                    })

        buf.record_raw_reading({
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }, timestamp=ts, verdict={"is_anomaly": False})

    return seed_records


# =====================================================================
# 2. POPULATION ANALYSIS & DISTRIBUTION METRICS
# =====================================================================
def analyze_and_save_all_distributions(df_pop: pd.DataFrame):
    print("\n==================================================================", flush=True)
    print("ANALYZING CLEAN VS FAULT DISTRIBUTIONS ACROSS PARAMETERS", flush=True)
    print("==================================================================", flush=True)

    # 1. Clean vs Fault Distribution
    df_pop.to_csv(OUTPUT_DIR / "spike_clean_vs_fault_distribution.csv", index=False)
    print(f"Saved spike_clean_vs_fault_distribution.csv ({len(df_pop)} records)")

    # 2. Pressure Deep Dive (Part 7)
    df_press = df_pop[df_pop["parameter"] == "pressure_hpa"].copy()
    print(f"Total Pressure Events: {len(df_press)}")
    df_press.to_csv(OUTPUT_DIR / "pressure_spike_distribution.csv", index=False)
    print(f"Saved pressure_spike_distribution.csv ({len(df_press)} records)")

    # 3. Temporal Shape & Derivative Analysis (Parts 6 & 10)
    shape_records = []
    for p in PARAMS:
        sub_df = df_pop[df_pop["parameter"] == p]
        clean_sub = sub_df[sub_df["is_clean_weather"]]
        spike_sub = sub_df[sub_df["is_true_spike"]]

        shape_records.append({
            "parameter": p,
            "category": "Clean_Natural_Movement",
            "count": len(clean_sub),
            "mean_abs_delta": clean_sub["delta_actual"].abs().mean(),
            "std_abs_delta": clean_sub["delta_actual"].abs().std(),
            "mean_abs_accel": clean_sub["accel_actual"].abs().mean(),
            "mean_abs_residual_delta": clean_sub["residual_delta"].abs().mean(),
            "mean_abs_peer_residual": clean_sub["peer_residual_delta"].abs().mean(),
            "fp_spike_triggers": clean_sub["is_spike_predicted"].sum()
        })
        shape_records.append({
            "parameter": p,
            "category": "True_Injected_Spike",
            "count": len(spike_sub),
            "mean_abs_delta": spike_sub["delta_actual"].abs().mean(),
            "std_abs_delta": spike_sub["delta_actual"].abs().std(),
            "mean_abs_accel": spike_sub["accel_actual"].abs().mean(),
            "mean_abs_residual_delta": spike_sub["residual_delta"].abs().mean(),
            "mean_abs_peer_residual": spike_sub["peer_residual_delta"].abs().mean(),
            "tp_spike_triggers": spike_sub["is_spike_predicted"].sum()
        })

    df_shape = pd.DataFrame(shape_records)
    print("\n=== TEMPORAL SHAPE SUMMARY ===")
    print(df_shape.to_string())
    df_shape.to_csv(OUTPUT_DIR / "spike_temporal_shape.csv", index=False)

    # 4. Peer-As-Context vs Peer-As-Veto Analysis (Part 11)
    peer_ctx_records = []
    for p in PARAMS:
        sub_df = df_pop[df_pop["parameter"] == p]
        clean_sub = sub_df[sub_df["is_clean_weather"]]
        spike_sub = sub_df[sub_df["is_true_spike"]]

        mu_clean_abs = clean_sub["delta_actual"].abs().mean()
        mu_spike_abs = spike_sub["delta_actual"].abs().mean()
        sigma_abs = (clean_sub["delta_actual"].abs().std() + spike_sub["delta_actual"].abs().std()) / 2.0
        sep_abs = (mu_spike_abs - mu_clean_abs) / max(1e-4, sigma_abs)

        mu_clean_exp_res = clean_sub["residual_delta"].abs().mean()
        mu_spike_exp_res = spike_sub["residual_delta"].abs().mean()
        sigma_exp_res = (clean_sub["residual_delta"].abs().std() + spike_sub["residual_delta"].abs().std()) / 2.0
        sep_exp_res = (mu_spike_exp_res - mu_clean_exp_res) / max(1e-4, sigma_exp_res)

        mu_clean_peer_res = clean_sub["peer_residual_delta"].abs().mean()
        mu_spike_peer_res = spike_sub["peer_residual_delta"].abs().mean()
        sigma_peer_res = (clean_sub["peer_residual_delta"].abs().std() + spike_sub["peer_residual_delta"].abs().std()) / 2.0
        sep_peer_res = (mu_spike_peer_res - mu_clean_peer_res) / max(1e-4, sigma_peer_res)

        peer_ctx_records.append({
            "parameter": p,
            "metric": "A_Absolute_Jump",
            "clean_mean": mu_clean_abs,
            "spike_mean": mu_spike_abs,
            "distribution_separation_d_prime": sep_abs
        })
        peer_ctx_records.append({
            "parameter": p,
            "metric": "B_Contextual_Expectation_Residual",
            "clean_mean": mu_clean_exp_res,
            "spike_mean": mu_spike_exp_res,
            "distribution_separation_d_prime": sep_exp_res
        })
        peer_ctx_records.append({
            "parameter": p,
            "metric": "C_Peer_Conditioned_Residual",
            "clean_mean": mu_clean_peer_res,
            "spike_mean": mu_spike_peer_res,
            "distribution_separation_d_prime": sep_peer_res
        })

    df_peer_ctx = pd.DataFrame(peer_ctx_records)
    print("\n=== PEER AS CONTEXT SEPARATION (d') ===")
    print(df_peer_ctx.to_string())
    df_peer_ctx.to_csv(OUTPUT_DIR / "peer_as_environment_context.csv", index=False)


# =====================================================================
# 3. UNCERTAINTY DECOMPOSITION AUDIT (PART 8)
# =====================================================================
def audit_uncertainty_decomposition(test_raw_df: pd.DataFrame):
    print("\n==================================================================", flush=True)
    print("AUDITING UNCERTAINTY DECOMPOSITION (SENSOR VS PROCESS VARIANCE)", flush=True)
    print("==================================================================", flush=True)

    records = []
    for p in PARAMS:
        floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
        sigma_sensor_jump = math.sqrt(2.0 * (floor ** 2) + 0.25)

        vals = pd.to_numeric(test_raw_df[p], errors="coerce").dropna().values
        hourly_deltas = np.diff(vals)
        sigma_process_empirical = float(np.std(hourly_deltas))
        mad_process = float(np.median(np.abs(hourly_deltas - np.median(hourly_deltas)))) * 1.4826

        ratio_process_to_sensor = sigma_process_empirical / max(1e-4, sigma_sensor_jump)

        records.append({
            "parameter": p,
            "quantization_floor": floor,
            "current_sigma_jump": sigma_sensor_jump,
            "empirical_process_std": sigma_process_empirical,
            "empirical_process_mad": mad_process,
            "process_to_sensor_ratio": ratio_process_to_sensor,
            "is_sensor_sigma_too_narrow_for_weather": ratio_process_to_sensor > 1.5,
            "diagnosis": f"Sensor sigma represents instrument floor; natural weather std exceeds sensor floor by {ratio_process_to_sensor:.2f}x"
        })

    df_u = pd.DataFrame(records)
    print(df_u.to_string())
    df_u.to_csv(OUTPUT_DIR / "uncertainty_decomposition_audit.csv", index=False)


# =====================================================================
# 4. SAMPLING ASSUMPTIONS AUDIT (PART 16)
# =====================================================================
def audit_sampling_assumptions():
    print("\n==================================================================", flush=True)
    print("SCANNING CODEBASE FOR SAMPLING / TEMPORAL ASSUMPTIONS (PART 16)", flush=True)
    print("==================================================================", flush=True)

    findings = []
    code_files = list((REPO_ROOT / "model").glob("*.py")) + list((REPO_ROOT / "evaluation").glob("*.py"))

    patterns = [
        (r"\.shift\(1\)", "shift(1) assumes contiguous uniform 1-step row alignment"),
        (r"\.shift\(2\)", "shift(2) assumes contiguous uniform 2-step row alignment"),
        (r"\.shift\(24\)", "shift(24) assumes exactly 24 rows per day"),
        (r"rolling\(24", "rolling(24) assumes 24 hourly rows per day"),
        (r"rolling\(48", "rolling(48) assumes 48 hourly rows per 2 days"),
        (r"dt_hours\s*=\s*1\.0", "Hard-coded fallback dt_hours = 1.0"),
        (r"5400", "5400 seconds (1.5h) hard-coded peer freshness window"),
        (r"3600", "3600 seconds (1.0h) hourly time conversion divisor")
    ]

    for fpath in code_files:
        content = fpath.read_text(encoding="utf-8")
        lines = content.splitlines()

        for idx, line in enumerate(lines, 1):
            for pat, desc in patterns:
                if re.search(pat, line):
                    findings.append({
                        "file": fpath.relative_to(REPO_ROOT).as_posix(),
                        "line_number": idx,
                        "code_snippet": line.strip()[:100],
                        "pattern_matched": pat,
                        "description": desc,
                        "impact_on_high_frequency_data": "Breaks or requires physical-time resampling if dt < 1h" if "shift" in pat or "rolling" in pat else "Minor / Standard unit conversion"
                    })

    df_sample = pd.DataFrame(findings)
    print(f"Total potential sampling assumptions identified: {len(df_sample)}")
    df_sample.to_csv(OUTPUT_DIR / "sampling_assumption_audit.csv", index=False)


# =====================================================================
# MAIN ENTRY
# =====================================================================
if __name__ == "__main__":
    df = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    test_raw_df = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    print("==================================================================", flush=True)
    print("RUNNING PARALLEL POPULATION EXTRACTION ACROSS 7 SEEDS (7 CORES)", flush=True)
    print("==================================================================", flush=True)

    t0 = time.time()
    tasks = [(s, test_raw_df) for s in SEEDS]
    with ProcessPoolExecutor(max_workers=7) as executor:
        all_record_lists = list(executor.map(extract_single_seed_records, tasks))

    all_records = []
    for rlist in all_record_lists:
        all_records.extend(rlist)

    df_pop = pd.DataFrame(all_records)
    print(f"Extraction completed in {time.time() - t0:.2f}s | Total candidate jump events: {len(df_pop)}")

    # 2. Analyze distributions
    analyze_and_save_all_distributions(df_pop)

    # 3. Audit uncertainty
    audit_uncertainty_decomposition(test_raw_df)

    # 4. Audit sampling assumptions
    audit_sampling_assumptions()

    print("\nStep 4 Forensic Analysis Complete.")
