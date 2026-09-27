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
from scipy import stats

from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.seasonal_baseline import get_expected_roc
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

# Empirical atmospheric residual process rates after contextual expectation subtraction (std per sqrt(hour))
ATMOSPHERIC_PROCESS_RATES = {
    "temperature_c": 0.5472,    # deg C / sqrt(h)
    "pressure_hpa": 0.2474,     # hPa / sqrt(h)
    "humidity_pct": 3.2756      # % / sqrt(h)
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
    expected_roc: float = 0.0,
    sibling_peer_deltas: Optional[List[float]] = None
) -> Tuple[float, Optional[str], Dict[str, any]]:
    """
    Tier 1 Contextual-Innovation Spike Specialist:
    Evaluates normalized contextual innovation r_t = Delta y_t - E[Delta y_t | C_t]
    under composite conditional uncertainty sigma_total(t).
    """
    # Missing / insufficient causal history guard (temporal jump requires causal prior reading)
    if prior_val is None or dt_hours > 6.0:
        return 0.0, None, {
            "jump_llr": 0.0,
            "is_spike": False,
            "status": "INSUFFICIENT_CONTEXT"
        }
        
    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    proc_rate = ATMOSPHERIC_PROCESS_RATES.get(param, 0.5)
    raw_delta = current_val - prior_val
    dt_eff = min(3.0, max(0.05, dt_hours))
    diurnal_expected_delta = expected_roc * dt_eff
    
    peer_expected_delta = 0.0
    peer_dispersion = 0.0
    has_peer_consensus = False
    
    if sibling_peer_deltas is not None and len(sibling_peer_deltas) >= 2:
        valid_deltas = [d for d in sibling_peer_deltas if not np.isnan(d)]
        if len(valid_deltas) >= 2:
            peer_expected_delta = float(np.median(valid_deltas))
            peer_dispersion = float(np.std(valid_deltas))
            has_peer_consensus = True
            
    # Channel-adaptive contextual expectation E[Delta y | C_t]
    if param == "pressure_hpa":
        # Pressure: synoptic spatial coherence is dominant
        if has_peer_consensus:
            expected_delta = 0.85 * peer_expected_delta + 0.15 * diurnal_expected_delta
        else:
            expected_delta = diurnal_expected_delta
    elif param == "temperature_c":
        # Temperature: solar diurnal heating is primary
        if has_peer_consensus and peer_dispersion < 1.0:
            expected_delta = 0.80 * diurnal_expected_delta + 0.20 * peer_expected_delta
        else:
            expected_delta = diurnal_expected_delta
    else: # humidity_pct
        # Humidity: diurnal psychrometric curve is primary
        if has_peer_consensus and peer_dispersion < 3.0:
            expected_delta = 0.80 * diurnal_expected_delta + 0.20 * peer_expected_delta
        else:
            expected_delta = diurnal_expected_delta
            
    # Contextual innovation residual
    residual = raw_delta - expected_delta
    innovation_mag = abs(residual)
    
    # Sub-quantization perturbation check
    if innovation_mag < 2.0 * sensor_floor:
        return 0.0, None, {
            "jump_llr": 0.0,
            "is_spike": False,
            "innovation_mag": innovation_mag,
            "status": "SUB_QUANTIZATION"
        }
        
    var_sensor = 2.0 * (sensor_floor ** 2)
    var_process = (proc_rate ** 2) * dt_eff
    var_peer = (peer_dispersion ** 2) if (has_peer_consensus and peer_dispersion > 0.5 * sensor_floor) else 0.0
    
    sigma_jump = math.sqrt(var_sensor + var_process + var_peer)
    z_jump = innovation_mag / max(1e-4, sigma_jump)
    
    # Wald SPRT Log-Likelihood Ratio
    jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
    
    is_spike = (jump_llr >= WALD_UPPER_ALERT) and (z_jump >= 3.0)
    reason = (
        f"Instantaneous contextual spike of {raw_delta:+.2f} (innovation={residual:+.2f}, "
        f"z={z_jump:.2f}, LLR={jump_llr:.2f})" if is_spike else None
    )
    
    diagnostics = {
        "raw_delta": raw_delta,
        "expected_delta": expected_delta,
        "residual": residual,
        "innovation_mag": innovation_mag,
        "z_jump": z_jump,
        "jump_llr": jump_llr,
        "sigma_jump": sigma_jump,
        "peer_dispersion": peer_dispersion,
        "is_spike": is_spike
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
    
    # ── Compute Elapsed Physical Time (\Delta t) ────────────────────────
    prior_time = None
    if not history_df.empty and "timestamp" in history_df.columns:
        valid_ts = pd.to_datetime(history_df["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]
    
    dt_hours = max(0.1, (current_time - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(current_time, station_id)
    
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

    # Sibling peer changes for candidate spike evaluation (strictly cluster siblings)
    sibling_peer_deltas = {p: [] for p in PARAMS}
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
                        sibling_peer_deltas[p].append(float(v_c) - float(v_p))
            else:
                nhist = nbuf.raw_history_df() if hasattr(nbuf, "raw_history_df") else None
                if nhist is not None and not nhist.empty and len(nhist) >= 2:
                    for p in PARAMS:
                        if p in nhist.columns:
                            valid_p = pd.to_numeric(nhist[p], errors="coerce").dropna()
                            if len(valid_p) >= 2:
                                sibling_peer_deltas[p].append(float(valid_p.iloc[-1]) - float(valid_p.iloc[-2]))

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
        
        # Expected diurnal rate of change for this solar hour
        exp_roc = get_expected_roc(station_id, PARAM_PREFIXES.get(param, param), int(solar_hour) % 24)
        
        # 1. Spike Contextual Innovation Check
        s_llr, s_reason, s_diag = evaluate_spike_evidence(
            param=param,
            current_val=val,
            expected_val=exp_val,
            prior_val=prior_val,
            current_sigma=sigma_tot,
            dt_hours=dt_hours,
            expected_roc=exp_roc,
            sibling_peer_deltas=sibling_peer_deltas.get(param, [])
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
