"""
model/cross_channel_covariance.py

Path 2 — Cross-Channel Thermodynamic Consistency & 3D Covariance Engine.
Handles:
1. Invariant thermodynamic physical envelope checks
2. Magnus-Tetens dewpoint & vapor pressure calculation
3. Robust 3D atmospheric covariance matrix \mathbf{\Sigma} & Mahalanobis distance D_\Sigma^2
4. Model-dominant multivariate outlierness scoring
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional

# Empirical atmospheric covariance for Indian meteorological network (clean baseline)
# Standardized scale: [Temp_z, Pressure_z, Humidity_z]
DEFAULT_CORRELATION_MATRIX = np.array([
    [ 1.00, -0.25, -0.65],  # Temp negatively correlated with RH (-0.65), weakly with Pressure (-0.25)
    [-0.25,  1.00,  0.15],  # Pressure weakly correlated with Humidity (+0.15)
    [-0.65,  0.15,  1.00]   # Humidity negatively correlated with Temp
], dtype=float)


def compute_dewpoint_c(temp_c: float, humidity_pct: float) -> float:
    """Computes Magnus-Tetens dewpoint temperature in deg C."""
    if pd.isna(temp_c) or pd.isna(humidity_pct):
        return float("nan")
    h_clamped = max(0.01, min(100.0, float(humidity_pct)))
    t = float(temp_c)
    gamma = (17.67 * t) / (243.5 + t) + math.log(h_clamped / 100.0)
    dewpoint = (243.5 * gamma) / (17.67 - gamma)
    return float(dewpoint)


def saturation_vapor_pressure_kpa(temp_c: float) -> float:
    """Computes Tetens saturation vapor pressure in kPa."""
    t = float(temp_c)
    exponent = (17.67 * t) / (t + 243.5)
    return float(0.6112 * math.exp(np.clip(exponent, -50.0, 50.0)))


class CrossChannelEngine:
    """
    Evaluates physical thermodynamic invariants and joint 3D Mahalanobis innovation distances.
    """

    @staticmethod
    def check_physical_invariants(
        temp_c: Optional[float],
        pressure_hpa: Optional[float],
        humidity_pct: Optional[float]
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks hard physical thermodynamic boundaries.
        Returns: (is_impossible, reason)
        """
        if humidity_pct is not None and not pd.isna(humidity_pct):
            if humidity_pct < 0.0 or humidity_pct > 100.01:
                return True, f"Physically impossible humidity ({humidity_pct:.1f}% outside [0, 100]%)"
        
        if temp_c is not None and not pd.isna(temp_c):
            if temp_c < -60.0 or temp_c > 65.0:
                return True, f"Physically impossible temperature ({temp_c:.1f}C outside terrestrial bounds)"
        
        if pressure_hpa is not None and not pd.isna(pressure_hpa):
            if pressure_hpa < 750.0 or pressure_hpa > 1100.0:
                return True, f"Physically impossible pressure ({pressure_hpa:.1f} hPa outside terrestrial bounds)"
        
        # Dewpoint envelope check: Dewpoint cannot exceed dry-bulb temperature
        if temp_c is not None and humidity_pct is not None and not pd.isna(temp_c) and not pd.isna(humidity_pct):
            dew_c = compute_dewpoint_c(temp_c, humidity_pct)
            if not pd.isna(dew_c) and dew_c > (temp_c + 1.5):  # 1.5C tolerance for sensor calibration
                return True, f"Thermodynamic violation: Dewpoint ({dew_c:.1f}C) exceeds Dry-Bulb ({temp_c:.1f}C)"
        
        return False, None

    @classmethod
    def compute_mahalanobis_distance(
        cls,
        temp_z: float,
        pressure_z: float,
        humidity_z: float,
        cov_matrix: Optional[np.ndarray] = None
    ) -> Tuple[float, float, Dict[str, any]]:
        """
        Computes 3D Mahalanobis distance D_\Sigma^2 = z^T \Sigma^{-1} z.
        D_\Sigma^2 follows \chi_3^2 distribution under H_0 (clean atmospheric coupling).
        Returns: (d_squared, p_value, diagnostics)
        """
        z_vec = np.array([
            float(temp_z) if not pd.isna(temp_z) else 0.0,
            float(pressure_z) if not pd.isna(pressure_z) else 0.0,
            float(humidity_z) if not pd.isna(humidity_z) else 0.0
        ], dtype=float)
        
        cov = cov_matrix if cov_matrix is not None else DEFAULT_CORRELATION_MATRIX
        
        try:
            # Regularized precision matrix
            inv_cov = np.linalg.pinv(cov + 1e-4 * np.eye(3))
            d_squared = float(z_vec.T @ inv_cov @ z_vec)
        except Exception:
            d_squared = float(np.sum(z_vec ** 2))
        
        # Approximate tail probability under \chi_3^2 (critical value for 99.9% is ~16.27)
        # Using Wilson-Hilferty transformation for Chi-Square(3) CDF approximation
        k = 3.0
        s = math.sqrt(2.0 / (9.0 * k))
        mu = 1.0 - 2.0 / (9.0 * k)
        val = (d_squared / k) ** (1.0 / 3.0)
        z_approx = (val - mu) / s
        
        # p-value approximation via standard normal survival function
        tail_prob = 0.5 * math.erfc(z_approx / math.sqrt(2.0))
        tail_prob = max(1e-12, min(1.0, tail_prob))
        
        cross_channel_llr = float(max(0.0, 0.5 * (d_squared - 3.0)))
        
        diagnostics = {
            "d_squared": d_squared,
            "tail_prob": tail_prob,
            "cross_channel_llr": cross_channel_llr,
            "is_multivariate_outlier": d_squared > 16.27
        }
        return d_squared, tail_prob, diagnostics
