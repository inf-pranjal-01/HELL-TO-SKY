"""
scratch/precision_forensics/run_step15_gap_benchmark.py

Step 15 Benchmark:
Evaluates:
1. Baseline Reference (Variant 0)
2. Step 12 Reference (Channel-scaled jump, capped dt_eff)
3. Step 14 Variant B (Cold-start safe: prior_val is not None)
4. Step 14 Variant C (Fixed 2.5h boundary + continuous linear scaling)
5. Step 15 Empirical Gap Model:
   - Data-derived nominal cadence: dt_nominal = 1.0h (inferred from median(dt))
   - Consecutive jump test eligible ONLY when dt <= 1.5 * dt_nominal (i.e. single consecutive cycle)
   - When dt > 1.5 * dt_nominal (data gap), instantaneous jump test against stale predecessor is disabled;
     observation is evaluated causally via Tier 2/3/4 expectation and predictive uncertainty.
   - Cold start: prior_val is not None strictly enforced.
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
    floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    dt_eff = min(1.5, max(0.1, dt_hours))
    var_jump = 2.0 * (floor ** 2) + (floor ** 2) * dt_eff
    return math.sqrt(var_jump)


def score_variant_evaluation(
    model_name: str,
    raw_reading: dict,
    history_df: pd.DataFrame,
    neighbor_buffers: dict = None,
) -> dict:
    """
    model_name in:
      - "baseline"
      - "step12"
      - "step14_b"
      - "step14_c"
      - "step15_empirical"
    """
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # Tier 0 Hard Invariants
    is_rail, rail_param, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    if is_rail:
        fault_type = "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"
        return {"is_anomaly": True, "fault_type": fault_type, "decision_basis": "TIER_0_HARD_INVARIANT"}

    temp_c = raw_reading.get("temperature_c")
    pressure_hpa = raw_reading.get("pressure_hpa")
    humidity_pct = raw_reading.get("humidity_pct")
    is_phys_impossible, _ = CrossChannelEngine.check_physical_invariants(temp_c, pressure_hpa, humidity_pct)
    if is_phys_impossible:
        return {"is_anomaly": True, "fault_type": "physical_bounds", "decision_basis": "TIER_0_THERMODYNAMIC_BOUND"}

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

    # Tier 1 Specialist
    tier1_evidence = []
    for param in PARAMS:
        val = float(raw_reading[param])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        
        prior_val = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                prior_val = float(valid_pvals.iloc[-1])

        jump_eligible = False
        jump_mag = 0.0
        sigma_jump = 0.20

        if model_name == "baseline":
            if prior_val is not None:
                jump_mag = abs(val - prior_val)
            else:
                jump_mag = abs(val - expectations[param])
            if jump_mag >= 2.5 * sensor_floor:
                sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))
                jump_eligible = True

        elif model_name == "step12":
            if prior_val is not None:
                jump_mag = abs(val - prior_val)
            else:
                jump_mag = abs(val - expectations[param])
            if jump_mag >= 2.5 * sensor_floor:
                sigma_jump = compute_channel_scaled_sigma_jump(param, dt_hours)
                jump_eligible = True

        elif model_name == "step14_b":
            if prior_val is not None:
                jump_mag = abs(val - prior_val)
                if jump_mag >= 2.5 * sensor_floor:
                    sigma_jump = compute_channel_scaled_sigma_jump(param, dt_hours)
                    jump_eligible = True

        elif model_name == "step14_c":
            if prior_val is not None:
                jump_mag = abs(val - prior_val)
                if jump_mag >= 2.5 * sensor_floor:
                    if dt_hours <= 2.5:
                        sigma_jump = compute_channel_scaled_sigma_jump(param, dt_hours)
                    else:
                        sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
                    jump_eligible = True

        elif model_name == "step15_empirical":
            # Data-Derived Gap Model:
            # 1. Requires valid causal predecessor (prior_val is not None)
            # 2. Inferred cadence: dt_nominal = 1.0h. Consecutive step if dt_hours <= 1.5h.
            # 3. If consecutive, instantaneous measurement jump sigma_jump = sqrt(2*floor^2 + floor^2 * dt).
            # 4. If dt_hours > 1.5h (gap), instantaneous jump is disabled (evaluated via expectation).
            if prior_val is not None and dt_hours <= 1.5:
                jump_mag = abs(val - prior_val)
                if jump_mag >= 2.5 * sensor_floor:
                    sigma_jump = compute_channel_scaled_sigma_jump(param, dt_hours)
                    jump_eligible = True

        if jump_eligible:
            z_jump = jump_mag / max(1e-4, sigma_jump)
            jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
            if jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0:
                tier1_evidence.append({
                    "tier": 1, "type": "spike", "parameter": param, "llr": jump_llr,
                    "confidence": min(98.0, 85.0 + jump_llr),
                    "reason": f"Instantaneous jump {jump_mag:.2f} (z={z_jump:.2f})",
                    "observed_value": val
                })

        # Frozen evaluation
        peer_disp = peer_dispersions.get(param)
        n_p = len(neighbor_buffers) if neighbor_buffers else 0
        f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(param, history_df, val, peer_disp, n_p)
        if f_diag["is_frozen"]:
            tier1_evidence.append({
                "tier": 1, "type": "frozen_value", "parameter": param, "llr": f_llr,
                "confidence": min(98.0, 85.0 + f_llr), "reason": f_reason, "observed_value": val
            })

    if tier1_evidence:
        strongest = max(tier1_evidence, key=lambda e: e["llr"])
        return {
            "is_anomaly": True, "fault_type": strongest["type"],
            "anomaly_score_pct": float(strongest["confidence"]),
            "decision_basis": f"TIER_1_SPECIALIST_{strongest['type'].upper()}",
            "likely_faulty_sensors": [strongest["parameter"]],
            "rules_fired": tier1_evidence,
        }

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
                "tier": 2, "type": "drift", "parameter": param, "llr": drift_llr,
                "confidence": min(95.0, 80.0 + drift_llr),
                "reason": f"SPRT drift LLR={drift_llr:.2f}",
                "observed_value": float(raw_reading[param])
            })

    if tier2_evidence:
        strongest = max(tier2_evidence, key=lambda e: e["llr"])
        return {
            "is_anomaly": True, "fault_type": "drift",
            "anomaly_score_pct": float(strongest["confidence"]),
            "decision_basis": "TIER_2_PERSISTENT_DRIFT",
            "likely_faulty_sensors": [strongest["parameter"]],
            "rules_fired": tier2_evidence,
        }

    # Tier 3 Mahalanobis
    z_map = {p: innovations[p] / max(1e-4, uncertainties[p]) for p in PARAMS}
    d_sq, p_val, cc_diag = CrossChannelEngine.compute_mahalanobis_distance(
        z_map["temperature_c"], z_map["pressure_hpa"], z_map["humidity_pct"]
    )
    if cc_diag["is_multivariate_outlier"]:
        return {
            "is_anomaly": True, "fault_type": "multivariate_inconsistency",
            "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_MAHALANOBIS",
            "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"Mahalanobis D^2={d_sq:.2f}"}],
        }

    return {"is_anomaly": False, "fault_type": None, "anomaly_score_pct": 5.0, "decision_basis": "NORMAL"}


def eval_seed_all_models(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    models = ["baseline", "step12", "step14_b", "step14_c", "step15_empirical"]
    
    results = {}
    rows = eval_df.to_dict("records")

    for m in models:
        buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
        tp = fp = fn = tn = 0
        lost_tps = []

        for row in rows:
            st_id = row["station_id"]
            ts = row["timestamp"]
            gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
            ftype = row.get("fault_type", "normal") if gt else "normal"

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

            verdict = score_variant_evaluation(m, raw_reading, hist_df, neighbor_bufs)
            is_pred = bool(verdict["is_anomaly"])
            buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

            if is_pred and gt:
                tp += 1
            elif is_pred and not gt:
                fp += 1
            elif not is_pred and gt:
                fn += 1
                lost_tps.append({"station": st_id, "timestamp": ts, "fault_type": ftype})
            else:
                tn += 1

        prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        results[m] = {
            "seed": seed, "model": m,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "prec": prec, "rec": rec, "f1": f1,
            "lost_tps": lost_tps
        }

    return results


def main():
    print("=" * 80)
    print("STEP 15 BENCHMARK: DATA-DERIVED EMPIRICAL GAP MODEL EVALUATION")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)
    print(f"Evaluating test split ({len(df_test_raw)} rows across {df_test_raw['station_id'].nunique()} stations)...")

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(eval_seed_all_models, tasks))

    models = ["baseline", "step12", "step14_b", "step14_c", "step15_empirical"]
    mod_names = {
        "baseline": "Original Baseline Reference",
        "step12": "Step 12 Reference (Channel-Scaled Jump)",
        "step14_b": "Step 14 Variant B (Cold-Start Safe)",
        "step14_c": "Step 14 Variant C (Cadence-Adaptive Gap)",
        "step15_empirical": "Step 15 Data-Derived Empirical Gap Model"
    }

    summary_rows = []
    for m in models:
        m_runs = [r[m] for r in results]
        df_m = pd.DataFrame(m_runs)
        summary_rows.append({
            "model": m,
            "name": mod_names[m],
            "macro_precision": df_m["prec"].mean(),
            "macro_recall": df_m["rec"].mean(),
            "macro_f1": df_m["f1"].mean(),
            "mean_tp": df_m["tp"].mean(),
            "mean_fp": df_m["fp"].mean(),
            "mean_fn": df_m["fn"].mean(),
        })

    sum_df = pd.DataFrame(summary_rows)
    print("\n" + "=" * 80)
    print("STEP 15 MACRO BENCHMARK SUMMARY (7 LOCKED SEEDS)")
    print("=" * 80)
    print(sum_df[["name", "macro_precision", "macro_recall", "macro_f1", "mean_tp", "mean_fp", "mean_fn"]].to_string(index=False))

    # Print per-seed for Step 15
    print("\n--- Step 15 Data-Derived Empirical Gap Model Per-Seed Breakdown ---")
    s15_runs = [r["step15_empirical"] for r in results]
    print(pd.DataFrame(s15_runs)[["seed", "tp", "fp", "fn", "prec", "rec", "f1"]].to_string(index=False))

    # Save summary CSV
    sum_df.to_csv(OUTPUT_DIR / "step15_final_macro_summary.csv", index=False)
    
    all_runs = []
    for m in models:
        for r in results:
            item = r[m]
            all_runs.append({
                "model": m, "seed": item["seed"],
                "tp": item["tp"], "fp": item["fp"], "fn": item["fn"], "tn": item["tn"],
                "precision": item["prec"], "recall": item["rec"], "f1": item["f1"]
            })
    pd.DataFrame(all_runs).to_csv(OUTPUT_DIR / "step15_all_models_per_seed.csv", index=False)
    print(f"\nSaved benchmark outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
