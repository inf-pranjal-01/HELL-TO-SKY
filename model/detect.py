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
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS, DEFAULT_DIURNAL_SPREAD
from model.sequential_sprt import SequentialSPRT
from model.peer_spatial_engine import PeerSpatialEngine
from model.cross_channel_covariance import CrossChannelEngine, compute_dewpoint_c
from config import PHYSICAL_BOUNDS, FAIL_LOW_FLOOR, RULE_BASE_CONFIDENCE, score_to_severity, get_station_normal_ranges

# Monitored physical parameters
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]
PARAM_PREFIXES = {
    "temperature_c": "temp",
    "pressure_hpa": "pressure",
    "humidity_pct": "humidity"
}

# Wald Decision Thresholds (alpha=0.0005 for 0.05% false alarm bound, beta=0.05)
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = SequentialSPRT.get_wald_boundaries(alpha=0.0005, beta=0.05)


class SensorHealthTracker:
    """
    Per-station / per-parameter health state tracker with Continuous Health Index Hysteresis.
    Eliminates state flickering / flapping on intermittent transducer noise using asymmetric decay/recovery:
      - Anomaly degradation: H <- max(0.0, H - penalty) [penalty 25-40 based on severity/type]
      - Asymmetric gradual recovery: H <- min(100.0, H + 6.67) per clean reading (full recovery in 15 normal readings)
      - Hysteresis thresholds:
          H >= 70.0 -> HEALTHY (Green)
          30.0 <= H < 70.0 -> WARNING / DEGRADED (Yellow; maintenance recommended at H < 50.0)
          H < 30.0 -> OFFLINE (Red; quarantined from peer spatial and temporal baselines)
    """
    def __init__(self, station_id: str):
        self.station_id = station_id
        self.status = "HEALTHY"
        self.health_index: float = 100.0
        self.offline_reason: Optional[str] = None
        self.param_status: dict[str, str] = {p: "HEALTHY" for p in PARAMS}
        self.param_health: dict[str, float] = {p: 100.0 for p in PARAMS}
        self.needs_maintenance: bool = False
        self._clean_streak: int = 0
        self._param_recent_10h: dict[str, deque] = {p: deque(maxlen=10) for p in PARAMS}
        self._param_recent_24h: dict[str, deque] = {p: deque(maxlen=24) for p in PARAMS}

    def should_include_in_baseline(self) -> bool:
        return self.status != "OFFLINE" and self.health_index >= 30.0

    def record(self, verdict: dict):
        is_anom = bool(verdict.get("is_anomaly", False))
        severity = str(verdict.get("severity", "medium")).lower()
        fault = verdict.get("fault_type") or "anomaly"
        affected = verdict.get("likely_faulty_sensors") or verdict.get("affected_parameters") or []

        if is_anom:
            self._clean_streak = 0
            penalty = 40.0 if severity == "critical" else (30.0 if severity == "high" else 25.0)
            self.health_index = max(0.0, self.health_index - penalty)
            self.offline_reason = fault

            for p in PARAMS:
                if p in affected or not affected:
                    self.param_health[p] = max(0.0, self.param_health[p] - penalty)
                else:
                    self.param_health[p] = min(100.0, self.param_health[p] + 1.0)
        else:
            self._clean_streak += 1
            # Asymmetric gradual recovery: 100.0 / 15 readings = ~6.67 points per clean reading (full recovery in 15 normal readings)
            recovery_step = 100.0 / 15.0
            self.health_index = min(100.0, self.health_index + recovery_step)
            for p in PARAMS:
                self.param_health[p] = min(100.0, self.param_health[p] + recovery_step)

        # Hysteresis state transition evaluation
        if self.health_index >= 70.0:
            self.status = "HEALTHY"
            self.offline_reason = None
        elif self.health_index >= 30.0:
            self.status = "WARNING"
        else:
            self.status = "OFFLINE"

        self.needs_maintenance = self.health_index < 50.0

        for p in PARAMS:
            if self.param_health[p] >= 70.0:
                self.param_status[p] = "HEALTHY"
            elif self.param_health[p] >= 30.0:
                self.param_status[p] = "WARNING"
            else:
                self.param_status[p] = "OFFLINE"

    def force_recover(self):
        self.status = "HEALTHY"
        self.health_index = 100.0
        self.offline_reason = None
        self.needs_maintenance = False
        self._clean_streak = 0
        for p in PARAMS:
            self.param_status[p] = "HEALTHY"
            self.param_health[p] = 100.0
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
) -> Tuple[float, Optional[str], Dict[str, Any]]:
    """
    Tier 1 Spike Check: Evaluates dynamic jump likelihood ratio relative to pre-jump state and spatial context.
    """
    if prior_val is None:
        return 0.0, None, {"jump_llr": 0.0, "is_spike": False, "status": "INSUFFICIENT_CONTEXT"}

    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    delta = current_val - prior_val
    expected_change = expected_roc * max(0.01, dt_hours)

    peer_dispersion = 0.0
    if sibling_peer_deltas:
        peer_arr = np.array(sibling_peer_deltas)
        peer_med = float(np.median(peer_arr))
        iqr = float(np.percentile(peer_arr, 75) - np.percentile(peer_arr, 25))
        peer_dispersion = max(0.10, iqr / 1.349 if iqr > 0 else float(np.std(peer_arr)))
        # If peers strongly agree on an environmental change, incorporate peer consensus
        if peer_dispersion < 1.0:
            expected_change = peer_med

    jump_mag = abs(delta - expected_change)

    # Sub-quantization gate (ignores sub-ADC noise within 2.5x sensor resolution floor)
    if abs(delta) < 2.5 * sensor_floor or jump_mag < 2.5 * sensor_floor:
        return 0.0, None, {"jump_mag": jump_mag, "z_jump": 0.0, "jump_llr": 0.0, "is_spike": False}

    from model.uncertainty_budget import GAP_GROWTH_RATES
    kappa = GAP_GROWTH_RATES.get(param, 0.25)
    
    # 1-step natural innovation scale combining quantization noise, diurnal channel volatility, and peer dispersion
    sigma_jump = math.sqrt(
        2.0 * (sensor_floor ** 2)
        + (0.6 * current_sigma) ** 2 * min(1.0, max(0.05, dt_hours))
        + (peer_dispersion ** 2)
        + kappa * max(0.05, dt_hours)
    )
    z_jump = jump_mag / max(1e-4, sigma_jump)

    # Dynamic Wald Jump LLR
    jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))

    is_spike = jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.5
    reason = f"Instantaneous jump of {jump_mag:.2f} (z_jump={z_jump:.2f}, LLR={jump_llr:.2f})" if is_spike else None

    diagnostics = {
        "jump_mag": jump_mag,
        "z_jump": z_jump,
        "jump_llr": jump_llr,
        "is_spike": is_spike
    }
    return jump_llr, reason, diagnostics


def evaluate_frozen_evidence(
    param: str,
    history_df: pd.DataFrame,
    current_val: float,
    peer_dispersion: Optional[float],
    eligible_peers: int,
    peer_median: Optional[float] = None,
) -> Tuple[float, Optional[str], Dict[str, any]]:
    """
    Tier 1 Frozen Check: Closed-form Bayesian F-ratio variance collapse test vs peer network.
    Evaluates likelihood of transducer mechanism failure vs regional atmospheric movement.
    """
    if history_df.empty or param not in history_df.columns or len(history_df) < 5:
        return 0.0, None, {"frozen_llr": 0.0, "is_frozen": False}
    
    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    
    # Extract last K readings fast
    raw_col = history_df[param].to_numpy()
    valid_vals = [float(v) for v in raw_col[-8:] if v is not None and not pd.isna(v)]
    recent_vals = valid_vals[-5:] + [current_val]
    
    if len(recent_vals) < 5:
        return 0.0, None, {"frozen_llr": 0.0, "is_frozen": False}
    
    target_var = float(np.var(recent_vals))
    target_range = float(max(recent_vals) - min(recent_vals))
    
    # 1. Saturation Equilibrium Guard for Relative Humidity:
    # Saturated ambient condensation is a natural thermodynamic equilibrium when peers agree
    if param == "humidity_pct" and current_val >= 98.0:
        if peer_median is None or peer_median >= 88.0:
            return 0.0, None, {"frozen_llr": 0.0, "is_frozen": False, "saturation_hold": True}
        else:
            return 12.0, f"Humidity sensor pinned at 100% saturation while cluster peers report {peer_median:.1f}%", {"frozen_llr": 12.0, "is_frozen": True}

    # 2. Expected Active Physical Variance under H0:
    # When peers are available, H0 variance reflects regional ambient dynamics + quantization noise.
    # When regional peers are also steady (peer_dispersion -> 0), peer_var naturally approaches sensor_floor^2,
    # causing F -> 1.0 and LLR -> 0.0 with zero magic thresholds.
    if peer_dispersion is not None and eligible_peers >= 2:
        peer_var = (peer_dispersion ** 2) + (sensor_floor ** 2)
    else:
        peer_var = (1.5 * sensor_floor) ** 2

    # 3. Observed Target Variance under H1:
    target_observed_var = target_var + (sensor_floor ** 2)
    
    # 4. Bayesian F-Ratio Log-Likelihood Ratio:
    f_ratio = target_observed_var / peer_var
    k_len = len(recent_vals)
    
    if f_ratio < 1.0:
        frozen_llr = float(0.5 * k_len * (math.log(1.0 / max(1e-4, f_ratio)) + f_ratio - 1.0))
    else:
        frozen_llr = 0.0
    
    # Physical Wald alert criterion: evidence cleared Wald threshold AND target variance is within sensor floor
    is_frozen = frozen_llr >= WALD_UPPER_ALERT and target_var <= (sensor_floor ** 2)
    reason = f"Variance collapse (target_var={target_var:.4f} vs peer_var={peer_var:.4f}, LLR={frozen_llr:.2f})" if is_frozen else None
    
    diagnostics = {
        "target_var": target_var,
        "target_range": target_range,
        "f_ratio": f_ratio,
        "frozen_llr": frozen_llr,
        "is_frozen": is_frozen
    }
    return frozen_llr, reason, diagnostics


def _compute_suggested_values(
    implicated_params: list[str],
    expectations: dict,
    neighbor_buffers: dict,
    station_id: str,
    current_time: Any,
    history_df: Optional[pd.DataFrame] = None
) -> dict:
    suggestions = {}
    normal_ranges = get_station_normal_ranges(station_id)
    for param in (implicated_params or PARAMS):
        if param in PARAMS:
            peer_med = None
            n_peers = 0
            if neighbor_buffers:
                peer_med, _, n_peers = PeerSpatialEngine.compute_robust_peer_consensus(
                    station_id, param, current_time, neighbor_buffers
                )
            if peer_med is not None and not pd.isna(peer_med) and n_peers >= 1:
                val = float(peer_med)
            elif expectations and param in expectations and expectations[param] is not None and not pd.isna(expectations[param]):
                val = float(expectations[param])
            elif history_df is not None and not history_df.empty and param in history_df.columns:
                valid_vals = pd.to_numeric(history_df[param], errors="coerce").dropna()
                # Exclude the current reading (last row) and filter for plausible normal range
                p_bounds = normal_ranges.get(param, {"normal_min": PHYSICAL_BOUNDS[param][0], "normal_max": PHYSICAL_BOUNDS[param][1]})
                clean_vals = valid_vals.iloc[:-1] if len(valid_vals) > 1 else valid_vals
                clean_in_bounds = clean_vals[(clean_vals >= p_bounds["normal_min"]) & (clean_vals <= p_bounds["normal_max"])]
                if not clean_in_bounds.empty:
                    val = float(clean_in_bounds.iloc[-1])
                else:
                    val = (p_bounds["normal_min"] + p_bounds["normal_max"]) / 2.0
            else:
                p_bounds = normal_ranges.get(param, {"normal_min": 5.0, "normal_max": 45.0})
                val = (p_bounds["normal_min"] + p_bounds["normal_max"]) / 2.0

            # Enforce thermodynamic physical envelope
            if param == "humidity_pct":
                val = max(0.0, min(100.0, val))
            elif param == "pressure_hpa":
                val = max(850.0, min(1085.0, val))
            elif param == "temperature_c":
                val = max(-50.0, min(60.0, val))

            suggestions[param] = round(val, 1)
    return suggestions


def score_reading(
    raw_reading: dict,
    history_df: pd.DataFrame,
    artifact: dict,
    neighbor_buffers: dict = None,
    state: Any = None,
    precomputed_features: pd.Series = None,
    precomputed_neighbors: dict = None,
    precomputed_history_featured: pd.DataFrame = None,
    include_evaluation_diagnostics: bool = True,
    **kwargs
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
        implicated = [rail_param] if rail_param else PARAMS
        return {
            "is_anomaly": True,
            "fault_type": fault_type,
            "severity": "critical",
            "anomaly_score_pct": 100.0,
            "decision_basis": "TIER_0_HARD_INVARIANT",
            "likely_faulty_sensors": implicated,
            "suggested_values": _compute_suggested_values(implicated, {}, neighbor_buffers, station_id, current_time, history_df),
            "rules_fired": [{"type": fault_type, "parameter": rail_param, "confidence": 100.0, "reason": rail_reason}],
            "regime": "UNKNOWN_INSUFFICIENT_DATA",
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
        implicated = PARAMS
        return {
            "is_anomaly": True,
            "fault_type": "physical_bounds",
            "severity": "critical",
            "anomaly_score_pct": 100.0,
            "decision_basis": "TIER_0_THERMODYNAMIC_BOUND",
            "likely_faulty_sensors": implicated,
            "suggested_values": _compute_suggested_values(implicated, {}, neighbor_buffers, station_id, current_time, history_df),
            "rules_fired": [{"type": "physical_bounds", "parameter": "multivariate", "confidence": 100.0, "reason": phys_reason}],
            "regime": "UNKNOWN_INSUFFICIENT_DATA",
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
        prior_ts = valid_ts[valid_ts < current_time]
        if not prior_ts.empty:
            prior_time = prior_ts.iloc[-1]
    
    if prior_time is not None:
        raw_dt = (current_time - prior_time).total_seconds() / 3600.0
        dt_hours = max(0.1, min(24.0, raw_dt))
    else:
        dt_hours = 1.0
    solar_hour = calculate_solar_hour(current_time, station_id)
    regime = _classify_regime(precomputed_features, raw_reading, history_df)
    
    # ── Dynamic Expectation & Uncertainty Evaluation ────────────────────
    innovations = {}
    uncertainties = {}
    expectations = {}
    expected_rocs = {}
    z_scores = {}
    
    for param in PARAMS:
        val = float(raw_reading[param])
        prefix = PARAM_PREFIXES.get(param, param)
        
        # Peer spatial consensus for this parameter
        peer_med, peer_disp, n_peers = PeerSpatialEngine.compute_robust_peer_consensus(
            station_id, param, current_time, neighbor_buffers or {}
        )
        
        # Dynamic expectation & solar ROC with spatial cold-start support
        exp_val, exp_roc = compute_dynamic_expectation(
            station_id, param, current_time, history_df, neighbor_median=peer_med
        )
        expected_rocs[param] = exp_roc
        
        if precomputed_features is not None and f"{prefix}_rolling_mean" in precomputed_features and not pd.isna(precomputed_features[f"{prefix}_rolling_mean"]):
            exp_val = float(precomputed_features[f"{prefix}_rolling_mean"])
            channel_sigma_floor = DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
            sigma_tot = max(channel_sigma_floor, float(precomputed_features.get(f"{prefix}_robust_scale", 1.0)))
            residual = val - exp_val
        else:
            # Composite uncertainty
            sigma_tot, u_breakdown = UncertaintyBudget.compute_composite_predictive_uncertainty(
                param, solar_hour, dt_hours, history_df, peer_dispersion=peer_disp or 0.0
            )
            residual = val - exp_val
            
        expectations[param] = exp_val
        uncertainties[param] = sigma_tot
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
            if "timestamp" in history_df.columns:
                valid_prior_rows = history_df[pd.to_datetime(history_df["timestamp"], utc=True) < current_time]
            else:
                valid_prior_rows = history_df.iloc[:-1]
            if not valid_prior_rows.empty and param in valid_prior_rows.columns:
                raw_vals = valid_prior_rows[param].to_numpy()
                for idx in range(len(raw_vals) - 1, -1, -1):
                    pv = raw_vals[idx]
                    if pv is not None and not pd.isna(pv):
                        prior_val = float(pv)
                        break
        
        # 1. Spike Jump Check with diurnal rate-of-change compensation
        s_llr, s_reason, s_diag = evaluate_spike_evidence(
            param, val, exp_val, prior_val, sigma_tot, dt_hours, expected_roc=expected_rocs.get(param, 0.0)
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
        peer_med, peer_disp, n_p = (None, None, 0)
        if neighbor_buffers:
            peer_med, peer_disp, n_p = PeerSpatialEngine.compute_robust_peer_consensus(station_id, param, current_time, neighbor_buffers)
            
        f_llr, f_reason, f_diag = evaluate_frozen_evidence(param, history_df, val, peer_disp, n_p, peer_median=peer_med)
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
        score_pct = float(strongest["confidence"])
        severity = "critical" if score_pct >= 90.0 else "high"
        implicated = [strongest["parameter"]]
        return {
            "is_anomaly": True,
            "fault_type": strongest["type"],
            "severity": severity,
            "anomaly_score_pct": score_pct,
            "decision_basis": f"TIER_1_SPECIALIST_{strongest['type'].upper()}",
            "likely_faulty_sensors": implicated,
            "suggested_values": _compute_suggested_values(implicated, expectations, neighbor_buffers, station_id, current_time, history_df),
            "rules_fired": tier1_evidence,
            "regime": regime,
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
                
        if drift_llr >= WALD_UPPER_ALERT and abs(z_scores[param]) >= 2.2:
            tier2_evidence.append({
                "tier": 2,
                "type": "drift",
                "parameter": param,
                "llr": drift_llr,
                "confidence": min(95.0, 80.0 + drift_llr),
                "reason": f"Pre-whitened SPRT accumulator (LLR={drift_llr:.2f}, z={z_scores[param]:.2f}) cleared Wald threshold",
                "observed_value": float(raw_reading[param])
            })
            
    if tier2_evidence:
        strongest = max(tier2_evidence, key=lambda e: e["llr"])
        score_pct = float(strongest["confidence"])
        severity = "high" if score_pct >= 85.0 else "medium"
        implicated = [strongest["parameter"]]
        return {
            "is_anomaly": True,
            "fault_type": "drift",
            "severity": severity,
            "anomaly_score_pct": score_pct,
            "decision_basis": "TIER_2_PERSISTENT_DRIFT",
            "likely_faulty_sensors": implicated,
            "suggested_values": _compute_suggested_values(implicated, expectations, neighbor_buffers, station_id, current_time, history_df),
            "rules_fired": tier2_evidence,
            "regime": regime,
            "evaluation_diagnostics": {
                "tier": 2,
                "peak_llr": strongest["llr"],
                "trigger_source": "drift"
            }
        }

    # ── TIER 3: Cross-Channel 3D Mahalanobis & Spatial Contrast ──────────
    # Pure peer-driven microclimate adaptation: compute spatial contrast against regional peer cluster
    peer_z = {}
    eligible_peer_count = 0
    for p in PARAMS:
        p_med, p_disp, n_p = PeerSpatialEngine.compute_robust_peer_consensus(
            station_id, p, current_time, neighbor_buffers or {}
        )
        if p_med is not None and not pd.isna(p_med) and n_p >= 2:
            spatial_diff = float(raw_reading[p]) - float(p_med)
            spatial_sigma = math.sqrt((uncertainties[p] ** 2) + ((p_disp or 0.5) ** 2))
            peer_z[p] = spatial_diff / max(1e-4, spatial_sigma)
            eligible_peer_count = max(eligible_peer_count, n_p)
        else:
            peer_z[p] = z_scores[p]

    if eligible_peer_count >= 2:
        # Spatial peer-subtracted Mahalanobis: captures true isolated transducer divergence
        d_sq, p_val, cc_diag = CrossChannelEngine.compute_mahalanobis_distance(
            peer_z["temperature_c"], peer_z["pressure_hpa"], peer_z["humidity_pct"]
        )
        is_multivariate = cc_diag["is_multivariate_outlier"] and d_sq > 16.27
    else:
        # Isolated station fallback: evaluate local temporal innovation with strict physical invariants
        d_sq, p_val, cc_diag = CrossChannelEngine.compute_mahalanobis_distance(
            z_scores["temperature_c"], z_scores["pressure_hpa"], z_scores["humidity_pct"]
        )
        is_hard_phys, _ = CrossChannelEngine.check_physical_invariants(
            raw_reading.get("temperature_c"), raw_reading.get("pressure_hpa"), raw_reading.get("humidity_pct")
        )
        has_sufficient_history = (
            not history_df.empty
            and len(history_df[pd.to_datetime(history_df["timestamp"], utc=True) < current_time]) >= 3
            if "timestamp" in history_df.columns
            else len(history_df) >= 3
        )
        is_multivariate = is_hard_phys or (has_sufficient_history and cc_diag["is_multivariate_outlier"] and d_sq > 60.0)

    if is_multivariate:
        implicated = ["temperature_c", "humidity_pct"]
        return {
            "is_anomaly": True,
            "fault_type": "multivariate_inconsistency",
            "severity": "high",
            "anomaly_score_pct": 90.0,
            "decision_basis": "TIER_3_MAHALANOBIS_CROSS_CHANNEL",
            "likely_faulty_sensors": implicated,
            "suggested_values": _compute_suggested_values(implicated, expectations, neighbor_buffers, station_id, current_time, history_df),
            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "joint", "confidence": 90.0, "reason": f"3D Spatial Mahalanobis distance D^2={d_sq:.2f} exceeded critical threshold (p={p_val:.4e})"}],
            "regime": regime,
            "evaluation_diagnostics": {
                "tier": 3,
                "d_squared": d_sq,
                "p_value": p_val,
                "eligible_peers": eligible_peer_count
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
                        implicated = ["temperature_c", "humidity_pct"]
                        return {
                            "is_anomaly": True,
                            "fault_type": "multivariate_inconsistency",
                            "severity": "medium",
                            "anomaly_score_pct": 88.0,
                            "decision_basis": "TIER_4_MODEL_DOMINANT_MULTIVARIATE",
                            "likely_faulty_sensors": implicated,
                            "suggested_values": _compute_suggested_values(implicated, expectations, neighbor_buffers, station_id, current_time, history_df),
                            "rules_fired": [{"type": "multivariate_inconsistency", "parameter": "model_joint", "confidence": 88.0, "reason": f"Isolation Forest empirical tail (z={z_if:.2f}) corroborated by cross-channel divergence (D^2={d_sq:.2f})"}],
                            "regime": regime,
                            "evaluation_diagnostics": {
                                "tier": 4,
                                "z_if": z_if,
                                "d_squared": d_sq,
                                "eligible_peers": eligible_peer_count
                            }
                        }
        except Exception:
            pass

    # ── TIER 5: Ambiguity vs Normal State ───────────────────────────────
    # Check if there is moderate unconfirmed tension
    max_z = max(abs(z) for z in z_scores.values())
    if max_z > 2.2 and (neighbor_buffers is None or len(neighbor_buffers) == 0):
        return {
            "is_anomaly": False,
            "fault_type": None,
            "severity": "low",
            "anomaly_score_pct": 35.0,
            "decision_basis": "AMBIGUOUS_NO_PEER_CORROBORATION",
            "likely_faulty_sensors": [],
            "rules_fired": [],
            "regime": regime,
            "evaluation_diagnostics": {
                "tier": 5,
                "status": "AMBIGUOUS",
                "reason": "Moderate innovation residual without peer verification"
            }
        }
        
    return {
        "is_anomaly": False,
        "fault_type": None,
        "severity": "low",
        "anomaly_score_pct": 5.0,
        "decision_basis": "NORMAL",
        "likely_faulty_sensors": [],
        "rules_fired": [],
        "regime": regime,
        "evaluation_diagnostics": {
            "tier": 5,
            "status": "NORMAL",
            "max_z": max_z
        }
    }


# ============================================================================
# Modular & Diagnostic Compatibility Layer
# (Supports isolated unit tests, offline evaluation suites, and legacy harnesses)
# ============================================================================

def _multiclass_fault_label(*args, **kwargs):
    if len(args) == 1 and isinstance(args[0], list):
        fired_rules = args[0]
        if not fired_rules:
            return "none"
        for r in fired_rules:
            t = r.get("type") if isinstance(r, dict) else r[0]
            if t in ("physical_bounds", "dropout", "sensor_fail_low", "spike", "frozen_value", "drift", "multivariate_inconsistency"):
                return t
        return "unstructured_anomaly"

    helper = args[0] if len(args) > 0 else kwargs.get("helper")
    feature_columns = args[1] if len(args) > 1 else kwargs.get("feature_columns", [])
    frame = args[2] if len(args) > 2 else kwargs.get("frame", pd.DataFrame())

    if helper is None or not hasattr(helper, "classes_"):
        return None, None

    classes = list(helper.classes_)
    if len(classes) <= 2 and (
        all(isinstance(c, (bool, np.bool_)) for c in classes)
        or set(classes) <= {True, False, 0, 1}
    ):
        return None, None

    try:
        cols = [c for c in feature_columns if c in frame.columns]
        sub_frame = frame[cols] if cols else frame
        probs = helper.predict_proba(sub_frame)[0]
        max_idx = int(np.argmax(probs))
        return str(classes[max_idx]), float(probs[max_idx])
    except Exception:
        return None, None

def _classify_regime(feature_row: pd.Series, raw_reading: dict, history_df: pd.DataFrame) -> str:
    try:
        ts_val = raw_reading.get("timestamp") or (history_df["timestamp"].iloc[-1] if not history_df.empty else None)
        hour = pd.to_datetime(ts_val).hour if ts_val is not None else 12

        def get(col, default=None):
            if feature_row is None:
                return default
            v = feature_row.get(col)
            if v is None or (hasattr(v, '__float__') and pd.isna(float(v))):
                return default
            return float(v)

        temp_c = get("temperature_c") or raw_reading.get("temperature_c")
        humidity_pct = get("humidity_pct") or raw_reading.get("humidity_pct")
        temp_dev = get("temp_deviation")
        humidity_dev = get("humidity_deviation")
        temp_roc_1h = get("temp_roc_1h", 0.0)
        temp_roc_3h = get("temp_roc_3h", 0.0)
        pressure_roc_3h = get("pressure_roc_3h", 0.0)
        temp_vol_z = get("temp_volatility_z", 0.0)
        pressure_vol_z = get("pressure_volatility_z", 0.0)
        humidity_vol_z = get("humidity_volatility_z", 0.0)

        if temp_dev is None or humidity_dev is None:
            return "UNKNOWN_INSUFFICIENT_DATA"

        if (temp_vol_z is not None and abs(temp_vol_z) > 2.0
                or pressure_vol_z is not None and abs(pressure_vol_z) > 2.0
                or humidity_vol_z is not None and abs(humidity_vol_z) > 2.0):
            return "HIGH_VOLATILITY"

        vapor_dev = get("vapor_pressure_consistency_dev", None)
        if vapor_dev is not None and abs(vapor_dev) > 15.0:
            return "THERMODYNAMIC_CONFLICT"

        if (temp_c is not None and temp_c > 35.0) or (temp_dev is not None and temp_dev > 2.5):
            return "HIGH_HEAT"

        if (humidity_pct is not None and humidity_pct > 85.0) or (humidity_dev is not None and humidity_dev > 2.0):
            return "HIGH_HUMIDITY"

        if pressure_roc_3h is not None and abs(pressure_roc_3h) > 2.0:
            return "PRESSURE_SHIFT"

        if history_df is not None and len(history_df) >= 3 and "temperature_c" in history_df.columns:
            recent_temps = pd.to_numeric(history_df["temperature_c"].tail(4), errors="coerce").dropna().to_numpy()
            if len(recent_temps) >= 3:
                diffs = [recent_temps[i+1] - recent_temps[i] for i in range(len(recent_temps)-1)]
                signs = [1 if d > 0 else (-1 if d < 0 else 0) for d in diffs]
                non_zero = [s for s in signs if s != 0]
                if len(non_zero) >= 2 and non_zero[-1] != non_zero[-2]:
                    return "REGIME_TRANSITION"

        if (abs(temp_roc_3h) < 0.5 and abs(temp_dev) < 0.5 and abs(pressure_roc_3h) < 0.5):
            return "STABLE"

        if 6 <= hour < 18:
            if temp_roc_3h is not None and temp_roc_3h > 0 and temp_dev > 0.2:
                return "DAYTIME_WARMING"
            return "STABLE"
        else:
            if temp_roc_3h is not None and temp_roc_3h < 0:
                return "NIGHTTIME_COOLING"
            return "STABLE"
    except Exception:
        return "UNKNOWN_CONTEXT_FAILURE"


def _rule_checks(
    raw_reading: dict,
    feature_row: pd.Series,
    history_df: pd.DataFrame,
    neighbor_buffers: dict = None,
    artifact: dict = None,
    precomputed_history_featured: pd.DataFrame = None,
    precomputed_cusum: dict = None,
) -> dict:
    fired = []

    # Physical limits check
    for param, (low, high) in PHYSICAL_BOUNDS.items():
        val = raw_reading.get(param)
        if val is not None and not pd.isna(val) and not (low <= float(val) <= high):
            fired.append({
                "type": "physical_bounds",
                "parameter": param,
                "confidence": RULE_BASE_CONFIDENCE["physical_bounds"],
                "observed_value": val,
                "threshold": f"[{low}, {high}]",
                "reason": f"{param} {val} out of bounds [{low}, {high}]"
            })

    # Dropout check
    for param in PARAMS:
        val = raw_reading.get(param)
        if val is None or pd.isna(val):
            fired.append({
                "type": "dropout",
                "parameter": param,
                "confidence": RULE_BASE_CONFIDENCE["dropout"],
                "observed_value": None,
                "threshold": "null",
                "reason": f"Sensor dropout: null measurement for {param}"
            })

    return {
        "fired": fired,
        "any": len(fired) > 0,
        "fast_path_offline_params": set(r["parameter"] for r in fired if r["type"] in ("physical_bounds", "dropout"))
    }


def _cusum_evidence(
    featured_buffer: pd.DataFrame,
    prefix: str,
    param: str,
    station_id: str = "",
    current_hour: int = 0,
) -> Optional[dict]:
    roc_col = f"{prefix}_roc_1h"
    if featured_buffer is None or featured_buffer.empty or roc_col not in featured_buffer:
        return None
    rocs = pd.to_numeric(featured_buffer[roc_col], errors="coerce").dropna().values
    if len(rocs) < 3:
        return None
    
    # Check continuous climbing or descending residuals
    pos_streak = sum(1 for r in rocs[-6:] if r > 0.2)
    neg_streak = sum(1 for r in rocs[-6:] if r < -0.2)
    
    if pos_streak >= 4 or neg_streak >= 4:
        direction = 1 if pos_streak >= 4 else -1
        conf = min(95.0, 85.0 + max(pos_streak, neg_streak) * 2.0)
        return {
            "type": "drift",
            "parameter": param,
            "confidence": conf,
            "direction": direction,
            "reason": f"Persistent {param} rate-of-change streak across {max(pos_streak, neg_streak)} steps."
        }
    return None


def _cusum_evidence_series(
    featured_buffer: pd.DataFrame,
    prefix: str,
    param: str,
    station_id: str = "",
    max_window: int | None = None
) -> list[dict | None]:
    if featured_buffer is None or featured_buffer.empty:
        return []
    results = []
    for i in range(len(featured_buffer)):
        sub = featured_buffer.iloc[max(0, i - 12): i + 1]
        results.append(_cusum_evidence(sub, prefix, param, station_id))
    return results


def _apply_diurnal_consensus_filter(
    fired: list,
    neighbor_buffers: dict,
    feature_row: pd.Series
) -> tuple:
    if not neighbor_buffers:
        return fired, {}

    from config import (
        SPIKE_DIURNAL_MIN_PEERS,
        SPIKE_DIURNAL_CONSENSUS_FRACTION,
        SPIKE_DIURNAL_SUPPRESSION_FACTOR,
        SPIKE_DIURNAL_PEER_MIN_ROC,
    )

    suppression_map = {}
    for param, prefix in PARAM_PREFIXES.items():
        param_spikes = [r for r in fired if r.get("type") == "spike" and r.get("parameter") == param]
        if not param_spikes:
            continue

        target_roc_raw = feature_row.get(f"{prefix}_roc_1h") if feature_row is not None else 1.0
        target_direction = 1 if (float(target_roc_raw) if target_roc_raw is not None and not pd.isna(target_roc_raw) else 1.0) > 0 else -1
        min_roc = SPIKE_DIURNAL_PEER_MIN_ROC.get(param, 0.5)

        n_eligible = 0
        n_agreeing = 0
        for _nid, nbuf_df in neighbor_buffers.items():
            if nbuf_df is None or nbuf_df.empty or param not in nbuf_df.columns:
                continue
            vals = pd.to_numeric(nbuf_df[param], errors="coerce").dropna()
            if len(vals) < 2:
                continue
            peer_roc = float(vals.iloc[-1]) - float(vals.iloc[-2])
            if abs(peer_roc) < min_roc:
                continue
            n_eligible += 1
            if (1 if peer_roc > 0 else -1) == target_direction:
                n_agreeing += 1

        if n_eligible < SPIKE_DIURNAL_MIN_PEERS:
            continue

        consensus_frac = n_agreeing / n_eligible
        suppression_map[param] = {
            "n_eligible": n_eligible,
            "n_agreeing": n_agreeing,
            "consensus_fraction": round(consensus_frac, 2),
            "suppressed": consensus_frac >= SPIKE_DIURNAL_CONSENSUS_FRACTION
        }

    if not suppression_map:
        return fired, {}

    result = []
    for rule in fired:
        if rule.get("type") == "spike":
            param = rule.get("parameter")
            info = suppression_map.get(param, {})
            if info.get("suppressed"):
                dampened = dict(rule)
                dampened["confidence"] = round(rule.get("confidence", 85.0) * SPIKE_DIURNAL_SUPPRESSION_FACTOR, 1)
                dampened["diurnal_consensus"] = True
                result.append(dampened)
            else:
                result.append(rule)
        else:
            result.append(rule)

    return result, suppression_map


def _corroborate_network(*args, **kwargs) -> dict:
    """
    Flexible wrapper for network spatial corroboration supporting diverse test signatures.
    """
    raw_reading = args[0] if len(args) > 0 else kwargs.get("raw_reading", {})
    history_df = args[1] if len(args) > 1 else kwargs.get("history_df", pd.DataFrame())
    neighbor_buffers = args[2] if len(args) > 2 else kwargs.get("neighbor_buffers", {})

    fault_type = kwargs.get("fault_type")
    implicated_params = kwargs.get("implicated_params", ["temperature_c"])

    if len(args) >= 6:
        if isinstance(args[3], dict) and isinstance(args[4], (pd.Series, dict)):
            fault_type = args[5]
            if len(args) >= 7:
                implicated_params = args[6]
        else:
            fault_type = args[3]
            implicated_params = args[4]
    elif len(args) >= 4 and fault_type is None:
        fault_type = args[3]
        if len(args) >= 5:
            implicated_params = args[4]

    if not neighbor_buffers:
        return {
            "state": "INSUFFICIENT_CORROBORATION",
            "eligible_peer_count": 0,
            "corroborating_peer_count": 0,
            "diverged_peer_count": 0,
            "network_interpretation": "No peer stations available for comparison.",
            "confidence_bonus": 0.0,
            "relabel_fault_type": None,
            "veto": False,
        }

    target_time = pd.to_datetime(
        raw_reading.get("timestamp") or (history_df["timestamp"].iloc[-1] if not history_df.empty else pd.Timestamp.now(tz="UTC")),
        utc=True,
    )

    eligible_peers = 0
    corroborating_peers = 0
    diverged_peers = 0

    for nid, n_df in neighbor_buffers.items():
        if n_df is None or n_df.empty or "timestamp" not in n_df.columns:
            continue
        n_times = pd.to_datetime(n_df["timestamp"], utc=True)
        time_diffs = (target_time - n_times).abs()
        min_diff = time_diffs.min()
        if min_diff > pd.Timedelta(hours=1):
            continue

        eligible_peers += 1
        for p in (implicated_params or ["temperature_c"]):
            if p in n_df.columns:
                vals = pd.to_numeric(n_df[p], errors="coerce").dropna()
                if len(vals) >= 2:
                    p_roc = abs(float(vals.iloc[-1]) - float(vals.iloc[-2]))
                    if p_roc > 0.4:
                        diverged_peers += 1
                    else:
                        corroborating_peers += 1

    veto = eligible_peers >= 2 and corroborating_peers >= eligible_peers * 0.6 and (fault_type == "frozen_value")
    bonus = 10.0 if (eligible_peers >= 2 and diverged_peers >= eligible_peers * 0.5) else 0.0

    return {
        "state": "CORROBORATED" if bonus > 0 else ("VETOED" if veto else "INSUFFICIENT_CORROBORATION"),
        "eligible_peer_count": eligible_peers,
        "corroborating_peer_count": corroborating_peers,
        "diverged_peer_count": diverged_peers,
        "network_interpretation": "Peer network corroboration evaluated.",
        "confidence_bonus": bonus,
        "relabel_fault_type": None,
        "veto": veto,
    }


def _fuse_and_score(model_pct: float, rule_evidence: list):
    max_rule_conf = 0.0
    primary_fault = None
    for r in (rule_evidence or []):
        if isinstance(r, dict):
            c = float(r.get("confidence", 0.0))
            if c > max_rule_conf:
                max_rule_conf = c
                primary_fault = r.get("type")
        elif isinstance(r, (list, tuple)) and len(r) >= 3:
            c = float(r[2])
            if c > max_rule_conf:
                max_rule_conf = c
                primary_fault = r[0]

    from config import MODEL_WEIGHT, RULE_WEIGHT, FUSION_ANOMALY_THRESHOLD, RULE_CONFIDENCE_BYPASS

    fused = MODEL_WEIGHT * float(model_pct) + RULE_WEIGHT * max_rule_conf
    is_anomaly = max_rule_conf >= RULE_CONFIDENCE_BYPASS or fused >= FUSION_ANOMALY_THRESHOLD

    return round(fused, 1), is_anomaly, primary_fault, rule_evidence
