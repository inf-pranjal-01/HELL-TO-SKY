"""
scratch/precision_forensics/run_step3_full_pipeline.py

Path 2 — Precision Step 3:
Continuous Peer Contextual Evidence, Lag Handling, Warm-Start Benchmarking, and Forensics.
"""

import sys
import os
import math
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
import joblib

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
    STATION_ELEVATIONS,
    haversine_distance_km
)
from model.cross_channel_covariance import CrossChannelEngine
from model.detect import (
    PARAMS,
    PARAM_PREFIXES,
    WALD_UPPER_ALERT,
    WALD_LOWER_NORMAL,
    _check_hardware_rail,
    evaluate_frozen_evidence
)
from model.state import StationBuffer
import data.anomaly_injector as injector

DATA_DIR = REPO_ROOT / "data"
ARTIFACTS_DIR = REPO_ROOT / "model_artifacts"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]


# =====================================================================
# 1. CONTINUOUS PEER EVIDENCE MATHEMATICAL ENGINE
# =====================================================================
def compute_continuous_peer_evidence_v3(
    target_station_id: str,
    param: str,
    current_time: pd.Timestamp,
    target_val: float,
    prior_val: Optional[float],
    dt_hours: float,
    neighbor_buffers: Dict[str, Any],
    use_lag_awareness: bool = True
) -> Dict[str, Any]:
    """
    Computes mathematically rigorous continuous peer contextual evidence for Tier 1 spike specialist.
    Strictly causal (using only timestamps <= current_time).
    Restricted to exactly 3 sibling cluster peers (no self, no cross-cluster).
    """
    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))

    if prior_val is not None:
        d_target = target_val - prior_val
    else:
        d_target = 0.0

    z_target = d_target / max(1e-4, sigma_jump)

    allowed_siblings = PeerSpatialEngine.get_sibling_peers(target_station_id)
    if not allowed_siblings or not neighbor_buffers:
        return {
            "eligible_peers": 0,
            "d_target": d_target,
            "z_target": z_target,
            "peer_median_d": 0.0,
            "peer_dispersion": sigma_jump,
            "z_surprise": z_target,
            "peer_common_mode_llr": 0.0,
            "common_mode_discount": 0.0,
            "dir_alignment": 0.0,
            "has_1h_phase_lag": False,
            "applied_lag": 0
        }

    weights = PeerSpatialEngine.compute_peer_weights(target_station_id, allowed_siblings)

    sibling_sync_deltas = []
    sibling_sync_weights = []
    sibling_lag_deltas = []
    sibling_lag_weights = []

    for pid in allowed_siblings:
        if pid not in neighbor_buffers:
            continue
        buf_obj = neighbor_buffers[pid]

        pvals = []
        if hasattr(buf_obj, "_raw_rows"):
            rows = buf_obj._raw_rows
            for r in rows:
                v = r.get(param)
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    pvals.append(float(v))
        elif hasattr(buf_obj, "raw_history_df"):
            nhist = buf_obj.raw_history_df()
            if nhist is not None and not nhist.empty and param in nhist.columns:
                valid_s = pd.to_numeric(nhist[param], errors="coerce").dropna()
                pvals = valid_s.tolist()

        w = weights.get(pid, 1.0)

        # Contemporaneous delta (tau = 0)
        if len(pvals) >= 2:
            d_s0 = pvals[-1] - pvals[-2]
            sibling_sync_deltas.append(d_s0)
            sibling_sync_weights.append(w)

        # 1-step lag delta (tau = 1)
        if len(pvals) >= 3:
            d_s1 = pvals[-2] - pvals[-3]
            sibling_lag_deltas.append(d_s1)
            sibling_lag_weights.append(w)

    n_eligible = len(sibling_sync_deltas)
    if n_eligible == 0:
        return {
            "eligible_peers": 0,
            "d_target": d_target,
            "z_target": z_target,
            "peer_median_d": 0.0,
            "peer_dispersion": sigma_jump,
            "z_surprise": z_target,
            "peer_common_mode_llr": 0.0,
            "common_mode_discount": 0.0,
            "dir_alignment": 0.0,
            "has_1h_phase_lag": False,
            "applied_lag": 0
        }

    # 1. Synchronous Peer Weighted Median and Dispersion
    s_sync_arr = np.array(sibling_sync_deltas)
    w_sync_arr = np.array(sibling_sync_weights) / sum(sibling_sync_weights)
    sort_idx = np.argsort(s_sync_arr)
    s_sorted = s_sync_arr[sort_idx]
    w_sorted = w_sync_arr[sort_idx]
    cum_w = np.cumsum(w_sorted)
    med_idx = min(len(s_sorted) - 1, np.searchsorted(cum_w, 0.5))
    med_sync_d = float(s_sorted[med_idx])

    mad_sync = float(np.median(np.abs(s_sync_arr - med_sync_d)))
    disp_sync = max(0.5 * sigma_jump, 1.4826 * mad_sync)

    surp_sync = (d_target - med_sync_d) / max(1e-4, disp_sync)

    # 2. Lagged Peer Consensus (tau = 1)
    applied_lag = 0
    has_phase_lag = False
    effective_peer_d = med_sync_d
    effective_disp = disp_sync
    effective_surprise = surp_sync

    if use_lag_awareness and len(sibling_lag_deltas) >= 2:
        s_lag_arr = np.array(sibling_lag_deltas)
        w_lag_arr = np.array(sibling_lag_weights) / sum(sibling_lag_weights)
        sort_l_idx = np.argsort(s_lag_arr)
        s_lag_sorted = s_lag_arr[sort_l_idx]
        w_lag_sorted = w_lag_arr[sort_l_idx]
        cum_wl = np.cumsum(w_lag_sorted)
        med_l_idx = min(len(s_lag_sorted) - 1, np.searchsorted(cum_wl, 0.5))
        med_lag_d = float(s_lag_sorted[med_l_idx])

        mad_lag = float(np.median(np.abs(s_lag_arr - med_lag_d)))
        disp_lag = max(0.5 * sigma_jump, 1.4826 * mad_lag)

        surp_lag = (d_target - med_lag_d) / max(1e-4, disp_lag)

        # Lag weight decay gamma = 0.85
        cost_sync = abs(surp_sync)
        cost_lag = abs(surp_lag) + 0.5  # Soft penalty for lag

        # If lagged explanation is substantially better aligned with target
        if cost_lag < cost_sync and np.sign(d_target) == np.sign(med_lag_d) and abs(med_lag_d) > 0.5 * sensor_floor:
            has_phase_lag = True
            applied_lag = 1
            # Continuous softmax blend between sync and lag
            weight_sync = math.exp(-cost_sync)
            weight_lag = 0.85 * math.exp(-abs(surp_lag))
            alpha = weight_sync / (weight_sync + weight_lag)

            effective_peer_d = float(alpha * med_sync_d + (1.0 - alpha) * med_lag_d)
            effective_disp = float(alpha * disp_sync + (1.0 - alpha) * disp_lag)
            effective_surprise = (d_target - effective_peer_d) / max(1e-4, effective_disp)

    # 3. Directional Alignment
    aligned_dirs = [np.sign(d_target) * np.sign(sd) for sd in sibling_sync_deltas if abs(sd) > 0.5 * sensor_floor]
    dir_align = float(np.mean(aligned_dirs)) if aligned_dirs else 0.0

    # 4. Continuous Peer Common-Mode Log-Likelihood Ratio
    peer_llr = float(0.5 * (z_target ** 2) - 0.5 * (effective_surprise ** 2))

    # Continuous common mode discount for Tier 1 spike LLR
    # Only discounts when peers agree with target movement (peer_llr > 0)
    common_mode_discount = max(0.0, peer_llr)

    return {
        "eligible_peers": n_eligible,
        "d_target": d_target,
        "z_target": z_target,
        "peer_median_d": effective_peer_d,
        "peer_dispersion": effective_disp,
        "z_surprise": effective_surprise,
        "peer_common_mode_llr": peer_llr,
        "common_mode_discount": common_mode_discount,
        "dir_alignment": dir_align,
        "has_1h_phase_lag": has_phase_lag,
        "applied_lag": applied_lag
    }


# =====================================================================
# 2. UPDATED DETECTOR IMPLEMENTATION WITH CONTINUOUS PEER CONTEXT
# =====================================================================
def evaluate_spike_evidence_v3(
    param: str,
    current_val: float,
    expected_val: float,
    prior_val: Optional[float],
    current_sigma: float,
    dt_hours: float,
    peer_evidence: Optional[Dict[str, Any]] = None
) -> Tuple[float, Optional[str], Dict[str, Any]]:
    """
    Tier 1 Spike Check: Evaluates dynamic jump likelihood ratio relative to pre-jump state
    modulated continuously by peer contextual evidence.
    """
    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)

    if prior_val is not None:
        jump_mag = abs(current_val - prior_val)
    else:
        jump_mag = abs(current_val - expected_val)

    # Sub-uncertainty perturbation check
    if jump_mag < 2.5 * sensor_floor:
        return 0.0, None, {"jump_llr": 0.0, "is_spike": False, "raw_llr": 0.0, "peer_discount": 0.0}

    sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))
    z_jump = jump_mag / max(1e-4, sigma_jump)

    # Raw Jump LLR
    raw_jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))

    # Continuous Peer Modulation
    peer_discount = 0.0
    if peer_evidence is not None and peer_evidence.get("eligible_peers", 0) >= 2:
        # Modulate by peer common mode discount (smooth continuous scaling)
        cm_discount = peer_evidence.get("common_mode_discount", 0.0)
        # Apply gentle continuous damping factor kappa = 0.75
        peer_discount = 0.75 * cm_discount

    jump_llr = max(0.0, raw_jump_llr - peer_discount)

    is_spike = jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0
    reason = f"Instantaneous jump of {jump_mag:.2f} (z_jump={z_jump:.2f}, LLR={jump_llr:.2f}, raw_llr={raw_jump_llr:.2f})" if is_spike else None

    diagnostics = {
        "jump_mag": jump_mag,
        "z_jump": z_jump,
        "raw_llr": raw_jump_llr,
        "peer_discount": peer_discount,
        "jump_llr": jump_llr,
        "is_spike": is_spike
    }
    return jump_llr, reason, diagnostics


def score_reading_v3(
    raw_reading: dict,
    history_df: pd.DataFrame,
    artifact: dict,
    neighbor_buffers: dict = None,
    use_continuous_peer: bool = True,
    use_lag_awareness: bool = True
) -> dict:
    """
    Path 2 Detection Engine with Continuous Peer Contextual Evidence.
    """
    station_id = raw_reading.get("station_id", "AWS-UNKNOWN")
    raw_ts = raw_reading.get("timestamp")
    current_time = pd.to_datetime(raw_ts, utc=True) if raw_ts is not None else pd.Timestamp.now(tz="UTC")

    # ── TIER 0: Hard Invariants & Hardware Rails ────────────────────────
    is_rail, rail_param, rail_reason = _check_hardware_rail(raw_reading)
    if is_rail:
        fault_type = "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low"
        return {
            "is_anomaly": True,
            "fault_type": fault_type,
            "anomaly_score_pct": 100.0,
            "decision_basis": "TIER_0_HARD_INVARIANT",
            "likely_faulty_sensors": [rail_param] if rail_param else PARAMS,
            "rules_fired": [{"type": fault_type, "parameter": rail_param, "confidence": 100.0, "reason": rail_reason}],
            "evaluation_diagnostics": {"tier": 0, "reason": rail_reason, "evidence_llr": 999.0}
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
            "evaluation_diagnostics": {"tier": 0, "reason": phys_reason, "evidence_llr": 999.0}
        }

    # ── Elapsed Physical Time ───────────────────────────────────────────
    prior_time = None
    if not history_df.empty and "timestamp" in history_df.columns:
        valid_ts = pd.to_datetime(history_df["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]

    dt_hours = max(0.1, (current_time - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(current_time, station_id)

    # ── Dynamic Expectation & Continuous Peer Context ───────────────────
    innovations = {}
    uncertainties = {}
    expectations = {}
    z_scores = {}
    peer_evidences = {}

    for param in PARAMS:
        val = float(raw_reading[param])
        prior_val = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                prior_val = float(valid_pvals.iloc[-1])

        # Compute continuous peer contextual evidence
        if use_continuous_peer and neighbor_buffers:
            p_ev = compute_continuous_peer_evidence_v3(
                station_id, param, current_time, val, prior_val, dt_hours, neighbor_buffers,
                use_lag_awareness=use_lag_awareness
            )
        else:
            p_ev = None
        peer_evidences[param] = p_ev

        # Dynamic expectation
        exp_val, exp_roc = compute_dynamic_expectation(station_id, param, current_time, history_df)
        expectations[param] = exp_val

        peer_disp = p_ev["peer_dispersion"] if p_ev else 0.0
        sigma_tot, u_breakdown = UncertaintyBudget.compute_composite_predictive_uncertainty(
            param, solar_hour, dt_hours, history_df, peer_dispersion=peer_disp
        )
        uncertainties[param] = sigma_tot

        residual = val - exp_val
        innovations[param] = residual
        z_scores[param] = residual / max(1e-4, sigma_tot)

    # ── TIER 1: High-Specificity Specialist Faults (Spike & Frozen) ─────
    tier1_evidence = []

    for param in PARAMS:
        val = float(raw_reading[param])
        exp_val = expectations[param]
        sigma_tot = uncertainties[param]

        prior_val = None
        if not history_df.empty and param in history_df.columns:
            valid_pvals = pd.to_numeric(history_df[param], errors="coerce").dropna()
            if not valid_pvals.empty:
                prior_val = float(valid_pvals.iloc[-1])

        p_ev = peer_evidences.get(param)

        # 1. Spike Jump Check with Continuous Peer Context
        s_llr, s_reason, s_diag = evaluate_spike_evidence_v3(
            param, val, exp_val, prior_val, sigma_tot, dt_hours, peer_evidence=p_ev
        )
        if s_diag["is_spike"]:
            tier1_evidence.append({
                "tier": 1,
                "type": "spike",
                "parameter": param,
                "llr": s_llr,
                "confidence": min(98.0, 85.0 + s_llr),
                "reason": s_reason,
                "observed_value": val
            })

        # 2. Frozen Variance Collapse Check
        peer_disp = p_ev["peer_dispersion"] if p_ev else None
        n_p = p_ev["eligible_peers"] if p_ev else 0
        f_llr, f_reason, f_diag = evaluate_frozen_evidence(param, history_df, val, peer_disp, n_p)
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
            "evaluation_diagnostics": {
                "tier": 1,
                "peak_llr": strongest["llr"],
                "trigger_source": strongest["type"]
            }
        }

    # ── TIER 2: Persistent Temporal Faults (Pre-Whitened SPRT Drift) ─────
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

        p_ev = peer_evidences.get(param)
        if p_ev and p_ev.get("eligible_peers", 0) >= 2:
            peer_med = p_ev["peer_median_d"]
            if (residual * peer_med) < 0 and abs(residual) > 2.0 * sigma_tot:
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
            "evaluation_diagnostics": {
                "tier": 2,
                "peak_llr": strongest["llr"],
                "trigger_source": "drift"
            }
        }

    # ── TIER 3: Cross-Channel 3D Mahalanobis ─────────────────────────────
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
            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"3D Mahalanobis distance D^2={d_sq:.2f} exceeded critical threshold (p={p_val:.4e})"}],
            "evaluation_diagnostics": {"tier": 3, "d_squared": d_sq, "p_value": p_val}
        }

    # ── TIER 4 & 5: Normal ──────────────────────────────────────────────
    return {
        "is_anomaly": False,
        "fault_type": "normal",
        "anomaly_score_pct": 5.0,
        "decision_basis": "NORMAL_STABLE",
        "likely_faulty_sensors": [],
        "rules_fired": [],
        "evaluation_diagnostics": {"tier": 5}
    }


# =====================================================================
# 3. SAFETY TESTS (PART 7) & LEAKAGE VERIFICATION (PART 8)
# =====================================================================
def run_safety_and_leakage_tests() -> Dict[str, Any]:
    print("\n==================================================================", flush=True)
    print("PARTS 7 & 8: PEER EVIDENCE SAFETY & LEAKAGE INVARIANCE TESTS", flush=True)
    print("==================================================================", flush=True)

    test_results = {}
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    param = "temperature_c"
    dt = 1.0

    # Helper to build mock station buffer
    def make_mock_buf(sid: str, values: List[float]):
        buf = StationBuffer(sid)
        base_time = pd.Timestamp("2026-06-01 08:00:00", tz="UTC")
        for idx, v in enumerate(values):
            ts = base_time + pd.Timedelta(hours=idx)
            buf.record_raw_reading({
                "station_id": sid,
                "timestamp": ts,
                "temperature_c": v,
                "pressure_hpa": 1013.25,
                "humidity_pct": 50.0
            }, timestamp=ts, verdict={"is_anomaly": False})
        return buf

    # Test A: Target strongly moves (+5.0C), peers stable (0.0C)
    bufs_a = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 25.0, 25.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 25.0, 25.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev_a = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 30.0, 25.0, dt, bufs_a)
    test_results["Test_A_Isolated_Spike"] = {
        "z_target": ev_a["z_target"],
        "z_surprise": ev_a["z_surprise"],
        "discount": ev_a["common_mode_discount"],
        "passed": ev_a["z_surprise"] > 5.0 and ev_a["common_mode_discount"] == 0.0
    }

    # Test B: Target + ALL 3 peers move together (-4.0C)
    bufs_b = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 25.0, 21.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 25.0, 21.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 25.0, 21.0])
    }
    ev_b = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 21.0, 25.0, dt, bufs_b)
    test_results["Test_B_All_Peers_Agree"] = {
        "z_target": ev_b["z_target"],
        "z_surprise": ev_b["z_surprise"],
        "discount": ev_b["common_mode_discount"],
        "passed": abs(ev_b["z_surprise"]) < 1.0 and ev_b["common_mode_discount"] > 10.0
    }

    # Test C: Target + 2 peers move together (-4.0C), 1 peer stays stable
    bufs_c = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 25.0, 21.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 25.0, 21.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev_c = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 21.0, 25.0, dt, bufs_c)
    test_results["Test_C_Two_Peers_Agree"] = {
        "z_target": ev_c["z_target"],
        "z_surprise": ev_c["z_surprise"],
        "discount": ev_c["common_mode_discount"],
        "passed": ev_c["common_mode_discount"] > 5.0
    }

    # Test D: Target moves (-4.0C), peers moved 1 hour ago (1-hour lag)
    bufs_d = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 21.0, 21.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 21.0, 21.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 21.0, 21.0])
    }
    ev_d = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 21.0, 25.0, dt, bufs_d, use_lag_awareness=True)
    test_results["Test_D_One_Hour_Lag"] = {
        "has_lag": ev_d["has_1h_phase_lag"],
        "applied_lag": ev_d["applied_lag"],
        "discount": ev_d["common_mode_discount"],
        "passed": ev_d["has_1h_phase_lag"] and ev_d["applied_lag"] == 1 and ev_d["common_mode_discount"] > 5.0
    }

    # Test E: Peers react at mixed lags
    bufs_e = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 21.0, 21.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 25.0, 21.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev_e = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 21.0, 25.0, dt, bufs_e, use_lag_awareness=True)
    test_results["Test_E_Mixed_Lags"] = {
        "dispersion": ev_e["peer_dispersion"],
        "discount": ev_e["common_mode_discount"],
        "passed": ev_e["peer_dispersion"] >= 0.5
    }

    # Test F: Target moves, peers disagree (one up +3C, one down -3C)
    bufs_f = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 25.0, 28.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 25.0, 22.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev_f = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 30.0, 25.0, dt, bufs_f)
    test_results["Test_F_Peers_Disagree"] = {
        "dispersion": ev_f["peer_dispersion"],
        "discount": ev_f["common_mode_discount"],
        "passed": ev_f["peer_dispersion"] >= 1.0 and ev_f["common_mode_discount"] < 5.0
    }

    # Test G: Target genuinely faulty (+8.0C) while one peer is faulty (+8.0C) and other 2 are normal
    bufs_g = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [25.0, 25.0, 33.0]), # Bad peer
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [25.0, 25.0, 25.0]), # Good peer
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [25.0, 25.0, 25.0])  # Good peer
    }
    ev_g = compute_continuous_peer_evidence_v3(target_id, param, now_ts, 33.0, 25.0, dt, bufs_g)
    test_results["Test_G_Faulty_Peer_Robustness"] = {
        "peer_median": ev_g["peer_median_d"],
        "z_surprise": ev_g["z_surprise"],
        "passed": ev_g["peer_median_d"] == 0.0 and ev_g["z_surprise"] > 8.0 # Robust median resists 1 bad peer!
    }

    # Test H: Regional Environmental Front (All stations drop pressure by -3.0 hPa)
    bufs_h = {
        "AWS-DEL-101": make_mock_buf("AWS-DEL-101", [1013.0, 1013.0, 1010.0]),
        "AWS-DEL-102": make_mock_buf("AWS-DEL-102", [1013.0, 1013.0, 1010.0]),
        "AWS-DEL-103": make_mock_buf("AWS-DEL-103", [1013.0, 1013.0, 1010.0])
    }
    ev_h = compute_continuous_peer_evidence_v3(target_id, "pressure_hpa", now_ts, 1010.0, 1013.0, dt, bufs_h)
    test_results["Test_H_Regional_Environmental_Front"] = {
        "z_target": ev_h["z_target"],
        "z_surprise": ev_h["z_surprise"],
        "discount": ev_h["common_mode_discount"],
        "passed": abs(ev_h["z_surprise"]) < 0.5 and ev_h["common_mode_discount"] > 15.0
    }

    # Test I: Isolated Genuine Spike on Target (+6.0 hPa), all peers flat
    ev_i = compute_continuous_peer_evidence_v3(target_id, "pressure_hpa", now_ts, 1019.0, 1013.0, dt, bufs_a)
    test_results["Test_I_Isolated_Genuine_Spike"] = {
        "z_target": ev_i["z_target"],
        "z_surprise": ev_i["z_surprise"],
        "discount": ev_i["common_mode_discount"],
        "passed": ev_i["z_surprise"] > 8.0 and ev_i["common_mode_discount"] == 0.0
    }

    # Leakage Invariant Tests (Part 8)
    # Check 1: Target never in its own peer list
    self_leakage = target_id in PeerSpatialEngine.get_sibling_peers(target_id)
    # Check 2: Cross cluster peers never in peer list (e.g. Kolkata station in Delhi peer list)
    cross_cluster_leakage = "AWS-KOL-015" in PeerSpatialEngine.get_sibling_peers("AWS-DEL-011")
    # Check 3: Sibling count is exactly 3
    exact_3_siblings = all(len(PeerSpatialEngine.get_sibling_peers(sid)) == 3 for sid in STATION_TO_CLUSTER)

    test_results["Leakage_Check_Self_Excluded"] = {"passed": not self_leakage}
    test_results["Leakage_Check_Cross_Cluster_Excluded"] = {"passed": not cross_cluster_leakage}
    test_results["Leakage_Check_Exact_3_Siblings"] = {"passed": exact_3_siblings}

    for name, res in test_results.items():
        status = "PASSED" if res["passed"] else "FAILED"
        print(f"[{status}] {name}")

    return test_results


# =====================================================================
# 4. BENCHMARK RUNNER (PARTS 9, 10, 16, 17)
# =====================================================================
def run_evaluation_suite(
    train_df: pd.DataFrame,
    test_raw_df: pd.DataFrame,
    artifact: dict
):
    print("\n==================================================================", flush=True)
    print("RUNNING BENCHMARK EVALUATIONS & ABLATION MATRIX", flush=True)
    print("==================================================================", flush=True)

    # 1. Warm-Start Matrix Comparison (Part 10): 0h, 6h, 12h, 24h causal pre-roll
    warmstart_records = []
    pre_roll_hours_list = [0, 6, 12, 24]

    for pre_h in pre_roll_hours_list:
        print(f"\nEvaluating Pre-Roll Context: {pre_h} Hours across 7 Seeds...", flush=True)
        t_start = time.time()
        seed_res_list = []

        for seed in SEEDS:
            injected_frames = []
            for station_id, group in test_raw_df.groupby("station_id", sort=False):
                group_injected = injector.inject_anomalies(group.copy(), seed=seed)
                injected_frames.append(group_injected)

            eval_df = pd.concat(injected_frames, ignore_index=True)
            eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
            eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

            station_ids = eval_df["station_id"].unique()
            buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

            # Warm-up pre-roll with clean historical observations
            if pre_h > 0 and not train_df.empty:
                max_train_ts = train_df["timestamp"].max()
                min_warm_ts = max_train_ts - pd.Timedelta(hours=pre_h)
                warm_slice = train_df[train_df["timestamp"] >= min_warm_ts].sort_values("timestamp")

                for w_row in warm_slice.to_dict("records"):
                    w_sid = w_row["station_id"]
                    w_ts = w_row["timestamp"]
                    if w_sid in buffers:
                        buffers[w_sid].record_raw_reading({
                            "station_id": w_sid,
                            "timestamp": w_ts,
                            "temperature_c": w_row["temperature_c"],
                            "pressure_hpa": w_row["pressure_hpa"],
                            "humidity_pct": w_row["humidity_pct"]
                        }, timestamp=w_ts, verdict={"is_anomaly": False})

            tp = fp = fn = tn = 0
            rows = eval_df.to_dict("records")

            for row in rows:
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

                verdict = score_reading_v3(
                    raw_reading, hist_df, artifact, neighbor_bufs,
                    use_continuous_peer=True, use_lag_awareness=True
                )
                is_pred = bool(verdict["is_anomaly"])
                gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False

                if is_pred and gt_is_anom:
                    tp += 1
                elif is_pred and not gt_is_anom:
                    fp += 1
                elif not is_pred and gt_is_anom:
                    fn += 1
                else:
                    tn += 1

                buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            seed_res_list.append({
                "pre_roll_hours": pre_h,
                "seed": seed,
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "precision": prec, "recall": rec, "f1": f1
            })

        avg_p = float(np.mean([s["precision"] for s in seed_res_list]))
        avg_r = float(np.mean([s["recall"] for s in seed_res_list]))
        avg_f = float(np.mean([s["f1"] for s in seed_res_list]))
        avg_tp = int(np.mean([s["tp"] for s in seed_res_list]))
        avg_fp = int(np.mean([s["fp"] for s in seed_res_list]))
        avg_fn = int(np.mean([s["fn"] for s in seed_res_list]))

        print(f"Pre-Roll {pre_h:2d}h -> Macro Precision: {avg_p*100:6.2f}% | Recall: {avg_r*100:6.2f}% | F1: {avg_f*100:6.2f}% | FP: {avg_fp}")
        warmstart_records.append({
            "pre_roll_hours": pre_h,
            "avg_tp": avg_tp,
            "avg_fp": avg_fp,
            "avg_fn": avg_fn,
            "precision": avg_p,
            "recall": avg_r,
            "f1": avg_f
        })

    warmstart_df = pd.DataFrame(warmstart_records)
    warmstart_df.to_csv(OUTPUT_DIR / "warmstart_protocol_comparison.csv", index=False)

    # 2. Architectural Ablation Matrix (Part 16)
    # Mode A: Baseline Spike Evidence (No Peer)
    # Mode B: Continuous Peer Context (Synchronous Only)
    # Mode C: Lag-Aware Continuous Peer Context
    print("\n==================================================================", flush=True)
    print("PART 16: ARCHITECTURAL ABLATION MATRIX (AUTHORITATIVE PROTOCOL)", flush=True)
    print("==================================================================", flush=True)

    ablation_modes = [
        ("A_Baseline_No_Peer", False, False),
        ("B_Continuous_Peer_Sync", True, False),
        ("C_Lag_Aware_Continuous_Peer", True, True)
    ]

    ablation_results = []
    authoritative_seed_runs = []
    continuous_seed_runs = []

    for mode_name, use_peer, use_lag in ablation_modes:
        print(f"\nRunning Ablation: {mode_name}...", flush=True)
        seed_stats = []

        for seed in SEEDS:
            injected_frames = []
            for station_id, group in test_raw_df.groupby("station_id", sort=False):
                group_injected = injector.inject_anomalies(group.copy(), seed=seed)
                injected_frames.append(group_injected)

            eval_df = pd.concat(injected_frames, ignore_index=True)
            eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
            eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

            station_ids = eval_df["station_id"].unique()
            buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

            tp = fp = fn = tn = 0
            fp_pressure = 0
            fp_weather = 0
            spike_tp = 0
            spike_gt = 0

            rows = eval_df.to_dict("records")
            t0 = time.time()

            for row in rows:
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

                verdict = score_reading_v3(
                    raw_reading, hist_df, artifact, neighbor_bufs,
                    use_continuous_peer=use_peer, use_lag_awareness=use_lag
                )
                is_pred = bool(verdict["is_anomaly"])
                gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
                gt_fault = str(row["fault_type"]) if pd.notna(row["fault_type"]) else "normal"

                if is_pred and gt_is_anom:
                    tp += 1
                    if gt_fault == "spike":
                        spike_tp += 1
                elif is_pred and not gt_is_anom:
                    fp += 1
                    # Track FP source
                    fault_type_pred = verdict.get("fault_type", "")
                    if "pressure" in str(verdict.get("likely_faulty_sensors", [])):
                        fp_pressure += 1
                    else:
                        fp_weather += 1
                elif not is_pred and gt_is_anom:
                    fn += 1
                else:
                    tn += 1

                if gt_fault == "spike":
                    spike_gt += 1

                buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

            dt = time.time() - t0
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            spike_recall = spike_tp / max(1, spike_gt)

            res_entry = {
                "architecture": mode_name,
                "seed": seed,
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "fp_pressure": fp_pressure,
                "fp_weather": fp_weather,
                "spike_recall": spike_recall,
                "precision": prec,
                "recall": rec,
                "f1": f1,
                "duration_sec": dt,
                "latency_ms": (dt / len(rows)) * 1000.0
            }
            seed_stats.append(res_entry)

            if mode_name == "C_Lag_Aware_Continuous_Peer":
                authoritative_seed_runs.append(res_entry)

        avg_p = float(np.mean([s["precision"] for s in seed_stats]))
        avg_r = float(np.mean([s["recall"] for s in seed_stats]))
        avg_f = float(np.mean([s["f1"] for s in seed_stats]))
        avg_sp_r = float(np.mean([s["spike_recall"] for s in seed_stats]))
        avg_fp_p = int(np.mean([s["fp_pressure"] for s in seed_stats]))
        avg_fp_w = int(np.mean([s["fp_weather"] for s in seed_stats]))

        print(f"{mode_name:28s} | Prec: {avg_p*100:6.2f}% | Rec: {avg_r*100:6.2f}% | F1: {avg_f*100:6.2f}% | Spike Rec: {avg_sp_r*100:6.2f}% | FP Press: {avg_fp_p:4d}")
        ablation_results.append({
            "architecture": mode_name,
            "precision": avg_p,
            "recall": avg_r,
            "f1": avg_f,
            "spike_recall": avg_sp_r,
            "avg_fp_pressure": avg_fp_p,
            "avg_fp_weather": avg_fp_w
        })

    ablation_df = pd.DataFrame(ablation_results)
    ablation_df.to_csv(OUTPUT_DIR / "peer_architecture_ablation.csv", index=False)

    # Save Authoritative Benchmark Results
    auth_df = pd.DataFrame(authoritative_seed_runs)
    auth_df.to_csv(OUTPUT_DIR / "peer_context_v3.csv", index=False)

    # 3. Separate Deployment-Realistic Continuous-Run Benchmark (Part 17)
    # Using 24-hour causal pre-roll
    print("\n==================================================================", flush=True)
    print("PART 17: DEPLOYMENT-REALISTIC CONTINUOUS-RUN BENCHMARK (24H PRE-ROLL)", flush=True)
    print("==================================================================", flush=True)

    continuous_benchmark_records = []
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

        # 24h clean historical pre-roll
        max_train_ts = train_df["timestamp"].max()
        min_warm_ts = max_train_ts - pd.Timedelta(hours=24)
        warm_slice = train_df[train_df["timestamp"] >= min_warm_ts].sort_values("timestamp")

        for w_row in warm_slice.to_dict("records"):
            w_sid = w_row["station_id"]
            w_ts = w_row["timestamp"]
            if w_sid in buffers:
                buffers[w_sid].record_raw_reading({
                    "station_id": w_sid,
                    "timestamp": w_ts,
                    "temperature_c": w_row["temperature_c"],
                    "pressure_hpa": w_row["pressure_hpa"],
                    "humidity_pct": w_row["humidity_pct"]
                }, timestamp=w_ts, verdict={"is_anomaly": False})

        tp = fp = fn = tn = 0
        rows = eval_df.to_dict("records")

        for row in rows:
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

            verdict = score_reading_v3(
                raw_reading, hist_df, artifact, neighbor_bufs,
                use_continuous_peer=True, use_lag_awareness=True
            )
            is_pred = bool(verdict["is_anomaly"])
            gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False

            if is_pred and gt_is_anom:
                tp += 1
            elif is_pred and not gt_is_anom:
                fp += 1
            elif not is_pred and gt_is_anom:
                fn += 1
            else:
                tn += 1

            buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

        dt = time.time() - t0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        continuous_benchmark_records.append({
            "seed": seed,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "duration_sec": dt,
            "latency_ms": (dt / len(rows)) * 1000.0
        })
        print(f"Continuous Seed {seed:12d} | Prec: {prec*100:6.2f}% | Rec: {rec*100:6.2f}% | F1: {f1*100:6.2f}%", flush=True)

    cont_df = pd.DataFrame(continuous_benchmark_records)
    cont_df.to_csv(OUTPUT_DIR / "continuous_run_benchmark.csv", index=False)

    macro_cp = float(np.mean(cont_df["precision"]))
    macro_cr = float(np.mean(cont_df["recall"]))
    macro_cf = float(np.mean(cont_df["f1"]))
    print(f"\nDEPLOYMENT-REALISTIC BENCHMARK MACRO: Precision = {macro_cp*100:.2f}% | Recall = {macro_cr*100:.2f}% | F1 = {macro_cf*100:.2f}%")


# =====================================================================
# 5. FORENSICS DATASETS GENERATION (PARTS 12 & 13)
# =====================================================================
def generate_forensics_datasets(test_raw_df: pd.DataFrame, artifact: dict):
    print("\n==================================================================", flush=True)
    print("PARTS 12 & 13: GENERATING PRESSURE & WEATHER FORENSIC DATASETS", flush=True)
    print("==================================================================", flush=True)

    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        group_injected = injector.inject_anomalies(group.copy(), seed=42)
        injected_frames.append(group_injected)

    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

    press_records = []
    weath_records = []
    lag_records = []

    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        buf = buffers[st_id]
        gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_fault = str(row["fault_type"]) if pd.notna(row["fault_type"]) else "normal"

        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
        hist_df = buf.raw_history_df()

        for p in PARAMS:
            val = float(row[p])
            prior_val = None
            if not hist_df.empty and p in hist_df.columns:
                valid_pvals = pd.to_numeric(hist_df[p], errors="coerce").dropna()
                if not valid_pvals.empty:
                    prior_val = float(valid_pvals.iloc[-1])

            if prior_val is not None:
                p_ev = compute_continuous_peer_evidence_v3(
                    st_id, p, ts, val, prior_val, 1.0, neighbor_bufs, use_lag_awareness=True
                )

                if abs(p_ev["z_target"]) >= 2.0:
                    rec = {
                        "station_id": st_id,
                        "timestamp": ts.isoformat(),
                        "parameter": p,
                        "d_target": p_ev["d_target"],
                        "z_target": p_ev["z_target"],
                        "peer_median_d": p_ev["peer_median_d"],
                        "peer_dispersion": p_ev["peer_dispersion"],
                        "z_surprise": p_ev["z_surprise"],
                        "peer_common_mode_llr": p_ev["peer_common_mode_llr"],
                        "common_mode_discount": p_ev["common_mode_discount"],
                        "dir_alignment": p_ev["dir_alignment"],
                        "has_1h_phase_lag": p_ev["has_1h_phase_lag"],
                        "applied_lag": p_ev["applied_lag"],
                        "is_ground_truth_anomaly": gt_is_anom,
                        "ground_truth_fault_type": gt_fault
                    }
                    if p == "pressure_hpa":
                        press_records.append(rec)
                        lag_records.append(rec)
                    else:
                        weath_records.append(rec)

        raw_reading = {
            "station_id": st_id, "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"]
        }
        verdict = score_reading_v3(raw_reading, hist_df, artifact, neighbor_bufs)
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)

    pd.DataFrame(press_records).to_csv(OUTPUT_DIR / "pressure_context_v3.csv", index=False)
    pd.DataFrame(weath_records).to_csv(OUTPUT_DIR / "weather_context_v3.csv", index=False)
    pd.DataFrame(lag_records).to_csv(OUTPUT_DIR / "peer_lag_analysis_v3.csv", index=False)
    print("Forensic CSV datasets successfully saved.")


# =====================================================================
# MAIN ENTRY
# =====================================================================
if __name__ == "__main__":
    stations_path = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(stations_path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    cutoff_idx = int(len(df) * 0.7)
    cutoff_date = df.iloc[cutoff_idx]["timestamp"]

    test_df = df[df["timestamp"] >= cutoff_date].copy().reset_index(drop=True)
    train_df = df[df["timestamp"] < cutoff_date].copy().reset_index(drop=True)

    artifact_path = ARTIFACTS_DIR / "isolation_forest.pkl"
    artifact = joblib.load(artifact_path) if artifact_path.exists() else {}

    # Run Safety Tests
    run_safety_and_leakage_tests()

    # Run Full Evaluation Suite
    run_evaluation_suite(train_df, test_df, artifact)

    # Generate Forensics Datasets
    generate_forensics_datasets(test_df, artifact)

    print("\nPrecision Step 3 Full Pipeline Complete.")
