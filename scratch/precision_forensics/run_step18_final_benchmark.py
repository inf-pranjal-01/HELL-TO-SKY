"""
scratch/precision_forensics/run_step18_final_benchmark.py

Authoritative Step 18 Benchmark:
Evaluates Tier 3 Instantaneous Cross-Channel Innovation Engine variants
with strictly isolated per-configuration buffer lifecycles across all 7 locked seeds.
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
from model.cross_channel_covariance import CrossChannelEngine, compute_dewpoint_c
from model.state import StationBuffer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = SequentialSPRT.get_wald_boundaries(alpha=0.002, beta=0.05)

# Clean 1-hour Empirical Covariance & Correlation (from 70% clean training partition)
COV_DELTA_1H = np.array([
    [ 1.779049, -0.016319, -6.494229],
    [-0.016319,  0.452587,  0.250640],
    [-6.494229,  0.250640, 32.893058]
], dtype=float)

CORR_DELTA = np.array([
    [ 1.000000, -0.018186, -0.848949],
    [-0.018186,  1.000000,  0.064960],
    [-0.848949,  0.064960,  1.000000]
], dtype=float)

INV_COV_DELTA_1H = np.linalg.pinv(COV_DELTA_1H + 1e-5 * np.eye(3))
INV_CORR_DELTA = np.linalg.pinv(CORR_DELTA + 1e-5 * np.eye(3))

SIGMA_CLEAN_DIFF = {
    "temperature_c": math.sqrt(1.779049),
    "pressure_hpa": math.sqrt(0.452587),
    "humidity_pct": math.sqrt(32.893058)
}


def score_config_reading(
    config_id: int,
    raw_reading: dict,
    history_df: pd.DataFrame,
    neighbor_buffers: dict = None,
) -> dict:
    """
    config_id:
      0 = Config 0: Original Locked Baseline Reference (Static Climatological Tier 3)
      1 = Config 1: Step 16 Locked Experimental Baseline (Cold-start Safe + Continuous Gap Jump, Static Climatological Tier 3)
      2 = Config 2: Step 18 Variant A (Instantaneous Innovation Covariance Sigma_Delta)
      3 = Config 3: Step 18 Variant B (Instantaneous Innovation Correlation R_Delta)
      4 = Config 4: Step 18 Variant C (Instantaneous Thermodynamic Co-directionality)
    """
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # ── TIER 0: Hard Invariants & Hardware Rails ──────────────────────
    is_rail, rail_param, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    if is_rail:
        fault_type = "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"
        return {"is_anomaly": True, "fault_type": fault_type, "decision_basis": "TIER_0_HARD_INVARIANT", "tier": 0}

    temp_c = raw_reading.get("temperature_c")
    pressure_hpa = raw_reading.get("pressure_hpa")
    humidity_pct = raw_reading.get("humidity_pct")
    is_phys_impossible, _ = CrossChannelEngine.check_physical_invariants(temp_c, pressure_hpa, humidity_pct)
    if is_phys_impossible:
        return {"is_anomaly": True, "fault_type": "physical_bounds", "decision_basis": "TIER_0_THERMODYNAMIC_BOUND", "tier": 0}

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
    z_scores = {}
    peer_medians = {}
    peer_dispersions = {}
    prior_vals = {}
    dy_vals = {}

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
        res = val - exp_val
        innovations[param] = res
        z_scores[param] = res / max(1e-4, sigma_tot)

        p_val = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                p_val = float(valid_pvals.iloc[-1])
        prior_vals[param] = p_val
        dy_vals[param] = (val - p_val) if p_val is not None else None

    # ── TIER 1: Specialist Faults (Spike & Frozen) ────────────────────
    tier1_evidence = []
    for param in PARAMS:
        val = float(raw_reading[param])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        p_val = prior_vals[param]

        jump_eligible = False
        jump_mag = 0.0
        sigma_jump = 0.20

        if config_id == 0:
            # Baseline: placeholder 0.25*dt, fallback to exp_val if prior is None
            if p_val is not None:
                jump_mag = abs(val - p_val)
            else:
                jump_mag = abs(val - expectations[param])
            if jump_mag >= 2.5 * sensor_floor:
                sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))
                jump_eligible = True

        else:
            # Step 16 / Step 18 Jump: strictly requires prior_val, continuous floor^2 * dt scaling
            if p_val is not None:
                jump_mag = abs(val - p_val)
                if jump_mag >= 2.5 * sensor_floor:
                    sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
                    jump_eligible = True

        if jump_eligible:
            z_jump = jump_mag / max(1e-4, sigma_jump)
            jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
            if jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0:
                tier1_evidence.append({
                    "tier": 1, "type": "spike", "parameter": param, "llr": jump_llr,
                    "confidence": min(98.0, 85.0 + jump_llr),
                    "reason": f"Instantaneous jump {jump_mag:.2f} (z={z_jump:.2f}, LLR={jump_llr:.2f})",
                    "observed_value": val
                })

        # Frozen evaluation (Identical across all configurations)
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
            "tier": 1
        }

    # ── TIER 2: Persistent Temporal Faults (SPRT Drift) ───────────────
    tier2_evidence = []
    for param in PARAMS:
        residual = innovations[param]
        sigma_tot = uncertainties[param]
        prior_res = None
        p_val = prior_vals[param]
        if p_val is not None:
            prior_res = p_val - expectations[param]

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
            "tier": 2
        }

    # ── TIER 3: Cross-Channel Mahalanobis Evaluators ──────────────────
    if config_id in [0, 1]:
        # Static Climatological Mahalanobis
        d_sq, p_val, cc_diag = CrossChannelEngine.compute_mahalanobis_distance(
            z_scores["temperature_c"], z_scores["pressure_hpa"], z_scores["humidity_pct"]
        )
        if cc_diag["is_multivariate_outlier"]:
            return {
                "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_STATIC_MAHALANOBIS",
                "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
                "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"Mahalanobis D^2={d_sq:.2f}"}],
                "tier": 3
            }

    elif config_id == 2:
        # Step 18 Variant A: Instantaneous Covariance Mahalanobis: D^2 = dy^T (Sigma * dt)^-1 dy
        if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
            dy_vec = np.array([dy_vals["temperature_c"], dy_vals["pressure_hpa"], dy_vals["humidity_pct"]], dtype=float)
            cov_dt = COV_DELTA_1H * dt_hours
            inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
            d_sq = float(dy_vec.T @ inv_cov_dt @ dy_vec)
            if d_sq > 16.27:
                return {
                    "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_INSTANT_COV",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
                    "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"Instantaneous Covariance D^2={d_sq:.2f}"}],
                    "tier": 3
                }

    elif config_id == 3:
        # Step 18 Variant B: Instantaneous Standardized Correlation Mahalanobis: dz_p = dy_p / (sigma_clean * sqrt(dt))
        if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
            dz_vec = np.array([
                dy_vals["temperature_c"] / (SIGMA_CLEAN_DIFF["temperature_c"] * math.sqrt(dt_hours)),
                dy_vals["pressure_hpa"] / (SIGMA_CLEAN_DIFF["pressure_hpa"] * math.sqrt(dt_hours)),
                dy_vals["humidity_pct"] / (SIGMA_CLEAN_DIFF["humidity_pct"] * math.sqrt(dt_hours))
            ], dtype=float)
            d_sq = float(dz_vec.T @ INV_CORR_DELTA @ dz_vec)
            if d_sq > 16.27:
                return {
                    "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_INSTANT_CORR",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
                    "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"Instantaneous Correlation D^2={d_sq:.2f}"}],
                    "tier": 3
                }

    elif config_id == 4:
        # Step 18 Variant C: Instantaneous Thermodynamic Co-directionality
        if dy_vals["temperature_c"] is not None and dy_vals["humidity_pct"] is not None and dt_hours <= 2.5:
            dy_t = dy_vals["temperature_c"]
            dy_h = dy_vals["humidity_pct"]
            s_t = SIGMA_CLEAN_DIFF["temperature_c"] * math.sqrt(dt_hours)
            s_h = SIGMA_CLEAN_DIFF["humidity_pct"] * math.sqrt(dt_hours)
            if (dy_t * dy_h > 0) and (abs(dy_t) > 2.0 * s_t) and (abs(dy_h) > 2.0 * s_h):
                return {
                    "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_THERMO_INNOVATION",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
                    "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"Thermodynamic Co-directionality Surge"}],
                    "tier": 3
                }

    return {"is_anomaly": False, "fault_type": None, "anomaly_score_pct": 5.0, "decision_basis": "NORMAL", "tier": -1}


def eval_seed_step18(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    configs = [0, 1, 2, 3, 4]
    
    results = {}
    rows = eval_df.to_dict("records")

    for cid in configs:
        buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
        tp = fp = fn = tn = 0
        tier_counts = {}
        fault_tp = {}
        fp_details = []

        for row in rows:
            st_id = row["station_id"]
            ts = row["timestamp"]
            gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
            fault_type = row.get("fault_type", "unknown") if gt else None

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

            verdict = score_config_reading(cid, raw_reading, hist_df, neighbor_bufs)
            is_pred = bool(verdict["is_anomaly"])
            buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

            tier_num = verdict.get("tier", -1)
            t_key = f"tier{tier_num}"

            if is_pred and gt:
                tp += 1
                tier_counts[t_key] = tier_counts.get(t_key, 0) + 1
                if fault_type:
                    fault_tp[fault_type] = fault_tp.get(fault_type, 0) + 1
            elif is_pred and not gt:
                fp += 1
                tier_counts[t_key] = tier_counts.get(t_key, 0) + 1
                fp_details.append({"station": st_id, "timestamp": ts, "basis": verdict.get("decision_basis"), "tier": tier_num})
            elif not is_pred and gt:
                fn += 1
            else:
                tn += 1

        prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        results[cid] = {
            "seed": seed, "config_id": cid,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "prec": prec, "rec": rec, "f1": f1,
            "tier_counts": tier_counts, "fault_tp": fault_tp,
            "fp_details": fp_details
        }

    return results


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 18: AUTHORITATIVE MULTI-CONFIGURATION BENCHMARK (7 LOCKED SEEDS)")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)
    print(f"Test Stream: {len(df_test_raw)} observations across {df_test_raw['station_id'].nunique()} stations.")

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(eval_seed_step18, tasks))

    elapsed = time.time() - t0
    print(f"Parallel evaluation completed in {elapsed:.2f} seconds!")

    cfg_names = {
        0: "CONFIG 0: Original Locked Baseline Reference",
        1: "CONFIG 1: Step 16 Locked Experimental Baseline (Static Mahalanobis)",
        2: "CONFIG 2: Step 18 Variant A (Instantaneous Innovation Covariance Sigma_Delta)",
        3: "CONFIG 3: Step 18 Variant B (Instantaneous Innovation Correlation R_Delta)",
        4: "CONFIG 4: Step 18 Variant C (Instantaneous Thermodynamic Co-directionality)"
    }

    summary_rows = []
    for cid in [0, 1, 2, 3, 4]:
        c_runs = [r[cid] for r in results]
        df_c = pd.DataFrame(c_runs)
        summary_rows.append({
            "config_id": cid,
            "name": cfg_names[cid],
            "macro_precision": df_c["prec"].mean(),
            "macro_recall": df_c["rec"].mean(),
            "macro_f1": df_c["f1"].mean(),
            "mean_tp": df_c["tp"].mean(),
            "mean_fp": df_c["fp"].mean(),
            "mean_fn": df_c["fn"].mean(),
        })

    sum_df = pd.DataFrame(summary_rows)
    print("\n" + "=" * 80)
    print("STEP 18 MACRO BENCHMARK SUMMARY ACROSS 7 LOCKED SEEDS")
    print("=" * 80)
    print(sum_df[["config_id", "macro_precision", "macro_recall", "macro_f1", "mean_tp", "mean_fp", "mean_fn"]].to_string(index=False))

    # Detailed per-seed breakdown
    for cid in [0, 1, 2, 3, 4]:
        print(f"\n--- {cfg_names[cid]} ---")
        c_runs = [r[cid] for r in results]
        print(pd.DataFrame(c_runs)[["seed", "tp", "fp", "fn", "prec", "rec", "f1"]].to_string(index=False))

    # Tier breakdown across configurations
    print("\n" + "=" * 80)
    print("AVERAGE DETECTIONS BY TIER (PER SEED)")
    print("=" * 80)
    for cid in [0, 1, 2, 3, 4]:
        c_runs = [r[cid] for r in results]
        tier_keys = ["tier0", "tier1", "tier2", "tier3"]
        tier_means = {}
        for tk in tier_keys:
            tier_means[tk] = np.mean([r["tier_counts"].get(tk, 0) for r in c_runs])
        print(f"{cfg_names[cid][:45]:<45} | T0: {tier_means['tier0']:<6.1f} | T1: {tier_means['tier1']:<7.1f} | T2: {tier_means['tier2']:<6.1f} | T3: {tier_means['tier3']:<7.1f}")

    # Save summary files
    sum_df.to_csv(OUTPUT_DIR / "step18_final_macro_summary.csv", index=False)
    
    all_runs = []
    for cid in [0, 1, 2, 3, 4]:
        for r in results:
            item = r[cid]
            all_runs.append({
                "config_id": cid, "config_name": cfg_names[cid], "seed": item["seed"],
                "tp": item["tp"], "fp": item["fp"], "fn": item["fn"], "tn": item["tn"],
                "precision": item["prec"], "recall": item["rec"], "f1": item["f1"],
                "tier_counts": item["tier_counts"]
            })
    pd.DataFrame(all_runs).to_csv(OUTPUT_DIR / "step18_final_all_configs_per_seed.csv", index=False)
    print(f"\nOutputs saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
