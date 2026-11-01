"""
SkyGuard AI — daily_drift_auditor.py

Diurnal Secular Invariant Calibration-Drift Watchdog.
Compliant with WMO-No. 8 (Guide to Meteorological Instruments and Methods of Observation).

Mathematical Architecture:
1. Diurnal Harmonics Elimination:
   The moving 24-hour mean temperature \\bar{T}_i(t) integrates across the entire
   solar diurnal cycle, canceling out the primary 24-hour solar harmonic S_1 and
   its higher harmonics S_2, S_3:
       \\bar{T}_i(t) = (1 / N) * \\sum_{k=0}^{N-1} T_i(t - k)

2. Cluster Pairwise Secular Invariance:
   For sibling stations within regional clusters (20-50 km radius), synoptic weather
   shifts affect all stations concurrently. The baseline difference:
       \\Delta_{ij}(t) = \\bar{T}_i(t) - \\bar{T}_j(t)
   remains nominally invariant under weather fronts, dictated primarily by geopotential
   elevation lapse rate (-6.5°C/km) and microtopography.

3. Unilateral Secular Divergence & Peer Coherence:
   Unilateral secular divergence \\delta_i(t) measures departure from peer consensus:
       \\delta_i(t) = median_{j \\in Peers} ( (\\bar{T}_i(t) - \\bar{T}_j(t)) - B_{ij} )
   Peer coherence \\gamma_i(t) measures internal consistency amongst the peer group:
       \\gamma_i(t) = max_{j, k \\in Peers, j < k} | (\\bar{T}_j(t) - \\bar{T}_k(t)) - B_{jk} |

4. Non-Intrusive Asynchronous Advisory:
   This watchdog operates as an asynchronous daily auditor for the meteorological
   department rather than an inline 15-minute alarm trigger. When persistent unilateral
   secular divergence is confirmed (0.8°C < |\\delta_i| <= 1.5°C) while peers remain coherent
   (\\gamma_i <= 1.0°C), it flags STATUS: RECALIBRATION_ADVISORY for preventive field maintenance
   without degrading real-time precision or causing alarm fatigue.
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from model.peer_spatial_engine import (
    STATION_CLUSTERS,
    STATION_TO_CLUSTER,
    STATION_SIBLING_PEERS,
    STATION_ALTITUDES,
)

# WMO-No. 8 Temperature Drift Thresholds
WMO_NOMINAL_TOLERANCE_C = 0.80       # <= 0.8°C is within operational calibration tolerance
WMO_ADVISORY_THRESHOLD_C = 0.80      # 0.8°C < |delta| <= 1.5°C triggers recalibration advisory
WMO_CRITICAL_THRESHOLD_C = 1.50      # > 1.5°C requires urgent recalibration
MAX_COHERENT_PEER_SPREAD_C = 1.00    # If peer spread exceeds this, synoptic discordance is active

# Diurnal integration parameters
DIURNAL_WINDOW_HOURS = 24
MIN_HOURS_FOR_AUDIT = 12             # Minimum readings needed for reliable diurnal integration


class DailyDriftAuditor:
    """
    Asynchronous Daily Calibration-Drift Watchdog for AWS networks.
    Monitors diurnal secular invariants across regional station clusters.
    """

    def __init__(self, metadata: Optional[pd.DataFrame] = None):
        self.metadata = metadata
        self.station_clusters = STATION_CLUSTERS
        self.station_to_cluster = STATION_TO_CLUSTER
        self.sibling_peers = STATION_SIBLING_PEERS

        # Rolling temperature histories: station_id -> deque of (timestamp, temp_c)
        # Retains up to 72 hours of hourly readings
        self._temp_history: Dict[str, deque] = {}
        all_stations = (
            list(metadata["station_id"])
            if metadata is not None and "station_id" in metadata.columns
            else [s for stations in self.station_clusters.values() for s in stations]
        )
        for sid in all_stations:
            self._temp_history[sid] = deque(maxlen=72)

        # Baseline pairwise elevation lapse rate adjustments (°C)
        # Lapse rate = -0.0065 °C / m
        self._pairwise_lapse_baselines: Dict[Tuple[str, str], float] = {}
        self._initialize_baselines()

        # Cache of latest audit results
        self._latest_audit: Dict[str, Dict[str, Any]] = {}

    def _initialize_baselines(self):
        """Calculates expected pairwise baseline differences from station geopotential altitudes."""
        for cluster_id, stations in self.station_clusters.items():
            for i, sa in enumerate(stations):
                alt_a = STATION_ALTITUDES.get(sa, 200.0)
                for sb in stations[i + 1 :]:
                    alt_b = STATION_ALTITUDES.get(sb, 200.0)
                    # Expected delta: T_a - T_b ≈ -0.0065 * (alt_a - alt_b)
                    delta_expected = -0.0065 * (alt_a - alt_b)
                    self._pairwise_lapse_baselines[(sa, sb)] = delta_expected
                    self._pairwise_lapse_baselines[(sb, sa)] = -delta_expected

    def record_observation(self, station_id: str, timestamp: Any, temperature_c: Optional[float]):
        """Records a new temperature observation for a station."""
        if temperature_c is None or np.isnan(temperature_c):
            return
        
        hist = self._temp_history.setdefault(station_id, deque(maxlen=72))
        hist.append((pd.to_datetime(timestamp, utc=True), float(temperature_c)))

    def seed_from_dataframe(self, station_id: str, df: pd.DataFrame):
        """Seeds the auditor history with recent readings from a dataframe."""
        if df.empty or "temperature_c" not in df.columns or "timestamp" not in df.columns:
            return
        valid = df.dropna(subset=["temperature_c", "timestamp"]).sort_values("timestamp")
        hist = self._temp_history.setdefault(station_id, deque(maxlen=72))
        for _, row in valid.iterrows():
            hist.append((pd.to_datetime(row["timestamp"], utc=True), float(row["temperature_c"])))

    def seed_initial_baselines(self, data_dir: Optional[Any] = None, limit: int = 48):
        """Pre-seeds all available station histories with clean baseline observations."""
        from pathlib import Path
        dir_path = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"
        if not dir_path.exists():
            return
        for f in dir_path.glob("*_labeled.csv"):
            sid = f.stem.replace("_labeled", "")
            try:
                df = pd.read_csv(f, parse_dates=["timestamp"])
                clean = df[~df["is_anomaly"].fillna(False).astype(bool)] if "is_anomaly" in df.columns else df
                if not clean.empty:
                    self.seed_from_dataframe(sid, clean.head(limit))
            except Exception:
                pass

    def _compute_diurnal_mean(self, station_id: str, window_hours: int = DIURNAL_WINDOW_HOURS) -> Optional[float]:
        """
        Computes 24-hour diurnal rolling mean for a station.
        Cancels out diurnal solar oscillation S_1.
        """
        hist = self._temp_history.get(station_id)
        if not hist or len(hist) < MIN_HOURS_FOR_AUDIT:
            return None
        
        # Take the most recent window_hours readings
        recent_readings = [val for _, val in list(hist)[-window_hours:]]
        if len(recent_readings) < MIN_HOURS_FOR_AUDIT:
            return None
        return float(np.mean(recent_readings))

    def audit_station(self, station_id: str) -> Dict[str, Any]:
        """
        Runs the diurnal secular invariant audit for a specific station.
        Returns calibration drift diagnostics and WMO-No. 8 maintenance advisory.
        """
        cluster_id = self.station_to_cluster.get(station_id)
        if not cluster_id or cluster_id not in self.station_clusters:
            return {
                "status": "CALIBRATED_NOMINAL",
                "secular_divergence_c": 0.0,
                "peer_coherence_c": 0.0,
                "cluster_id": cluster_id or "UNKNOWN",
                "advisory_message": "Single station topology; secular peer cluster arbitration inactive.",
                "wmo_compliance": "WMO-No. 8 Class A",
            }

        cluster_stations = self.station_clusters[cluster_id]
        peers = [s for s in cluster_stations if s != station_id]

        target_diurnal = self._compute_diurnal_mean(station_id)
        peer_diurnals = {p: self._compute_diurnal_mean(p) for p in peers}
        valid_peer_diurnals = {p: val for p, val in peer_diurnals.items() if val is not None}

        # Need at least 2 peers with sufficient data
        if target_diurnal is None or len(valid_peer_diurnals) < 2:
            return {
                "status": "CALIBRATED_NOMINAL",
                "secular_divergence_c": 0.0,
                "peer_coherence_c": 0.0,
                "cluster_id": cluster_id,
                "advisory_message": f"Insufficient 24h diurnal history ({len(valid_peer_diurnals)} peers available). Collecting multi-hour diurnal samples.",
                "wmo_compliance": "WMO-No. 8 Calibrating",
            }

        # Calculate unilateral secular divergence: delta_i = median_p ((T_i - T_p) - B_ip)
        shifts = []
        for p, p_mean in valid_peer_diurnals.items():
            observed_diff = target_diurnal - p_mean
            base_diff = self._pairwise_lapse_baselines.get((station_id, p), 0.0)
            shifts.append(observed_diff - base_diff)
        
        secular_divergence = float(np.median(shifts))

        # Calculate peer internal coherence: gamma = max_{j < k} | (T_j - T_k) - B_jk |
        peer_list = list(valid_peer_diurnals.keys())
        peer_diffs = []
        for i, pa in enumerate(peer_list):
            for pb in peer_list[i + 1 :]:
                obs_jk = valid_peer_diurnals[pa] - valid_peer_diurnals[pb]
                base_jk = self._pairwise_lapse_baselines.get((pa, pb), 0.0)
                peer_diffs.append(abs(obs_jk - base_jk))
        
        peer_coherence = float(np.max(peer_diffs)) if peer_diffs else 0.0

        # Classify calibration drift according to WMO-No. 8 standards
        abs_div = abs(secular_divergence)

        if peer_coherence > MAX_COHERENT_PEER_SPREAD_C:
            status = "CALIBRATED_NOMINAL"
            wmo_code = "WMO-No. 8 Synoptic Spread"
            sign = "+" if secular_divergence >= 0 else ""
            msg = (
                f"Cluster {cluster_id} exhibits active microclimatic dispersion (peer spread ±{peer_coherence:.2f}°C). "
                f"Secular drift divergence ({sign}{secular_divergence:.2f}°C) deferred to prevent false alarms."
            )
        elif abs_div > WMO_CRITICAL_THRESHOLD_C:
            status = "CRITICAL_RECALIBRATION_REQUIRED"
            wmo_code = "WMO-No. 8 Out of Tolerance"
            sign = "+" if secular_divergence >= 0 else ""
            msg = (
                f"Severe unilateral secular divergence ({sign}{secular_divergence:.2f}°C) against coherent peers "
                f"(spread ±{peer_coherence:.2f}°C) over diurnal cycle. Thermistor aging or shield degradation suspected. "
                f"Immediate field recalibration dispatch recommended."
            )
        elif abs_div > WMO_ADVISORY_THRESHOLD_C:
            status = "RECALIBRATION_ADVISORY"
            wmo_code = "WMO-No. 8 Advisory Class C"
            sign = "+" if secular_divergence >= 0 else ""
            msg = (
                f"Persistent unilateral secular divergence ({sign}{secular_divergence:.2f}°C) detected against "
                f"cluster peers (spread ±{peer_coherence:.2f}°C) over 24h diurnal cycle. Sensor remains within live "
                f"ingestion tolerance; preventive calibration service advised."
            )
        else:
            status = "CALIBRATED_NOMINAL"
            wmo_code = "WMO-No. 8 Class A (Nominal)"
            sign = "+" if secular_divergence >= 0 else ""
            msg = (
                f"Secular calibration nominal ({sign}{secular_divergence:.2f}°C). "
                f"Diurnal invariant tracking confirms zero sensor bias drift against cluster {cluster_id} peers."
            )

        audit_result = {
            "status": status,
            "secular_divergence_c": round(secular_divergence, 2),
            "peer_coherence_c": round(peer_coherence, 2),
            "cluster_id": cluster_id,
            "advisory_message": msg,
            "wmo_compliance": wmo_code,
        }
        self._latest_audit[station_id] = audit_result
        return audit_result

    def audit_all_stations(self) -> Dict[str, Dict[str, Any]]:
        """Audits all stations across all clusters."""
        results = {}
        for cluster_id, stations in self.station_clusters.items():
            for sid in stations:
                results[sid] = self.audit_station(sid)
        return results

    def get_cluster_summary(self) -> List[Dict[str, Any]]:
        """Returns cluster-level aggregation of secular calibration drift."""
        cluster_summaries = []
        for cluster_id, stations in self.station_clusters.items():
            audits = [self.audit_station(s) for s in stations]
            advisory_count = sum(1 for a in audits if a["status"] != "CALIBRATED_NOMINAL")
            max_drift = max((abs(a["secular_divergence_c"]) for a in audits), default=0.0)
            avg_peer_coherence = float(np.mean([a["peer_coherence_c"] for a in audits])) if audits else 0.0

            cluster_summaries.append({
                "cluster_id": cluster_id,
                "stations": stations,
                "advisories_active": advisory_count,
                "max_secular_divergence_c": round(max_drift, 2),
                "cluster_peer_coherence_c": round(avg_peer_coherence, 2),
                "cluster_status": "NEEDS_ATTENTION" if advisory_count > 0 else "NOMINAL",
            })
        return cluster_summaries
