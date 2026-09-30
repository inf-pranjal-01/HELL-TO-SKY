
import asyncio
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import httpx
import joblib
import pandas as pd
from model.state import StateManager
from config import RULE_BASE_CONFIDENCE, score_to_severity
DATA_DIR = Path(__file__).parent.parent / "data"
ARTIFACTS_PATH = Path(__file__).parent.parent / "model_artifacts" / "isolation_forest.pkl"
REPLAY_STEP_SECONDS = 2
LIVE_FETCH_INTERVAL_SECONDS = 15 * 60
TREND_HISTORY_MAXLEN = 2000
RECENT_ANOMALIES_MAXLEN = 200
OPEN_METEO_CURRENT_URL = "https://api.open-meteo.com/v1/forecast"
ROOT_CAUSE_BY_FAULT_TYPE = {
    "physical_bounds": "Reading outside physically possible range",
    "dropout": "Sensor communication failure",
    "frozen_value": "Sensor stuck / communication fault",
    "drift": "Calibration drift suspected",
    "spike": "Sudden reading spike -- possible sensor malfunction",
    "statistical_anomaly": "Unusual reading pattern flagged by model",
}
LIVE_FETCH_SEMAPHORE = asyncio.Semaphore(10)
async def _fetch_live_reading(client: httpx.AsyncClient, lat: float, lon: float) -> dict | None:
    try:
        async with LIVE_FETCH_SEMAPHORE:
            resp = await client.get(
                OPEN_METEO_CURRENT_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,surface_pressure,relative_humidity_2m",
                    "timezone": "UTC",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()["current"]
            return {
                "temperature_c": float(data["temperature_2m"]),
                "pressure_hpa": float(data["surface_pressure"]),
                "humidity_pct": float(data["relative_humidity_2m"]),
                "_observed_at": data.get("time"),
            }
    except Exception:
        return None
class SimulatorState:
    def __init__(self, metadata: pd.DataFrame, artifact: dict, broadcast_callback=None):
        self.metadata = metadata
        self.manager = StateManager(metadata, artifact)
        self.broadcast_callback = broadcast_callback
        self._replay_cursor_idx: int = 0
        self._replay_frames: dict[str, pd.DataFrame] = {}
        self._replay_len: int = 0
        self._live_cache: dict[str, dict] = {}
        self._live_observed_at: dict[str, datetime] = {}
        self._live_last_fetch: datetime | None = None
        self._last_live_latest: dict[str, dict] = {}
        self._live_refresh_requested = False
        self._last_ingested: dict[str, dict] = {}
        self._last_ingested_timestamp: dict[str, datetime] = {}
        self.latest: dict[str, dict] = {}
        self.trend_history: dict[str, deque] = {
            sid: deque(maxlen=TREND_HISTORY_MAXLEN) for sid in metadata["station_id"]
        }
        self.recent_anomalies: deque = deque(maxlen=RECENT_ANOMALIES_MAXLEN)
        self._anomaly_counter = 0
        self._http_client = httpx.AsyncClient()
        self._seed_live_cache_from_local_data()
    async def _broadcast_event(self, payload: dict):
        if self.broadcast_callback:
            try:
                res = self.broadcast_callback(payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[simulator] broadcast exception: {e!r}")
    def _seed_live_cache_from_local_data(self) -> None:
        required_columns = ["timestamp", "temperature_c", "pressure_hpa", "humidity_pct"]
        for station_id in self.metadata["station_id"]:
            path = DATA_DIR / f"{station_id}.csv"
            try:
                frame = pd.read_csv(path, usecols=required_columns).dropna(subset=required_columns)
                if frame.empty:
                    continue
                row = frame.iloc[-1]
                self._live_cache[station_id] = {
                    "temperature_c": float(row["temperature_c"]),
                    "pressure_hpa": float(row["pressure_hpa"]),
                    "humidity_pct": float(row["humidity_pct"]),
                }
                self._live_observed_at[station_id] = datetime.now(timezone.utc)
            except (FileNotFoundError, ValueError, KeyError, pd.errors.ParserError):
                continue
    @property
    def mode(self) -> str:
        return self.manager.mode
    async def close(self):
        await self._http_client.aclose()
    def start_replay(self, target_station_id: str | None = None, target_fault_type: str | None = None) -> str:
        self.manager.history.clear_all(source="replay")
        if self.mode == "live":
            self._last_live_latest = dict(self.latest)
        self._replay_frames = {}
        for sid in self.metadata["station_id"]:
            path = DATA_DIR / f"{sid}_labeled.csv"
            if not path.exists():
                raise FileNotFoundError(f"No labeled data for {sid} at {path} -- run anomaly_injector.py first.")
            df = pd.read_csv(path, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            self._replay_frames[sid] = df
        self._replay_len = min(len(df) for df in self._replay_frames.values())
        self._replay_cursor_idx = 0
        self.manager.start_replay()
        self._last_ingested = {}
        self._last_ingested_timestamp = {}
        self.latest = {}
        self.trend_history = {
            sid: deque(maxlen=TREND_HISTORY_MAXLEN)
            for sid in self.metadata["station_id"]
        }
        self.recent_anomalies.clear()
        self._anomaly_counter += 1
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_event({
                "type": "MODE_CHANGE",
                "mode": "replay",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except RuntimeError:
            pass
        return f"anom_{self._anomaly_counter:05d}"
    def _stop_replay(self):
        self.manager.switch_to_live()
        self.manager.history.clear_all(source="replay")
        self._replay_frames = {}
        self._last_ingested = {}
        self._last_ingested_timestamp = {}
        self.latest = dict(self._last_live_latest)
        self.trend_history = {
            sid: deque(maxlen=TREND_HISTORY_MAXLEN)
            for sid in self.metadata["station_id"]
        }
        self.recent_anomalies.clear()
        self._live_last_fetch = None
        self._live_refresh_requested = True
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_event({
                "type": "MODE_CHANGE",
                "mode": "live",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except RuntimeError:
            pass
    def stop_replay(self):
        if self.mode == "replay":
            self._stop_replay()
    async def refresh_live_now(self) -> None:
        if self.mode != "live":
            return
        self._live_last_fetch = None
        self._force_live_ingest = True
        self._last_ingested_timestamp.clear()
        self._last_ingested.clear()
        await self._maybe_refresh_live_cache()
        await self.tick()
    async def _maybe_refresh_live_cache(self):
        now = datetime.now(timezone.utc)
        if (
            self._live_last_fetch is not None
            and (now - self._live_last_fetch).total_seconds() < LIVE_FETCH_INTERVAL_SECONDS
        ):
            return
        self._live_last_fetch = now
        station_requests = [
            (row["station_id"], _fetch_live_reading(self._http_client, row["lat"], row["lon"]))
            for _, row in self.metadata.iterrows()
        ]
        readings = await asyncio.gather(
            *(request for _, request in station_requests),
            return_exceptions=True,
        )
        for (sid, _), reading in zip(station_requests, readings):
            if isinstance(reading, Exception):
                print(f"[simulator] live fetch failed for {sid}: {reading!r}")
                continue
            if reading is not None:
                observed_at = reading.pop("_observed_at", None)
                if observed_at:
                    observed = pd.Timestamp(observed_at)
                    if observed.tzinfo is None:
                        observed = observed.tz_localize("UTC")
                    self._live_observed_at[sid] = observed.to_pydatetime()
                self._live_cache[sid] = reading
    def _next_live_row(self, station_id: str) -> dict | None:
        return self._live_cache.get(station_id)
    def _next_replay_row(self, station_id: str) -> dict:
        df = self._replay_frames[station_id]
        row = df.iloc[self._replay_cursor_idx]
        return {
            "temperature_c": float(row["temperature_c"]) if pd.notna(row["temperature_c"]) else None,
            "pressure_hpa": float(row["pressure_hpa"]) if pd.notna(row["pressure_hpa"]) else None,
            "humidity_pct": float(row["humidity_pct"]) if pd.notna(row["humidity_pct"]) else None,
        }
    async def tick(self):
        now = datetime.now(timezone.utc)
        current_mode = self.mode
        if current_mode == "live":
            await self._maybe_refresh_live_cache()
        network_snapshot = {}
        for sid in self.metadata["station_id"]:
            if current_mode == "replay":
                r_reading = self._next_replay_row(sid)
                r_row = self._replay_frames[sid].iloc[self._replay_cursor_idx]
                r_ts = pd.Timestamp(r_row["timestamp"])
                if r_ts.tzinfo is None:
                    r_ts = r_ts.tz_localize("UTC")
                r_ts = r_ts.to_pydatetime()
            else:
                r_reading = self._next_live_row(sid)
                if getattr(self, "_force_live_ingest", False):
                    r_ts = now
                else:
                    r_ts = self._live_observed_at.get(sid, now)
                if hasattr(r_ts, "year") and r_ts.year <= 2025:
                    r_ts = now
            if r_reading is not None:
                network_snapshot[sid] = (r_reading, r_ts)
        for station_id in self.metadata["station_id"]:
            if station_id not in network_snapshot:
                continue
            raw_reading, reading_timestamp = network_snapshot[station_id]
            should_ingest = (
                current_mode == "replay"
                or getattr(self, "_force_live_ingest", False)
                or self._last_ingested_timestamp.get(station_id) != reading_timestamp
            )
            if should_ingest:
                verdict = await asyncio.to_thread(
                    self.manager.ingest_reading,
                    station_id,
                    raw_reading,
                    reading_timestamp,
                    network_snapshot,
                )
                self._last_ingested[station_id] = dict(raw_reading)
                self._last_ingested_timestamp[station_id] = reading_timestamp
            else:
                cached = self.latest.get(station_id)
                if cached is None:
                    continue
                verdict = cached["verdict"]
            self.latest[station_id] = {
                "raw_reading": raw_reading,
                "verdict": verdict,
                "timestamp": reading_timestamp,
                "source": current_mode,
            }
            self.trend_history[station_id].append({
                "timestamp": reading_timestamp,
                "temperature_c": raw_reading.get("temperature_c"),
                "pressure_hpa": raw_reading.get("pressure_hpa"),
                "humidity_pct": raw_reading.get("humidity_pct"),
                "is_anomaly": verdict["is_anomaly"],
                "health_status": verdict.get("health_status"),
                "source": current_mode,
            })
            ingest_time_ms = int(time.time() * 1000)
            await self._broadcast_event({
                "type": "TELEMETRY_TICK",
                "station_id": station_id,
                "timestamp": reading_timestamp.isoformat() if hasattr(reading_timestamp, "isoformat") else str(reading_timestamp),
                "reading": {
                    "temperature_c": raw_reading.get("temperature_c"),
                    "pressure_hpa": raw_reading.get("pressure_hpa"),
                    "humidity_pct": raw_reading.get("humidity_pct"),
                },
                "verdict": {
                    "is_anomaly": bool(verdict.get("is_anomaly", False)),
                    "anomaly_score_pct": verdict.get("anomaly_score_pct"),
                    "model_confidence_pct": verdict.get("model_confidence_pct"),
                    "rule_confidence_pct": verdict.get("rule_confidence_pct"),
                    "fault_type": verdict.get("fault_type"),
                    "severity": verdict.get("severity"),
                    "health_status": verdict.get("health_status"),
                    "suggested_values": verdict.get("suggested_values"),
                    "decision_basis": verdict.get("decision_basis"),
                    "likely_faulty_sensors": verdict.get("likely_faulty_sensors", []),
                },
                "mode": current_mode,
                "ingest_time_ms": ingest_time_ms,
            })
            for spike in verdict.get("confirmed_spikes", []):
                self._anomaly_counter += 1
                spike_item = {
                    "anomaly_id": f"anom_{self._anomaly_counter:05d}",
                    "timestamp": spike["timestamp"],
                    "station_id": station_id,
                    "anomaly_score_pct": RULE_BASE_CONFIDENCE["spike"],
                    "model_confidence_pct": None,
                    "rule_confidence_pct": RULE_BASE_CONFIDENCE["spike"],
                    "suggested_values": {spike["parameter"]: spike["suggested_value"]},
                    "observed_values": {spike["parameter"]: spike["observed_value"]},
                    "affected_parameters": [spike["parameter"]],
                    "shap_features": [],
                    "explanation_method": None,
                    "likely_faulty_sensors": [spike["parameter"]],
                    "severity": "medium",
                    "type": "spike",
                    "root_cause": ROOT_CAUSE_BY_FAULT_TYPE["spike"],
                    "regime": verdict.get("regime"),
                    "network_corroboration": verdict.get("network_corroboration"),
                    "model_status": verdict.get("model_status"),
                }
                self.recent_anomalies.appendleft(spike_item)
                await self._broadcast_event({
                    "type": "ANOMALY_EVENT",
                    "station_id": station_id,
                    "anomaly": spike_item,
                    "ingest_time_ms": ingest_time_ms,
                })
            if should_ingest and verdict["is_anomaly"]:
                affected_parameters = list(dict.fromkeys(
                    verdict.get("likely_faulty_sensors", [])
                    or [
                        rule.get("parameter") if isinstance(rule, dict) else rule[1]
                        for rule in verdict.get("rules_fired", [])
                    ]
                    or list((verdict.get("suggested_values") or {}).keys())
                ))
                observed_values = {
                    param: raw_reading.get(param)
                    for param in affected_parameters
                    if param in raw_reading
                }
                self._anomaly_counter += 1
                anomaly_item = {
                    "anomaly_id": f"anom_{self._anomaly_counter:05d}",
                    "timestamp": reading_timestamp,
                    "station_id": station_id,
                    "anomaly_score_pct": verdict["anomaly_score_pct"],
                    "model_confidence_pct": verdict.get("model_confidence_pct"),
                    "rule_confidence_pct": verdict.get("rule_confidence_pct"),
                    "suggested_values": verdict.get("suggested_values"),
                    "observed_values": observed_values,
                    "affected_parameters": affected_parameters,
                    "shap_features": verdict.get("shap_features", []),
                    "explanation_method": verdict.get("explanation_method"),
                    "suggested_metadata": verdict.get("suggested_metadata", {}),
                    "likely_faulty_sensors": verdict.get("likely_faulty_sensors", []),
                    "severity": verdict["severity"],
                    "rules_fired": verdict.get("rules_fired", []),
                    "type": verdict["fault_type"] or "statistical_anomaly",
                    "root_cause": ROOT_CAUSE_BY_FAULT_TYPE.get(
                        verdict["fault_type"],
                        "Unusual reading pattern flagged by model"
                    ),
                    "regime": verdict.get("regime"),
                    "network_corroboration": verdict.get("network_corroboration"),
                    "model_status": verdict.get("model_status"),
                }
                self.recent_anomalies.appendleft(anomaly_item)
                await self._broadcast_event({
                    "type": "ANOMALY_EVENT",
                    "station_id": station_id,
                    "anomaly": anomaly_item,
                    "ingest_time_ms": ingest_time_ms,
                })
        if current_mode == "replay":
            self._replay_cursor_idx += 1
            if self._replay_cursor_idx >= self._replay_len:
                self._stop_replay()
        self._force_live_ingest = False
async def run_simulation_loop(sim_state: SimulatorState):
    next_live_tick = 0.0
    while True:
        try:
            now = asyncio.get_running_loop().time()
            if sim_state.mode == "replay" or now >= next_live_tick:
                await sim_state.tick()
                if sim_state.mode == "live":
                    if sim_state._live_refresh_requested:
                        next_live_tick = 0.0
                        sim_state._live_refresh_requested = False
                    else:
                        next_live_tick = asyncio.get_running_loop().time() + LIVE_FETCH_INTERVAL_SECONDS
        except Exception as e:
            print(f"[simulator] tick failed: {e!r}\n{traceback.format_exc()}")
        await asyncio.sleep(REPLAY_STEP_SECONDS if sim_state.mode == "replay" else 1)
def create_simulator_state(broadcast_callback=None) -> SimulatorState:
    if not ARTIFACTS_PATH.exists():
        raise FileNotFoundError(f"No trained model at {ARTIFACTS_PATH} -- run model/train.py first.")
    artifact = joblib.load(ARTIFACTS_PATH)
    if "rule_thresholds" not in artifact:
        raise KeyError("Artifact missing 'rule_thresholds' -- retrain with the current train.py.")
    metadata_path = DATA_DIR / "stations_metadata.csv"
    metadata = pd.read_csv(metadata_path)
    return SimulatorState(metadata, artifact, broadcast_callback=broadcast_callback)
