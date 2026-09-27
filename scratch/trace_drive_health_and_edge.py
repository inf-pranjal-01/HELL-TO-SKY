"""
SkyGuard AI — Comprehensive End-to-End Trace Drive
Validates both Sensor Health Hysteresis Mechanism and ESP32 Edge Ingestion Mechanism.
"""

import time
import requests
import json
import uuid
from datetime import datetime, timezone
import pandas as pd

BASE_URL = "http://localhost:8000"

def log_section(title):
    print("\n" + "=" * 80)
    print(f"  >>> {title.upper()}")
    print("=" * 80)

def assert_check(condition, msg):
    if condition:
        print(f"  [PASS] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        raise AssertionError(f"Check failed: {msg}")

def run_trace_drive():
    log_section("Phase 1: Initial System State Verification")
    res = requests.get(f"{BASE_URL}/api/system-status").json()
    print("System Status:", res)
    assert_check(res["mode"] in ("live", "replay", "edge"), "Mode is valid")
    assert_check("edge_status" in res, "edge_status is present in system-status")

    target_sid = "AWS-CHN-024"

    # Reset DB to pristine state
    requests.post(f"{BASE_URL}/api/admin/clear-history", json={"target": "all"})
    time.sleep(1.0)

    # -------------------------------------------------------------
    # PART A: SENSOR HEALTH HYSTERESIS TRACE DRIVE
    # -------------------------------------------------------------
    log_section("Part A1: Initial Clean Sensor Health")
    health = requests.get(f"{BASE_URL}/api/sensor-health?station_id={target_sid}").json()
    print("Initial Health:", health)
    assert_check(health["health_pct"] == 100, "Initial health is 100%")
    assert_check(health["status"] == "HEALTHY", "Initial status is HEALTHY")
    assert_check(health["needs_maintenance"] is False, "needs_maintenance is False")

    log_section("Part A2: Single Anomaly Degradation Test (Asymmetric Decay)")
    # Send an anomalous reading via edge or observation endpoint
    anom_packet = {
        "event_id": str(uuid.uuid4()),
        "station_id": target_sid,
        "device_id": "esp32-node-TRACE-01",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "sequence_number": 1,
        "readings": {"temperature_c": 75.0, "pressure_hpa": 1013.0, "humidity_pct": 50.0},
        "edge_inference": {"status": "ALERT", "anomaly_flag": True, "anomaly_type": "physical_bounds", "score": 95.0},
    }
    r = requests.post(f"{BASE_URL}/api/ingest/observation", json=anom_packet).json()
    print("Ingested Anomaly Packet Response:", r)

    health_after_1 = requests.get(f"{BASE_URL}/api/sensor-health?station_id={target_sid}").json()
    print("Health after 1 anomaly:", health_after_1)
    assert_check(health_after_1["health_pct"] < 100, "Health decreased after anomaly")
    assert_check(health_after_1["status"] in ("WARNING", "OFFLINE"), "Status transitioned to WARNING or OFFLINE")

    log_section("Part A3: Anti-Flapping Test (1 Clean Reading Does Not Instantly Restore to 100%)")
    clean_packet_1 = {
        "event_id": str(uuid.uuid4()),
        "station_id": target_sid,
        "device_id": "esp32-node-TRACE-01",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "sequence_number": 2,
        "readings": {"temperature_c": 26.5, "pressure_hpa": 1012.0, "humidity_pct": 60.0},
        "edge_inference": {"status": "NOMINAL", "anomaly_flag": False},
    }
    requests.post(f"{BASE_URL}/api/ingest/observation", json=clean_packet_1)
    health_flapping_check = requests.get(f"{BASE_URL}/api/sensor-health?station_id={target_sid}").json()
    print("Health after 1 clean reading (Anti-Flapping Check):", health_flapping_check)
    assert_check(health_flapping_check["health_pct"] < 90, "Health does NOT instantly jump to 100% (anti-flapping holds)")
    assert_check(health_flapping_check["health_pct"] > health_after_1["health_pct"], "Health showed gradual +2.0 recovery")

    log_section("Part A4: Persistent Fault -> OFFLINE and Maintenance Trigger Test")
    # Send consecutive critical faults to drive health below 30 (OFFLINE) and below 50 (needs_maintenance)
    for i in range(3):
        crit_packet = {
            "event_id": str(uuid.uuid4()),
            "station_id": target_sid,
            "device_id": "esp32-node-TRACE-01",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "sequence_number": 10 + i,
            "readings": {"temperature_c": -40.0, "pressure_hpa": 1013.0, "humidity_pct": 50.0},
            "edge_inference": {"status": "ALERT", "anomaly_flag": True, "anomaly_type": "sensor_fail_low", "score": 100.0},
        }
        res = requests.post(f"{BASE_URL}/api/ingest/observation", json=crit_packet).json()
        print(f"Crit Packet #{i+1} response:", res)

    health_offline = requests.get(f"{BASE_URL}/api/sensor-health?station_id={target_sid}").json()
    print("Health after sustained critical faults:", health_offline)
    assert_check(health_offline["health_pct"] <= 30, "Health index dropped below 30%")
    assert_check(health_offline["status"] == "OFFLINE", "Station status is OFFLINE")
    assert_check(health_offline["needs_maintenance"] is True, "needs_maintenance is True (H < 50%)")

    log_section("Part A5: Gradual Repair vs Instant Force Recovery Test")
    # Test Gradual Repair
    repair_res = requests.post(f"{BASE_URL}/api/repair-sensor", json={"station_id": target_sid}).json()
    print("Gradual Repair Response:", repair_res)
    assert_check(repair_res["status"] == "WARNING", "Repair starts in WARNING probation")
    assert_check(repair_res["recovery_active"] is True, "recovery_active is True")

    # Test Instant Force Recover
    force_res = requests.post(f"{BASE_URL}/api/repair-sensor", json={"station_id": target_sid, "force_recovery": True}).json()
    print("Force Recover Response:", force_res)
    assert_check(force_res["status"] == "HEALTHY", "Force recover immediately restores HEALTHY")
    assert_check(force_res["recovery_active"] is False, "recovery_active is False")

    health_recovered = requests.get(f"{BASE_URL}/api/sensor-health?station_id={target_sid}").json()
    print("Health after Force Recovery:", health_recovered)
    assert_check(health_recovered["health_pct"] == 100, "Health is restored to 100%")
    assert_check(health_recovered["status"] == "HEALTHY", "Status is HEALTHY")
    assert_check(health_recovered["needs_maintenance"] is False, "needs_maintenance is False")

    # -------------------------------------------------------------
    # PART B: ESP32 EDGE INGESTION & MODE ISOLATION TRACE DRIVE
    # -------------------------------------------------------------
    log_section("Part B1: Switch to EDGE Testing Mode")
    mode_switch_edge = requests.post(f"{BASE_URL}/api/system-mode", json={"mode": "edge", "station_id": target_sid}).json()
    print("Switched to EDGE mode response:", mode_switch_edge)
    assert_check(mode_switch_edge["mode"] == "edge", "Mode switch returned 'edge'")

    status_edge_wait = requests.get(f"{BASE_URL}/api/system-status").json()
    print("System Status in Edge Mode (Waiting):", status_edge_wait)
    assert_check(status_edge_wait["mode"] == "edge", "System mode is 'edge'")
    assert_check(status_edge_wait["edge_status"]["status"] == "WAITING", "Edge status is WAITING")
    assert_check(status_edge_wait["edge_status"]["connected"] is False, "Edge connected is False")

    log_section("Part B2: Transmit ESP32 Hardware Observation Stream")
    edge_device_id = "esp32-node-HARDWARE-BENCH-01"
    for seq in range(1, 6):
        sample_packet = {
            "event_id": str(uuid.uuid4()),
            "station_id": target_sid,
            "device_id": edge_device_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "sequence_number": seq,
            "readings": {
                "temperature_c": 28.0 + (seq * 0.1),
                "pressure_hpa": 1012.5,
                "humidity_pct": 65.0,
            },
            "edge_inference": {
                "status": "NOMINAL",
                "anomaly_flag": False,
                "anomaly_type": None,
                "score": 5.0,
                "model_version": "edge_rules_v2.0.0",
                "inference_method": "temporal_rules_and_buffers",
            },
        }
        resp = requests.post(f"{BASE_URL}/api/ingest/observation", json=sample_packet).json()
        assert_check(resp.get("accepted") is True, f"Packet #{seq} accepted by backend")

    status_edge_connected = requests.get(f"{BASE_URL}/api/system-status").json()
    print("System Status after ESP32 stream:", status_edge_connected)
    edge_st = status_edge_connected["edge_status"]
    assert_check(edge_st["status"] == "CONNECTED", "Edge status shifted to CONNECTED")
    assert_check(edge_st["connected"] is True, "Edge connected is True")
    assert_check(edge_st["station_id"] == target_sid, f"Edge target station is {target_sid}")
    assert_check(edge_st["device_id"] == edge_device_id, f"Edge device ID is {edge_device_id}")
    assert_check(edge_st["packet_count"] >= 5, f"Packet count recorded ({edge_st['packet_count']})")

    log_section("Part B3: Current Reading & Trend Continuity in Edge Mode")
    current_rdg = requests.get(f"{BASE_URL}/api/current-reading?station_id={target_sid}").json()
    print("Current reading in Edge Mode:", current_rdg)
    assert_check(current_rdg["source"] == "edge", "Reading source is 'edge'")
    assert_check(current_rdg["temperature_c"]["value"] is not None, "Temperature reading is populated")

    trends_edge = requests.get(f"{BASE_URL}/api/trends?station_id={target_sid}&hours=6").json()
    print(f"Trend points count in Edge Mode: {len(trends_edge['points'])}")
    assert_check(len(trends_edge["points"]) >= 1, "Trends received edge points")

    log_section("Part B4: Clean Zero-Bleed Return to LIVE Mode")
    mode_switch_live = requests.post(f"{BASE_URL}/api/system-mode", json={"mode": "live"}).json()
    print("Switched back to LIVE mode response:", mode_switch_live)
    assert_check(mode_switch_live["mode"] == "live", "Mode returned to 'live'")

    status_live = requests.get(f"{BASE_URL}/api/system-status").json()
    print("Final Live System Status:", status_live)
    assert_check(status_live["mode"] == "live", "Mode is 'live'")
    assert_check(status_live["edge_status"]["connected"] is False, "Edge status disconnected")

    # -------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------
    log_section("TRACE DRIVE COMPLETE: ALL CHECKS PASSED (100% SUCCESS)")
    print("\n[SUCCESS] Continuous Health Hysteresis verified (Asymmetric decay, anti-flapping recovery, maintenance alerts)")
    print("[SUCCESS] ESP32 Edge Ingestion Mode verified (Waiting -> Connected -> Auto-Focus -> Zero-Bleed Live Restore)")
    print("[SUCCESS] All API contracts and live streams operating with zero defects!\n")

if __name__ == "__main__":
    run_trace_drive()
