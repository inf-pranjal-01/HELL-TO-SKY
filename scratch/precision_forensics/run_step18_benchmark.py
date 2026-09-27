"""
scratch/precision_forensics/run_step18_benchmark.py

Highly Optimized Step 18 Benchmark:
Evaluates Tier 3 Instantaneous Cross-Channel Innovation Engine variants
alongside Original Baseline and Step 16 Baseline across all 7 locked seeds.
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


def score_reading_multi_config(
    raw_reading: dict,
    history_df: pd.DataFrame,
    neighbor_buffers: dict = None
) -> dict:
    """
    Evaluates Tier 0, 1, 2, and all Tier 3 candidate variants in a single pass.
    Returns dictionary of verdicts keyed by config name.
    """
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # ── Tier 0: Hard Invariants & Hardware Rails ─────────────────────────
    is_rail, rail_param, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    if is_rail:
        fault_type = "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"
        res = {"is_anomaly": True, "fault_type": fault_type, "decision_basis": "TIER_0_HARD_INVARIANT", "tier": 0}
        return {
            "baseline": res, "step16": res, "step18_instant_cov": res,
            "step18_instant_corr": res, "step18_thermo_innovation": res
        }

    temp_c = raw_reading.get("temperature_c")
    pressure_hpa = raw_reading.get("pressure_hpa")
    humidity_pct = raw_reading.get("humidity_pct")
    is_phys_impossible, _ = CrossChannelEngine.check_physical_invariants(temp_c, pressure_hpa, humidity_pct)
    if is_phys_impossible:
        res = {"is_anomaly": True, "fault_type": "physical_bounds", "decision_basis": "TIER_0_THERMODYNAMIC_BOUND", "tier": 0}
        return {
            "baseline": res, "step16": res, "step18_instant_cov": res,
            "step18_instant_corr": res, "step18_thermo_innovation": res
        }

    # ── Elapsed Time & Dynamic Expectations ──────────────────────────────
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
    z_predictive = {}
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
        z_predictive[param] = res / max(1e-4, sigma_tot)

        p_val = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                p_val = float(valid_pvals.iloc[-1])
        prior_vals[param] = p_val
        dy_vals[param] = (val - p_val) if p_val is not None else None

    # ── Tier 1: Specialist Faults (Spike & Frozen) ───────────────────────
    # We evaluate both Baseline Jump and Step 16/18 Gap-Safe Jump
    t1_base_ev = []
    t1_step16_ev = []

    for param in PARAMS:
        val = float(raw_reading[param])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        p_val = prior_vals[param]

        # 1a. Baseline Jump: fallback to exp_val on cold start, 0.25*dt in sigma
        jump_mag_b = abs(val - p_val) if p_val is not None else abs(val - expectations[param])
        if jump_mag_b >= 2.5 * sensor_floor:
            sig_j_b = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))
            z_j_b = jump_mag_b / max(1e-4, sig_j_b)
            llr_b = float(0.5 * (z_j_b ** 2) - math.log(max(1.1, sig_j_b / sensor_floor)))
            if llr_b >= WALD_UPPER_ALERT and z_j_b >= 3.0:
                t1_base_ev.append({
                    "tier": 1, "type": "spike", "parameter": param, "llr": llr_b,
                    "confidence": min(98.0, 85.0 + llr_b), "observed_value": val
                })

        # 1b. Step 16/18 Jump: strictly requires p_val (cold-start safe), continuous floor^2 * dt scaling
        if p_val is not None:
            jump_mag_16 = abs(val - p_val)
            if jump_mag_16 >= 2.5 * sensor_floor:
                sig_j_16 = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
                z_j_16 = jump_mag_16 / max(1e-4, sig_j_16)
                llr_16 = float(0.5 * (z_j_16 ** 2) - math.log(max(1.1, sig_j_16 / sensor_floor)))
                if llr_16 >= WALD_UPPER_ALERT and z_j_16 >= 3.0:
                    t1_step16_ev.append({
                        "tier": 1, "type": "spike", "parameter": param, "llr": llr_16,
                        "confidence": min(98.0, 85.0 + llr_16), "observed_value": val
                    })

        # Frozen evaluation (Identical across all)
        peer_disp = peer_dispersions.get(param)
        n_p = len(neighbor_buffers) if neighbor_buffers else 0
        f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(param, history_df, val, peer_disp, n_p)
        if f_diag["is_frozen"]:
            f_item = {
                "tier": 1, "type": "frozen_value", "parameter": param, "llr": f_llr,
                "confidence": min(98.0, 85.0 + f_llr), "observed_value": val
            }
            t1_base_ev.append(f_item)
            t1_step16_ev.append(f_item)

    # ── Tier 2: Persistent Drift (SPRT CUSUM) ────────────────────────────
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
                "confidence": min(95.0, 80.0 + drift_llr), "observed_value": float(raw_reading[param])
            })

    # Helper to resolve early tier verdicts
    def get_tier1_2_verdict(t1_ev):
        if t1_ev:
            st = max(t1_ev, key=lambda e: e["llr"])
            return {"is_anomaly": True, "fault_type": st["type"], "decision_basis": f"TIER_1_SPECIALIST_{st['type'].upper()}", "tier": 1}
        if tier2_evidence:
            st = max(tier2_evidence, key=lambda e: e["llr"])
            return {"is_anomaly": True, "fault_type": "drift", "decision_basis": "TIER_2_PERSISTENT_DRIFT", "tier": 2}
        return None

    res_base = get_tier1_2_verdict(t1_base_ev)
    res_16 = get_tier1_2_verdict(t1_step16_ev)

    # ── Tier 3 Evaluators ────────────────────────────────────────────────
    # 1. Static Climatological Mahalanobis (Old Tier 3)
    d_sq_static, p_val_static, cc_static = CrossChannelEngine.compute_mahalanobis_distance(
        z_predictive["temperature_c"], z_predictive["pressure_hpa"], z_predictive["humidity_pct"]
    )
    t3_static_outlier = cc_static["is_multivariate_outlier"]

    # 2. Instantaneous Covariance Mahalanobis: D^2 = dy^T (Sigma * dt)^-1 dy
    t3_instant_cov_outlier = False
    if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
        dy_vec = np.array([dy_vals["temperature_c"], dy_vals["pressure_hpa"], dy_vals["humidity_pct"]], dtype=float)
        cov_dt = COV_DELTA_1H * dt_hours
        inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
        d_sq_cov = float(dy_vec.T @ inv_cov_dt @ dy_vec)
        if d_sq_cov > 16.27:
            t3_instant_cov_outlier = True

    # 3. Instantaneous Standardized Correlation Mahalanobis: dz_p = dy_p / (sigma_clean * sqrt(dt))
    t3_instant_corr_outlier = False
    if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
        dz_vec = np.array([
            dy_vals["temperature_c"] / (SIGMA_CLEAN_DIFF["temperature_c"] * math.sqrt(dt_hours)),
            dy_vals["pressure_hpa"] / (SIGMA_CLEAN_DIFF["pressure_hpa"] * math.sqrt(dt_hours)),
            dy_vals["humidity_pct"] / (SIGMA_CLEAN_DIFF["humidity_pct"] * math.sqrt(dt_hours))
        ], dtype=float)
        d_sq_corr = float(dz_vec.T @ INV_CORR_DELTA @ dz_vec)
        if d_sq_corr > 16.27:
            t3_instant_corr_outlier = True

    # 4. Instantaneous Thermodynamic Co-directionality:
    t3_thermo_outlier = False
    if dy_vals["temperature_c"] is not None and dy_vals["humidity_pct"] is not None and dt_hours <= 2.5:
        dy_t = dy_vals["temperature_c"]
        dy_h = dy_vals["humidity_pct"]
        s_t = SIGMA_CLEAN_DIFF["temperature_c"] * math.sqrt(dt_hours)
        s_h = SIGMA_CLEAN_DIFF["humidity_pct"] * math.sqrt(dt_hours)
        # Co-directional movement violation: T and RH move in same direction with statistical significance
        if (dy_t * dy_h > 0) and (abs(dy_t) > 2.0 * s_t) and (abs(dy_h) > 2.0 * s_h):
            t3_thermo_outlier = True

    normal_verdict = {"is_anomaly": False, "fault_type": None, "decision_basis": "NORMAL", "tier": -1}
    t3_static_verdict = {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "decision_basis": "TIER_3_STATIC_MAHALANOBIS", "tier": 3}
    t3_cov_verdict = {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "decision_basis": "TIER_3_INSTANT_COV", "tier": 3}
    t3_corr_verdict = {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "decision_basis": "TIER_3_INSTANT_CORR", "tier": 3}
    t3_thermo_verdict = {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "decision_basis": "TIER_3_THERMO_INNOVATION", "tier": 3}

    verdicts = {
        "baseline": res_base if res_base else (t3_static_verdict if t3_static_outlier else normal_verdict),
        "step16": res_16 if res_16 else (t3_static_verdict if t3_static_outlier else normal_verdict),
        "step18_instant_cov": res_16 if res_16 else (t3_cov_verdict if t3_instant_cov_outlier else normal_verdict),
        "step18_instant_corr": res_16 if res_16 else (t3_corr_verdict if t3_instant_corr_outlier else normal_verdict),
        "step18_thermo_innovation": res_16 if res_16 else (t3_thermo_verdict if t3_thermo_outlier else normal_verdict),
    }

    return verdicts


def eval_single_seed_stream(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

    config_keys = ["baseline", "step16", "step18_instant_cov", "step18_instant_corr", "step18_thermo_innovation"]
    stats = {k: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "tier_counts": {}, "fault_tp": {}} for k in config_keys}

    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type", "unknown") if gt else None

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

        verdicts = score_reading_multi_config(raw_reading, hist_df, neighbor_bufs)

        # Record history using the step18_instant_cov / primary state to maintain stream continuity
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdicts["step18_instant_cov"])

        for k in config_keys:
            v = verdicts[k]
            is_pred = bool(v["is_anomaly"])
            tier_num = v.get("tier", -1)
            t_key = f"tier{tier_num}"

            if is_pred and gt:
                stats[k]["tp"] += 1
                stats[k]["tier_counts"][t_key] = stats[k]["tier_counts"].get(t_key, 0) + 1
                if gt_type:
                    stats[k]["fault_tp"][gt_type] = stats[k]["fault_tp"].get(gt_type, 0) + 1
            elif is_pred and not gt:
                stats[k]["fp"] += 1
                stats[k]["tier_counts"][t_key] = stats[k]["tier_counts"].get(t_key, 0) + 1
            elif not is_pred and gt:
                stats[k]["fn"] += 1
            else:
                stats[k]["tn"] += 1

    seed_results = {}
    for k in config_keys:
        tp = stats[k]["tp"]
        fp = stats[k]["fp"]
        fn = stats[k]["fn"]
        prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        seed_results[k] = {
            "seed": seed, "config": k, "tp": tp, "fp": fp, "fn": fn,
            "prec": prec, "rec": rec, "f1": f1,
            "tier_counts": stats[k]["tier_counts"],
            "fault_tp": stats[k]["fault_tp"]
        }

    return seed_results


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 18: HIGH-PERFORMANCE UNIFIED MULTI-CONFIG BENCHMARK (7 LOCKED SEEDS)")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)
    print(f"Test Stream: {len(df_test_raw)} readings across {df_test_raw['station_id'].nunique()} stations.")

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    print(f"Executing 7 seeds in parallel across CPU cores...")
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        worker_outputs = list(executor.map(eval_single_seed_stream, tasks))

    elapsed = time.time() - t0
    print(f"Parallel evaluation completed in {elapsed:.2f} seconds!")

    config_keys = ["baseline", "step16", "step18_instant_cov", "step18_instant_corr", "step18_thermo_innovation"]
    
    macro_records = []
    all_seed_records = []

    for k in config_keys:
        runs = [w[k] for w in worker_outputs]
        df_k = pd.DataFrame(runs)
        
        macro_p = df_k["prec"].mean()
        macro_r = df_k["rec"].mean()
        macro_f1 = df_k["f1"].mean()
        mean_tp = df_k["tp"].mean()
        mean_fp = df_k["fp"].mean()
        mean_fn = df_k["fn"].mean()

        macro_records.append({
            "config": k,
            "macro_precision": macro_p,
            "macro_recall": macro_r,
            "macro_f1": macro_f1,
            "mean_tp": mean_tp,
            "mean_fp": mean_fp,
            "mean_fn": mean_fn,
        })

        for r in runs:
            all_seed_records.append({
                "config": k,
                "seed": r["seed"],
                "tp": r["tp"],
                "fp": r["fp"],
                "fn": r["fn"],
                "precision": r["prec"],
                "recall": r["rec"],
                "f1": r["f1"]
            })

    macro_df = pd.DataFrame(macro_records)
    all_seeds_df = pd.DataFrame(all_seed_records)

    print("\n" + "=" * 80)
    print("STEP 18 MACRO BENCHMARK RESULTS ACROSS 7 LOCKED SEEDS")
    print("=" * 80)
    print(macro_df.to_string(index=False))

    print("\n" + "=" * 80)
    print("PER-SEED BREAKDOWN")
    print("=" * 80)
    for k in config_keys:
        print(f"\n--- {k} ---")
        print(all_seeds_df[all_seeds_df["config"] == k][["seed", "precision", "recall", "f1", "tp", "fp", "fn"]].to_string(index=False))

    # Save summary files
    macro_df.to_csv(OUTPUT_DIR / "step18_macro_summary.csv", index=False)
    all_seeds_df.to_csv(OUTPUT_DIR / "step18_all_configs_per_seed.csv", index=False)
    print(f"\nBenchmark results saved to {OUTPUT_DIR / 'step18_macro_summary.csv'}")


if __name__ == "__main__":
    main()
