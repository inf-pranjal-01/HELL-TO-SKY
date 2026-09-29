r"""
model/uncertainty_budget.py

Path 2 — Heteroskedastic Dynamic Uncertainty Budget.
Maintains and computes explicit decomposition of:
1. Instrument quantization & calibration noise (\sigma_sensor)
2. Diurnal environmental variance (\sigma_diurnal)
3. Physical time-gap uncertainty growth (\sigma_gap(\Delta t))
4. Peer spatial dispersion (\sigma_peer)
5. Counterfactual reconstruction uncertainty (\sigma_reconstruct)

Strict separation between observation uncertainty and environmental/model uncertainty.
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, Tuple

# Physical / Transducer Quantization Noise Floors (Physical Invariants)
SENSOR_QUANTIZATION_FLOORS = {
    "temperature_c": 0.10,  # 0.1 deg C ADC / resolution floor
    "pressure_hpa": 0.50,   # 0.5 hPa barometer precision floor
    "humidity_pct": 1.00,   # 1.0 % RH sensor hygrometer resolution
}

# Empirical Diurnal Base Uncertainty (Default when history is short)
DEFAULT_DIURNAL_SPREAD = {
    "temperature_c": 1.20,
    "pressure_hpa": 0.80,
    "humidity_pct": 3.50,
}

# Time-gap uncertainty growth rates (\kappa_c in (unit)^2 / hour)
GAP_GROWTH_RATES = {
    "temperature_c": 0.25,  # Variance grows by ~0.25 (C)^2 per hour of missing data
    "pressure_hpa": 0.10,   # Barometric pressure changes smoothly
    "humidity_pct": 1.50,   # Humidity variance expands faster across gaps
}


class UncertaintyBudget:
    """
    Manages and estimates causal multi-component predictive uncertainty.
    """

    @staticmethod
    def get_sensor_noise_floor(param: str) -> float:
        """Returns the physical hardware resolution / quantization noise floor."""
        return SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)

    @staticmethod
    def compute_diurnal_uncertainty(
        param: str,
        solar_hour: float,
        history_df: pd.DataFrame
    ) -> float:
        """
        Computes the empirical standard deviation of clean historical observations at solar_hour.
        """
        if history_df.empty or param not in history_df.columns or len(history_df) < 24:
            return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
        
        try:
            vals = history_df[param].values
            if len(vals) < 24:
                return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
            valid_vals = vals[pd.notna(vals)].astype(float)
            if len(valid_vals) < 24:
                return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
            
            # Use robust MAD over clean trusted history
            med = np.median(valid_vals)
            mad = np.median(np.abs(valid_vals - med))
            robust_sigma = float(1.4826 * mad) if mad > 1e-6 else float(np.std(valid_vals))
            
            floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
            return max(floor, robust_sigma)
        except Exception:
            return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)

    @staticmethod
    def compute_gap_uncertainty(param: str, dt_hours: float) -> float:
        r"""
        Computes predictive variance growth due to physical elapsed time \Delta t.
        \sigma_gap = sqrt(\kappa_c * dt_hours)
        """
        kappa = GAP_GROWTH_RATES.get(param, 0.20)
        return math.sqrt(kappa * max(0.0, dt_hours))

    @classmethod
    def compute_composite_predictive_uncertainty(
        cls,
        param: str,
        solar_hour: float,
        dt_hours: float,
        history_df: pd.DataFrame,
        peer_dispersion: float = 0.0
    ) -> Tuple[float, Dict[str, float]]:
        r"""
        Computes total 1-step-ahead predictive scale \sigma_{t|t-1}:
        \sigma_{t|t-1}^2 = \sigma_sensor^2 + \sigma_diurnal^2 + \sigma_gap^2 + \sigma_peer^2
        """
        sigma_sensor = cls.get_sensor_noise_floor(param)
        sigma_diurnal = cls.compute_diurnal_uncertainty(param, solar_hour, history_df)
        sigma_gap = cls.compute_gap_uncertainty(param, dt_hours)
        sigma_peer = max(0.0, peer_dispersion)
        
        var_total = (sigma_sensor ** 2) + (sigma_diurnal ** 2) + (sigma_gap ** 2) + (sigma_peer ** 2)
        sigma_total = math.sqrt(var_total)
        
        breakdown = {
            "sigma_sensor": sigma_sensor,
            "sigma_diurnal": sigma_diurnal,
            "sigma_gap": sigma_gap,
            "sigma_peer": sigma_peer,
            "sigma_total": sigma_total
        }
        return sigma_total, breakdown

    @classmethod
    def compute_reconstruction_uncertainty(
        cls,
        param: str,
        base_sigma: float,
        gap_step_count: int
    ) -> float:
        r"""
        Computes uncertainty of a counterfactual reconstructed value.
        Inflates with repeated consecutive imputation steps:
        \sigma_reconstruct = base_sigma * sqrt(1 + 0.5 * gap_step_count)
        """
        inflation = math.sqrt(1.0 + 0.5 * max(0, gap_step_count))
        return float(base_sigma * inflation)
