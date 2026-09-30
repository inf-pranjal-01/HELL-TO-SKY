r
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, Tuple
SENSOR_QUANTIZATION_FLOORS = {
    "temperature_c": 0.10,
    "pressure_hpa": 0.50,
    "humidity_pct": 1.00,
}
DEFAULT_DIURNAL_SPREAD = {
    "temperature_c": 1.20,
    "pressure_hpa": 0.80,
    "humidity_pct": 3.50,
}
GAP_GROWTH_RATES = {
    "temperature_c": 0.25,
    "pressure_hpa": 0.10,
    "humidity_pct": 1.50,
}
class UncertaintyBudget:
    @staticmethod
    def get_sensor_noise_floor(param: str) -> float:
        return SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    @staticmethod
    def compute_diurnal_uncertainty(
        param: str,
        solar_hour: float,
        history_df: pd.DataFrame
    ) -> float:
        if history_df.empty or param not in history_df.columns or len(history_df) < 24:
            return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
        try:
            vals = history_df[param].values
            if len(vals) < 24:
                return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
            valid_vals = vals[pd.notna(vals)].astype(float)
            if len(valid_vals) < 24:
                return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
            med = np.median(valid_vals)
            mad = np.median(np.abs(valid_vals - med))
            robust_sigma = float(1.4826 * mad) if mad > 1e-6 else float(np.std(valid_vals))
            floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
            return max(floor, robust_sigma)
        except Exception:
            return DEFAULT_DIURNAL_SPREAD.get(param, 1.0)
    @staticmethod
    def compute_gap_uncertainty(param: str, dt_hours: float) -> float:
        r
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
        r
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
        r
        inflation = math.sqrt(1.0 + 0.5 * max(0, gap_step_count))
        return float(base_sigma * inflation)
