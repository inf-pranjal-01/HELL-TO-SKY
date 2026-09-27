r"""
model/dynamic_expectation.py

Path 2 — Dynamic Multi-Scale Causal Expectation Engine.
Combines:
1. Astronomical solar-hour diurnal baseline \mu(h_solar, doy)
2. Continuous-time local trend s(t) with adaptive bandwidth
3. Regional peer innovation delta \delta_peer(t)

Strict continuous-time physical scaling: zero positional row indexing.
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple

# Station coordinates lookup for solar-time calculation
STATION_COORDS = {
    # Delhi
    "AWS-DEL-011": (28.6139, 77.2090), "AWS-DEL-101": (28.5355, 77.3910),
    "AWS-DEL-102": (28.4595, 77.0266), "AWS-DEL-103": (28.6692, 77.4538),
    # Mumbai
    "AWS-MUM-007": (19.0760, 72.8777), "AWS-MUM-101": (19.2183, 72.9781),
    "AWS-MUM-102": (19.0330, 73.0297), "AWS-MUM-103": (19.2403, 73.1305),
    # Chennai
    "AWS-CHN-024": (13.0827, 80.2707), "AWS-CHN-101": (12.9249, 80.1000),
    "AWS-CHN-102": (13.1143, 80.1548), "AWS-CHN-103": (12.9675, 79.9430),
    # Kolkata
    "AWS-KOL-015": (22.5726, 88.3639), "AWS-KOL-101": (22.5958, 88.2636),
    "AWS-KOL-102": (22.5697, 88.4171), "AWS-KOL-103": (22.7645, 88.3792),
    # Bhopal
    "AWS-BHO-030": (23.2599, 77.4126), "AWS-BHO-101": (23.2032, 77.0844),
    "AWS-BHO-102": (23.5251, 77.8081), "AWS-BHO-103": (23.3315, 77.7899),
    # Varanasi
    "AWS-VAR-052": (25.3176, 82.9739), "AWS-VAR-101": (25.2708, 83.0281),
    "AWS-VAR-102": (25.2585, 83.2648), "AWS-VAR-103": (25.3919, 82.5686),
    # Ranchi
    "AWS-RAN-067": (23.3441, 85.3096), "AWS-RAN-101": (23.0725, 85.2789),
    "AWS-RAN-102": (23.6307, 85.5121), "AWS-RAN-103": (23.1667, 85.5833),
}

DEFAULT_LON = 77.0  # Central India approximate longitude


def calculate_solar_hour(timestamp: pd.Timestamp, station_id: str) -> float:
    """
    Computes true astronomical solar hour in [0, 24) using station longitude
    and the Equation of Time (EoT) approximation.
    """
    utc_hour = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
    doy = timestamp.dayofyear
    
    lat, lon = STATION_COORDS.get(station_id, (20.0, DEFAULT_LON))
    
    # Equation of time (in minutes)
    b = 2.0 * math.pi * (doy - 81) / 365.0
    eot = 9.87 * math.sin(2.0 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    
    # Solar time = UTC + (lon / 15) hours + (eot / 60) hours
    solar_time = (utc_hour + lon / 15.0 + eot / 60.0) % 24.0
    return solar_time


def compute_physical_solar_roc(param: str, solar_hour: float, lat: float = 20.0) -> float:
    """
    Computes analytical physics-based diurnal rate of change (ROC per hour)
    from astronomical solar radiation flux derivative:
    - Temperature: morning heating +1.8 to +2.5 C/h, afternoon cooling -1.5 C/h, night -0.3 C/h
    - Barometric Pressure: 12-hour atmospheric solar tide harmonic (-0.45 * sin(4*pi*(h-3.5)/24))
    - Humidity: psychrometric inverse of temperature (-2.8 * temp_roc)
    Zero external files, zero CSV dependencies.
    """
    h = solar_hour % 24.0
    
    if param in ("temperature_c", "temp"):
        if 6.0 <= h < 14.0:
            # Morning insolation heating phase (peaks around 09:00 - 10:00 solar hour)
            angle = math.pi * (h - 6.0) / 8.0
            return float(2.4 * math.sin(angle))
        elif 14.0 <= h < 20.0:
            # Afternoon and evening cooling phase (peaks around 17:00 solar hour)
            angle = math.pi * (h - 14.0) / 6.0
            return float(-1.8 * math.sin(angle))
        else:
            # Nighttime radiative cooling (~ -0.3 C/h)
            return -0.3
            
    elif param in ("pressure_hpa", "pressure"):
        # Semi-diurnal atmospheric thermal tide (12-hour period)
        return float(-0.45 * math.sin(4.0 * math.pi * (h - 3.5) / 24.0))
        
    elif param in ("humidity_pct", "humidity"):
        # Psychrometric inverse of temperature curve
        temp_roc = compute_physical_solar_roc("temperature_c", solar_hour, lat)
        return float(np.clip(-2.8 * temp_roc, -8.0, 8.0))
        
    return 0.0


def compute_continuous_trend_state(
    current_time: pd.Timestamp,
    prior_time: Optional[pd.Timestamp],
    prior_trend: float,
    prior_residual: float,
    tau_hours: float = 6.0,
    peer_correlation: float = 0.0
) -> float:
    """
    Updates continuous-time exponential trend:
    s(t) = s(t - dt) * exp(-dt / tau_eff) + (1 - exp(-dt / tau_eff)) * residual(t - dt)
    tau_eff scales dynamically with peer consensus.
    """
    if prior_time is None or pd.isna(prior_time):
        return 0.0
    
    dt_hours = max(0.0, (current_time - prior_time).total_seconds() / 3600.0)
    if dt_hours > 24.0:
        return 0.0
    
    # Adaptive bandwidth scaling: tau contracts when peers agree
    tau_eff = max(1.0, tau_hours * (1.0 - 0.5 * max(0.0, min(1.0, peer_correlation))))
    alpha = 1.0 - math.exp(-dt_hours / tau_eff)
    new_trend = (1.0 - alpha) * prior_trend + alpha * prior_residual
    return float(new_trend)


def compute_dynamic_expectation(
    station_id: str,
    param: str,
    current_time: pd.Timestamp,
    history_df: pd.DataFrame,
    trend_state: float = 0.0,
    peer_innovation_delta: float = 0.0,
    neighbor_median: Optional[float] = None,
) -> Tuple[float, float]:
    r"""
    Pure online causal 1-step dynamic expectation without any offline CSV files:
    1. If prior clean reading exists in history_df (within 6h):
       extrapolate momentum: \hat{x}_{t|t-1} = x_{t-dt} + (ROC_solar * dt) + peer_delta
    2. If history is cold-starting:
       - If peer median is available: \hat{x}_0 = neighbor_median
       - If isolated: initialize from history mean or physical default midpoint
    3. Diurnal ROC is derived directly from solar insolation physics.
    Returns: (\hat{x}_{t|t-1}, expected_derivative_per_hour)
    """
    lat, lon = STATION_COORDS.get(station_id, (20.0, DEFAULT_LON))
    solar_h = calculate_solar_hour(current_time, station_id)
    expected_roc = compute_physical_solar_roc(param, solar_h, lat)
    
    # 1-Step causal extrapolation from trusted runtime history buffer
    prior_val = None
    dt_hours = 1.0
    p_bounds = {
        "temperature_c": (-50.0, 60.0),
        "pressure_hpa": (850.0, 1085.0),
        "humidity_pct": (0.0, 100.0),
    }
    b_min, b_max = p_bounds.get(param, (-100.0, 200.0))

    if not history_df.empty and param in history_df.columns:
        valid_rows = history_df[history_df[param].notna()]
        if not valid_rows.empty:
            # Filter strictly for uncorrupted physical readings to prevent anomaly feedback loops
            clean_rows = valid_rows[(valid_rows[param] >= b_min) & (valid_rows[param] <= b_max)]
            if not clean_rows.empty:
                prior_val = float(clean_rows[param].iloc[-1])
                if "timestamp" in clean_rows.columns:
                    p_ts = pd.to_datetime(clean_rows["timestamp"].iloc[-1], utc=True)
                    dt_hours = max(0.1, min(24.0, (current_time - p_ts).total_seconds() / 3600.0))

    if prior_val is not None and dt_hours <= 6.0:
        expected_val = prior_val + (expected_roc * dt_hours) + peer_innovation_delta
    elif neighbor_median is not None and not pd.isna(neighbor_median):
        expected_val = float(neighbor_median) + (expected_roc * dt_hours)
    elif not history_df.empty and param in history_df.columns and len(history_df[param].dropna()) > 0:
        clean_vals = history_df[param].dropna()
        clean_in_bounds = clean_vals[(clean_vals >= b_min) & (clean_vals <= b_max)]
        if not clean_in_bounds.empty:
            expected_val = float(clean_in_bounds.mean()) + (expected_roc * dt_hours)
        else:
            defaults = {"temperature_c": 25.0, "pressure_hpa": 1000.0, "humidity_pct": 50.0}
            expected_val = defaults.get(param, 25.0)
    else:
        # Cold start physical default midpoint
        defaults = {"temperature_c": 25.0, "pressure_hpa": 1000.0, "humidity_pct": 50.0}
        expected_val = defaults.get(param, 25.0)
    
    # Enforce strict thermodynamic boundary constraints
    if param == "humidity_pct":
        expected_val = max(0.0, min(100.0, expected_val))
    elif param == "pressure_hpa":
        expected_val = max(850.0, min(1085.0, expected_val))
    elif param == "temperature_c":
        expected_val = max(-50.0, min(60.0, expected_val))

    return float(expected_val), float(expected_roc)
