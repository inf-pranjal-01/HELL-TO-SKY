
import sys
from collections import deque
from pathlib import Path
import pandas as pd
sys.path.append(str(Path(__file__).parent.parent))
from model.engine import DecisionEngine
from model.detect import SensorHealthTracker, PARAMS
from model.features import (
    ROLLING_WINDOW_HOURS, DRIFT_LOOKBACK_HOURS, build_features_for_history,
)
from model.explain import ExplainerCache
from config import RECOVERY_CLEAN_STREAK_REQUIRED
from history_store import HistoryStore
RAW_HISTORY_MAXLEN_HOURS = max(int(str(ROLLING_WINDOW_HOURS).replace('h', '')), int(DRIFT_LOOKBACK_HOURS)) + 12
MODE_LIVE = "live"
MODE_REPLAY = "replay"
class StationBuffer:
    def __init__(self, station_id: str):
        self.station_id = station_id
        self.health = SensorHealthTracker(station_id)
        self._raw_rows: deque = deque(maxlen=RAW_HISTORY_MAXLEN_HOURS)
        self.recovery_active: bool = False
        self.recovery_clean_count: int = 0
        self._cached_df = None
        self._cache_dirty = True
    def raw_history_df(self) -> pd.DataFrame:
        if self._cache_dirty:
            self._cached_df = pd.DataFrame(list(self._raw_rows))
            self._cache_dirty = False
        return self._cached_df
    def record_raw_reading(self, raw_reading: dict, timestamp, verdict: dict):
        if not self.health.should_include_in_baseline():
            return
        if verdict.get("is_anomaly"):
            return
        if self.recovery_active:
            return
        row = dict(raw_reading)
        row["station_id"] = self.station_id
        row["timestamp"] = timestamp
        self._raw_rows.append(row)
        self._cache_dirty = True
    def reset_detection_state(self):
        self._raw_rows.clear()
        self._cache_dirty = True
        self.health = SensorHealthTracker(self.station_id)
        self.recovery_active = False
        self.recovery_clean_count = 0
    def mark_repaired(self, timestamp):
        self.recovery_active = True
        self.recovery_clean_count = 0
        self.health.status = "WARNING"
        self.health.offline_reason = None
        self.health._clean_streak = 0
        for p in self.health.param_status:
            self.health.param_status[p] = "WARNING"
            self.health.param_offline_reason[p] = None
            self.health._param_clean_streak[p] = 0
            self.health._param_recent_10h[p].clear()
            self.health._param_recent_24h[p].clear()
    def force_recover(self):
        self.recovery_active = False
        self.recovery_clean_count = 0
        self.health.status = "HEALTHY"
        self.health.offline_reason = None
        self.health._clean_streak = 0
        for p in self.health.param_status:
            self.health.param_status[p] = "HEALTHY"
            self.health.param_offline_reason[p] = None
            self.health._param_clean_streak[p] = 0
            self.health._param_recent_10h[p].clear()
            self.health._param_recent_24h[p].clear()
    def update_recovery(self, verdict: dict):
        if not self.recovery_active:
            return
        if self.health.status == "OFFLINE":
            self.recovery_active = False
            self.recovery_clean_count = 0
            return
        if verdict["is_anomaly"]:
            self.recovery_clean_count = 0
            return
        self.recovery_clean_count += 1
        if self.recovery_clean_count >= RECOVERY_CLEAN_STREAK_REQUIRED:
            self.recovery_active = False
            self.recovery_clean_count = 0
            self.health.status = "HEALTHY"
class StateManager:
    def __init__(self, metadata: pd.DataFrame, artifact: dict, history_store: HistoryStore = None):
        self.metadata = metadata
        self.artifact = artifact
        self.explainer = ExplainerCache(artifact)
        self.buffers: dict[str, StationBuffer] = {
            sid: StationBuffer(sid) for sid in metadata["station_id"]
        }
        self.history = history_store or HistoryStore()
        self.neighbor_map = {}
        for sid in metadata["station_id"]:
            cluster = metadata[metadata["station_id"] == sid]["cluster_id"].iloc[0]
            self.neighbor_map[sid] = metadata[(metadata["cluster_id"] == cluster) & (metadata["station_id"] != sid)]["station_id"].tolist()
        self.mode: str = MODE_LIVE
    def switch_to_live(self):
        self.mode = MODE_LIVE
        for buf in self.buffers.values():
            buf.reset_detection_state()
    def start_replay(self):
        self.mode = MODE_REPLAY
        for buf in self.buffers.values():
            buf.reset_detection_state()
    def force_recover_station(self, station_id: str):
        self.buffers[station_id].force_recover()
    def ingest_reading(
        self,
        station_id: str,
        raw_reading: dict,
        timestamp,
        current_network_readings: Optional[dict] = None,
        include_evaluation_diagnostics: bool = False,
    ) -> dict:
        buf = self.buffers[station_id]
        history_df = buf.raw_history_df()
        current_row = dict(raw_reading, station_id=station_id, timestamp=timestamp)
        history_df_with_current = (
            pd.concat([history_df, pd.DataFrame([current_row])], ignore_index=True)
            if not history_df.empty else pd.DataFrame([current_row])
        )
        featured_history = build_features_for_history(history_df_with_current)
        neighbor_buffers = {}
        for nid in self.neighbor_map.get(station_id, []):
            nbuf_df = self.buffers[nid].raw_history_df()
            if current_network_readings and nid in current_network_readings:
                n_raw, n_ts = current_network_readings[nid]
                if n_raw is not None:
                    n_ts_dt = pd.to_datetime(n_ts, utc=True)
                    has_ts = False
                    if not nbuf_df.empty and "timestamp" in nbuf_df.columns:
                        has_ts = (pd.to_datetime(nbuf_df["timestamp"], utc=True) == n_ts_dt).any()
                    if not has_ts:
                        n_row = dict(n_raw, station_id=nid, timestamp=n_ts)
                        nbuf_df = pd.concat([nbuf_df, pd.DataFrame([n_row])], ignore_index=True) if not nbuf_df.empty else pd.DataFrame([n_row])
            neighbor_buffers[nid] = nbuf_df
        verdict = DecisionEngine.decide(
            raw_reading,
            history_df_with_current,
            neighbor_buffers,
            self.artifact,
            state=self.explainer,
            precomputed_features=featured_history.iloc[-1],
            precomputed_history_featured=featured_history,
            include_evaluation_diagnostics=include_evaluation_diagnostics,
        )
        verdict["confirmed_spike_params"] = {
            event["parameter"] for event in verdict.get("confirmed_spikes", [])
        }
        buf.health.record(verdict)
        if buf.recovery_active:
            buf.update_recovery(verdict)
        verdict["health_status"] = buf.health.status
        for spike in verdict.get("confirmed_spikes", []):
            self.history.mark_spike(
                station_id, spike["timestamp"], spike["parameter"],
                spike["suggested_value"], self.mode,
            )
            buf._raw_rows = deque(
                (row for row in buf._raw_rows if pd.Timestamp(row["timestamp"]) != spike["timestamp"]),
                maxlen=RAW_HISTORY_MAXLEN_HOURS,
            )
            buf._cache_dirty = True
        buf.record_raw_reading(raw_reading, timestamp, verdict)
        self.history.append(station_id, timestamp, raw_reading, verdict, source=self.mode)
        return verdict
    def mark_station_repaired(self, station_id: str, timestamp):
        self.buffers[station_id].mark_repaired(timestamp)
    def get_station_status(self, station_id: str) -> dict:
        buf = self.buffers[station_id]
        return {
            "station_id": station_id,
            "status": buf.health.status,
            "offline_reason": buf.health.offline_reason,
            "recovery_active": buf.recovery_active,
            "mode": self.mode,
        }
    def get_station_history(self, station_id: str, hours: float = 24, include_replay: bool = False) -> list[dict]:
        active_source = None if include_replay else self.mode
        df = self.history.get_recent(station_id, hours=hours, source=active_source)
        return df.to_dict(orient="records")
