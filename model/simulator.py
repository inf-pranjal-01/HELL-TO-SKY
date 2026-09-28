"""
SkyGuard AI — simulator.py: drives the live/demo data stream.

TWO MODES, switched by the whole system at once (not per-station):

  LIVE (default): fetches CURRENT real weather from Open-Meteo for
  each station's real coordinates. No faults -- genuine, unsupervised
  detection against real present-day conditions. This is the actual
  production behavior.

  REPLAY (demo/simulator mode): steps through all 20 *_labeled.csv
  files in lockstep at live cadence. These already contain real
  injected faults with known ground truth (anomaly_injector.py) --
  detect.py scores each reading BLIND, exactly as it would any other
  reading, and whatever it flags is a genuine model detection, not a
  scripted/faked frontend event. This replaces an earlier design that
  reimplemented fault shapes live; that's been removed -- there's no
  reason to reinvent faults when validated labeled data already exists.

MODE SWITCH VIA EXISTING CONTRACT: the frontend's POST
/api/inject-anomaly button ({station_id, type} -> {anomaly_id,
message}) is the only trigger the frontend already has wired, and the
frontend doc explicitly prohibits inventing new endpoints. So that
route (wired in main.py, not here) calls SimulatorState.start_replay(),
which switches the WHOLE system into replay mode -- station_id/type
are accepted for contract-shape compatibility but not used to target
a single station, since replay always drives all 20 simultaneously
from their own pre-injected faults. Replay auto-reverts to LIVE once
every labeled file is exhausted. If per-station/per-type targeting is
actually wanted instead, this needs revisiting -- flagging the
assumption rather than guessing further.

LIVE-FETCH CAVEAT: the exact Open-Meteo "current conditions" call
below is written to the pattern data_fetch.py's archive-history call
likely follows (same station coordinates from stations_metadata.csv),
but I don't have data_fetch.py in context to confirm the exact
endpoint/params it uses. Verify _fetch_live_reading against your real
data_fetch.py before relying on it -- the shape may need adjusting.

============================================================================
PATCH (this pass): REPLAY -> LIVE was silently skipping state.py's own
purge fix. THIS IS THE ACTUAL BUG YOU FLAGGED.
============================================================================
The old start_replay()/_stop_replay() each did:

    self.manager = StateManager(self.metadata, self.manager.artifact)

-- i.e. they THREW AWAY the old StateManager and built a brand new one
from scratch, instead of calling the mode-switch methods state.py's own
rewrite was specifically built to provide (StateManager.start_replay() /
switch_to_live()). This mattered for one concrete reason:

  StateManager.__init__ does `self.history = history_store or
  HistoryStore()`. A freshly constructed HistoryStore() still points at
  the SAME on-disk DATA_DIR/data/history/ -- it's not a fresh sandbox,
  it's the exact same per-station CSV files the old manager was writing
  to. So building a new StateManager did NOT clear anything on disk.
  It just meant switch_to_live()'s actual fix -- purging every
  source="replay" row via HistoryStore.clear_all(source="replay") --
  never ran at all, on either transition. Replay's synthetic injected
  anomalies were left sitting permanently in the same file live rows
  get appended to, EXACTLY the bleed-through bug state.py's own rewrite
  was supposed to close. The only thing hiding it was
  get_station_history()'s defensive `source == self.mode` READ-TIME
  filter, which state.py's own docstring explicitly says is a second
  layer, "not a replacement for" the real purge.

  Rebuilding StateManager from scratch also meant every mode transition
  was silently O(this-run-only) instead of using the reset methods that
  actually integrate with HistoryStore correctly.

FIXED: both transitions now call self.manager.start_replay() /
self.manager.switch_to_live() on the SAME long-lived manager instance.
The manager (and its one HistoryStore) is now created ONCE, in
SimulatorState.__init__, and never rebuilt for the life of the process.

ALSO FIXED:
  - Import path: state.py lives at the backend root (imports bare
    `from config import ...` / `from history_store import HistoryStore`
    -- both root-level modules, not `model/`-prefixed), not inside
    model/. `from model.state import StateManager` would ImportError.
    Corrected to `from state import StateManager`; the sys.path append
    up to the parent of model/ is no longer needed for this import
    specifically but is left in place since detect.py/train.py's own
    `from model.X import Y` pattern still needs it if this file ever
    imports those directly.
  - Removed the duplicate `self.mode` string SimulatorState was
    tracking independently of StateManager.mode. Two independent mode
    trackers on two different objects is exactly the kind of "two
    derivations of the same fact that can silently drift apart" bug
    this project has hit before (see features.py's RULE_ONLY_PREFIXES
    comment, state.py/detect.py's threshold-drift postmortem). `.mode`
    is now a read-only property proxying self.manager.mode, so there is
    exactly one source of truth and any external caller (e.g. a status
    endpoint in main.py) reading sim_state.mode keeps working unchanged.
"""

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

REPLAY_STEP_SECONDS = 2  # one historical hour is streamed every two wall-clock seconds
LIVE_FETCH_INTERVAL_SECONDS = 15 * 60  # Open-Meteo current weather: poll every 15 minutes
EDGE_INACTIVITY_TIMEOUT_SECONDS = 35  # Auto-exit ESP32 edge mode after 35s of inactivity
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

async def _fetch_live_reading(client: httpx.AsyncClient, lat: float, lon: float) -> tuple[dict | None, str | None]:
    """
    Pulls CURRENT conditions for one station's coordinates.
    Returns (reading_dict, None) on success.
    Returns (None, error_diagnosis_string) on failure so callers can diagnose
    whether API is rate-limiting, timing out, or encountering network issues.
    """
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
            data = resp.json().get("current", {})
            if "temperature_2m" not in data or "surface_pressure" not in data:
                return None, "Open-Meteo response payload missing required atmospheric channels"
            return {
                "temperature_c": float(data["temperature_2m"]),
                "pressure_hpa": float(data["surface_pressure"]),
                "humidity_pct": float(data["relative_humidity_2m"]),
                "_observed_at": data.get("time"),
            }, None
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 429:
            return None, "Open-Meteo Rate Limit Exceeded (HTTP 429: Rate Limit Reached)"
        elif 500 <= status_code < 600:
            return None, f"Open-Meteo Server Outage (HTTP {status_code})"
        return None, f"Open-Meteo HTTP Error ({status_code}): {e.response.text[:100]}"
    except httpx.TimeoutException:
        return None, "Open-Meteo Gateway Timeout (>10.0s): API did not respond"
    except (httpx.ConnectError, httpx.NetworkError) as e:
        return None, f"Network Connection Failure: Unable to reach Open-Meteo ({type(e).__name__})"
    except Exception as e:
        return None, f"Provider Exception: {str(e)[:120]}"



class SimulatorState:
    """
    The object main.py's routes read from. One instance, created at
    FastAPI startup.

    self.manager is now created ONCE here and lives for the whole
    process -- see module docstring PATCH note. Mode transitions call
    self.manager.start_replay()/switch_to_live() on this SAME instance;
    they never rebuild it.
    """

    def __init__(self, metadata: pd.DataFrame, artifact: dict, broadcast_callback=None):
        self.metadata = metadata
        self.manager = StateManager(metadata, artifact)
        self.broadcast_callback = broadcast_callback

        self._replay_cursor_idx: int = 0
        self._replay_frames: dict[str, pd.DataFrame] = {}  # populated lazily on start_replay()
        self._replay_len: int = 0

        self._live_cache: dict[str, dict] = {}  # station_id -> last fetched reading
        self._live_observed_at: dict[str, datetime] = {}
        self._live_last_fetch: datetime | None = None
        # Last genuinely live readings remain available while an operator runs
        # a demo replay. They let the cards return immediately on exit rather
        # than showing a false "not found" state for up to 30 minutes.
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

        # Provider health & consecutive failure tracker
        self.provider_consecutive_failures: dict[str, int] = {sid: 0 for sid in metadata["station_id"]}
        self.provider_last_error: dict[str, str | None] = {sid: None for sid in metadata["station_id"]}
        self.provider_status: dict = {
            "status": "HEALTHY",
            "consecutive_failures": 0,
            "failing_stations": [],
            "diagnosed_cause": None,
            "last_error": None,
            "timestamp": None,
        }

        # ESP32 Edge hardware testing tracker
        self.edge_status: dict = {
            "status": "DISCONNECTED",
            "connected": False,
            "station_id": None,
            "device_id": None,
            "last_packet_time": None,
            "packet_count": 0,
        }
        self._edge_mode_started_at: datetime | None = None
        self._edge_last_packet_monotonic: float = 0.0

    async def _broadcast_event(self, payload: dict):
        """Asynchronously dispatch real-time events to connected WebSocket clients."""
        if self.broadcast_callback:
            try:
                res = self.broadcast_callback(payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[simulator] broadcast exception: {e!r}")

    @property
    def mode(self) -> str:
        return self.manager.mode

    async def close(self):
        """Clean shutdown handler."""
        pass

    # ---------------- mode control ----------------

    def start_replay(self, target_station_id: str | None = None, target_fault_type: str | None = None) -> str:
        """
        Called from main.py's POST /api/inject-anomaly handler. Loads
        every *_labeled.csv fresh (so repeated demo runs always replay
        from the start) and switches mode.

        FIXED: calls self.manager.start_replay() on the EXISTING manager.
        """
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

        # Simulator-local caches are cleared entirely
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

    def inject_fault_dynamic(self, station_id: str, fault_type: str | None = None) -> str:
        """
        Dynamically positions or injects a fault into active replay for the targeted station.
        If replay is running, locates the next labeled episode or resets to the fault start.
        """
        if self._replay_frames and station_id in self._replay_frames:
            df = self._replay_frames[station_id]
            if "fault_type" in df.columns and fault_type:
                matches = df[df["fault_type"] == fault_type]
                if not matches.empty:
                    self._replay_cursor_idx = max(0, int(matches.index[0]) - 2)
        self._anomaly_counter += 1
        return f"anom_{self._anomaly_counter:05d}"

    def _stop_replay(self):
        """
        Switches back to live mode and immediately purges all replay scratch
        data from TimescaleDB and local CSV files so no demo trash lingers.
        """
        self.manager.switch_to_live()
        self.manager.history.clear_all(source="replay")

        self._replay_frames = {}
        self._last_ingested = {}
        self._last_ingested_timestamp = {}
        # Restore the last Open-Meteo snapshot immediately. The next live
        # tick replaces it with a newly ingested sample; replay values never
        # leak back into the cards.
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
            loop.create_task(self.refresh_live_now())
        except RuntimeError:
            pass

    def stop_replay(self):
        """Operator-initiated replay -> live transition."""
        if self.mode == "replay":
            self._stop_replay()

    def start_edge_mode(self, target_station_id: str | None = None) -> str:
        """
        Switches system to EDGE mode (ESP32 hardware testing).
        Initializes edge status to WAITING until the ESP32 node sends its first packet.
        """
        self.manager.switch_to_edge()
        self._replay_frames = {}
        self._last_ingested = {}
        self._last_ingested_timestamp = {}
        self.latest = {}
        self.trend_history = {
            sid: deque(maxlen=TREND_HISTORY_MAXLEN)
            for sid in self.metadata["station_id"]
        }
        self.recent_anomalies.clear()

        self._edge_mode_started_at = datetime.now(timezone.utc)
        self._edge_last_packet_monotonic = time.monotonic()

        self.edge_status = {
            "status": "WAITING",
            "connected": False,
            "station_id": target_station_id,
            "device_id": None,
            "last_packet_time": None,
            "packet_count": 0,
        }

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_event({
                "type": "MODE_CHANGE",
                "mode": "edge",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            loop.create_task(self._broadcast_event({
                "type": "EDGE_STATUS",
                "edge_status": self.edge_status,
            }))
        except RuntimeError:
            pass

        return "edge_ready"

    def stop_edge_mode(self, reason: str = "manual"):
        """
        Switches back from EDGE to LIVE mode.
        Purges edge scratch state, restores live buffers, and resumes live Open-Meteo updates.
        """
        self.manager.switch_to_live()
        self._replay_frames = {}
        self._last_ingested = {}
        self._last_ingested_timestamp = {}
        self.latest = dict(self._last_live_latest)
        self.trend_history = {
            sid: deque(maxlen=TREND_HISTORY_MAXLEN)
            for sid in self.metadata["station_id"]
        }
        self.recent_anomalies.clear()

        self.edge_status = {
            "status": "DISCONNECTED",
            "connected": False,
            "station_id": None,
            "device_id": None,
            "last_packet_time": None,
            "packet_count": 0,
        }

        self._edge_mode_started_at = None
        self._edge_last_packet_monotonic = 0.0

        self._live_last_fetch = None
        self._live_refresh_requested = True

        msg = (
            "ESP32 hardware link timed out (no packets received for >35s). Auto-exited to Live Mode."
            if reason == "timeout"
            else "ESP32 mode closed. Switched to Live Mode."
        )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_event({
                "type": "MODE_CHANGE",
                "mode": "live",
                "reason": reason,
                "message": msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            loop.create_task(self._broadcast_event({
                "type": "EDGE_STATUS",
                "edge_status": self.edge_status,
            }))
            loop.create_task(self.refresh_live_now())
        except RuntimeError:
            pass

    async def refresh_live_now(self, priority_station_id: str | None = None) -> None:
        """Fetch the current provider observation outside the 30-min cadence.
        Prioritizes the active station for immediate processing.
        """
        if self.mode != "live":
            return
        self._live_last_fetch = None
        self._force_live_ingest = True
        self._last_ingested_timestamp.clear()
        self._last_ingested.clear()
        await self._maybe_refresh_live_cache(priority_station_id=priority_station_id)
        await self.tick()

    # ---------------- per-tick data sourcing ----------------

    async def _maybe_refresh_live_cache(self, priority_station_id: str | None = None):
        now = datetime.now(timezone.utc)
        if (
            self._live_last_fetch is not None
            and (now - self._live_last_fetch).total_seconds() < LIVE_FETCH_INTERVAL_SECONDS
            and not getattr(self, "_force_live_ingest", False)
        ):
            return
        self._live_last_fetch = now

        # Ensure priority station is at the front of the queue
        metadata_records = self.metadata.to_dict(orient="records")
        if priority_station_id:
            metadata_records = sorted(
                metadata_records,
                key=lambda r: 0 if r["station_id"] == priority_station_id else 1
            )

        async with httpx.AsyncClient() as client:
            station_requests = [
                (row["station_id"], _fetch_live_reading(client, float(row["lat"]), float(row["lon"])))
                for row in metadata_records
            ]
            fetch_results = await asyncio.gather(
                *(request for _, request in station_requests),
                return_exceptions=True,
            )

        failing_stations = []
        primary_diagnosed_cause = None

        for (sid, _), res in zip(station_requests, fetch_results):
            if isinstance(res, Exception):
                reading, err_diag = None, f"Unexpected fetch exception: {str(res)[:100]}"
            elif isinstance(res, tuple):
                reading, err_diag = res
            else:
                reading, err_diag = res, None

            if reading is not None:
                observed_at = reading.pop("_observed_at", None)
                if observed_at:
                    observed = pd.Timestamp(observed_at)
                    if observed.tzinfo is None:
                        observed = observed.tz_localize("UTC")
                    self._live_observed_at[sid] = observed.to_pydatetime()
                self._live_cache[sid] = reading
                # Reset failure tracking on success
                self.provider_consecutive_failures[sid] = 0
                self.provider_last_error[sid] = None
            else:
                # Provider fetch failed for this station
                self.provider_consecutive_failures[sid] = self.provider_consecutive_failures.get(sid, 0) + 1
                self.provider_last_error[sid] = err_diag
                if self.provider_consecutive_failures[sid] >= 2:
                    failing_stations.append(sid)
                    if not primary_diagnosed_cause and err_diag:
                        primary_diagnosed_cause = err_diag
                # Single tick failure: we gracefully skip the point and reuse cached readings
                # rather than synthesizing fake 0.0 or trigger false sensor dropouts.

        # Evaluate aggregate provider health
        prev_provider_status = self.provider_status.get("status", "HEALTHY")
        max_consecutive = max(self.provider_consecutive_failures.values()) if self.provider_consecutive_failures else 0

        if len(failing_stations) > 0:
            new_status = "FAILING" if len(failing_stations) >= max(1, len(metadata_records) // 2) else "DEGRADED"
            self.provider_status = {
                "status": new_status,
                "consecutive_failures": max_consecutive,
                "failing_stations": failing_stations,
                "diagnosed_cause": primary_diagnosed_cause or "Consecutive Open-Meteo API data retrieval failures",
                "last_error": primary_diagnosed_cause,
                "timestamp": now.isoformat(),
            }
            await self._broadcast_event({
                "type": "PROVIDER_STATUS",
                "provider_status": self.provider_status,
            })
        else:
            if prev_provider_status != "HEALTHY":
                self.provider_status = {
                    "status": "HEALTHY",
                    "consecutive_failures": 0,
                    "failing_stations": [],
                    "diagnosed_cause": None,
                    "last_error": None,
                    "timestamp": now.isoformat(),
                }
                await self._broadcast_event({
                    "type": "PROVIDER_STATUS",
                    "provider_status": self.provider_status,
                })

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

    # ---------------- the tick ----------------

    async def tick(self):
        """
        One simulation step across all stations. Replay retains each
        CSV reading's original hourly timestamp even though the stream
        advances at two seconds per hour; graph placement and detector
        rolling windows must follow measurement time, never wall-clock
        animation speed. Live uses the current UTC measurement time.
        """
        now = datetime.now(timezone.utc)
        current_mode = self.mode

        if current_mode == "live":
            await self._maybe_refresh_live_cache()

        # Phase 1: Collect simultaneous network snapshot across all stations
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

        # Phase 2: Ingest with complete symmetric peer consensus (Concurrent across all stations)
        async def _ingest_station(station_id):
            if station_id not in network_snapshot:
                return None
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
                    False,  # include_evaluation_diagnostics
                    False,  # persist_history (batched below)
                )
                self._last_ingested[station_id] = dict(raw_reading)
                self._last_ingested_timestamp[station_id] = reading_timestamp
            else:
                cached = self.latest.get(station_id)
                if cached is None:
                    return None
                verdict = cached["verdict"]

            return station_id, raw_reading, reading_timestamp, verdict, should_ingest

        results = await asyncio.gather(*[_ingest_station(sid) for sid in self.metadata["station_id"]], return_exceptions=True)

        batch_to_persist = []

        for res in results:
            if res is None or isinstance(res, Exception):
                continue
            station_id, raw_reading, reading_timestamp, verdict, should_ingest = res

            if should_ingest:
                batch_to_persist.append((station_id, reading_timestamp, raw_reading, verdict))

            self.latest[station_id] = {
                "raw_reading": raw_reading,
                "verdict": verdict,
                "timestamp": reading_timestamp,
                "source": current_mode,
            }
            if current_mode == "live":
                self._last_live_latest[station_id] = dict(self.latest[station_id])

            suggested = verdict.get("suggested_values") or {}
            self.trend_history[station_id].append({
                "timestamp": reading_timestamp,
                "temperature_c": raw_reading.get("temperature_c"),
                "pressure_hpa": raw_reading.get("pressure_hpa"),
                "humidity_pct": raw_reading.get("humidity_pct"),
                "is_anomaly": bool(verdict.get("is_anomaly", False)),
                "fault_type": verdict.get("fault_type"),
                "severity": verdict.get("severity"),
                "anomaly_score_pct": verdict.get("anomaly_score_pct"),
                "suggested_temperature_c": suggested.get("temperature_c"),
                "suggested_pressure_hpa": suggested.get("pressure_hpa"),
                "suggested_humidity_pct": suggested.get("humidity_pct"),
                "affected_parameters": verdict.get("affected_parameters") or verdict.get("likely_faulty_sensors") or [],
                "health_status": verdict.get("health_status"),
                "source": current_mode,
            })

        # Phase 3: High-throughput single vectorized batch commit to TimescaleDB & CSV
        if batch_to_persist:
            await asyncio.to_thread(
                self.manager.history.append_batch,
                batch_to_persist,
                source=current_mode,
            )

            # Broadcast live push over WebSocket for every station with updated telemetry
            ingest_time_ms = int(time.time() * 1000)
            for item in batch_to_persist:
                st_id, r_ts, r_raw, r_verdict = item
                ts_str = r_ts.isoformat() if hasattr(r_ts, "isoformat") else str(r_ts)
                await self._broadcast_event({
                    "type": "TELEMETRY_TICK",
                    "station_id": st_id,
                    "timestamp": ts_str,
                    "reading": {
                        "temperature_c": r_raw.get("temperature_c"),
                        "pressure_hpa": r_raw.get("pressure_hpa"),
                        "humidity_pct": r_raw.get("humidity_pct"),
                    },
                    "verdict": {
                        "is_anomaly": bool(r_verdict.get("is_anomaly", False)),
                        "anomaly_score_pct": r_verdict.get("anomaly_score_pct"),
                        "model_confidence_pct": r_verdict.get("model_confidence_pct"),
                        "rule_confidence_pct": r_verdict.get("rule_confidence_pct"),
                        "fault_type": r_verdict.get("fault_type"),
                        "severity": r_verdict.get("severity"),
                        "health_status": r_verdict.get("health_status"),
                        "suggested_values": r_verdict.get("suggested_values"),
                        "decision_basis": r_verdict.get("decision_basis"),
                        "likely_faulty_sensors": r_verdict.get("likely_faulty_sensors", []),
                    },
                    "mode": current_mode,
                    "ingest_time_ms": ingest_time_ms,
                })

                # A spike is confirmed by the following reading. Publish an
                # event at the original timestamp even though the current
                # confirming reading remains normal.
                for spike in r_verdict.get("confirmed_spikes", []):
                    self._anomaly_counter += 1
                    spike_item = {
                        "anomaly_id": f"anom_{self._anomaly_counter:05d}",
                        "timestamp": spike["timestamp"],
                        "station_id": st_id,
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
                        "regime": r_verdict.get("regime"),
                        "network_corroboration": r_verdict.get("network_corroboration"),
                        "model_status": r_verdict.get("model_status"),
                    }
                    self.recent_anomalies.appendleft(spike_item)
                    await self._broadcast_event({
                        "type": "ANOMALY_EVENT",
                        "station_id": st_id,
                        "anomaly": spike_item,
                        "ingest_time_ms": ingest_time_ms,
                    })

                # Broadcast anomaly event if this reading was scored anomalous
                if r_verdict.get("is_anomaly"):
                    affected_parameters = list(dict.fromkeys(
                        r_verdict.get("likely_faulty_sensors", [])
                        or [
                            rule.get("parameter") if isinstance(rule, dict) else rule[1]
                            for rule in r_verdict.get("rules_fired", [])
                        ]
                        or list((r_verdict.get("suggested_values") or {}).keys())
                    ))
                    observed_values = {
                        param: r_raw.get(param)
                        for param in affected_parameters
                        if param in r_raw
                    }
                    self._anomaly_counter += 1
                    anomaly_item = {
                        "anomaly_id": f"anom_{self._anomaly_counter:05d}",
                        "timestamp": r_ts,
                        "station_id": st_id,
                        "anomaly_score_pct": r_verdict.get("anomaly_score_pct", 0.0),
                        "model_confidence_pct": r_verdict.get("model_confidence_pct"),
                        "rule_confidence_pct": r_verdict.get("rule_confidence_pct"),
                        "suggested_values": r_verdict.get("suggested_values"),
                        "observed_values": observed_values,
                        "affected_parameters": affected_parameters,
                        "shap_features": r_verdict.get("shap_features", []),
                        "explanation_method": r_verdict.get("explanation_method"),
                        "suggested_metadata": r_verdict.get("suggested_metadata", {}),
                        "likely_faulty_sensors": r_verdict.get("likely_faulty_sensors", []),
                        "severity": r_verdict.get("severity"),
                        "rules_fired": r_verdict.get("rules_fired", []),
                        "type": r_verdict.get("fault_type") or "statistical_anomaly",
                        "root_cause": ROOT_CAUSE_BY_FAULT_TYPE.get(
                            r_verdict.get("fault_type"),
                            "Unusual reading pattern flagged by model"
                        ),
                        "regime": r_verdict.get("regime"),
                        "network_corroboration": r_verdict.get("network_corroboration"),
                        "model_status": r_verdict.get("model_status"),
                    }
                    self.recent_anomalies.appendleft(anomaly_item)
                    await self._broadcast_event({
                        "type": "ANOMALY_EVENT",
                        "station_id": st_id,
                        "anomaly": anomaly_item,
                        "ingest_time_ms": ingest_time_ms,
                    })

        if current_mode == "replay":
            self._replay_cursor_idx += 1
            if self._replay_cursor_idx >= self._replay_len:
                self._stop_replay()

        self._force_live_ingest = False


async def run_simulation_loop(sim_state: SimulatorState):
    """Replay steps every 2s; live/edge fetch/ingest runs on cadence."""
    next_live_tick = 0.0
    while True:
        tick_start = asyncio.get_running_loop().time()
        try:
            now = tick_start
            if sim_state.mode == "replay":
                await sim_state.tick()
            elif sim_state.mode == "edge":
                # Watchdog check: Auto-exit edge mode if no packets received for >330 seconds
                last_pkt_mono = getattr(sim_state, "_edge_last_packet_monotonic", 0.0)
                if last_pkt_mono > 0.0 and (time.monotonic() - last_pkt_mono) >= EDGE_INACTIVITY_TIMEOUT_SECONDS:
                    print(f"[simulator] ESP32 edge mode inactivity timeout (> {EDGE_INACTIVITY_TIMEOUT_SECONDS}s). Auto-exiting to Live Mode.")
                    sim_state.stop_edge_mode(reason="timeout")
                elif now >= next_live_tick:
                    # In EDGE mode: background live fetching continues to persist unbroken records
                    # for all 20 stations to TimescaleDB/CSV without interrupting active edge testing UI.
                    await sim_state._maybe_refresh_live_cache()
                    batch_bg = []
                    b_now = datetime.now(timezone.utc)
                    for sid in sim_state.metadata["station_id"]:
                        r_reading = sim_state._next_live_row(sid)
                        if r_reading:
                            r_ts = sim_state._live_observed_at.get(sid, b_now)
                            batch_bg.append((sid, r_ts, r_reading, {"is_anomaly": False, "health_status": "HEALTHY"}))
                    if batch_bg:
                        await asyncio.to_thread(sim_state.manager.history.append_batch, batch_bg, source="live")
                    next_live_tick = asyncio.get_running_loop().time() + LIVE_FETCH_INTERVAL_SECONDS
            elif sim_state.mode == "live" and now >= next_live_tick:
                await sim_state.tick()
                if sim_state._live_refresh_requested:
                    next_live_tick = 0.0
                    sim_state._live_refresh_requested = False
                else:
                    next_live_tick = asyncio.get_running_loop().time() + LIVE_FETCH_INTERVAL_SECONDS
        except Exception as e:
            # Preserve the actual file/line in server logs. A one-line error
            # hides whether an upstream record or detector rule failed.
            print(f"[simulator] loop error: {e!r}\n{traceback.format_exc()}")
        
        tick_elapsed = asyncio.get_running_loop().time() - tick_start
        wait_seconds = max(0.05, REPLAY_STEP_SECONDS - tick_elapsed) if sim_state.mode == "replay" else 1.0
        await asyncio.sleep(wait_seconds)


def create_simulator_state(broadcast_callback=None) -> SimulatorState:
    """Called once from main.py's startup event."""
    if not ARTIFACTS_PATH.exists():
        raise FileNotFoundError(f"No trained model at {ARTIFACTS_PATH} -- run model/train.py first.")
    artifact = joblib.load(ARTIFACTS_PATH)
    if "rule_thresholds" not in artifact:
        raise KeyError("Artifact missing 'rule_thresholds' -- retrain with the current train.py.")

    metadata_path = DATA_DIR / "stations_metadata.csv"
    metadata = pd.read_csv(metadata_path)

    return SimulatorState(metadata, artifact, broadcast_callback=broadcast_callback)
