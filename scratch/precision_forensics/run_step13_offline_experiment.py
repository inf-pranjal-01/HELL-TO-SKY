"""
scratch/precision_forensics/run_step13_offline_experiment.py

Offline Experiment: Evaluates the effect of:
1. Causal Gap Handling: Restricting instantaneous spike evaluation to consecutive measurements (dt <= 2.5 hr, prior_val exists).
2. Proper gap uncertainty for dt > 2.5 hr.
3. Additive non-destructive environmental disambiguation.

Measures exact P, R, F1 across all 7 locked seeds.
"""

import sys
import math
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
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

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = SequentialSPRT.get_wald_boundaries(alpha=0.002, beta=0.05)


def compute_channel_scaled_sigma_jump(param: str, dt_hours: float) -> float:
    """Channel-scaled jump uncertainty for consecutive readings (dt <= 2.5 hr)."""
    floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    dt_eff = min(2.5, max(0.1, dt_hours))
    var_jump = 2.0 * (floor ** 2) + (floor ** 2) * dt_eff
    return math.sqrt(var_jump)


def score_offline_candidate(raw_reading: dict, history_df: pd.DataFrame, neighbor_buffers: dict = None) -> dict:
    """
    Offline Candidate:
    - Channel-scaled sigma_jump for genuine consecutive steps (dt <= 2.5 hr).
    - If dt > 2.5 hr or cold start (prior_val is None), instantaneous spike rule does NOT fire on jump_mag vs default exp;
      instead standard composite expectation/uncertainty is evaluated.
    """
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # Hard rails
    is_rail, rail_param, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    if is_rail:
        return {"is_anomaly": True, "fault_type": "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"}

    temp_c = raw_reading.get("temperature_c")
    pressure_hpa = raw_reading.get("pressure_hpa")
    humidity_pct = raw_reading.get("humidity_pct")
    is_phys_impossible, _ = CrossChannelEngine.check_physical_invariants(temp_c, pressure_hpa, humidity_pct)
    if is_phys_impossible:
        return {"is_anomaly": True, "fault_type": "physical_bounds"}

    prior_time = None
    if not history_df.empty and "timestamp" in history_df.columns:
        valid_ts = pd.to_datetime(history_df["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]
    dt_hours = max(0.1, (current_time - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(current_time, station_id)

    expectations = {}
    uncertainties = {}
    innovations = {}
    peer_medians = {}
    peer_dispersions = {}

    for param in PARAMS:
        val = float(raw_reading[param])
        peer_med, peer_disp, n_peers = PeerSpatialEngine.compute_robust_peer_consensus(
            station_id, param, current_time, neighbor_buffers or {}
        )
        peer_medians[param] = peer_med
        peer_dispersions[param] = peer_disp
        
        exp_val, _ = compute_dynamic_expectation(station_id, param, current_time, history_df)
        expectations[param] = exp_val
        
        sigma_tot, _ = UncertaintyBudget.compute_composite_predictive_uncertainty(
            param, solar_hour, dt_hours, history_df, peer_dispersion=peer_disp or 0.0
        )
        uncertainties[param] = sigma_tot
        innovations[param] = val - exp_val

    tier1_evidence = []
    for param in PARAMS:
        val = float(raw_reading[param])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        
        prior_val = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                prior_val = float(valid_pvals.iloc[-1])

        # Instantaneous spike check ONLY on consecutive valid readings (dt <= 2.5 hr and prior_val is not None)
        if prior_val is not None and dt_hours <= 2.5:
            jump_mag = abs(val - prior_val)
            if jump_mag >= 2.5 * sensor_floor:
                sigma_jump = compute_channel_scaled_sigma_jump(param, dt_hours)
                z_jump = jump_mag / max(1e-4, sigma_jump)
                jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
                
                if jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0:
                    tier1_evidence.append({
                        "tier": 1, "type": "spike", "parameter": param, "llr": jump_llr
                    })

        # Frozen check
        peer_disp = peer_dispersions.get(param)
        n_p = len(neighbor_buffers) if neighbor_buffers else 0
        f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(param, history_df, val, peer_disp, n_p)
        if f_diag["is_frozen"]:
            tier1_evidence.append({"tier": 1, "type": "frozen_value", "parameter": param, "llr": f_llr})

    if tier1_evidence:
        strongest = max(tier1_evidence, key=lambda e: e["llr"])
        return {"is_anomaly": True, "fault_type": strongest["type"]}

    # Tier 2 SPRT Drift
    tier2_evidence = []
    for param in PARAMS:
        residual = innovations[param]
        sigma_tot = uncertainties[param]
        prior_res = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                prior_res = float(valid_pvals.iloc[-1]) - expectations[param]

        whitened_eps = SequentialSPRT.pre_whiten_residual(param, residual, prior_res, dt_hours, sigma_tot)
        s_pos, s_neg, drift_llr = SequentialSPRT.update_cusum(
            param, s_pos_prev=0.0, s_neg_prev=0.0,
            whitened_epsilon=whitened_eps, dt_hours=dt_hours, current_sigma=sigma_tot
        )
        
        peer_med = peer_medians.get(param)
        if peer_med is not None and (len(neighbor_buffers) if neighbor_buffers else 0) >= 2:
            peer_res = peer_med - expectations[param]
            if (residual * peer_res) < 0 and abs(residual) > 2.0 * sigma_tot:
                drift_llr *= 1.4

        if drift_llr >= WALD_UPPER_ALERT:
            tier2_evidence.append({
                "tier": 2, "type": "drift", "parameter": param, "llr": drift_llr
            })

    if tier2_evidence:
        strongest = max(tier2_evidence, key=lambda e: e["llr"])
        return {"is_anomaly": True, "fault_type": "drift"}

    return {"is_anomaly": False, "fault_type": None}


def eval_seed_candidate(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    
    tp = fp = fn = 0
    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False

        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        buf = buffers[st_id]
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
        hist_df = buf.raw_history_df()

        raw_reading = {
            "station_id": st_id, "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }

        verdict = score_offline_candidate(raw_reading, hist_df, neighbor_bufs)
        is_pred = bool(verdict["is_anomaly"])
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

        if is_pred and gt:
            tp += 1
        elif is_pred and not gt:
            fp += 1
        elif not is_pred and gt:
            fn += 1

    prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    return {"seed": seed, "tp": tp, "fp": fp, "fn": fn, "prec": prec, "rec": rec, "f1": f1}


def main():
    print("=" * 80)
    print("RUNNING OFFLINE GAP-AWARE CAUSAL SPIKE BENCHMARK ACROSS 7 SEEDS")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(eval_seed_candidate, tasks))

    res_df = pd.DataFrame(results)
    macro_p = res_df["prec"].mean()
    macro_r = res_df["rec"].mean()
    macro_f1 = res_df["f1"].mean()
    mean_tp = res_df["tp"].mean()
    mean_fp = res_df["fp"].mean()
    mean_fn = res_df["fn"].mean()

    print("\n--- OFFLINE CANDIDATE BENCHMARK RESULTS ---")
    print(res_df.to_string(index=False))
    print("\n" + "=" * 80)
    print(f"MACRO RESULTS: Precision = {macro_p:.2f}% | Recall = {macro_r:.2f}% | F1 = {macro_f1:.2f}%")
    print(f"Mean TP = {mean_tp:.1f} | Mean FP = {mean_fp:.1f} | Mean FN = {mean_fn:.1f}")
    print("=" * 80)

    res_df.to_csv(OUTPUT_DIR / "step13_offline_gap_aware_results.csv", index=False)

if __name__ == "__main__":
    main()
