
from __future__ import annotations
import math
import numpy as np
from typing import Dict, Tuple, Optional
DECORRELATION_HOURS = {
    "temperature_c": 4.0,
    "pressure_hpa": 8.0,
    "humidity_pct": 3.0,
}
DEFAULT_ALPHA = 0.002
DEFAULT_BETA = 0.05
class SequentialSPRT:
    @staticmethod
    def compute_autocorrelation(param: str, dt_hours: float) -> float:
        tau = DECORRELATION_HOURS.get(param, 4.0)
        return float(math.exp(-max(0.0, dt_hours) / tau))
    @classmethod
    def pre_whiten_residual(
        cls,
        param: str,
        current_residual: float,
        prior_residual: Optional[float],
        dt_hours: float,
        current_sigma: float
    ) -> float:
        if prior_residual is None or dt_hours > 12.0 or current_sigma < 1e-6:
            return float(np.clip(current_residual / max(1e-4, current_sigma), -5.0, 5.0))
        rho = cls.compute_autocorrelation(param, dt_hours)
        rho_clamped = min(0.95, max(0.0, rho))
        whitened_num = current_residual - rho_clamped * prior_residual
        whitened_den = current_sigma * math.sqrt(max(0.05, 1.0 - (rho_clamped ** 2)))
        epsilon = whitened_num / max(1e-4, whitened_den)
        return float(np.clip(epsilon, -5.0, 5.0))
    @staticmethod
    def compute_drift_allowance(param: str, current_sigma: float) -> float:
        from model.uncertainty_budget import SENSOR_QUANTIZATION_FLOORS
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
        ratio = sensor_floor / max(1e-4, current_sigma)
        return float(max(0.05, min(0.35, ratio)))
    @classmethod
    def update_cusum(
        cls,
        param: str,
        s_pos_prev: float,
        s_neg_prev: float,
        whitened_epsilon: float,
        dt_hours: float,
        current_sigma: float
    ) -> Tuple[float, float, float]:
        gap_decay = math.exp(-max(0.0, dt_hours - 1.0) / 24.0)
        s_pos_in = max(0.0, s_pos_prev * gap_decay)
        s_neg_in = max(0.0, s_neg_prev * gap_decay)
        allowance = cls.compute_drift_allowance(param, current_sigma)
        half_allowance = allowance / 2.0
        s_pos = max(0.0, s_pos_in + whitened_epsilon - half_allowance)
        s_neg = max(0.0, s_neg_in - whitened_epsilon - half_allowance)
        max_accum = max(s_pos, s_neg)
        drift_llr = float(max_accum)
        return float(s_pos), float(s_neg), drift_llr
    @staticmethod
    def get_wald_boundaries(
        alpha: float = DEFAULT_ALPHA,
        beta: float = DEFAULT_BETA
    ) -> Tuple[float, float]:
        upper = math.log((1.0 - beta) / max(1e-9, alpha))
        lower = math.log(beta / max(1e-9, 1.0 - alpha))
        return float(upper), float(lower)
