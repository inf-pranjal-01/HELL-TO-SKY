r"""
model/peer_spatial_engine.py

Path 2 — Robust Peer / Spatial Context Engine.
Handles:
1. Spatial cluster topology and distance computation
2. Elevation-adjusted, correlation-weighted peer weighting
3. Robust weighted median aggregation (50% breakdown point against bad peers)
4. Kriging distance-based variance inflation for cluster-edge stations
5. Regional consensus weather corroboration vs. isolated fault contrast
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

from model.dynamic_expectation import STATION_COORDS

# Approximate station elevations (meters above sea level)
STATION_ELEVATIONS = {
    # Delhi (~215m)
    "AWS-DEL-011": 215.0, "AWS-DEL-101": 200.0, "AWS-DEL-102": 220.0, "AWS-DEL-103": 210.0,
    # Mumbai (~15m)
    "AWS-MUM-007": 14.0, "AWS-MUM-101": 15.0, "AWS-MUM-102": 10.0, "AWS-MUM-103": 18.0,
    # Chennai (~10m)
    "AWS-CHN-024": 7.0, "AWS-CHN-101": 18.0, "AWS-CHN-102": 15.0, "AWS-CHN-103": 35.0,
    # Kolkata (~10m)
    "AWS-KOL-015": 9.0, "AWS-KOL-101": 12.0, "AWS-KOL-102": 10.0, "AWS-KOL-103": 15.0,
    # Bhopal (~500m)
    "AWS-BHO-030": 527.0, "AWS-BHO-101": 500.0, "AWS-BHO-102": 430.0, "AWS-BHO-103": 450.0,
    # Varanasi (~80m)
    "AWS-VAR-052": 80.0, "AWS-VAR-101": 85.0, "AWS-VAR-102": 78.0, "AWS-VAR-103": 82.0,
    # Ranchi (~650m)
    "AWS-RAN-067": 651.0, "AWS-RAN-101": 660.0, "AWS-RAN-102": 330.0, "AWS-RAN-103": 600.0,
}


# 7 Regional Clusters of 4 Stations Each (28 stations total)
STATION_CLUSTERS: Dict[str, List[str]] = {
    "BHO": ["AWS-BHO-030", "AWS-BHO-101", "AWS-BHO-102", "AWS-BHO-103"],
    "CHN": ["AWS-CHN-024", "AWS-CHN-101", "AWS-CHN-102", "AWS-CHN-103"],
    "DEL": ["AWS-DEL-011", "AWS-DEL-101", "AWS-DEL-102", "AWS-DEL-103"],
    "KOL": ["AWS-KOL-015", "AWS-KOL-101", "AWS-KOL-102", "AWS-KOL-103"],
    "MUM": ["AWS-MUM-007", "AWS-MUM-101", "AWS-MUM-102", "AWS-MUM-103"],
    "RAN": ["AWS-RAN-067", "AWS-RAN-101", "AWS-RAN-102", "AWS-RAN-103"],
    "VAR": ["AWS-VAR-052", "AWS-VAR-101", "AWS-VAR-102", "AWS-VAR-103"],
}

STATION_TO_CLUSTER: Dict[str, str] = {
    station_id: cluster_id
    for cluster_id, stations in STATION_CLUSTERS.items()
    for station_id in stations
}

STATION_SIBLING_PEERS: Dict[str, List[str]] = {
    station_id: [s for s in STATION_CLUSTERS[cluster_id] if s != station_id]
    for station_id, cluster_id in STATION_TO_CLUSTER.items()
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class PeerSpatialEngine:
    """
    Robust Spatial Aggregation and Regional Anomaly Contrast Engine.
    Strictly isolated per 4-station cluster (target + exactly 3 valid sibling peers).
    """

    @classmethod
    def get_sibling_peers(cls, target_station_id: str) -> List[str]:
        """Returns the exact 3 valid sibling peers belonging to the target's cluster."""
        return STATION_SIBLING_PEERS.get(target_station_id, [])

    @classmethod
    def compute_peer_weights(
        cls,
        target_station_id: str,
        peer_station_ids: List[str]
    ) -> Dict[str, float]:
        r"""
        Computes distance & elevation-adjusted spatial weights:
        w_ij \propto exp(-dist / d_scale) * exp(-|delta_alt| / h_scale)
        """
        if not peer_station_ids:
            return {}
        
        target_lat, target_lon = STATION_COORDS.get(target_station_id, (20.0, 77.0))
        target_alt = STATION_ELEVATIONS.get(target_station_id, 100.0)
        
        raw_weights = {}
        for pid in peer_station_ids:
            plat, plon = STATION_COORDS.get(pid, (20.0, 77.0))
            palt = STATION_ELEVATIONS.get(pid, 100.0)
            
            dist_km = haversine_distance_km(target_lat, target_lon, plat, plon)
            alt_diff = abs(target_alt - palt)
            
            # Spatial decay (30km scale) and lapse-rate elevation decay (500m scale)
            w = math.exp(-dist_km / 30.0) * math.exp(-alt_diff / 500.0)
            raw_weights[pid] = max(1e-4, w)
        
        total_w = sum(raw_weights.values())
        return {pid: w / total_w for pid, w in raw_weights.items()}

    @classmethod
    def compute_robust_peer_consensus(
        cls,
        target_station_id: str,
        param: str,
        current_time: pd.Timestamp,
        neighbor_buffers: Dict[str, pd.DataFrame]
    ) -> Tuple[Optional[float], Optional[float], int]:
        """
        Computes robust weighted median of peer derivatives/innovations.
        Strictly restricted to the target's 3 sibling cluster peers.
        Returns: (peer_median_innovation, peer_dispersion, eligible_peer_count)
        """
        if not neighbor_buffers:
            return None, None, 0
        
        # Enforce exact cluster topology: only 3 sibling peers
        allowed_siblings = cls.get_sibling_peers(target_station_id)
        if not allowed_siblings:
            return None, None, 0
            
        valid_peer_vals = []
        valid_peer_weights = []
        
        weights = cls.compute_peer_weights(target_station_id, allowed_siblings)
        
        for pid in allowed_siblings:
            if pid not in neighbor_buffers:
                continue
            buf_obj = neighbor_buffers[pid]
            
            # Fast path for StationBuffer
            if hasattr(buf_obj, "_raw_rows"):
                raw_rows = buf_obj._raw_rows
                if not raw_rows:
                    continue
                last_row = raw_rows[-1]
                ts_val = last_row.get("timestamp")
                if ts_val is None:
                    continue
                latest_time = ts_val if isinstance(ts_val, pd.Timestamp) else pd.to_datetime(ts_val, utc=True)
                if abs((current_time - latest_time).total_seconds()) > 5400:
                    continue
                val = last_row.get(param)
                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                    try:
                        valid_peer_vals.append(float(val))
                        valid_peer_weights.append(weights.get(pid, 1.0))
                    except (ValueError, TypeError):
                        pass
                continue
                
            ndf = buf_obj.raw_history_df() if hasattr(buf_obj, "raw_history_df") else buf_obj
            if ndf is None or not isinstance(ndf, pd.DataFrame) or ndf.empty or param not in ndf.columns:
                continue
            
            # Check freshness: latest reading within 1.5h
            pts = pd.to_datetime(ndf["timestamp"], utc=True, errors="coerce")
            pvals = pd.to_numeric(ndf[param], errors="coerce")
            valid_mask = pts.notna() & pvals.notna()
            if not valid_mask.any():
                continue
            
            latest_time = pts[valid_mask].iloc[-1]
            if abs((current_time - latest_time).total_seconds()) > 5400:
                continue  # Stale peer reading
            
            val = float(pvals[valid_mask].iloc[-1])
            valid_peer_vals.append(val)
            valid_peer_weights.append(weights.get(pid, 1.0))
        
        n_eligible = len(valid_peer_vals)
        if n_eligible == 0:
            return None, None, 0
        
        # Robust weighted median
        vals_arr = np.array(valid_peer_vals)
        weights_arr = np.array(valid_peer_weights) / sum(valid_peer_weights)
        
        sort_idx = np.argsort(vals_arr)
        sorted_vals = vals_arr[sort_idx]
        sorted_weights = weights_arr[sort_idx]
        cum_weights = np.cumsum(sorted_weights)
        
        med_idx = np.searchsorted(cum_weights, 0.5)
        med_idx = min(len(sorted_vals) - 1, med_idx)
        peer_median = float(sorted_vals[med_idx])
        
        # Peer dispersion (Weighted MAD)
        mad = float(np.median(np.abs(sorted_vals - peer_median)))
        peer_dispersion = max(0.10, 1.4826 * mad)
        
        return peer_median, peer_dispersion, n_eligible

    @classmethod
    def evaluate_spatial_contrast_llr(
        cls,
        target_residual: float,
        target_sigma: float,
        peer_median_residual: Optional[float],
        peer_dispersion: Optional[float],
        n_eligible: int
    ) -> Tuple[float, Dict[str, any]]:
        r"""
        Evaluates log-likelihood of isolated divergence vs. regional consensus.
        \Lambda_spatial = (e_target - e_peer)^2 / (2 * \sigma_diff^2)
        """
        if peer_median_residual is None or n_eligible < 2:
            return 0.0, {"state": "INSUFFICIENT_PEERS", "veto": False, "eligible_peers": n_eligible}
        
        diff = target_residual - peer_median_residual
        sigma_diff = math.sqrt((target_sigma ** 2) + ((peer_dispersion or 0.5) ** 2))
        
        z_spatial = diff / max(1e-4, sigma_diff)
        
        # Spatial contrast LLR
        spatial_llr = float(0.5 * (z_spatial ** 2))
        
        # Regional consensus check: if target agrees with peers, it's regional weather
        is_regional_weather = abs(diff) <= 1.5 * sigma_diff and abs(peer_median_residual) > 1.5 * target_sigma
        
        diagnostics = {
            "state": "REGIONAL_WEATHER" if is_regional_weather else "DIVERGENT" if abs(z_spatial) > 2.5 else "CONSISTENT",
            "z_spatial": z_spatial,
            "spatial_diff": diff,
            "eligible_peers": n_eligible,
            "veto": bool(is_regional_weather)
        }
        return spatial_llr, diagnostics
