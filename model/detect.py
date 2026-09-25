"""
model/detect.py

Path 2 — Dynamic Data-Adaptive Sensor Anomaly Detector.
Implements the 6-tier fault priority hierarchy:
  TIER 0: Hard Invariant / Hardware Rail Failures
  TIER 1: High-Specificity Specialist Faults (Spike, Frozen)
  TIER 2: Persistent Temporal Faults (Drift via Pre-Whitened SPRT)
  TIER 3: Cross-Channel & Peer-Supported Faults (Mahalanobis 3D, Spatial Contrast)
  TIER 4: Model-Dominant Supported Faults (Multivariate Inconsistency via IF statistical tail)
  TIER 5: AMBIGUOUS / NORMAL

Outputs clean causal verdicts with structured 3-time episodic diagnostics.
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from collections import deque

from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS
from model.sequential_sprt import SequentialSPRT
from model.peer_spatial_engine import PeerSpatialEngine
from model.cross_channel_covariance import CrossChannelEngine, compute_dewpoint_c

# Monitored physical parameters
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]
PARAM_PREFIXES = {
    "temperature_c": "temp",
    "pressure_hpa": "pressure",
    "humidity_pct": "humidity"
}

# Wald Decision Thresholds
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = SequentialSPRT.get_wald_boundaries(alpha=0.002, beta=0.05)


class SensorHealthTracker:
    """
    Per-station / per-parameter health state tracker and circuit breaker.
    """
    def __init__(self, station_id: str):
        self.station_id = station_id
        self.status = "HEALTHY"
        self.offline_reason = None
        self.param_status = {p: "HEALTHY" for p in PARAMS}
        self._clean_streak = 0
        self._param_recent_10h = {p: deque(maxlen=10) for p in PARAMS}
        self._param_recent_24h = {p: deque(maxlen=24) for p in PARAMS}

    def should_include_in_baseline(self) -> bool:
        return self.status != "OFFLINE"

    def record(self, verdict: dict):
        if verdict.get("is_anomaly"):
            self._clean_streak = 0
            fault = verdict.get("fault_type")
            if fault in ("sensor_fail_low", "dropout", "physical_bounds"):
                self.status = "OFFLINE"
                self.offline_reason = fault
        else:
            self._clean_streak += 1
            if self._clean_streak >= 3 and self.status == "WARNING":
                self.status = "HEALTHY"

    def force_recover(self):
        self.status = "HEALTHY"
        self.offline_reason = None
        self._clean_streak = 0
        for p in PARAMS:
            self.param_status[p] = "HEALTHY"
            self._param_recent_10h[p].clear()
            self._param_recent_24h[p].clear()


def _check_hardware_rail(raw_reading: dict) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Tier 0 Check: Detects exact electrical rail / transducer ground sentinels.
    Returns: (is_rail, param, reason)
    """
    for param in PARAMS:
        val = raw_reading.get(param)
        if val is None or pd.isna(val):
            return True, param, f"Sensor dropout: null measurement for {param}"
        
        v = float(val)
        if param == "temperature_c" and abs(v - (-40.0)) < 0.05:
            return True, param, f"Electrical fail-low rail detected: Temperature == -40.0C"
        if param == "pressure_hpa" and abs(v - 0.0) < 0.05:
            return True, param, f"Electrical fail-low rail detected: Pressure == 0.0 hPa"
        if param == "humidity_pct" and abs(v - 0.0) < 0.05:
            return True, param, f"Electrical fail-low rail detected: Humidity == 0.0%"
            
    return False, None, None


def evaluate_spike_evidence(
    param: str,
    current_val: float,
    expected_val: float,
    prior_val: Optional[float],
    current_sigma: float,
    dt_hours: float,
    valid_history_hours: float = 24.0,
    sibling_changes: Optional[List[float]] = None
) -> Tuple[float, Optional[str], Dict[str, any]]:
    """
    Tier 1 Spike Check: Evaluates dynamic jump likelihood ratio relative to pre-jump state.
    Requires at least 6.0 hours of valid contextual history. Never substitutes expected_val for missing prior.
    Incorporates sibling peer directional movement to distinguish isolated transducer spikes from regional weather events.
    """
    # ── 1. Physical-Time History Maturity Guard ─────────────────────────
    # If history is insufficient (< 6.0h) or prior is missing/stale (> 6.0h gap), jump evidence is unavailable.
    if prior_val is None or valid_history_hours < 6.0 or dt_hours > 6.0:
        return 0.0, None, {
            "jump_llr": 0.0,
            "is_spike": False,
            "status": "INSUFFICIENT_CONTEXT",
            "valid_history_hours": valid_history_hours,
            "dt_hours": dt_hours
        }

    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    
    # Measure discontinuity strictly against immediate causal prior reading
    raw_delta = current_val - prior_val
    jump_mag = abs(raw_delta)
    
    # Sub-uncertainty perturbation check
    if jump_mag < 2.5 * sensor_floor:
        return 0.0, None, {"jump_llr": 0.0, "is_spike": False, "status": "SUB_QUANTIZATION"}
    
    sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))
    z_jump = jump_mag / max(1e-4, sigma_jump)
    
    # Jump LLR
    jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
    
    # ── 2. Sibling Peer Common-Mode Corroboration ─────────────────────────
    is_common_mode = False
    peer_diag = {}
    if sibling_changes is not None and len(sibling_changes) >= 2:
        # Check directional alignment with sibling peers (normalized changes)
        target_sign = 1.0 if raw_delta > 0 else -1.0
        aligned_siblings = [z for z in sibling_changes if (z * target_sign) >= 1.5]
        peer_diag["sibling_count"] = len(sibling_changes)
        peer_diag["aligned_siblings_count"] = len(aligned_siblings)
        
        # Case B: Common-Mode Environmental Movement (>=2 siblings show aligned movement)
        if len(aligned_siblings) >= 2:
            is_common_mode = True
            jump_llr = 0.0  # Discount spike evidence in favor of regional environmental front
    
    is_spike = (jump_llr >= WALD_UPPER_ALERT) and (z_jump >= 3.0) and (not is_common_mode)
    
    if is_spike:
        reason = f"Instantaneous jump of {jump_mag:.2f} (z_jump={z_jump:.2f}, LLR={jump_llr:.2f})"
    elif is_common_mode:
        reason = f"Common-mode environmental movement corroborated by {len(aligned_siblings)} sibling peers"
    else:
        reason = None
    
    diagnostics = {
        "jump_mag": jump_mag,
        "z_jump": z_jump,
        "jump_llr": jump_llr,
        "is_spike": is_spike,
        "is_common_mode": is_common_mode,
        "valid_history_hours": valid_history_hours,
        "peer_corroboration": peer_diag
    }
    return jump_llr, reason, diagnostics


def evaluate_frozen_evidence(
    param: str,
    history_df: pd.DataFrame,
    current_val: float,
    peer_dispersion: Optional[float],
    eligible_peers: int
) -> Tuple[float, Optional[str], Dict[str, any]]:
    """
    Tier 1 Frozen Check: Evaluates F-ratio variance collapse vs peer network.
    """
    if history_df.empty or param not in history_df.columns or len(history_df) < 5:
        return 0.0, None, {"frozen_llr": 0.0, "is_frozen": False}
    
    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    
    # Extract last K readings (K = 6)
    valid_vals = pd.to_numeric(history_df[param], errors="coerce").dropna().tolist()
    recent_vals = valid_vals[-5:] + [current_val]
    
    if len(recent_vals) < 5:
        return 0.0, None, {"frozen_llr": 0.0, "is_frozen": False}
    
    target_var = float(np.var(recent_vals))
    target_range = float(max(recent_vals) - min(recent_vals))
    
    # Mode A: Bit-exact / quantized freeze
    is_exact_hold = target_range < 1e-4 and len(recent_vals) >= 5
    if is_exact_hold:
        return 12.0, f"Exact frozen hold across {len(recent_vals)} readings", {"frozen_llr": 12.0, "is_frozen": True}
    
    # Mode B: Jitter freeze vs Peer Active Variance
    peer_var = (peer_dispersion ** 2) if (peer_dispersion is not None and eligible_peers >= 2) else (1.5 * sensor_floor) ** 2
    
    f_ratio = (target_var + sensor_floor ** 2) / (peer_var + sensor_floor ** 2)
    
    # Frozen LLR
    k_len = len(recent_vals)
    frozen_llr = float(0.5 * k_len * (math.log(max(1e-4, 1.0 / max(1e-4, f_ratio))) + f_ratio - 1.0))
    
    # Pressure calmness guard
    if param == "pressure_hpa" and (peer_dispersion is None or peer_dispersion < 0.4):
        # Calm regional barometric pressure -> penalize LLR
        frozen_llr = min(0.0, frozen_llr)
    
    is_frozen = frozen_llr >= WALD_UPPER_ALERT and target_var <= (1.2 * sensor_floor) ** 2
    reason = f"Variance collapse (target_var={target_var:.4f} vs peer_var={peer_var:.4f}, LLR={frozen_llr:.2f})" if is_frozen else None
    
    diagnostics = {
        "target_var": target_var,
        "target_range": target_range,
        "f_ratio": f_ratio,
        "frozen_llr": frozen_llr,
        "is_frozen": is_frozen
    }
    return frozen_llr, reason, diagnostics


def score_reading(
    raw_reading: dict,
    history_df: pd.DataFrame,
    artifact: dict,
    neighbor_buffers: dict = None,
    state: Any = None,
    precomputed_features: pd.Series = None,
    precomputed_neighbors: dict = None,
    precomputed_history_featured: pd.DataFrame = None,
    include_evaluation_diagnostics: bool = True
) -> dict:
    """
    Main Path 2 Detection Entry Point.
    Executes the 6-tier fault priority hierarchy with strict causality.
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
            "evaluation_diagnostics": {
                "tier": 0,
                "reason": rail_reason,
                "evidence_llr": 999.0
            }
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
            "evaluation_diagnostics": {
                "tier": 0,
                "reason": phys_reason,
                "evidence_llr": 999.0
            }
        }
    
    # ── Compute Elapsed Physical Time & Context Maturity Duration ───────
    valid_history_hours = 0.0
    prior_time = None
    if not history_df.empty and "timestamp" in history_df.columns:
        ts_col = history_df["timestamp"]
        if not ts_col.empty:
            p_raw = ts_col.iloc[-1]
            f_raw = ts_col.iloc[0]
            prior_time = p_raw if isinstance(p_raw, pd.Timestamp) else pd.to_datetime(p_raw, utc=True)
            first_time = f_raw if isinstance(f_raw, pd.Timestamp) else pd.to_datetime(f_raw, utc=True)
            valid_history_hours = max(0.0, (prior_time - first_time).total_seconds() / 3600.0)
    
    dt_hours = max(0.1, (current_time - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(current_time, station_id)
    
    # Sibling peer changes for candidate spike evaluation (strictly 3 cluster siblings)
    sibling_peer_changes = {p: [] for p in PARAMS}
    if neighbor_buffers:
        for nid, nbuf in neighbor_buffers.items():
            rows = getattr(nbuf, "_raw_rows", None)
            if rows is not None and len(rows) >= 2:
                r_curr = rows[-1]
                r_prev = rows[-2]
                for p in PARAMS:
                    v_c = r_curr.get(p)
                    v_p = r_prev.get(p)
                    if v_c is not None and v_p is not None and not (pd.isna(v_c) or pd.isna(v_p)):
                        d_v = float(v_c) - float(v_p)
                        floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                        s_jump = math.sqrt(2.0 * (floor ** 2) + 0.25 * max(0.5, dt_hours))
                        sibling_peer_changes[p].append(d_v / max(1e-4, s_jump))
            else:
                nhist = nbuf.raw_history_df() if hasattr(nbuf, "raw_history_df") else None
                if nhist is not None and not nhist.empty and len(nhist) >= 2:
                    for p in PARAMS:
                        if p in nhist.columns:
                            valid_p = pd.to_numeric(nhist[p], errors="coerce").dropna()
                            if len(valid_p) >= 2:
                                d_v = float(valid_p.iloc[-1]) - float(valid_p.iloc[-2])
                                floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                                s_jump = math.sqrt(2.0 * (floor ** 2) + 0.25 * max(0.5, dt_hours))
                                sibling_peer_changes[p].append(d_v / max(1e-4, s_jump))
    
    # ── Dynamic Expectation & Uncertainty Evaluation ────────────────────
    innovations = {}
    uncertainties = {}
    expectations = {}
    z_scores = {}
    
    for param in PARAMS:
        val = float(raw_reading[param])
        
        # Peer spatial consensus for this parameter
        peer_med, peer_disp, n_peers = PeerSpatialEngine.compute_robust_peer_consensus(
            station_id, param, current_time, neighbor_buffers or {}
        )
        
        # Dynamic expectation
        exp_val, exp_roc = compute_dynamic_expectation(station_id, param, current_time, history_df)
        expectations[param] = exp_val
        
        # Composite uncertainty
        sigma_tot, u_breakdown = UncertaintyBudget.compute_composite_predictive_uncertainty(
            param, solar_hour, dt_hours, history_df, peer_dispersion=peer_disp or 0.0
        )
        uncertainties[param] = sigma_tot
        
        # Standardized innovation
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
        
        # 1. Spike Jump Check
        s_llr, s_reason, s_diag = evaluate_spike_evidence(
            param=param,
            current_val=val,
            expected_val=exp_val,
            prior_val=prior_val,
            current_sigma=sigma_tot,
            dt_hours=dt_hours,
            valid_history_hours=valid_history_hours,
            sibling_changes=sibling_peer_changes.get(param, [])
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
        peer_disp = None
        if neighbor_buffers:
            _, peer_disp, n_p = PeerSpatialEngine.compute_robust_peer_consensus(station_id, param, current_time, neighbor_buffers)
        else:
            n_p = 0
            
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
        
        # Autoregressive pre-whitening
        whitened_eps = SequentialSPRT.pre_whiten_residual(param, residual, prior_res, dt_hours, sigma_tot)
        
        # Dual CUSUM update
        s_pos, s_neg, drift_llr = SequentialSPRT.update_cusum(
            param, s_pos_prev=0.0, s_neg_prev=0.0,
            whitened_epsilon=whitened_eps, dt_hours=dt_hours, current_sigma=sigma_tot
        )
        
        # Directional contrast against peer network
        peer_med, _, n_p = PeerSpatialEngine.compute_robust_peer_consensus(station_id, param, current_time, neighbor_buffers or {})
        if peer_med is not None and n_p >= 2:
            peer_res = peer_med - expectations[param]
            if (residual * peer_res) < 0 and abs(residual) > 2.0 * sigma_tot:
                drift_llr *= 1.4  # Boost evidence on directional divergence
                
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

    # ── TIER 3: Cross-Channel 3D Mahalanobis & Spatial Contrast ──────────
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
            "evaluation_diagnostics": {
                "tier": 3,
                "d_squared": d_sq,
                "p_value": p_val
            }
        }

    # ── TIER 4: Model-Dominant Supported Faults (Isolation Forest) ───────
    # Evaluated strictly for multivariate inconsistency, never unstructured anomaly
    model = artifact.get("model") if artifact else None
    if model is not None and precomputed_features is not None:
        try:
            feat_cols = artifact.get("feature_columns", [])
            if feat_cols and all(col in precomputed_features.index for col in feat_cols):
                X = precomputed_features[feat_cols].values.reshape(1, -1).astype(float)
                if not np.isnan(X).any():
                    raw_if_score = float(model.decision_function(X)[0])
                    # Calibrated clean distribution std
                    train_std = artifact.get("training_score_std", 0.08)
                    z_if = (0.0 - raw_if_score) / max(1e-4, train_std)
                    
                    # Model dominant trigger: extreme statistical tail (z_if > 3.0) + cross-channel elevation
                    if z_if > 3.0 and d_sq > 8.0:
                        return {
                            "is_anomaly": True,
                            "fault_type": "multivariate_inconsistency",
                            "anomaly_score_pct": 88.0,
                            "decision_basis": "TIER_4_MODEL_DOMINANT_MULTIVARIATE",
                            "likely_faulty_sensors": ["temperature_c", "humidity_pct"],
                            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "model_joint", "confidence": 88.0, "reason": f"Isolation Forest empirical tail (z={z_if:.2f}) corroborated by cross-channel divergence (D^2={d_sq:.2f})"}],
                            "evaluation_diagnostics": {
                                "tier": 4,
                                "z_if": z_if,
                                "d_squared": d_sq
                            }
                        }
        except Exception:
            pass

    # ── TIER 5: Ambiguity vs Normal State ───────────────────────────────
    # Check if there is moderate unconfirmed tension
    max_z = max(abs(z) for z in z_scores.values())
    if max_z > 2.2 and neighbor_buffers and len(neighbor_buffers) == 0:
        return {
            "is_anomaly": False,
            "fault_type": None,
            "anomaly_score_pct": 35.0,
            "decision_basis": "AMBIGUOUS_NO_PEER_CORROBORATION",
            "likely_faulty_sensors": [],
            "rules_fired": [],
            "evaluation_diagnostics": {
                "tier": 5,
                "status": "AMBIGUOUS",
                "reason": "Moderate innovation residual without peer verification"
            }
        }
        
    return {
        "is_anomaly": False,
        "fault_type": None,
        "anomaly_score_pct": 5.0,
        "decision_basis": "NORMAL",
        "likely_faulty_sensors": [],
        "rules_fired": [],
        "evaluation_diagnostics": {
            "tier": 5,
            "status": "NORMAL",
            "max_z": max_z
        }
    }
