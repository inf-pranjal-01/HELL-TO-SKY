"""
scratch/precision_forensics/run_step12_experiment.py

Runs the complete Step 12 production improvement benchmark across all 7 locked seeds.
Evaluates Variants 0, 1, 2, 3, and 4 in controlled isolation:
  - Variant 0: Exact baseline reference
  - Variant 1: Baseline + channel-scaled sigma_jump only
  - Variant 2: Baseline + contamination-resistant trusted state only
  - Variant 3: Baseline + non-destructive additive contextual evidence only
  - Variant 4: Full Step 12 architecture (channel-scaled sigma + trusted state + additive context)

Extracts full per-seed and macro metrics, FP reduction forensics, and TP safety checks.
"""

import sys
import math
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import deque
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
PARAM_PREFIXES = {"temperature_c": "temp", "pressure_hpa": "pressure", "humidity_pct": "humidity"}
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = SequentialSPRT.get_wald_boundaries(alpha=0.002, beta=0.05)


def compute_channel_scaled_sigma_jump(param: str, dt_hours: float) -> float:
    """
    Channel-scaled measurement jump uncertainty (Improvement B).
    Scales strictly with instrument quantization floor sigma_floor, avoiding arbitrary 0.25 placeholder.
    """
    floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    dt_eff = min(2.0, max(0.1, dt_hours))
    # Two independent quantization samples (current and prior) plus short-interval measurement drift
    var_jump = 2.0 * (floor ** 2) + (floor ** 2) * dt_eff
    return math.sqrt(var_jump)


def score_variant(
    variant_id: int,
    raw_reading: dict,
    history_df: pd.DataFrame,
    artifact: dict,
    neighbor_buffers: dict = None,
    trusted_prior_vals: dict = None
) -> dict:
    """
    Evaluates reading under specified variant architecture:
    Variant 0: Baseline logic
    Variant 1: Baseline + Channel-scaled sigma_jump
    Variant 2: Baseline + Contamination-resistant trusted prior
    Variant 3: Baseline + Additive contextual evidence
    Variant 4: Full Step 12 (All improvements combined)
    """
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # ── TIER 0: Hard Invariants & Hardware Rails (Identical across all variants) ──
    is_rail, rail_param, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    if is_rail:
        fault_type = "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"
        return {
            "is_anomaly": True,
            "fault_type": fault_type,
            "anomaly_score_pct": 100.0,
            "decision_basis": "TIER_0_HARD_INVARIANT",
            "likely_faulty_sensors": [rail_param] if rail_param else PARAMS,
            "rules_fired": [{"type": fault_type, "parameter": rail_param, "confidence": 100.0, "reason": rail_reason}],
        }

    temp_c = raw_reading.get("temperature_c")
    pressure_hpa = raw_reading.get("pressure_hpa")
    humidity_pct = raw_reading.get("humidity_pct")
    
    is_phys_impossible, phys_reason = CrossChannelEngine.check_physical_invariants(temp_c, pressure_hpa, humidity_pct)
    if is_phys_impossible:
        return {
            "is_anomaly": True,
            "fault_type": "physical_bounds",
            "anomaly_score_pct": 100.0,
            "decision_basis": "TIER_0_THERMODYNAMIC_BOUND",
            "likely_faulty_sensors": PARAMS,
            "rules_fired": [{"type": "physical_bounds", "parameter": "multivariate", "confidence": 100.0, "reason": phys_reason}],
        }

    # ── Physical Time Step Delta ──────────────────────────────────────
    prior_time = None
    if not history_df.empty and "timestamp" in history_df.columns:
        valid_ts = pd.to_datetime(history_df["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]
    dt_hours = max(0.1, (current_time - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(current_time, station_id)

    # ── Dynamic Expectation & Uncertainty Evaluation ──────────────────
    innovations = {}
    uncertainties = {}
    expectations = {}
    z_scores = {}
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
        
        residual = val - exp_val
        innovations[param] = residual
        z_scores[param] = residual / max(1e-4, sigma_tot)

    # ── TIER 1: High-Specificity Specialist Faults (Spike & Frozen) ───
    tier1_evidence = []
    
    for param in PARAMS:
        val = float(raw_reading[param])
        exp_val = expectations[param]
        sigma_tot = uncertainties[param]
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        
        # Prior reading selection
        if variant_id in (2, 4) and trusted_prior_vals is not None and trusted_prior_vals.get(param) is not None:
            prior_val = trusted_prior_vals[param]
        else:
            prior_val = None
            if not history_df.empty and param in history_df.columns:
                valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
                if not valid_pvals.empty:
                    prior_val = float(valid_pvals.iloc[-1])

        # ── 1. Spike Evaluation ───────────────────────────────────────
        if prior_val is not None:
            jump_mag = abs(val - prior_val)
        else:
            jump_mag = abs(val - exp_val)

        # Noise floor check
        if jump_mag >= 2.5 * sensor_floor:
            # Jump sigma calculation
            if variant_id in (1, 4):
                sigma_jump = compute_channel_scaled_sigma_jump(param, dt_hours)
            else:
                sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))

            z_jump = jump_mag / max(1e-4, sigma_jump)
            jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
            
            # Primary Raw Jump Alert
            is_spike = (jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0)
            
            # Improvement D: Additive Contextual Corroboration for Ambiguous Jumps (Variants 3, 4)
            if not is_spike and variant_id in (3, 4):
                # If raw jump is in ambiguous range [2.2, 3.0) AND contextual residual strongly diverges from peer consensus
                if z_jump >= 2.2 and abs(z_scores[param]) >= 2.5 and prior_val is not None:
                    peer_m = peer_medians.get(param)
                    if peer_m is not None and (val - prior_val) * (peer_m - prior_val) <= 0:
                        is_spike = True
                        jump_llr = max(jump_llr, WALD_UPPER_ALERT + 0.5)

            if is_spike:
                tier1_evidence.append({
                    "tier": 1,
                    "type": "spike",
                    "parameter": param,
                    "llr": jump_llr,
                    "confidence": min(98.0, 85.0 + jump_llr),
                    "reason": f"Instantaneous jump of {jump_mag:.2f} (z_jump={z_jump:.2f}, LLR={jump_llr:.2f})",
                    "observed_value": val
                })

        # ── 2. Frozen Evaluation ──────────────────────────────────────
        peer_disp = peer_dispersions.get(param)
        n_p = len(neighbor_buffers) if neighbor_buffers else 0
        f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(param, history_df, val, peer_disp, n_p)
        if f_diag["is_frozen"]:
            tier1_evidence.append({
                "tier": 1,
                "type": "frozen_value",
                "parameter": param,
                "llr": f_llr,
                "confidence": min(98.0, 85.0 + f_llr),
                "reason": f_reason,
                "observed_value": val
            })

    if tier1_evidence:
        strongest = max(tier1_evidence, key=lambda e: e["llr"])
        return {
            "is_anomaly": True,
            "fault_type": strongest["type"],
            "anomaly_score_pct": float(strongest["confidence"]),
            "decision_basis": f"TIER_1_SPECIALIST_{strongest['type'].upper()}",
            "likely_faulty_sensors": [strongest["parameter"]],
            "rules_fired": tier1_evidence,
        }

    # ── TIER 2: Persistent Temporal Faults (SPRT Drift) ───────────────
    tier2_evidence = []
    for param in PARAMS:
        residual = innovations[param]
        sigma_tot = uncertainties[param]
        
        prior_res = None
        if variant_id in (2, 4) and trusted_prior_vals is not None and trusted_prior_vals.get(param) is not None:
            prior_res = trusted_prior_vals[param] - expectations[param]
        else:
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
                "tier": 2,
                "type": "drift",
                "parameter": param,
                "llr": drift_llr,
                "confidence": min(95.0, 80.0 + drift_llr),
                "reason": f"Pre-whitened SPRT accumulator (LLR={drift_llr:.2f}) cleared Wald threshold",
                "observed_value": float(raw_reading[param])
            })

    if tier2_evidence:
        strongest = max(tier2_evidence, key=lambda e: e["llr"])
        return {
            "is_anomaly": True,
            "fault_type": "drift",
            "anomaly_score_pct": float(strongest["confidence"]),
            "decision_basis": "TIER_2_PERSISTENT_DRIFT",
            "likely_faulty_sensors": [strongest["parameter"]],
            "rules_fired": tier2_evidence,
        }

    # ── TIER 3: Cross-Channel 3D Mahalanobis ───────────────────────────
    d_sq, p_val, cc_diag = CrossChannelEngine.compute_mahalanobis_distance(
        z_scores["temperature_c"], z_scores["pressure_hpa"], z_scores["humidity_pct"]
    )
    if cc_diag["is_multivariate_outlier"]:
        return {
            "is_anomaly": True,
            "fault_type": "multivariate_inconsistency",
            "anomaly_score_pct": 90.0,
            "decision_basis": "TIER_3_MAHALANOBIS_CROSS_CHANNEL",
            "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"3D Mahalanobis D^2={d_sq:.2f} exceeded critical threshold"}],
        }

    # ── TIER 4: Model-Dominant Supported Faults (Isolation Forest) ────
    model = artifact.get("model") if artifact else None
    precomputed_features = raw_reading.get("precomputed_features")
    if model is not None and precomputed_features is not None:
        try:
            feat_cols = artifact.get("feature_columns", [])
            if feat_cols and all(col in precomputed_features.index for col in feat_cols):
                X = precomputed_features[feat_cols].values.reshape(1, -1).astype(float)
                if not np.isnan(X).any():
                    raw_if_score = float(model.decision_function(X)[0])
                    train_std = artifact.get("training_score_std", 0.08)
                    z_if = (0.0 - raw_if_score) / max(1e-4, train_std)
                    if z_if > 3.0 and d_sq > 8.0:
                        return {
                            "is_anomaly": True,
                            "fault_type": "multivariate_inconsistency",
                            "anomaly_score_pct": 88.0,
                            "decision_basis": "TIER_4_MODEL_DOMINANT_MULTIVARIATE",
                            "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
                            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "model_joint", "confidence": 88.0, "reason": "Isolation Forest empirical tail"}],
                        }
        except Exception:
            pass

    # ── TIER 5: Ambiguity vs Normal State ──────────────────────────────
    max_z = max(abs(z) for z in z_scores.values())
    if max_z > 2.2 and neighbor_buffers and len(neighbor_buffers) == 0:
        return {
            "is_anomaly": False,
            "fault_type": None,
            "anomaly_score_pct": 35.0,
            "decision_basis": "AMBIGUOUS_NO_PEER_CORROBORATION",
            "likely_faulty_sensors": [],
            "rules_fired": [],
        }

    return {
        "is_anomaly": False,
        "fault_type": None,
        "anomaly_score_pct": 5.0,
        "decision_basis": "NORMAL",
        "likely_faulty_sensors": [],
        "rules_fired": [],
    }


def eval_variant_for_seed(args):
    """
    Evaluates one variant on one seed across the full test stream.
    """
    variant_id, seed, test_raw_df = args
    
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    trusted_priors = {st_id: {p: None for p in PARAMS} for st_id in station_ids}
    
    tp = fp = fn = tn = 0
    lost_records = []
    fp_records = []
    
    t0 = time.time()
    rows = eval_df.to_dict("records")

    for row_idx, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        fault_type = row.get("fault_type", "normal")
        
        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        buf = buffers[st_id]
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
        hist_df = buf.raw_history_df()
        
        raw_reading = {
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }
        
        verdict = score_variant(
            variant_id=variant_id,
            raw_reading=raw_reading,
            history_df=hist_df,
            artifact={},
            neighbor_buffers=neighbor_bufs,
            trusted_prior_vals=trusted_priors[st_id]
        )
        
        is_pred = bool(verdict["is_anomaly"])
        
        if is_pred and gt_is_anom:
            tp += 1
        elif is_pred and not gt_is_anom:
            fp += 1
            fp_records.append({
                "seed": seed, "station_id": st_id, "timestamp": ts.isoformat(),
                "basis": verdict.get("decision_basis", "")
            })
        elif not is_pred and gt_is_anom:
            fn += 1
            lost_records.append({
                "seed": seed, "station_id": st_id, "timestamp": ts.isoformat(),
                "fault_type": fault_type, "basis": verdict.get("decision_basis", "")
            })
        else:
            tn += 1
            
        # Update station buffer
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)
        
        # Update trusted reference state (Improvement C)
        if not is_pred:
            for p in PARAMS:
                trusted_priors[st_id][p] = float(row[p])

    elapsed = time.time() - t0
    prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "variant_id": variant_id,
        "seed": seed,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": prec, "recall": rec, "f1": f1,
        "elapsed_sec": elapsed,
        "n_lost": len(lost_records),
        "n_fp": len(fp_records)
    }


def run_full_step12_suite():
    print("=" * 80)
    print("PATH 2 — PRECISION STEP 12: FIRST PRODUCTION IMPROVEMENT EXPERIMENT")
    print("=" * 80)

    # Load test split
    print("Loading test split (all_stations.csv with 0.7 cutoff)...")
    df = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    test_raw_df = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)
    print(f"Loaded {len(test_raw_df)} rows across {df['station_id'].nunique()} stations.")

    variants = [
        (0, "Variant 0: Exact Baseline Reference"),
        (1, "Variant 1: Baseline + Channel-Scaled sigma_jump"),
        (2, "Variant 2: Baseline + Contamination-Resistant Trusted State"),
        (3, "Variant 3: Baseline + Additive Contextual Corroboration"),
        (4, "Variant 4: Full Step 12 Architecture (All Improvements Combined)")
    ]

    all_results = []
    
    for v_id, v_name in variants:
        print(f"\nEvaluating {v_name} across {len(SEEDS)} seeds in parallel...")
        t0 = time.time()
        tasks = [(v_id, s, test_raw_df) for s in SEEDS]
        with ProcessPoolExecutor(max_workers=7) as executor:
            v_results = list(executor.map(eval_variant_for_seed, tasks))
        elapsed = time.time() - t0
        print(f"Finished {v_name} in {elapsed:.1f}s.")
        all_results.extend(v_results)

    df_res = pd.DataFrame(all_results)
    df_res.to_csv(OUTPUT_DIR / "step12_all_variants_per_seed.csv", index=False)

    print("\n" + "=" * 80)
    print("STEP 12 BENCHMARK RESULTS SUMMARY (MACRO ACROSS 7 SEEDS)")
    print("=" * 80)

    summary_rows = []
    for v_id, v_name in variants:
        v_df = df_res[df_res["variant_id"] == v_id]
        mean_p = v_df["precision"].mean()
        mean_r = v_df["recall"].mean()
        mean_f1 = v_df["f1"].mean()
        mean_tp = v_df["tp"].mean()
        mean_fp = v_df["fp"].mean()
        mean_fn = v_df["fn"].mean()
        mean_tn = v_df["tn"].mean()
        
        summary_rows.append({
            "variant_id": v_id,
            "name": v_name,
            "macro_precision": mean_p,
            "macro_recall": mean_r,
            "macro_f1": mean_f1,
            "mean_tp": mean_tp,
            "mean_fp": mean_fp,
            "mean_fn": mean_fn,
            "prec_diff_pp": mean_p - 72.35,
            "rec_diff_pp": mean_r - 97.27,
            "f1_diff_pp": mean_f1 - 82.97,
            "fp_reduction": 4858.0 - mean_fp
        })

    sum_df = pd.DataFrame(summary_rows)
    sum_df.to_csv(OUTPUT_DIR / "step12_variants_macro_summary.csv", index=False)
    print(sum_df[["variant_id", "name", "macro_precision", "macro_recall", "macro_f1", "prec_diff_pp", "rec_diff_pp", "f1_diff_pp", "fp_reduction"]].to_string(index=False))

    print("\n" + "=" * 80)
    print("PER-SEED BREAKDOWN FOR EACH VARIANT")
    print("=" * 80)
    for v_id, v_name in variants:
        print(f"\n--- {v_name} ---")
        v_df = df_res[df_res["variant_id"] == v_id]
        print(v_df[["seed", "tp", "fp", "fn", "precision", "recall", "f1"]].to_string(index=False))


if __name__ == "__main__":
    run_full_step12_suite()
