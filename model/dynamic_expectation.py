r
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from model.seasonal_baseline import get_expected_roc, _ensure_loaded, _cache, _PARAMS
STATION_COORDS = {
    "AWS-DEL-011": (28.6139, 77.2090), "AWS-DEL-101": (28.5355, 77.3910),
    "AWS-DEL-102": (28.4595, 77.0266), "AWS-DEL-103": (28.6692, 77.4538),
    "AWS-MUM-007": (19.0760, 72.8777), "AWS-MUM-101": (19.2183, 72.9781),
    "AWS-MUM-102": (19.0330, 73.0297), "AWS-MUM-103": (19.2403, 73.1305),
    "AWS-CHN-024": (13.0827, 80.2707), "AWS-CHN-101": (12.9249, 80.1000),
    "AWS-CHN-102": (13.1143, 80.1548), "AWS-CHN-103": (12.9675, 79.9430),
    "AWS-KOL-015": (22.5726, 88.3639), "AWS-KOL-101": (22.5958, 88.2636),
    "AWS-KOL-102": (22.5697, 88.4171), "AWS-KOL-103": (22.7645, 88.3792),
    "AWS-BHO-030": (23.2599, 77.4126), "AWS-BHO-101": (23.2032, 77.0844),
    "AWS-BHO-102": (23.5251, 77.8081), "AWS-BHO-103": (23.3315, 77.7899),
    "AWS-VAR-052": (25.3176, 82.9739), "AWS-VAR-101": (25.2708, 83.0281),
    "AWS-VAR-102": (25.2585, 83.2648), "AWS-VAR-103": (25.3919, 82.5686),
    "AWS-RAN-067": (23.3441, 85.3096), "AWS-RAN-101": (23.0725, 85.2789),
    "AWS-RAN-102": (23.6307, 85.5121), "AWS-RAN-103": (23.1667, 85.5833),
}
DEFAULT_LON = 77.0
def calculate_solar_hour(timestamp: pd.Timestamp, station_id: str) -> float:
    utc_hour = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
    doy = timestamp.dayofyear
    lat, lon = STATION_COORDS.get(station_id, (20.0, DEFAULT_LON))
    b = 2.0 * math.pi * (doy - 81) / 365.0
    eot = 9.87 * math.sin(2.0 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    solar_time = (utc_hour + lon / 15.0 + eot / 60.0) % 24.0
    return solar_time
def get_diurnal_baseline_level(station_id: str, param_prefix: str, solar_hour: float, history_df: pd.DataFrame) -> float:
    h_floor = int(math.floor(solar_hour)) % 24
    h_ceil = (h_floor + 1) % 24
    weight = solar_hour - math.floor(solar_hour)
    col = {"temp": "temperature_c", "pressure": "pressure_hpa", "humidity": "humidity_pct"}.get(param_prefix, param_prefix)
    if not history_df.empty and col in history_df.columns:
        vals = history_df[col].values
        ts = history_df["timestamp"].values
        if len(vals) >= 24:
            valid_mask = pd.notna(vals) & pd.notna(ts)
            if np.count_nonzero(valid_mask) >= 24:
                valid_vals = vals[valid_mask].astype(float)
                ts_series = pd.to_datetime(ts[valid_mask], utc=True)
                hours = ts_series.hour.values if hasattr(ts_series, "hour") else ts_series.dt.hour.values
                mask_floor = (hours == h_floor)
                mask_ceil = (hours == h_ceil)
                has_floor = np.any(mask_floor)
                has_ceil = np.any(mask_ceil)
                if has_floor and has_ceil:
                    val_floor = np.mean(valid_vals[mask_floor])
                    val_ceil = np.mean(valid_vals[mask_ceil])
                    return float((1.0 - weight) * val_floor + weight * val_ceil)
                elif has_floor:
                    return float(np.mean(valid_vals[mask_floor]))
        valid_vals = vals[pd.notna(vals)]
        if len(valid_vals) > 0:
            return float(valid_vals[-1])
    _ensure_loaded(station_id)
    default_vals = {"temp": 25.0, "pressure": 1013.25, "humidity": 60.0}
    return default_vals.get(param_prefix, 0.0)
def compute_continuous_trend_state(
    current_time: pd.Timestamp,
    prior_time: Optional[pd.Timestamp],
    prior_trend: float,
    prior_residual: float,
    tau_hours: float = 6.0,
    peer_correlation: float = 0.0
) -> float:
    if prior_time is None or pd.isna(prior_time):
        return 0.0
    dt_hours = max(0.0, (current_time - prior_time).total_seconds() / 3600.0)
    if dt_hours > 24.0:
        return 0.0
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
    peer_innovation_delta: float = 0.0
) -> Tuple[float, float]:
    r
    prefix_map = {"temperature_c": "temp", "pressure_hpa": "pressure", "humidity_pct": "humidity"}
    prefix = prefix_map.get(param, param)
    solar_h = calculate_solar_hour(current_time, station_id)
    base_level = get_diurnal_baseline_level(station_id, prefix, solar_h, history_df)
    expected_roc = get_expected_roc(station_id, prefix, int(solar_h) % 24)
    expected_val = base_level + trend_state + peer_innovation_delta
    return float(expected_val), float(expected_roc)
