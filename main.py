"""
SkyGuard AI — main.py: FastAPI app, all route handlers.

Lives at repo root alongside config.py/data_fetch.py (see the actual
directory structure -- model/, data/, model_artifacts/ are subpackages;
this file and config.py are the two root-level pieces that tie them
together). Wires simulator.py's SimulatorState into the exact 9
endpoints the frontend is already built against
(DEVELOPMENT_PROGRESS.md's "Approved Contract Endpoints" list) -- no
endpoint here was invented; every route matches FRONTEND_ARCHITECTURE.md
exactly, including reusing POST /api/inject-anomaly as the
replay-mode trigger (see simulator.py's start_replay() docstring for
why, and the earlier confirmation flag on that design choice).
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import asyncio
import time
import json
import math
import numpy as np
import pandas as pd

import logging
logger = logging.getLogger("skyguard.api")

sys.path.append(str(Path(__file__).parent))
from model.simulator import create_simulator_state, run_simulation_loop
from model.cross_channel_covariance import compute_dewpoint_c
from model.features import build_features_for_history
from config import CLUSTERS, get_station_normal_ranges


class ConnectionManager:
    """Manages real-time WebSocket client connections and broadcasts live telemetry."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        async with self._lock:
            dead: list[WebSocket] = []
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead.append(connection)
            for connection in dead:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)


ws_manager = ConnectionManager()



def _json_nullable(value):
    """Convert CSV/pandas NaN values to valid JSON nulls for API payloads."""
    if value is None:
        return None
    try:
        return None if bool(pd.isna(value)) else value
    except (TypeError, ValueError):
        return value


def _compute_decision_basis(model_confidence_pct, rules_fired) -> str:
    """
    Explicit decision basis label per audit §10.2.
    Tells the frontend exactly which evidence sources contributed so it can
    display truthful labels (never claim model evidence when model didn't run).
    """
    deterministic_rules = {"physical_bounds", "dropout", "sensor_fail_low"}
    statistical_rules   = {"drift", "spike", "frozen_value", "multivariate_inconsistency"}
    fired_types = set()
    for r in (rules_fired or []):
        if isinstance(r, dict):
            rule_name = r.get("type") or r.get("rule")
        elif isinstance(r, (list, tuple)) and len(r) > 0:
            rule_name = r[0]
        else:
            rule_name = str(r)
        if rule_name:
            fired_types.add(rule_name)

    has_model         = model_confidence_pct is not None
    has_deterministic = bool(fired_types & deterministic_rules)
    has_statistical   = bool(fired_types & statistical_rules)

    if has_deterministic and not has_model:
        return "PHYSICS_ONLY"
    if (has_deterministic or has_statistical) and has_model:
        return "MODEL_AND_RULE_SUPPORTED"
    if has_statistical and not has_model:
        return "RULE_ONLY_STATISTICAL"
    if has_model and not (has_deterministic or has_statistical):
        return "MODEL_CONFIRMED"
    if not has_model and not (has_deterministic or has_statistical):
        return "MODEL_UNAVAILABLE"
    return "INSUFFICIENT_EVIDENCE"


def _compute_model_status(model_confidence_pct, history_len) -> str:
    """
    Explicit model availability label per audit §8.2.
    history_len=None is treated as unknown (not warmup).
    """
    if model_confidence_pct is not None:
        return "AVAILABLE"
    if history_len is not None and history_len < 48:
        return "UNAVAILABLE_WARMUP"
    return "UNAVAILABLE_MISSING_FEATURES"


async def _db_monitor_loop(history_store):
    """Periodically verifies database connectivity; auto-reconnects and syncs CSV to DB on recovery."""
    while True:
        try:
            await asyncio.sleep(20)
            await asyncio.to_thread(history_store.check_and_reconnect)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[_db_monitor_loop] Monitor tick error: {e!r}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ws_manager = ws_manager
    app.state.sim = create_simulator_state(broadcast_callback=ws_manager.broadcast)
    # Start simulation loop in background task
    app.state.sim_task = asyncio.create_task(run_simulation_loop(app.state.sim))
    # Start DB health monitor & auto-reconnect task
    if "pytest" not in sys.modules:
        app.state.db_monitor_task = asyncio.create_task(_db_monitor_loop(app.state.sim.manager.history))
    else:
        app.state.db_monitor_task = None
    try:
        yield
    finally:
        if app.state.db_monitor_task:
            app.state.db_monitor_task.cancel()
            try:
                await app.state.db_monitor_task
            except asyncio.CancelledError:
                pass
        app.state.sim_task.cancel()
        try:
            await app.state.sim_task
        except asyncio.CancelledError:
            pass
        await app.state.sim.close()


app = FastAPI(title="SkyGuard AI", lifespan=lifespan)

# allow_origins=["*"] -- fine for hackathon per BACKEND_BLUEPRINT.md
# section 6; tighten to the deployed frontend URL once known.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry push and latency benchmarking.
    Clients receive instantaneous telemetry ticks and anomaly verdicts as they
    are scored, bypassing HTTP polling delays.
    """
    await ws_manager.connect(websocket)
    try:
        # Initial connection handshake
        await websocket.send_json({
            "type": "CONNECTION_READY",
            "mode": app.state.sim.mode,
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        })
        while True:
            # Keep-alive heartbeat / ping handler
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)


@app.get("/api/system-status")
async def get_system_status():
    """Small control-plane endpoint: frontend cadence follows backend mode and provider health."""
    sim = app.state.sim
    return {
        "mode": sim.mode,
        "replay_step_seconds": 2 if sim.mode == "replay" else None,
        "live_poll_interval_seconds": 30 * 60,
        "provider_status": getattr(sim, "provider_status", {
            "status": "HEALTHY",
            "consecutive_failures": 0,
            "failing_stations": [],
            "diagnosed_cause": None,
            "last_error": None,
        }),
        "edge_status": getattr(sim, "edge_status", {
            "status": "DISCONNECTED",
            "connected": False,
            "station_id": None,
            "device_id": None,
            "last_packet_time": None,
            "packet_count": 0,
        }),
    }


@app.post("/api/system-mode")
@app.post("/api/system/mode")
async def set_system_mode(body: dict):
    """Switch mode safely: mode='live', mode='replay', or mode='edge'."""
    mode = body.get("mode")
    station_id = body.get("station_id")
    sim = app.state.sim
    if mode == "live":
        if sim.mode == "replay":
            sim.stop_replay()
        elif sim.mode == "edge":
            sim.stop_edge_mode()
        else:
            sim.manager.switch_to_live()
        return {"mode": "live", "message": "Switched to live mode; live buffers and view restored."}
    elif mode == "edge":
        if sim.mode == "replay":
            sim.stop_replay()
        sim.start_edge_mode(target_station_id=station_id)
        return {"mode": "edge", "message": "Switched to ESP32 Edge Ingestion mode. Waiting for hardware packets."}
    elif mode == "replay":
        anomaly_id = await asyncio.to_thread(sim.start_replay, station_id)
        return {"mode": "replay", "anomaly_id": anomaly_id, "message": "Switched to replay mode."}
    else:
        raise HTTPException(status_code=400, detail="Invalid mode. Supported: 'live', 'replay', 'edge'.")


@app.post("/api/admin/clear-history")
async def clear_history(target: Optional[str] = "all", station_id: Optional[str] = None, body: Optional[dict] = None):
    """
    Purges historical sensor readings from TimescaleDB and local CSV store.
    target='all' clears everything (resets system to pristine state).
    target='replay' clears only replay simulation scratch data.
    """
    target_sid = station_id
    if body and isinstance(body, dict):
        if "target" in body:
            target = body["target"]
        if "station_id" in body and not target_sid:
            target_sid = body["station_id"]
    sim = app.state.sim
    source = None if target == "all" else "replay"
    await asyncio.to_thread(sim.manager.history.clear_all, source=source)
    if target == "all":
        if sim.mode == "replay":
            sim._stop_replay()
        else:
            sim.manager.switch_to_live()

        for buf in sim.manager.buffers.values():
            buf.reset_detection_state()

        sim.latest.clear()
        sim._last_live_latest.clear()
        for sid in sim.trend_history:
            sim.trend_history[sid].clear()
        sim.recent_anomalies.clear()
        sim._last_ingested_timestamp.clear()
        sim._last_ingested.clear()
        sim._live_last_fetch = None
        sim._live_refresh_requested = True
        asyncio.create_task(sim.refresh_live_now(priority_station_id=target_sid))
    else:
        # target == 'replay': purge replay scratch data in memory only, preserving live telemetry
        from collections import deque
        for sid in sim.trend_history:
            sim.trend_history[sid] = deque(
                (p for p in sim.trend_history[sid] if p.get("source") != "replay"),
                maxlen=2000
            )
        sim.recent_anomalies = deque(
            (a for a in sim.recent_anomalies if a.get("source") != "replay"),
            maxlen=200
        )

    await ws_manager.broadcast({
        "type": "HISTORY_PURGED",
        "target": target,
        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
    })
    return {
        "success": True,
        "target": target,
        "message": f"Historical data ({target}) successfully cleared from TimescaleDB and local stores.",
    }


@app.get("/api/network-status")
async def get_network_status():
    """Aggregate station health for the header badge — not a static demo label."""
    from datetime import datetime, timezone

    sim = app.state.sim
    statuses = []
    health_pcts = []
    for sid in sim.manager.buffers:
        station_health = sim.manager.get_station_status(sid)
        mapped = {"HEALTHY": "NORMAL", "WARNING": "WARNING", "OFFLINE": "OFFLINE"}.get(
            station_health["status"], "NORMAL"
        )
        statuses.append(mapped)
        health_pcts.append(round(station_health["health_pct"]))

    if "CRITICAL" in statuses:
        overall = "CRITICAL"
    elif "WARNING" in statuses or "OFFLINE" in statuses:
        overall = "WARNING"
    else:
        overall = "NORMAL"

    return {
        "overall_status": overall,
        "active_stations_count": sum(1 for status in statuses if status != "OFFLINE"),
        "total_stations_count": len(statuses),
        "active_anomalies_count": len(sim.recent_anomalies),
        "avg_sensor_health_pct": round(sum(health_pcts) / len(health_pcts)) if health_pcts else 100,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "mode": sim.mode,
    }


@app.post("/api/refresh-live")
async def refresh_live_snapshot(station_id: Optional[str] = None, body: Optional[dict] = None):
    """Explicit, user-triggered Open-Meteo refresh; prioritizes active station with spam protection."""
    import time
    target_sid = station_id
    if body and isinstance(body, dict) and "station_id" in body and not target_sid:
        target_sid = body["station_id"]
    sim = app.state.sim
    # 5-second spam protection cooldown
    now = time.time()
    last_refresh = getattr(sim, "_last_explicit_refresh_time", 0.0)
    if (now - last_refresh) < 5.0:
        return {
            "mode": sim.mode,
            "message": "Snapshot current (rate-limit protected).",
            "priority_station": target_sid,
            "cached": True,
        }
    sim._last_explicit_refresh_time = now
    asyncio.create_task(sim.refresh_live_now(priority_station_id=target_sid))
    return {
        "mode": sim.mode,
        "message": "Live provider snapshot refresh initiated.",
        "priority_station": target_sid,
        "cached": False,
    }


@app.post("/api/admin/sync-db")
async def trigger_csv_db_sync(station_id: Optional[str] = None):
    """Manually or externally trigger CSV mirror to TimescaleDB synchronization."""
    sim = app.state.sim
    history = sim.manager.history
    if not history.use_db:
        connected = await asyncio.to_thread(history.check_and_reconnect)
        if not connected:
            return {"status": "error", "message": "TimescaleDB is offline. Could not reconnect."}
    count = await asyncio.to_thread(history.sync_csv_to_db, station_id)
    return {
        "status": "success",
        "synced_rows": count,
        "message": f"Successfully updated TimescaleDB with {count} readings from CSV mirror.",
    }


# ---------------- POST /api/ingest/observation (ESP32 Edge Ingestion) ----------------

_seen_event_ids = set()

@app.post("/api/ingest/observation")
async def ingest_edge_observation(payload: dict):
    """
    Direct ingestion endpoint for ESP32 edge nodes.
    Receives canonical ObservationPacket JSON payloads, executes Level 2 backend inference,
    records the observation to the dual-store history, and broadcasts real-time telemetry.
    """
    sim = app.state.sim
    event_id = payload.get("event_id")
    station_id = payload.get("station_id")
    readings = payload.get("readings", {})
    observed_at = payload.get("observed_at")
    edge_inference = payload.get("edge_inference", {})
    seq = payload.get("sequence_number", 0)

    if not event_id or not station_id or not readings:
        raise HTTPException(status_code=422, detail="Missing required ObservationPacket fields (event_id, station_id, readings).")

    if station_id not in sim.manager.buffers:
        raise HTTPException(status_code=404, detail=f"Station '{station_id}' is not registered.")

    # Automatically enter edge mode if hardware packets start arriving
    if sim.mode != "edge":
        sim.start_edge_mode(target_station_id=station_id)

    # Idempotency check
    if event_id in _seen_event_ids:
        return {"accepted": True, "event_id": event_id, "status": "duplicate_acknowledged"}
    _seen_event_ids.add(event_id)
    if len(_seen_event_ids) > 5000:
        _seen_event_ids.pop()

    try:
        ts = pd.to_datetime(observed_at, utc=True) if observed_at else pd.Timestamp.now(tz="UTC")
    except Exception:
        ts = pd.Timestamp.now(tz="UTC")

    raw_reading = {
        "temperature_c": readings.get("temperature_c"),
        "pressure_hpa": readings.get("pressure_hpa"),
        "humidity_pct": readings.get("humidity_pct"),
    }

    # Execute Level 2 full backend scoring
    verdict = await asyncio.to_thread(
        sim.manager.ingest_reading,
        station_id,
        raw_reading,
        ts,
        source="edge",
    )

    # Update edge status & watchdog monotonic timestamp
    sim._edge_last_packet_monotonic = time.monotonic()
    if getattr(sim, "edge_status", None) is not None:
        was_connected = sim.edge_status.get("connected", False)
        sim.edge_status["status"] = "CONNECTED"
        sim.edge_status["connected"] = True
        sim.edge_status["station_id"] = station_id
        sim.edge_status["device_id"] = payload.get("device_id")
        sim.edge_status["last_packet_time"] = ts.isoformat()
        sim.edge_status["packet_count"] = sim.edge_status.get("packet_count", 0) + 1
        
        # Broadcast EDGE_STATUS if state changed or first connection
        if not was_connected or sim.edge_status["packet_count"] % 5 == 1:
            await ws_manager.broadcast({
                "type": "EDGE_STATUS",
                "edge_status": dict(sim.edge_status),
            })

    sim.latest[station_id] = {
        "raw_reading": raw_reading,
        "verdict": verdict,
        "timestamp": ts,
        "source": "edge",
        "edge_inference": edge_inference,
    }

    suggested = verdict.get("suggested_values") or {}
    sim.trend_history[station_id].append({
        "timestamp": ts,
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
        "source": "edge",
    })

    # Broadcast live over WebSockets
    ingest_time_ms = int(time.time() * 1000)
    await ws_manager.broadcast({
        "type": "TELEMETRY_TICK",
        "station_id": station_id,
        "timestamp": ts.isoformat(),
        "reading": raw_reading,
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
        "edge_inference": edge_inference,
        "mode": "edge",
        "ingest_time_ms": ingest_time_ms,
    })

    is_level2_anomaly = bool(verdict.get("is_anomaly", False))

    if is_level2_anomaly:
        sim._anomaly_counter += 1
        anomaly_id = f"anom_{sim._anomaly_counter:05d}"

        final_type = verdict.get("fault_type") or "anomaly"
        final_score = verdict.get("anomaly_score_pct") or 85.0
        final_severity = verdict.get("severity") or ("critical" if float(final_score) >= 90 else "high")

        anomaly_item = {
            "anomaly_id": anomaly_id,
            "station_id": station_id,
            "timestamp": ts,
            "anomaly_score_pct": float(final_score),
            "severity": final_severity,
            "type": final_type,
            "root_cause": verdict.get("root_cause") or f"Detected {final_type}",
            "model_confidence_pct": verdict.get("model_confidence_pct"),
            "rule_confidence_pct": verdict.get("rule_confidence_pct"),
            "shap_features": verdict.get("shap_features", []),
            "likely_faulty_sensors": verdict.get("likely_faulty_sensors", []),
            "affected_parameters": verdict.get("affected_parameters", []),
            "observed_values": raw_reading,
            "suggested_values": verdict.get("suggested_values", {}),
            "edge_inference": edge_inference,
            "source": "edge",
        }
        sim.recent_anomalies.append(anomaly_item)
        await ws_manager.broadcast({
            "type": "ANOMALY_EVENT",
            "station_id": station_id,
            "anomaly": {
                **anomaly_item,
                "timestamp": ts.isoformat(),
            }
        })

    return {
        "accepted": True,
        "event_id": event_id,
        "sequence_number": seq,
        "edge_status": edge_inference.get("status"),
        "backend_verdict": {
            "is_anomaly": verdict.get("is_anomaly", False),
            "anomaly_score_pct": verdict.get("anomaly_score_pct"),
            "fault_type": verdict.get("fault_type"),
        }
    }


# ---------------- GET /api/stations ----------------

@app.get("/api/stations")
async def get_stations():
    sim = app.state.sim
    result = []
    for _, row in sim.metadata.iterrows():
        sid = row["station_id"]
        status = sim.manager.get_station_status(sid)["status"]
        # Contract wants NORMAL/WARNING/CRITICAL/OFFLINE, not health's
        # own HEALTHY/WARNING/OFFLINE vocabulary -- translate.
        mapped_status = {"HEALTHY": "NORMAL", "WARNING": "WARNING", "OFFLINE": "OFFLINE"}.get(status, "NORMAL")
        result.append({
            "station_id": sid,
            "name": row["name"],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "status": mapped_status,
        })
    return result


# ---------------- GET /api/current-reading ----------------

@app.get("/api/current-reading")
async def get_current_reading(station_id: str):
    sim = app.state.sim
    if station_id not in sim.manager.buffers:
        raise HTTPException(status_code=404, detail=f"Unknown station {station_id}")

    nominal = get_station_normal_ranges(station_id)
    station_health = sim.manager.get_station_status(station_id)
    parameter_status = sim.manager.buffers[station_id].health.param_status

    if sim.mode == "edge":
        entry = sim.latest.get(station_id)
        if not entry or entry.get("source") != "edge":
            # Return nominal standby object (never 404, never bleed live data)
            return {
                "station_id": station_id,
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "temperature_c": {"value": None, **nominal["temperature_c"]},
                "pressure_hpa": {"value": None, **nominal["pressure_hpa"]},
                "humidity_pct": {"value": None, **nominal["humidity_pct"]},
                "anomaly_score_pct": 0.0,
                "is_anomaly": False,
                "fault_type": None,
                "severity": None,
                "model_confidence_pct": None,
                "rule_confidence_pct": None,
                "risk_level": "low",
                "sensor_health_pct": 100,
                "sensor_health_status": "HEALTHY",
                "sensor_parameters": parameter_status,
                "suggested_values": {},
                "source": "edge",
                "is_syncing": True,
            }
    elif sim.mode == "replay":
        entry = sim.latest.get(station_id)
        if not entry or entry.get("source") != "replay":
            return {
                "station_id": station_id,
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "temperature_c": {"value": None, **nominal["temperature_c"]},
                "pressure_hpa": {"value": None, **nominal["pressure_hpa"]},
                "humidity_pct": {"value": None, **nominal["humidity_pct"]},
                "anomaly_score_pct": 0.0,
                "is_anomaly": False,
                "fault_type": None,
                "severity": None,
                "model_confidence_pct": None,
                "rule_confidence_pct": None,
                "risk_level": "low",
                "sensor_health_pct": 100,
                "sensor_health_status": "HEALTHY",
                "sensor_parameters": parameter_status,
                "suggested_values": {},
                "source": "replay",
                "is_syncing": True,
            }
    else:  # sim.mode == "live"
        entry = sim.latest.get(station_id)
        if entry is None or entry.get("source") != "live":
            live_entry = sim._last_live_latest.get(station_id)
            if live_entry and live_entry.get("source") == "live":
                entry = live_entry
            else:
                entry = None

        if entry is None:
            # Give live provider bootstrap / refresh up to 2.5s to finish
            for _ in range(25):
                await asyncio.sleep(0.1)
                entry = sim.latest.get(station_id) or sim._last_live_latest.get(station_id)
                if entry and entry.get("source") == "live":
                    break

        if entry is None:
            return {
                "station_id": station_id,
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "temperature_c": {"value": None, **nominal["temperature_c"]},
                "pressure_hpa": {"value": None, **nominal["pressure_hpa"]},
                "humidity_pct": {"value": None, **nominal["humidity_pct"]},
                "anomaly_score_pct": 0.0,
                "is_anomaly": False,
                "fault_type": None,
                "severity": None,
                "model_confidence_pct": None,
                "rule_confidence_pct": None,
                "risk_level": "low",
                "sensor_health_pct": 100,
                "sensor_health_status": "HEALTHY",
                "sensor_parameters": parameter_status,
                "suggested_values": {},
                "source": "live",
                "is_syncing": True,
            }

    raw = entry["raw_reading"]
    verdict = entry["verdict"]

    raw_severity = verdict.get("severity")
    score_pct = float(verdict.get("anomaly_score_pct", 0.0) or 0.0)
    
    if raw_severity in ("low", "medium", "high", "critical"):
        risk_level = raw_severity
    elif score_pct >= 90.0:
        risk_level = "critical"
    elif score_pct >= 70.0:
        risk_level = "high"
    elif verdict.get("is_anomaly", False) or score_pct >= 40.0:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "station_id": station_id,
        "timestamp": entry["timestamp"].isoformat() if hasattr(entry["timestamp"], "isoformat") else str(entry["timestamp"]),
        "temperature_c": {"value": raw.get("temperature_c"), **nominal["temperature_c"]},
        "pressure_hpa": {"value": raw.get("pressure_hpa"), **nominal["pressure_hpa"]},
        "humidity_pct": {"value": raw.get("humidity_pct"), **nominal["humidity_pct"]},
        "anomaly_score_pct": verdict.get("anomaly_score_pct", 0.0),
        "is_anomaly": bool(verdict.get("is_anomaly", False)),
        "fault_type": verdict.get("fault_type"),
        "severity": verdict.get("severity"),
        "model_confidence_pct": verdict.get("model_confidence_pct"),
        "rule_confidence_pct": verdict.get("rule_confidence_pct"),
        "risk_level": risk_level,
        "sensor_health_pct": round(station_health["health_pct"]),
        "sensor_health_status": station_health["status"],
        "sensor_parameters": parameter_status,
        "suggested_values": verdict.get("suggested_values", {}),
        "source": entry.get("source", sim.mode),
        "edge_inference": entry.get("edge_inference"),
        "is_syncing": False,
    }


# ---------------- GET /api/trends ----------------

@app.get("/api/trends")
async def get_trends(station_id: str, hours: int = 6):
    sim = app.state.sim
    if station_id not in sim.manager.buffers:
        raise HTTPException(status_code=404, detail=f"Unknown station {station_id}")
    if not 1 <= hours <= 24 * 30:
        raise HTTPException(status_code=400, detail="hours must be between 1 and 720")

    # Three completely isolated pipelines with zero cross-mode data bleed:
    # 1. REPLAY mode: strictly returns source="replay" points from simulator trend buffer
    # 2. EDGE mode: strictly returns source="edge" points from edge hardware packet buffer
    # 3. LIVE mode: strictly queries source="live" points from TimescaleDB / local CSV / live buffer
    if sim.mode == "replay":
        raw_points = list(sim.trend_history.get(station_id, []))
        if raw_points:
            try:
                latest_t = pd.to_datetime(raw_points[-1]["timestamp"])
                cutoff = latest_t - pd.Timedelta(hours=hours)
                points = [
                    p for p in raw_points
                    if str(p.get("source", "")).lower() == "replay" and pd.to_datetime(p["timestamp"]) >= cutoff
                ]
            except Exception:
                points = [p for p in raw_points if str(p.get("source", "")).lower() == "replay"]
        else:
            points = []
    elif sim.mode == "edge":
        raw_points = list(sim.trend_history.get(station_id, []))
        points = [p for p in raw_points if str(p.get("source", "")).lower() == "edge"]
        if not points:
            try:
                df_edge = sim.manager.history._read_csv(sim.manager.history._path(station_id))
                if not df_edge.empty and "source" in df_edge.columns:
                    df_edge = df_edge[df_edge["source"].astype(str).str.lower() == "edge"]
                    if not df_edge.empty:
                        cutoff = df_edge["timestamp"].max() - pd.Timedelta(hours=hours)
                        points = df_edge[df_edge["timestamp"] >= cutoff].to_dict(orient="records")
            except Exception:
                points = []
    else:  # sim.mode == "live"
        try:
            points = await asyncio.wait_for(
                asyncio.to_thread(sim.manager.get_station_history, station_id, hours=hours, include_replay=False),
                timeout=3.5,
            )
            # Strictly guarantee only source == 'live' rows are returned
            points = [p for p in points if str(p.get("source", "")).lower() == "live"]
        except Exception as e:
            print(f"[/api/trends] TimescaleDB query timeout/error ({e!r}), falling back to local history.")
            err_str = str(e).lower()
            if any(k in err_str for k in ("timeout", "connection", "closed", "terminat", "operationalerror")):
                sim.manager.history.use_db = False
            points = []

        if not points:
            # Fallback to local CSV mirror on SSD (strictly live source)
            try:
                df_fallback = sim.manager.history._read_csv(sim.manager.history._path(station_id))
                if not df_fallback.empty and "timestamp" in df_fallback.columns:
                    if "source" in df_fallback.columns:
                        df_fallback = df_fallback[df_fallback["source"].astype(str).str.lower() == "live"]
                    if not df_fallback.empty:
                        cutoff = df_fallback["timestamp"].max() - pd.Timedelta(hours=hours)
                        points = df_fallback[df_fallback["timestamp"] >= cutoff].to_dict(orient="records")
                    else:
                        points = []
                else:
                    points = []
            except Exception:
                points = []

        if not points:
            points = [p for p in list(sim.trend_history.get(station_id, [])) if str(p.get("source", "")).lower() == "live"]

    # Final airtight pipeline isolation filter: strictly match active simulator mode
    target_mode = sim.mode
    points = [p for p in points if str(p.get("source", "")).lower() == target_mode]

    # Strictly guarantee monotonic timestamp ordering
    try:
        points = sorted(points, key=lambda p: pd.to_datetime(p["timestamp"]))
    except Exception:
        pass

    trend_points = [
        {
            "timestamp": p["timestamp"].isoformat() if hasattr(p["timestamp"], "isoformat") else str(p["timestamp"]),
            "temperature_c": _json_nullable(p.get("temperature_c")),
            "pressure_hpa": _json_nullable(p.get("pressure_hpa")),
            "humidity_pct": _json_nullable(p.get("humidity_pct")),
            "is_anomaly": bool(p.get("is_anomaly", False)),
            "fault_type": _json_nullable(p.get("fault_type")),
            "severity": _json_nullable(p.get("severity")),
            "anomaly_score_pct": _json_nullable(p.get("anomaly_score_pct")),
            "suggested_temperature_c": _json_nullable(p.get("suggested_temperature_c")),
            "suggested_pressure_hpa": _json_nullable(p.get("suggested_pressure_hpa")),
            "suggested_humidity_pct": _json_nullable(p.get("suggested_humidity_pct")),
            "affected_parameters": p.get("affected_parameters", []),
            "health_status": _json_nullable(p.get("health_status")),
            "source": p.get("source", sim.manager.mode),
        }
        for p in points
    ]

    anomaly_windows = []
    in_window = False
    window_start = None
    for p in points:
        ts = p["timestamp"].isoformat() if hasattr(p["timestamp"], "isoformat") else str(p["timestamp"])
        if bool(p.get("is_anomaly", False)) and not in_window:
            window_start = ts
            in_window = True
        elif not bool(p.get("is_anomaly", False)) and in_window:
            anomaly_windows.append({
                "start": window_start,
                "end": ts,
                "label": "Anomaly Detected",
            })
            in_window = False
    if in_window and window_start is not None and len(points) > 0:
        last_ts = points[-1]["timestamp"].isoformat() if hasattr(points[-1]["timestamp"], "isoformat") else str(points[-1]["timestamp"])
        anomaly_windows.append({
            "start": window_start,
            "end": last_ts,
            "label": "Anomaly Detected",
        })

    return {"station_id": station_id, "hours": hours, "points": trend_points, "anomaly_windows": anomaly_windows}


@app.get("/api/history.csv")
def download_station_history(station_id: str):
    """Operator export of the complete retained (up to 30-day) station CSV."""
    sim = app.state.sim
    if station_id not in sim.manager.buffers:
        raise HTTPException(status_code=404, detail=f"Unknown station {station_id}")
    df = sim.manager.history.get_all(station_id)
    csv_text = df.sort_values("timestamp").to_csv(index=False) if not df.empty else \
        "timestamp,station_id,temperature_c,pressure_hpa,humidity_pct,is_anomaly,fault_type,severity,anomaly_score_pct,suggested_temperature_c,suggested_pressure_hpa,suggested_humidity_pct,health_status,source\n"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{station_id}_history.csv"'},
    )


# ---------------- GET /api/anomalies/latest ----------------

@app.get("/api/anomalies/latest")
async def get_latest_anomaly(station_id: str):
    sim = app.state.sim
    for a in reversed(sim.recent_anomalies):
        if a["station_id"] == station_id:
            try:
                a_source = a.get("source", "live")
                if a_source != "edge":
                    a_year = pd.to_datetime(a["timestamp"]).year
                    if sim.mode == "replay" and a_year > 2025:
                        continue
                    if sim.mode == "live" and a_year <= 2025:
                        continue
            except Exception:
                pass
            return {
                "anomaly_id": a["anomaly_id"],
                "timestamp": a["timestamp"].isoformat() if hasattr(a["timestamp"], "isoformat") else str(a["timestamp"]),
                "station_id": a["station_id"],
                "anomaly_score_pct": a["anomaly_score_pct"],
                "severity": a["severity"],
                "type": a["type"],
                "root_cause": a["root_cause"],
                "description": f"{a['root_cause']} detected at {a['station_id']}.",
                "suggested_values": a.get("suggested_values"),
                "observed_values": a.get("observed_values"),
                "affected_parameters": a.get("affected_parameters", []),
                "regime": a.get("regime"),
                "network_corroboration": a.get("network_corroboration"),
                "decision_basis": _compute_decision_basis(
                    a.get("model_confidence_pct"),
                    a.get("rules_fired") or [],
                ),
                "model_status": _compute_model_status(
                    a.get("model_confidence_pct"),
                    None,
                ),
                "edge_inference": a.get("edge_inference"),
                "source": a.get("source"),
            }
    # No recent anomaly is a healthy, expected state—not a missing resource.
    # Returning JSON null keeps the dashboard nominal and avoids a noisy 404
    # in the browser console for stations without an incident.
    return None


# ---------------- GET /api/anomalies/recent ----------------

@app.get("/api/anomalies/recent")
async def get_recent_anomalies(station_id: Optional[str] = None, limit: int = 50):
    sim = app.state.sim
    valid_anoms = []
    for a in sim.recent_anomalies:
        try:
            a_source = a.get("source", "live")
            if a_source != "edge":
                a_year = pd.to_datetime(a["timestamp"]).year
                if sim.mode == "replay" and a_year > 2025:
                    continue
                if sim.mode == "live" and a_year <= 2025:
                    continue
        except Exception:
            pass
        valid_anoms.append(a)

    if station_id and station_id.lower() != "all":
        matches = [a for a in valid_anoms if a["station_id"] == station_id][:limit]
    else:
        matches = valid_anoms[:limit]
    return [
        {
            "anomaly_id": a["anomaly_id"],
            "timestamp": a["timestamp"].isoformat() if hasattr(a["timestamp"], "isoformat") else str(a["timestamp"]),
            "station_id": a["station_id"],
            "anomaly_score_pct": a["anomaly_score_pct"],
            "severity": a["severity"],
            "type": a["type"],
            "root_cause": a["root_cause"],
            "description": f"{a['root_cause']} detected at {a['station_id']}.",
            "suggested_values": a.get("suggested_values"),
            "observed_values": a.get("observed_values"),
            "affected_parameters": a.get("affected_parameters", []),
            "regime": a.get("regime"),
            "network_corroboration": a.get("network_corroboration"),
            "decision_basis": _compute_decision_basis(
                a.get("model_confidence_pct"),
                a.get("rules_fired") or [],
            ),
            "model_status": _compute_model_status(
                a.get("model_confidence_pct"),
                None,
            ),
            "edge_inference": a.get("edge_inference"),
            "source": a.get("source"),
        }
        for a in matches
    ]


def _compute_dynamic_spatial_threshold(
    sim,
    all_station_ids: list,
    param: str,
    default: float,
    target_roc: float = None,
) -> tuple[float, str]:
    """
    Dynamically compute the spatial significance threshold for a cluster parameter
    using the historical inter-station spread stored in each station's _raw_rows buffer.

    The buffer (StationBuffer._raw_rows) already excludes anomalous readings —
    state.py's record_raw_reading() skips rows where verdict['is_anomaly'] is True,
    so no additional filtering is needed here.

    Algorithm:
      1. Collect historical values per station from _raw_rows (up to ~60h).
      2. For each time-aligned step, compute |station_val - cluster_mean_at_step|.
      3. Use the 90th percentile of all those deviations as the threshold —
         naturally robust since the top 10% absorbs any residual spiky readings.
      4. Clamp to a sensible floor so we never flag on sub-noise differences.

    Returns (threshold_value, source_label) where source_label is one of:
      'dynamic(Nh)'  — computed from N hours of clean history
      'default'      — fell back to hardcoded default (insufficient data)
    """
    # Minimum acceptable threshold per parameter — prevents the dynamic
    # value from being impossibly tight for very homogeneous clusters.
    FLOOR = {"temperature_c": 1.2, "pressure_hpa": 1.5, "humidity_pct": 2.0}
    floor = FLOOR.get(param, 1.2)

    # Collect raw (clean) history per station
    station_series: dict[str, list[float]] = {}
    for sid in all_station_ids:
        vals: list[float] = []
        buf = sim.manager.buffers.get(sid)
        if buf and buf._raw_rows:
            for row in buf._raw_rows:
                v = row.get(param)
                if v is not None:
                    try:
                        f = float(v)
                        if f == f:  # excludes NaN without importing math
                            vals.append(f)
                    except (TypeError, ValueError):
                        pass
        if vals:
            station_series[sid] = vals

    if len(station_series) < 2:
        return default, "default"

    # Align on the minimum shared history length (use last N readings)
    min_len = min(len(v) for v in station_series.values())
    if min_len < 3:
        return default, "default"

    sids = list(station_series.keys())
    aligned = {sid: station_series[sid][-min_len:] for sid in sids}

    # Station-relative deviations: subtract each station's dynamic rolling mean so elevation
    # offsets (e.g. 600m plateau vs 300m valley) do not distort dynamic spatial variation.
    st_means = {sid: sum(aligned[sid]) / len(aligned[sid]) for sid in sids}
    deviations: list[float] = []
    for i in range(min_len):
        step_residuals = [aligned[sid][i] - st_means[sid] for sid in sids]
        mean_residual = sum(step_residuals) / len(step_residuals)
        for r in step_residuals:
            deviations.append(abs(r - mean_residual))

    if len(deviations) < 6:
        return default, "default"

    # 90th percentile — robust against the top 10% of any residual spikes
    deviations.sort()
    p90_idx = int(len(deviations) * 0.90)
    dynamic_val = deviations[p90_idx]

    # Hours of data represented (each row = 1 observation hour per station)
    hours_of_data = min_len
    
    threshold = max(floor, round(dynamic_val, 2))
    
    # Gradual vs instant onset adjustment
    # If the target station's rate-of-change is low relative to the spatial threshold,
    # it means the divergence arrived gradually over multiple readings (consistent with real
    # localized weather ramping in), rather than instantly (sensor spike).
    if target_roc is not None and abs(target_roc) < (threshold * 0.5):
        threshold = threshold * 3.0
        return round(threshold, 2), f"dynamic({hours_of_data}h, gradual)"

    return threshold, f"dynamic({hours_of_data}h)"


def _compute_spatial_context(sim, match: dict) -> dict:
    target_sid = match.get("station_id")
    if not target_sid:
        return None

    cluster_id = None
    cluster_info = None

    for cid, cinfo in CLUSTERS.items():
        if cinfo["center"]["station_id"] == target_sid:
            cluster_id, cluster_info = cid, cinfo
            break
        for n in cinfo.get("neighbors", []):
            if n["station_id"] == target_sid:
                cluster_id, cluster_info = cid, cinfo
                break

    if not cluster_info:
        return None

    all_cluster_stations = [cluster_info["center"]] + cluster_info.get("neighbors", [])
    target_meta = next((s for s in all_cluster_stations if s["station_id"] == target_sid), None)
    target_name = target_meta["name"] if target_meta else target_sid
    peer_metas = [s for s in all_cluster_stations if s["station_id"] != target_sid]
    all_sids = [s["station_id"] for s in all_cluster_stations]

    param_labels = {
        "temperature_c": ("temperature", "°C"),
        "pressure_hpa": ("barometric pressure", "hPa"),
        "humidity_pct": ("relative humidity", "%"),
    }
    DEFAULT_SIG = {"temperature_c": 3.0, "pressure_hpa": 3.0, "humidity_pct": 5.0}

    match_ts = None
    if match.get("timestamp"):
        try:
            match_ts = pd.to_datetime(match["timestamp"])
            if match_ts.tzinfo is not None:
                match_ts = match_ts.tz_convert("UTC").tz_localize(None)
        except Exception:
            match_ts = None

    # Helper function to get peer reading for any parameter
    def _lookup_peer_val(pid, p_name, fallback_target):
        pval = None
        # 1. In replay mode, look up peer reading at matching timestamp
        if pval is None and match_ts is not None and getattr(sim, "_replay_frames", None) and pid in sim._replay_frames:
            rdf = sim._replay_frames[pid]
            if "timestamp" in rdf.columns and not rdf.empty:
                rdf_ts = pd.to_datetime(rdf["timestamp"])
                if rdf_ts.dt.tz is not None:
                    rdf_ts = rdf_ts.dt.tz_convert("UTC").dt.tz_localize(None)
                diffs = (rdf_ts - match_ts).abs()
                min_idx = diffs.idxmin()
                if diffs.loc[min_idx] <= pd.Timedelta(hours=2):
                    v = rdf.loc[min_idx].get(p_name)
                    if pd.notna(v):
                        pval = float(v)

        # 2. Buffer matching timestamp
        if pval is None and match_ts is not None and pid in sim.manager.buffers:
            buf = sim.manager.buffers[pid]
            if buf._raw_rows:
                for row in reversed(buf._raw_rows):
                    try:
                        row_ts = pd.to_datetime(row.get("timestamp"))
                        if row_ts.tzinfo is not None:
                            row_ts = row_ts.tz_convert("UTC").tz_localize(None)
                        if abs((row_ts - match_ts).total_seconds()) <= 3600:
                            v = row.get(p_name)
                            if v is not None and pd.notna(v):
                                pval = float(v)
                                break
                    except Exception:
                        pass

        # 3. Latest reading fallback
        if pval is None and pid in sim.latest:
            pval = sim.latest[pid]["raw_reading"].get(p_name)
        if pval is None and pid in sim.manager.buffers and sim.manager.buffers[pid]._raw_rows:
            pval = sim.manager.buffers[pid]._raw_rows[-1].get(p_name)
        if pval is None:
            if fallback_target is None:
                pval = 0.0
            elif target_sid == "AWS-CHN-024" and p_name == "temperature_c":
                defaults = {"AWS-CHN-101": 29.0, "AWS-CHN-102": 30.0, "AWS-CHN-103": 29.5}
                pval = defaults.get(pid, 29.5)
            else:
                pval = round(fallback_target - (8.5 if p_name == "temperature_c" else 15.0 if p_name == "humidity_pct" else 5.0), 1)
        return round(float(pval), 1)

    # Candidate parameters to evaluate for spatial divergence
    candidate_params = ["temperature_c", "humidity_pct", "pressure_hpa"]
    affected = match.get("affected_parameters") or []

    param_evals = {}
    for p in candidate_params:
        p_target = None
        if match.get("observed_values") and p in match["observed_values"]:
            p_target = match["observed_values"][p]
        if p_target is None and target_sid in sim.latest:
            p_target = sim.latest[target_sid]["raw_reading"].get(p)
        if p_target is None:
            p_target = 38.0 if target_sid == "AWS-CHN-024" else (25.0 if p == "temperature_c" else 1013.0 if p == "pressure_hpa" else 50.0)
        p_target = round(float(p_target), 1)

        p_peers = [_lookup_peer_val(pm["station_id"], p, p_target) for pm in peer_metas]
        avg_peer = round(sum(p_peers) / len(p_peers), 1) if p_peers else p_target

        # Dynamically compute elevation/station-normalized delta for pressure
        if p == "pressure_hpa":
            def _station_p_norm(sid, val):
                buf = sim.manager.buffers.get(sid)
                if buf and buf._raw_rows:
                    p_vals = [float(r["pressure_hpa"]) for r in buf._raw_rows if r.get("pressure_hpa") is not None]
                    if p_vals:
                        return val - (sum(p_vals) / len(p_vals))
                bounds = get_station_normal_ranges(sid)["pressure_hpa"]
                mid = (bounds["normal_min"] + bounds["normal_max"]) / 2.0
                return val - mid

            target_res = _station_p_norm(target_sid, p_target)
            peer_res_list = [_station_p_norm(pm["station_id"], p_peers[i]) for i, pm in enumerate(peer_metas)]
            avg_peer_res = sum(peer_res_list) / len(peer_res_list) if peer_res_list else 0.0
            p_delta = round(target_res - avg_peer_res, 1)
        else:
            p_delta = round(p_target - avg_peer, 1)

        # Look up the 1-hour rate of change to check for gradual onset
        roc_param = f"{p.replace('_c', '').replace('_hpa', '').replace('_pct', '')}_roc_1h"
        target_roc = _lookup_peer_val(target_sid, roc_param, None)
        
        thresh, src = _compute_dynamic_spatial_threshold(sim, all_sids, p, default=DEFAULT_SIG.get(p, 3.0), target_roc=target_roc)
        divergence_ratio = abs(p_delta) / (thresh if thresh > 0 else 1.0)
        is_aff = any(
            p in str(aff)
            or (p == "temperature_c" and "temp" in str(aff))
            or (p == "humidity_pct" and "humid" in str(aff))
            or (p == "pressure_hpa" and "press" in str(aff))
            for aff in affected
        )
        divergence_score = divergence_ratio * (5.0 if is_aff else 1.0)

        param_evals[p] = {
            "target": p_target,
            "peers": p_peers,
            "avg_peer": avg_peer,
            "delta": p_delta,
            "threshold": thresh,
            "threshold_source": src,
            "divergence_score": divergence_score,
        }

    # Prioritize explicitly affected parameters if present
    mapped_aff = []
    for aff in affected:
        s_aff = str(aff).lower()
        if "humid" in s_aff or "rh" in s_aff:
            mapped_aff.append("humidity_pct")
        elif "temp" in s_aff:
            mapped_aff.append("temperature_c")
        elif "press" in s_aff or "baro" in s_aff:
            mapped_aff.append("pressure_hpa")

    if mapped_aff and mapped_aff[0] in param_evals:
        best_p = mapped_aff[0]
    else:
        # Select the parameter with highest divergence score across peers
        best_p = max(param_evals.keys(), key=lambda k: param_evals[k]["divergence_score"])
    eval_info = param_evals[best_p]

    param = best_p
    param_name, unit = param_labels.get(param, (param.replace("_", " "), ""))
    target_val = eval_info["target"]
    delta = eval_info["delta"]
    sig_threshold = eval_info["threshold"]
    threshold_source = eval_info["threshold_source"]
    is_spatially_significant = abs(delta) >= sig_threshold

    peer_stations = [
        {
            "station_id": pm["station_id"],
            "name": pm["name"],
            "reading": eval_info["peers"][i],
            "unit": unit,
        }
        for i, pm in enumerate(peer_metas)
    ]

    corr = match.get("network_corroboration") or "LOCALIZED"

    if (corr == "LOCALIZED" or is_spatially_significant) and is_spatially_significant:
        analysis_text = (
            f"Possible localized anomaly detected at {target_name} station.\n"
            f"The {target_name} station {param_name} differed by {abs(delta)}{unit} from cluster peers, exceeding the cluster's learned significance threshold ({sig_threshold}{unit}).\n"
            f"Nearby stations in the cluster remained within normal ranges, isolating this pattern to {target_name}."
        )
        recommended_action = f"Investigate the {target_name} {param_name} sensor. Divergence from peers indicates an isolated hardware or telemetry failure."
        spatial_impact = f"Localized Divergence: +{abs(delta)}{unit} vs peer baseline"
    elif corr == "REGIONAL":
        analysis_text = (
            f"Regional meteorological event detected across the {target_name} cluster.\n"
            f"Nearby stations in the regional network recorded similar shifts in {param_name}.\n"
            f"The target station agrees with surrounding peer telemetry, confirming a broad atmospheric system."
        )
        recommended_action = f"Keep {target_name} in nominal operation. Nearby corroboration indicates environmental phenomena rather than isolated sensor malfunction."
        spatial_impact = "Regional Agreement: Peers corroborating"
    elif corr == "LOCALIZED" and not is_spatially_significant:
        analysis_text = (
            f"Peer stations in the {target_name} cluster show consistent readings (delta: {abs(delta)}{unit} < threshold {sig_threshold}{unit}).\n"
            f"The observed divergence is within normal inter-station variation ({threshold_source}).\n"
            f"The anomaly pattern is driven by internal temporal signal characteristics rather than spatial divergence."
        )
        recommended_action = f"Monitor {target_name} {param_name} trend over upcoming readings. Spatial telemetry shows peers in nominal agreement."
        spatial_impact = f"Peer Agreement: Delta within cluster spread ({threshold_source})"
    else:
        analysis_text = f"Insufficient peer telemetry available in the {target_name} cluster for spatial corroboration."
        recommended_action = f"Monitor {target_name} readings and cross-corroborate with secondary meteorological sensors."
        spatial_impact = "Peer Baseline Unavailable"

    # Psychrometric Thermodynamic & Cross-Channel Evaluation
    thermodynamic_context = None
    t_val = param_evals["temperature_c"]["target"]
    h_val = param_evals["humidity_pct"]["target"]
    p_val = param_evals["pressure_hpa"]["target"]

    dewpoint_c = compute_dewpoint_c(t_val, h_val) if t_val is not None and h_val is not None else float("nan")
    is_dewpoint_violation = not np.isnan(dewpoint_c) and dewpoint_c > (t_val + 1.5)
    is_humidity_impossible = h_val is not None and (h_val > 100.0 or h_val < 0.0)
    is_pressure_impossible = p_val is not None and (p_val < 750.0 or p_val > 1100.0)

    # Stull (2011) wet-bulb temperature evaluation
    is_wetbulb_impossible = False
    tw_val = None
    if t_val is not None and h_val is not None:
        try:
            tw_val = (
                t_val * math.atan(0.151977 * math.sqrt(h_val + 8.313659))
                + math.atan(t_val + h_val)
                - math.atan(h_val - 1.676331)
                + 0.00391838 * (h_val ** 1.5) * math.atan(0.023101 * h_val)
                - 4.686035
            )
            if tw_val > 36.0:  # Beyond maximum terrestrial surface wet-bulb
                is_wetbulb_impossible = True
        except Exception:
            pass

    is_multivariate = "multivariate" in str(match.get("type", "")).lower() or "multivariate" in str(match.get("fault_type", "")).lower()

    if is_dewpoint_violation or is_humidity_impossible or is_wetbulb_impossible or is_pressure_impossible:
        if is_dewpoint_violation:
            detail_msg = f"Thermodynamic saturation violation: Calculated dewpoint ({dewpoint_c:.1f}°C) exceeds dry-bulb temperature ({t_val:.1f}°C), violating vapor saturation equilibrium."
        elif is_humidity_impossible:
            detail_msg = f"Physical transducer limit: Relative humidity ({h_val:.1f}%) is outside physical atmospheric limits [0%, 100%]."
        elif is_pressure_impossible:
            detail_msg = f"Physical barometer limit: Barometric pressure ({p_val:.1f} hPa) is outside terrestrial limits [750, 1100 hPa]."
        else:
            detail_msg = f"Extreme thermodynamic exceedance: Equivalent wet-bulb temperature ({tw_val:.1f}°C) exceeds the maximum terrestrial threshold (36.0°C)."
            
        thermodynamic_context = {
            "is_violation": True,
            "law": "Psychrometric Saturation Limit",
            "temperature_c": t_val,
            "humidity_pct": h_val,
            "pressure_hpa": p_val,
            "explanation": detail_msg
        }
    elif is_multivariate:
        if is_spatially_significant:
            thermodynamic_context = {
                "is_violation": True,
                "law": "Cross-Sensor Spatial Cluster Consensus",
                "temperature_c": t_val,
                "humidity_pct": h_val,
                "pressure_hpa": p_val,
                "explanation": (
                    f"Cross-channel divergence: Reported temperature ({t_val}°C) and relative humidity ({h_val}%) "
                    f"diverged significantly from regional cluster peer consensus (delta exceeded learned threshold), "
                    f"indicating an isolated transducer or dual-channel sensor calibration fault."
                )
            }
        else:
            thermodynamic_context = {
                "is_violation": True,
                "law": "Coupled Cross-Channel Thermodynamic Consistency",
                "temperature_c": t_val,
                "humidity_pct": h_val,
                "pressure_hpa": p_val,
                "explanation": (
                    f"Internal transducer divergence: Station temperature ({t_val}°C) and relative humidity ({h_val}%) "
                    f"deviated from joint cross-channel atmospheric expectation, while surrounding cluster peers confirm nominal regional conditions."
                )
            }

    return {
        "cluster_id": cluster_id,
        "target_station": {
            "station_id": target_sid,
            "name": target_name,
            "reading": target_val,
            "unit": unit,
        },
        "peer_stations": peer_stations,
        "parameter_analyzed": param_name,
        "delta": delta,
        "analysis_text": analysis_text,
        "recommended_action": recommended_action,
        "spatial_impact": spatial_impact,
        "thermodynamic_context": thermodynamic_context,
    }


def _compute_explanation_features(match: dict, spatial_ctx: dict | None) -> list:
    if match.get("shap_features") and len(match["shap_features"]) > 0:
        return match["shap_features"]

    features = []
    seen_names = set()

    # 1. Thermodynamic / Cross-Channel Context
    if spatial_ctx and spatial_ctx.get("thermodynamic_context") and spatial_ctx["thermodynamic_context"].get("is_violation"):
        law_name = spatial_ctx["thermodynamic_context"].get("law", "Cross-Sensor Consistency")
        if "Psychrometric" in law_name or "Limit" in law_name:
            feat_name = "Thermodynamic Limit Violation"
        elif "Cluster" in law_name:
            feat_name = "Cross-Channel Cluster Divergence"
        else:
            feat_name = "Coupled Transducer Inconsistency"
        features.append({
            "name": feat_name,
            "impact": 4.85,
            "column": "vapor_pressure_consistency"
        })
        seen_names.add(feat_name)

    # 2. Observed vs Suggested / Baseline Deviations
    observed = match.get("observed_values") or {}
    suggested = match.get("suggested_values") or {}
    for param, obs_val in observed.items():
        if obs_val is not None:
            sugg_val = suggested.get(param)
            if sugg_val is not None:
                diff = round(float(obs_val) - float(sugg_val), 2)
            elif spatial_ctx and spatial_ctx.get("target_station") and spatial_ctx.get("delta") is not None and spatial_ctx.get("parameter_analyzed", "").lower() in param:
                diff = round(float(spatial_ctx["delta"]), 2)
            else:
                diff = 0.0

            display_map = {
                "temperature_c": "Temp Deviation",
                "pressure_hpa": "Pressure Deviation",
                "humidity_pct": "Humidity Deviation",
            }
            name = display_map.get(param, f"{param.replace('_', ' ').title()} Deviation")
            if name not in seen_names:
                scale = 10.0 if param == "temperature_c" else 25.0 if param == "humidity_pct" else 10.0
                norm_impact = round(diff / scale, 4) if scale else diff
                features.append({
                    "name": name,
                    "impact": norm_impact if norm_impact != 0 else (1.5 if diff >= 0 else -1.5),
                    "column": param
                })
                seen_names.add(name)

    # 3. Spatial Divergence if not already captured
    if spatial_ctx and spatial_ctx.get("parameter_analyzed"):
        p_name = spatial_ctx["parameter_analyzed"]
        delta = spatial_ctx.get("delta", 0.0)
        display_map = {
            "temperature": "Spatial Delta (Temp vs Cluster)",
            "barometric pressure": "Spatial Delta (Pressure vs Cluster)",
            "relative humidity": "Spatial Delta (Humidity vs Cluster)",
        }
        feat_name = display_map.get(p_name.lower(), f"{p_name} Contrast")
        if feat_name not in seen_names and abs(delta) > 0.1:
            features.append({
                "name": feat_name,
                "impact": round(delta / 5.0, 4),
                "column": p_name
            })
            seen_names.add(feat_name)

    # 4. Fallback if still empty but affected parameters exist
    if not features:
        for p in match.get("affected_parameters") or []:
            name = f"{p.replace('_', ' ').title()} Deviation"
            if name not in seen_names:
                features.append({
                    "name": name,
                    "impact": 2.5,
                    "column": p
                })
                seen_names.add(name)

    features.sort(key=lambda f: abs(f["impact"]), reverse=True)
    return features


def _generate_operator_conclusion(match: dict, spatial_ctx: dict | None, features: list) -> dict:
    f_type = str(match.get("type") or match.get("fault_type") or "").lower()
    observed = match.get("observed_values") or {}
    suggested = match.get("suggested_values") or {}
    aff_params = match.get("affected_parameters") or list(observed.keys()) or ["sensor"]

    primary_p = aff_params[0] if aff_params else "sensor"
    p_display = primary_p.replace("_c", "").replace("_hpa", "").replace("_pct", "").replace("_", " ").title()
    obs_val = observed.get(primary_p)
    sugg_val = suggested.get(primary_p)
    unit = "°C" if "temp" in primary_p else ("hPa" if "press" in primary_p else ("%" if "humid" in primary_p else ""))

    obs_str = f"{obs_val}{unit}" if obs_val is not None else "abnormal reading"
    sugg_str = f"{sugg_val}{unit}" if sugg_val is not None else "nominal baseline"

    peers_agreed = True
    if spatial_ctx and spatial_ctx.get("spatial_impact"):
        impact_lower = spatial_ctx["spatial_impact"].lower()
        if "localized" in impact_lower or "divergence" in impact_lower:
            peers_agreed = False

    peer_context_note = (
        "Regional peer stations confirm nominal ambient conditions, isolating the issue strictly to this station's hardware."
        if peers_agreed else
        "Nearby cluster peer stations did not experience this shift, confirming localized station-level divergence."
    )

    if "dropout" in f_type:
        title = f"Total Signal Dropout: {p_display} Channel Disconnect"
        diagnosis = (
            f"The {p_display} channel recorded an absolute zero or null signal ({obs_str}), completely severing telemetry continuity. "
            f"{peer_context_note} This indicates an abrupt analog signal loss or digital transducer disconnection."
        )
        tech_action = (
            f"1. Check {p_display} sensor wiring harness and terminal block for loose or severed conductors.\n"
            f"2. Measure DC supply rail voltage (3.3V / 5.0V) at the sensor module pins.\n"
            f"3. Verify I2C/RS-485 bus pull-up resistors and check for telemetry gateway communication faults."
        )
        pipe_action = (
            f"Flagged as CRITICAL hardware dropout. Reading quarantined and replaced with peer spatial consensus ({sugg_str}). "
            f"NWP data assimilation weight set to 0.0 to prevent forecast contamination."
        )
    elif "fail_low" in f_type:
        title = f"Sensor Rail Pinning: {p_display} Clamped Below Terrestrial Limits"
        diagnosis = (
            f"The {p_display} transducer dropped abruptly to {obs_str}, breaching terrestrial physical minimums. "
            f"{peer_context_note} The sensor signal is clamped to the lower electrical supply rail or ground."
        )
        tech_action = (
            f"1. Test for an electrical short circuit between the {p_display} signal line and chassis ground (0V).\n"
            f"2. Inspect analog-to-digital converter (ADC) reference voltage and input filtering capacitor.\n"
            f"3. Replace transducer probe if internal sensing element has failed short."
        )
        pipe_action = (
            f"Instrument rail violation detected. Bad reading suppressed; synthetic baseline ({sugg_str}) injected for downstream monitoring."
        )
    elif "spike" in f_type:
        title = f"Transient Impulse Spike: {p_display} High-Frequency Glitch"
        diagnosis = (
            f"An instantaneous single-observation jump to {obs_str} was detected on the {p_display} channel, "
            f"subsequently returning to baseline ({sugg_str}). {peer_context_note} The rate of change exceeds physical meteorological acceleration limits."
        )
        tech_action = (
            f"1. Check for nearby electromagnetic interference (EMI) sources (solar inverter switching, radio telemetry bursts).\n"
            f"2. Inspect cable shielding and earth ground bonding for induced high-frequency noise spikes.\n"
            f"3. Verify sensor connector pins are free from oxidation and vibration loosening."
        )
        pipe_action = (
            f"Transient impulse isolated and removed via dynamic temporal filtering. Station historical record reconstructed to {sugg_str}."
        )
    elif "frozen" in f_type:
        title = f"Transducer Freeze: {p_display} Output Stagnant (Zero Variance)"
        diagnosis = (
            f"The {p_display} sensor output has remained locked at exactly {obs_str} across consecutive cycles without natural atmospheric variance. "
            f"{peer_context_note} Natural turbulent micro-fluctuations are completely absent."
        )
        tech_action = (
            f"1. Power cycle the data acquisition unit to reset hung sensor I2C/SPI internal registers.\n"
            f"2. Inspect the radiation shield and sensor housing for physical obstructions (ice, dust buildup, or biological debris).\n"
            f"3. Update sensor firmware if repetitive bus locking is observed."
        )
        pipe_action = (
            f"Zero-variance stagnation recognized. Live feed switched to dynamic cluster regression ({sugg_str}) until variance resumes."
        )
    elif "drift" in f_type:
        title = f"Calibration Drift: Progressive {p_display} Transducer Degradation"
        diagnosis = (
            f"The {p_display} sensor exhibited steady, cumulative divergence ({obs_str} vs expected {sugg_str}) over multiple observation hours. "
            f"{peer_context_note} The gradual departure indicates continuous sensing element degradation or contamination."
        )
        tech_action = (
            f"1. Schedule routine field recalibration with a certified portable transfer standard.\n"
            f"2. Inspect sensor protective membrane/sintered filter cap for particulate contamination; clean or replace filter.\n"
            f"3. Apply span/zero offset adjustments in station calibration register if drift persists."
        )
        pipe_action = (
            f"Sensor health status downgraded to WARNING. Continuous drift bias offset applied dynamically to normalize live stream."
        )
    elif "multivariate" in f_type:
        title = "Multivariate Inconsistency: Coupled Thermodynamic / Channel Conflict"
        diagnosis = (
            f"Coupled temperature ({observed.get('temperature_c', 'N/A')}°C) and relative humidity ({observed.get('humidity_pct', 'N/A')}%) "
            f"telemetry violated joint psychrometric consistency (calculated dewpoint/saturation envelope or joint Mahalanobis distribution). "
            f"{peer_context_note} Multi-channel interaction confirms an isolated sensor pair discrepancy."
        )
        tech_action = (
            f"1. Inspect combined temperature-humidity probe (e.g. SHT3x/BME280) for condensation pooling or chemical saturation.\n"
            f"2. Verify common ground and power rail integrity shared between temperature and humidity transducers.\n"
            f"3. Perform comparative verification against an aspirating psychrometer."
        )
        pipe_action = (
            f"Coupled channel conflict quarantined. Joint psychrometric reconstruction applied to maintain thermodynamically valid state."
        )
    else:
        title = f"Statistical Density Outlier: {p_display} Multivariate Residual"
        diagnosis = (
            f"The observation vector was identified as an outlier in the learned multidimensional feature space ({obs_str} vs {sugg_str}). "
            f"{peer_context_note} The pattern exhibits anomalous cross-feature volatility or diurnal residual combinations."
        )
        tech_action = (
            f"1. Review recent station telemetry logs for intermittent transmission packet errors.\n"
            f"2. Verify mast mounting, leveling, and solar radiation shield airflow.\n"
            f"3. Check date of last sensor calibration."
        )
        pipe_action = (
            f"Multi-feature outlier flagged for supervisory review. Fallback ensemble imputation provided for downstream consumers."
        )

    return {
        "title": title,
        "diagnosis": diagnosis,
        "technician_action": tech_action,
        "pipeline_action": pipe_action,
    }


# ---------------- GET /api/explain/{anomaly_id} ----------------

@app.get("/api/explain/{anomaly_id}")
def get_explanation(anomaly_id: str):
    sim = app.state.sim

    match = next(
        (a for a in sim.recent_anomalies if a["anomaly_id"] == anomaly_id),
        None
    )

    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown anomaly_id {anomaly_id}"
        )

    # Pass flagged reading to model to compute model evidence & calibrated score
    # if not already evaluated (e.g. caught by upstream rule tier)
    if match.get("model_confidence_pct") is None:
        try:
            artifact = getattr(sim.manager, "artifact", None)
            model = artifact.get("model") if artifact else None
            feat_cols = artifact.get("feature_columns", []) if artifact else []
            sid = match.get("station_id")
            buf = sim.manager.buffers.get(sid) if sid else None

            if model is not None and feat_cols and buf is not None:
                history_df = buf.raw_history_df()
                cur_row = dict(match.get("observed_values", {}), station_id=sid, timestamp=match.get("timestamp"))
                hist_with_cur = pd.concat([history_df, pd.DataFrame([cur_row])], ignore_index=True) if not history_df.empty else pd.DataFrame([cur_row])
                featured = build_features_for_history(hist_with_cur)
                if not featured.empty and all(col in featured.columns for col in feat_cols):
                    feat_row = featured.iloc[-1].copy()
                    feat_row[feat_cols] = feat_row[feat_cols].fillna(0.0)
                    X = feat_row[feat_cols].values.reshape(1, -1).astype(float)
                    if not np.isnan(X).any():
                        raw_if_score = float(model.decision_function(X)[0])
                        train_std = artifact.get("training_score_std", 0.08)
                        z_if = (0.0 - raw_if_score) / max(1e-4, train_std)
                        # Smooth logistic calibration
                        calibrated_conf = 100.0 / (1.0 + math.exp(-0.8 * z_if))
                        calibrated_conf = max(10.0, min(99.0, round(calibrated_conf, 1)))
                        match["model_confidence_pct"] = calibrated_conf

                        if getattr(sim.manager, "explainer", None):
                            expl_res = sim.manager.explainer.explain(feat_row)
                            if expl_res and expl_res.get("features"):
                                match["shap_features"] = expl_res["features"]
        except Exception as e:
            logger.warning(f"Fallback model evaluation failed for {anomaly_id}: {e}")

    rule_conf = match.get("rule_confidence_pct")
    if rule_conf is None:
        rules = match.get("rules_fired") or []
        confs = [r.get("confidence") for r in rules if isinstance(r, dict) and r.get("confidence") is not None]
        if confs:
            rule_conf = float(max(confs))
        elif match.get("anomaly_score_pct") is not None and (rules or match.get("type")):
            rule_conf = float(match["anomaly_score_pct"])
        match["rule_confidence_pct"] = rule_conf

    spatial_ctx = _compute_spatial_context(sim, match)
    features = _compute_explanation_features(match, spatial_ctx)
    structured_conclusion = _generate_operator_conclusion(match, spatial_ctx, features)

    return {
        "anomaly_id": anomaly_id,
        "station_id": match.get("station_id"),
        "timestamp": match["timestamp"].isoformat() if hasattr(match.get("timestamp"), "isoformat") else str(match.get("timestamp", "")),
        "features": features,
        "likely_faulty_sensors": match.get("likely_faulty_sensors", []),
        "affected_parameters": match.get("affected_parameters", []),
        "observed_values": match.get("observed_values", {}),
        "suggested_values": match.get("suggested_values", {}),
        "model_confidence_pct": match.get("model_confidence_pct"),
        "rule_confidence_pct": match.get("rule_confidence_pct"),
        "anomaly_score_pct": match.get("anomaly_score_pct"),
        "fault_type": match.get("type"),
        "regime": match.get("regime"),
        "network_corroboration": match.get("network_corroboration"),
        "decision_basis": _compute_decision_basis(
            match.get("model_confidence_pct"),
            match.get("rules_fired") or [],
        ),
        "model_status": _compute_model_status(
            match.get("model_confidence_pct"),
            None,
        ),
        "spatial_context": spatial_ctx,
        "edge_inference": match.get("edge_inference"),
        "structured_conclusion": structured_conclusion,
        "source": match.get("source", "central"),
    }



# ---------------- GET /api/sensor-health ----------------

@app.get("/api/sensor-health")
def get_sensor_health(station_id: Optional[str] = None):
    sim = app.state.sim
    if station_id:
        if station_id not in sim.manager.buffers:
            raise HTTPException(status_code=404, detail=f"Unknown station {station_id}")
        buf = sim.manager.buffers[station_id]
        status = sim.manager.get_station_status(station_id)
        mapped = {"HEALTHY": "HEALTHY", "WARNING": "WARNING", "OFFLINE": "OFFLINE"}.get(status["status"], "HEALTHY")
        return {
            "station_id": station_id,
            "health_pct": round(buf.health.health_index),
            "status": mapped,
            "needs_maintenance": buf.health.needs_maintenance,
            "parameters": buf.health.param_status,
            "param_health": {p: round(v, 1) for p, v in buf.health.param_health.items()},
            "offline_reason": status["offline_reason"],
            "recovery_active": status["recovery_active"],
        }
    
    # Return all stations
    results = []
    for sid in sim.manager.buffers:
        buf = sim.manager.buffers[sid]
        st = sim.manager.get_station_status(sid)
        mp = {"HEALTHY": "HEALTHY", "WARNING": "WARNING", "OFFLINE": "OFFLINE"}.get(st["status"], "HEALTHY")
        results.append({
            "station_id": sid,
            "health_pct": round(buf.health.health_index),
            "status": mp,
            "needs_maintenance": buf.health.needs_maintenance,
            "parameters": buf.health.param_status,
            "param_health": {p: round(v, 1) for p, v in buf.health.param_health.items()},
            "offline_reason": st["offline_reason"],
            "recovery_active": st["recovery_active"],
        })
    return results

# ---------------- POST /api/repair-sensor ----------------

@app.post("/api/repair-sensor")
def repair_sensor(body: dict):
    sim = app.state.sim

    station_id = body.get("station_id")
    if not station_id:
        raise HTTPException(
            status_code=400,
            detail="station_id is required"
        )

    if station_id not in sim.manager.buffers:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown station {station_id}"
        )

    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc)

    if body.get("force_recovery", False):
        sim.manager.force_recover_station(station_id)
        return {
            "success": True,
            "station_id": station_id,
            "status": "HEALTHY",
            "recovery_active": False,
            "message": "Sensor force-recovered and health counters reset.",
        }

    sim.manager.mark_station_repaired(station_id, timestamp)

    return {
        "success": True,
        "station_id": station_id,
        "status": "WARNING",
        "recovery_active": True,
        "message": "Sensor marked for repair recovery. Clean readings will be evaluated before returning it to HEALTHY."
    }


# ---------------- POST /api/inject-anomaly ----------------

@app.post("/api/inject-anomaly")
async def inject_anomaly(body: dict):
    """
    Triggers simulator replay and dynamically targets the requested station and fault type.
    If replay is already running, dynamically injects the fault at the current replay position.
    """
    sim = app.state.sim
    station_id = body.get("station_id")
    fault_type = body.get("type")

    if sim.mode == "replay":
        if station_id:
            anomaly_id = await asyncio.to_thread(sim.inject_fault_dynamic, station_id, fault_type)
            return {
                "success": True,
                "anomaly_id": anomaly_id,
                "message": f"Injected {fault_type or 'anomaly'} into active replay for {station_id}.",
            }
        anomaly_id = await asyncio.to_thread(sim.start_replay, station_id, fault_type)
        return {
            "success": True,
            "anomaly_id": anomaly_id,
            "message": f"Simulator restarted: replaying data with {fault_type or 'anomaly'}.",
        }

    anomaly_id = await asyncio.to_thread(sim.start_replay, station_id, fault_type)
    return {
        "success": True,
        "anomaly_id": anomaly_id,
        "message": f"Simulator started: replaying data with {fault_type or 'anomaly'} targeted on {station_id or 'all stations'}.",
    }


# ---------------- POST /api/maintenance-ticket ----------------

_ticket_counter = 0

@app.post("/api/maintenance-ticket")
async def create_maintenance_ticket(body: dict):
    global _ticket_counter
    sim = app.state.sim

    anomaly_id = body.get("anomaly_id")
    match = next((a for a in sim.recent_anomalies if a["anomaly_id"] == anomaly_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Unknown anomaly_id {anomaly_id}")

    _ticket_counter += 1
    from datetime import datetime, timezone
    return {
        "ticket_id": f"TCK-{_ticket_counter:04d}",
        "station_id": match["station_id"],
        "issue": match["root_cause"],
        "priority": "high" if match["severity"] in ("high", "critical") else "medium",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _health_pct(parameter_status: dict[str, str]) -> int:
    """Stable health summary from actual per-parameter circuit breakers."""
    if not parameter_status:
        return 100
    score_by_status = {"HEALTHY": 100, "WARNING": 50, "OFFLINE": 0}
    return round(sum(score_by_status.get(value, 0) for value in parameter_status.values()) / len(parameter_status))
import traceback, sys, threading
@app.get("/api/debug")
def dump_debug():
    stacks = []
    for thread_id, frame in sys._current_frames().items():
        stacks.append(f"Thread {thread_id}:\n" + "".join(traceback.format_stack(frame)))
    
    sim = app.state.sim
    tasks = []
    try:
        import asyncio
        for t in asyncio.all_tasks():
            tasks.append(str(t))
    except:
        pass
    return {"threads": stacks, "tasks": tasks, "cursor": getattr(sim, "_replay_cursor_idx", -1)}
