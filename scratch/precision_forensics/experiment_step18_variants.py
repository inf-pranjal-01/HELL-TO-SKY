"""
scratch/precision_forensics/experiment_step18_variants.py

Explores and benchmarks Step 18 Tier 3 Instantaneous Cross-Channel Innovation variants
across all 7 locked seeds.
"""

import sys
import math
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

# Empirical Clean Instantaneous Covariance Matrix (dt = 1h)
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

INV_COV_DELTA = np.linalg.pinv(COV_DELTA_1H + 1e-6 * np.eye(3))
INV_CORR_DELTA = np.linalg.pinv(CORR_DELTA + 1e-6 * np.eye(3))

SIGMA_CLEAN_DIFF = {
    "temperature_c": math.sqrt(1.779049),
    "pressure_hpa": math.sqrt(0.452587),
    "humidity_pct": math.sqrt(32.893058)
}


def score_reading_variant(
    variant_name: str,
    raw_reading: dict,
    history_df: pd.DataFrame,
    neighbor_buffers: dict = None,
    artifact: dict = None,
    precomputed_features: pd.Series = None
) -> dict:
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # Tier 0 Hard Rails
    is_rail, rail_param, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    if is_rail:
        fault_type = "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"
        return {"is_anomaly": True, "fault_type": fault_type, "decision_basis": "TIER_0_HARD_INVARIANT", "tier": 0}

    temp_c = raw_reading.get("temperature_c")
    pressure_hpa = raw_reading.get("pressure_hpa")
    humidity_pct = raw_reading.get("humidity_pct")
    is_phys_impossible, phys_reason = CrossChannelEngine.check_physical_invariants(temp_c, pressure_hpa, humidity_pct)
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

    # Tier 1 Specialist
    tier1_evidence = []
    for param in PARAMS:
        val = float(raw_reading[param])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        p_val = prior_vals[param]

        # Step 16 Jump
        if p_val is not None:
            jump_mag = abs(val - p_val)
            sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
            z_jump = jump_mag / max(1e-4, sigma_jump)
            jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
            if jump_mag >= 2.5 * sensor_floor and jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0:
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
            "tier": 1
        }

    # Tier 2 SPRT Drift
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

    # Tier 3 Variants:
    if variant_name == "step16_baseline":
        # Uses static climatological z_predictive
        d_sq, p_val, cc_diag = CrossChannelEngine.compute_mahalanobis_distance(
            z_scores["temperature_c"], z_scores["pressure_hpa"], z_scores["humidity_pct"]
        )
        if cc_diag["is_multivariate_outlier"]:
            return {
                "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_MAHALANOBIS_CROSS_CHANNEL",
                "likely_faulty_sensors": ["temperature_c", "humidity_pct"], "tier": 3
            }

    elif variant_name == "step18_instantaneous_cov":
        # Formulate instantaneous difference vector dy = [dy_T, dy_P, dy_H]
        # Only evaluate if prior values exist for all channels and dt <= 2.5h
        if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
            dy_vec = np.array([dy_vals["temperature_c"], dy_vals["pressure_hpa"], dy_vals["humidity_pct"]], dtype=float)
            # Scaled covariance with dt
            cov_dt = COV_DELTA_1H * dt_hours
            inv_cov_dt = np.linalg.pinv(cov_dt + 1e-6 * np.eye(3))
            d_sq = float(dy_vec.T @ inv_cov_dt @ dy_vec)
            if d_sq > 16.27:
                return {
                    "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_INSTANTANEOUS_MAHALANOBIS",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"], "tier": 3
                }

    elif variant_name == "step18_instantaneous_corr":
        # Standardized instantaneous innovation: dz_p = dy_p / (sigma_clean_diff(p) * sqrt(dt))
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
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_INSTANTANEOUS_CORRELATION",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"], "tier": 3
                }

    elif variant_name == "step18_instantaneous_jump_corr":
        # Standardized instantaneous innovation using sensor jump sigma: dz_p = dy_p / sigma_jump(p, dt)
        if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
            sigma_j = {
                p: math.sqrt(2.0 * (SENSOR_QUANTIZATION_FLOORS[p]**2) + (SENSOR_QUANTIZATION_FLOORS[p]**2) * dt_hours)
                for p in PARAMS
            }
            dz_vec = np.array([dy_vals[p] / sigma_j[p] for p in PARAMS], dtype=float)
            d_sq = float(dz_vec.T @ INV_CORR_DELTA @ dz_vec)
            # High threshold since sigma_jump is sensor-floor scale
            if d_sq > 16.27:
                return {
                    "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_INSTANTANEOUS_JUMP_CORR",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"], "tier": 3
                }

    elif variant_name == "step18_thermo_innovation":
        # Direct Clausius-Clapeyron thermodynamic innovation check:
        # If dT and dRH move in the SAME direction with substantial magnitude:
        if dy_vals["temperature_c"] is not None and dy_vals["humidity_pct"] is not None:
            dy_t = dy_vals["temperature_c"]
            dy_h = dy_vals["humidity_pct"]
            # Co-directional movement violation: dT > 1.5 * sigma_t and dRH > 1.5 * sigma_h in same direction
            s_t = SIGMA_CLEAN_DIFF["temperature_c"] * math.sqrt(dt_hours)
            s_h = SIGMA_CLEAN_DIFF["humidity_pct"] * math.sqrt(dt_hours)
            if (dy_t * dy_h > 0) and (abs(dy_t) > 2.0 * s_t) and (abs(dy_h) > 2.0 * s_h):
                return {
                    "is_anomaly": True, "fault_type": "multivariate_inconsistency",
                    "anomaly_score_pct": 90.0, "decision_basis": "TIER_3_THERMO_INNOVATION",
                    "likely_faulty_sensors": ["temperature_c", "humidity_pct"], "tier": 3
                }

    return {"is_anomaly": False, "fault_type": None, "anomaly_score_pct": 5.0, "decision_basis": "NORMAL", "tier": -1}


def eval_variant_seed(args):
    variant_name, seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    tp = fp = fn = tn = 0
    tier_counts = {"tier0": 0, "tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0}
    fault_tp_counts = {}

    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type")

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

        verdict = score_reading_variant(variant_name, raw_reading, hist_df, neighbor_bufs)
        is_pred = bool(verdict["is_anomaly"])
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

        if is_pred and gt:
            tp += 1
            t_k = f"tier{verdict.get('tier', -1)}"
            tier_counts[t_k] = tier_counts.get(t_k, 0) + 1
            if gt_type:
                fault_tp_counts[gt_type] = fault_tp_counts.get(gt_type, 0) + 1
        elif is_pred and not gt:
            fp += 1
            t_k = f"tier{verdict.get('tier', -1)}"
            tier_counts[t_k] = tier_counts.get(t_k, 0) + 1
        elif not is_pred and gt:
            fn += 1
        else:
            tn += 1

    prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "variant": variant_name, "seed": seed, "tp": tp, "fp": fp, "fn": fn,
        "prec": prec, "rec": rec, "f1": f1, "tier_counts": tier_counts,
        "fault_tp_counts": fault_tp_counts
    }


def main():
    print("=" * 80)
    print("STEP 18: TIER 3 INSTANTANEOUS INNOVATION VARIANTS BENCHMARK")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    variants = [
        "step16_baseline",
        "step18_instantaneous_cov",
        "step18_instantaneous_corr",
        "step18_thermo_innovation"
    ]

    all_results = []
    for var in variants:
        print(f"\n--- Running Variant: {var} ---")
        tasks = [(var, seed, df_test_raw) for seed in SEEDS]
        with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
            res = list(executor.map(eval_variant_seed, tasks))
        all_results.extend(res)

        df_v = pd.DataFrame(res)
        print(df_v[["seed", "prec", "rec", "f1", "tp", "fp", "fn"]].to_string(index=False))
        print(f"Macro P: {df_v['prec'].mean():.2f}%, Macro R: {df_v['rec'].mean():.2f}%, Macro F1: {df_v['f1'].mean():.2f}%")
        print(f"Mean FP: {df_v['fp'].mean():.1f}, Mean TP: {df_v['tp'].mean():.1f}, Mean FN: {df_v['fn'].mean():.1f}")

    df_all = pd.DataFrame(all_results)
    df_all.to_csv(OUTPUT_DIR / "step18_variants_exploratory_benchmark.csv", index=False)


if __name__ == "__main__":
    main()
