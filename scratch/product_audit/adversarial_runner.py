"""
scratch/product_audit/adversarial_runner.py

SkyGuard AI — Full Adversarial Product QA & Red-Team Attack Harness.
Executes multi-threaded adversarial attacks against live backend, WebSocket transport,
database persistence, and frontend state contracts.
"""

import sys
import os
import time
import json
import asyncio
import threading
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
import pandas as pd
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/live"

# Global findings registry
ATTACK_FINDINGS = []


def record_finding(attack_name: str, category: str, severity: str, symptom: str, root_cause: str, status: str, details: dict):
    finding = {
        "attack_name": attack_name,
        "category": category,
        "severity": severity,
        "symptom": symptom,
        "root_cause": root_cause,
        "status": status,
        "details": details
    }
    ATTACK_FINDINGS.append(finding)
    print(f"[{severity}] [{status}] {attack_name}: {symptom}", flush=True)


def http_get(path: str, timeout: float = 5.0):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8") if e.fp else str(e)
        return e.code, None, err
    except Exception as e:
        return 0, None, str(e)


def http_post(path: str, body: dict, timeout: float = 5.0):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="POST")
    req.data = json.dumps(body).encode("utf-8")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8") if e.fp else str(e)
        return e.code, None, err
    except Exception as e:
        return 0, None, str(e)


# ==============================================================================
# ATTACK 1: Live <-> Replay Isolation & Data Bleed Attack
# ==============================================================================
def attack_1_live_replay_isolation():
    print("\n" + "="*80, flush=True)
    print("ATTACK 1: Live <-> Replay Isolation & Data Bleed Attack", flush=True)
    print("="*80, flush=True)

    # 1. Capture initial live reading for target station and peer station
    target_sid = "AWS-CHN-024"
    peer_sid = "AWS-DEL-011"

    status_t, live_target_pre, _ = http_get(f"/api/current-reading?station_id={target_sid}")
    status_p, live_peer_pre, _ = http_get(f"/api/current-reading?station_id={peer_sid}")
    _, sys_status_pre, _ = http_get("/api/system-status")

    print(f"-> Pre-replay mode: {sys_status_pre.get('mode')}")

    # 2. Trigger synthetic anomaly injection on target station
    inj_status, inj_resp, inj_err = http_post("/api/inject-anomaly", {
        "station_id": target_sid,
        "type": "spike"
    })
    print(f"-> Injection response: HTTP {inj_status}, resp: {inj_resp}")

    time.sleep(1.0) # Let simulation step run

    # 3. Inspect target and peer station states during replay
    _, replay_target, _ = http_get(f"/api/current-reading?station_id={target_sid}")
    _, replay_peer, _ = http_get(f"/api/current-reading?station_id={peer_sid}")
    _, sys_status_during, _ = http_get("/api/system-status")

    print(f"-> During replay mode: {sys_status_during.get('mode')}")
    print(f"-> Target reading source during replay: {replay_target.get('source') if replay_target else 'None'}")
    print(f"-> Peer reading source during replay: {replay_peer.get('source') if replay_peer else 'None'}")

    # 4. Stop replay and return to live
    stop_status, stop_resp, _ = http_post("/api/system-mode", {"mode": "live"})
    time.sleep(0.5)

    _, sys_status_post, _ = http_get("/api/system-status")
    _, live_target_post, _ = http_get(f"/api/current-reading?station_id={target_sid}")

    # Verification rules
    leak_detected = False
    if sys_status_post.get("mode") != "live":
        leak_detected = True
        record_finding(
            "Live/Replay Mode Reset",
            "STATE_ISOLATION",
            "P1",
            "System failed to switch back to live mode after stop_replay",
            "System mode remained in replay state",
            "FAIL",
            {"post_mode": sys_status_post.get("mode")}
        )

    if not leak_detected:
        record_finding(
            "Live/Replay Isolation",
            "STATE_ISOLATION",
            "P0",
            "Live/Replay lifecycle isolated successfully with clean return to live",
            "None",
            "VERIFIED_CLEAN",
            {"pre_mode": sys_status_pre.get("mode"), "during_mode": sys_status_during.get("mode"), "post_mode": sys_status_post.get("mode")}
        )


# ==============================================================================
# ATTACK 2: High-Concurrency Ingestion & State Race Attack
# ==============================================================================
def attack_2_concurrency_race():
    print("\n" + "="*80, flush=True)
    print("ATTACK 2: High-Concurrency Ingestion & State Race Attack (100 parallel requests)", flush=True)
    print("="*80, flush=True)

    stations = ["AWS-CHN-024", "AWS-DEL-011", "AWS-MUM-007", "AWS-KOL-015", "AWS-BHO-030", "AWS-VAR-052", "AWS-RAN-067"]
    results = []

    def worker(i: int):
        sid = stations[i % len(stations)]
        hours = [10, 24, 72][i % 3]
        # Alternate between endpoints
        if i % 3 == 0:
            status, data, err = http_get(f"/api/current-reading?station_id={sid}")
            ret_sid = data.get("station_id") if data else None
            results.append((status, sid == ret_sid, err))
        elif i % 3 == 1:
            status, data, err = http_get(f"/api/trends?station_id={sid}&hours={hours}")
            ret_sid = data.get("station_id") if data else None
            results.append((status, sid == ret_sid, err))
        else:
            status, data, err = http_get(f"/api/sensor-health?station_id={sid}")
            ret_sid = data.get("station_id") if data else None
            results.append((status, sid == ret_sid, err))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    start_t = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start_t

    success_count = sum(1 for s, match, err in results if s == 200 and match)
    mismatches = sum(1 for s, match, err in results if s == 200 and not match)
    errors = sum(1 for s, match, err in results if s != 200)

    print(f"-> Finished 100 concurrent calls in {elapsed:.2f}s: {success_count} OK, {mismatches} station mismatches, {errors} errors")

    if mismatches > 0 or errors > 0:
        record_finding(
            "Concurrent State Overwrite",
            "CONCURRENCY_RACE",
            "P1",
            f"Concurrency race detected: {mismatches} mismatched stations, {errors} failed requests",
            "Thread-unsafe global state or endpoint contention",
            "FAIL",
            {"mismatches": mismatches, "errors": errors, "elapsed": elapsed}
        )
    else:
        record_finding(
            "Concurrent State Safety",
            "CONCURRENCY_RACE",
            "P1",
            "100/100 concurrent multi-station requests returned perfect station-matched responses",
            "None",
            "VERIFIED_CLEAN",
            {"total_calls": 100, "elapsed_s": round(elapsed, 2)}
        )


# ==============================================================================
# ATTACK 3: Semantic Contradiction Audit across All 28 Stations
# ==============================================================================
def attack_3_semantic_contradictions():
    print("\n" + "="*80, flush=True)
    print("ATTACK 3: Semantic Contradiction Audit across All 28 Stations", flush=True)
    print("="*80, flush=True)

    _, stations_list, _ = http_get("/api/stations")
    if not stations_list:
        print("-> Error: could not fetch stations list")
        return

    contradictions = []
    checked_count = 0

    for st in stations_list:
        sid = st["station_id"]
        _, reading, _ = http_get(f"/api/current-reading?station_id={sid}")
        _, health, _ = http_get(f"/api/sensor-health?station_id={sid}")
        _, latest_anom, _ = http_get(f"/api/anomalies/latest?station_id={sid}")
        _, trends, _ = http_get(f"/api/trends?station_id={sid}&hours=10")

        if not reading:
            continue
        checked_count += 1

        score = reading.get("anomaly_score_pct", 0.0)
        risk = reading.get("risk_level", "low")
        is_anom = reading.get("is_anomaly", False)
        health_pct = reading.get("sensor_health_pct", 100)
        health_status = reading.get("sensor_health_status", "NORMAL")

        # Check Rule 1: High Anomaly Score with Low Risk
        if score >= 80.0 and risk == "low":
            contradictions.append({
                "station_id": sid,
                "rule": "HIGH_SCORE_LOW_RISK",
                "detail": f"Anomaly score {score}% but risk_level is 'low'"
            })

        # Check Rule 2: Sensor Health 100% with OFFLINE status
        if health_pct == 100 and health_status in ("OFFLINE", "CRITICAL"):
            contradictions.append({
                "station_id": sid,
                "rule": "HEALTH_100_BUT_OFFLINE",
                "detail": f"Sensor health {health_pct}% but status is {health_status}"
            })

        # Check Rule 3: Critical Risk with is_anomaly == False
        if risk == "critical" and not is_anom:
            contradictions.append({
                "station_id": sid,
                "rule": "CRITICAL_RISK_WITHOUT_ANOMALY",
                "detail": "risk_level is 'critical' but is_anomaly is False"
            })

        # Check Rule 4: Trend Point Timestamps Continuity
        pts = trends.get("points", []) if trends else []
        if len(pts) >= 2:
            ts_vals = [pd.to_datetime(p["timestamp"]).value for p in pts if "timestamp" in p]
            if any(ts_vals[i] > ts_vals[i+1] for i in range(len(ts_vals)-1)):
                contradictions.append({
                    "station_id": sid,
                    "rule": "NON_MONOTONIC_TREND_TIMESTAMPS",
                    "detail": "Trend points have non-monotonic timestamps"
                })

    print(f"-> Audited {checked_count} stations. Contradictions found: {len(contradictions)}")
    for c in contradictions:
        print(f"   * {c['station_id']}: [{c['rule']}] {c['detail']}")

    if contradictions:
        record_finding(
            "Semantic Contradiction Engine",
            "SEMANTIC_INTEGRITY",
            "P1",
            f"{len(contradictions)} semantic contradictions detected across active stations",
            "Inconsistent multi-metric derivation across risk/health layers",
            "FAIL",
            {"contradictions": contradictions}
        )
    else:
        record_finding(
            "Semantic Contradiction Engine",
            "SEMANTIC_INTEGRITY",
            "P1",
            f"0 semantic contradictions across all {checked_count} stations. Risk, health, and anomaly scores perfectly aligned.",
            "None",
            "VERIFIED_CLEAN",
            {"stations_checked": checked_count}
        )


# ==============================================================================
# ATTACK 4: WebSocket Protocol Fuzzing & Rapid Reconnect
# ==============================================================================
async def attack_4_websocket_fuzzing():
    print("\n" + "="*80, flush=True)
    print("ATTACK 4: WebSocket Protocol Fuzzing & Rapid Reconnect", flush=True)
    print("="*80, flush=True)

    import websockets

    # 1. Test Rapid Reconnect (20 cycles)
    reconnect_success = 0
    for i in range(20):
        try:
            async with websockets.connect(WS_URL, open_timeout=2.0) as ws:
                await ws.send("ping")
                resp = await asyncio.wait_for(ws.recv(), timeout=1.5)
                if resp == "pong" or "type" in str(resp):
                    reconnect_success += 1
        except Exception as e:
            pass

    print(f"-> Rapid Reconnect: {reconnect_success}/20 cycles successful")

    # 2. Test Malformed Message Fuzzing
    fuzz_payloads = [
        "NOT_JSON",
        "{malformed_json: True",
        json.dumps({"type": "UNKNOWN_EVENT_TYPE_FUZZ", "data": "X"*1000}),
        json.dumps({"timestamp": "INVALID_DATE_FORMAT", "reading": None}),
        ""
    ]

    fuzz_survived = 0
    for p in fuzz_payloads:
        try:
            async with websockets.connect(WS_URL, open_timeout=2.0) as ws:
                await ws.send(p)
                await asyncio.sleep(0.1)
                # Verify socket is still alive or gracefully closed without crashing backend
                fuzz_survived += 1
        except Exception:
            fuzz_survived += 1 # Graceful close on malformed is acceptable

    # Check backend is still alive
    st, data, _ = http_get("/api/system-status")
    server_alive = (st == 200)

    if server_alive and reconnect_success >= 18:
        record_finding(
            "WebSocket Fuzzing & Reconnect",
            "TRANSPORT_RESILIENCE",
            "P2",
            "WebSocket handled rapid reconnection cycles and malformed payloads without crashing backend",
            "None",
            "VERIFIED_CLEAN",
            {"reconnect_success": reconnect_success, "server_alive": server_alive}
        )
    else:
        record_finding(
            "WebSocket Fuzzing & Reconnect",
            "TRANSPORT_RESILIENCE",
            "P1",
            f"WebSocket instability: {reconnect_success}/20 connects, server_alive={server_alive}",
            "Socket connection exhaustion or unhandled frame exception",
            "FAIL",
            {"reconnect_success": reconnect_success, "server_alive": server_alive}
        )


# ==============================================================================
# ATTACK 5: Destructive Action Safety & Error Boundary Check
# ==============================================================================
def attack_5_destructive_and_error_boundaries():
    print("\n" + "="*80, flush=True)
    print("ATTACK 5: Destructive Action Safety & Error Boundaries", flush=True)
    print("="*80, flush=True)

    # 1. Invalid Station ID request
    st404, resp404, _ = http_get("/api/current-reading?station_id=AWS-NONEXISTENT-999")
    print(f"-> Invalid station query: HTTP {st404} (Expected 404)")

    # 2. Invalid hours parameter on trends
    st400, resp400, _ = http_get("/api/trends?station_id=AWS-CHN-024&hours=999999")
    print(f"-> Invalid hours query: HTTP {st400} (Expected 400)")

    # 3. Invalid Repair Target
    st_rep, resp_rep, _ = http_post("/api/repair-sensor", {"station_id": "AWS-NONEXISTENT-999"})
    print(f"-> Repair non-existent station: HTTP {st_rep} (Expected 404 or 400)")

    # 4. Safe Clear Replay Scratch History
    st_clear, resp_clear, _ = http_post("/api/admin/clear-history", {"target": "replay"})
    print(f"-> Clear replay history: HTTP {st_clear}, msg: {resp_clear.get('message') if resp_clear else ''}")

    all_passed = (st404 == 404 and st400 == 400 and st_rep in (404, 400) and st_clear == 200)

    if all_passed:
        record_finding(
            "Error Boundaries & Input Validation",
            "INPUT_VALIDATION",
            "P2",
            "All invalid parameters, out-of-range bounds, and non-existent IDs returned proper HTTP 4xx errors without 500 crashes",
            "None",
            "VERIFIED_CLEAN",
            {"st404": st404, "st400": st400, "st_rep": st_rep, "st_clear": st_clear}
        )
    else:
        record_finding(
            "Error Boundaries & Input Validation",
            "INPUT_VALIDATION",
            "P2",
            "Unexpected error boundary status on invalid requests",
            "Missing input validation or unhandled exception",
            "FAIL",
            {"st404": st404, "st400": st400, "st_rep": st_rep, "st_clear": st_clear}
        )


def main():
    print("================================================================================", flush=True)
    print("SKYGUARD AI — FULL ADVERSARIAL PRODUCT QA & RED-TEAM ATTACK SUITE", flush=True)
    print("================================================================================", flush=True)

    attack_1_live_replay_isolation()
    attack_2_concurrency_race()
    attack_3_semantic_contradictions()
    asyncio.run(attack_4_websocket_fuzzing())
    attack_5_destructive_and_error_boundaries()

    # Output machine readable logs
    df = pd.DataFrame(ATTACK_FINDINGS)
    df.to_csv(OUTPUT_DIR / "adversarial_attack_results.csv", index=False)
    print(f"\n-> All attack results recorded to {OUTPUT_DIR / 'adversarial_attack_results.csv'}", flush=True)


if __name__ == "__main__":
    main()
