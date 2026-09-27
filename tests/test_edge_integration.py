"""
Unit & Integration test for Level 1 Temporal Edge Node and FastAPI Backend Ingestion
"""

import math
from fastapi.testclient import TestClient
from main import app
from scripts.virtual_esp32_node import run_level1_edge_inference, build_observation_packet, VirtualEdgeRingBuffer

def test_level1_edge_inference_rules():
    buf = VirtualEdgeRingBuffer(capacity=128)

    # 1. Normal
    res = run_level1_edge_inference(buf, 25.0, 1013.25, 60.0)
    assert res["status"] == "ok"
    assert res["anomaly_flag"] is False
    assert res["anomaly_type"] is None

    # 2. Dropout
    res_drop = run_level1_edge_inference(buf, float("nan"), 1013.25, 60.0)
    assert res_drop["status"] == "anomaly_detected"
    assert res_drop["anomaly_flag"] is True
    assert res_drop["anomaly_type"] == "dropout"

    # 3. Fail-low
    res_fail = run_level1_edge_inference(buf, 25.0, 0.0, 60.0)
    assert res_fail["status"] == "anomaly_detected"
    assert res_fail["anomaly_flag"] is True
    assert res_fail["anomaly_type"] == "sensor_fail_low"

    # 4. Physical Bounds
    res_bounds = run_level1_edge_inference(buf, 80.0, 1013.25, 60.0)
    assert res_bounds["status"] == "anomaly_detected"
    assert res_bounds["anomaly_flag"] is True
    assert res_bounds["anomaly_type"] == "physical_bounds"

    # 5. Rate of Change Spike (T jump from 25.0 to 32.0 in 1 step)
    res_spike = run_level1_edge_inference(buf, 32.0, 1013.25, 60.0)
    assert res_spike["status"] == "anomaly_detected"
    assert res_spike["anomaly_flag"] is True
    assert res_spike["anomaly_type"] == "spike"

    # 6. Frozen Value / Stuck Sensor Test
    frozen_buf = VirtualEdgeRingBuffer(capacity=128)
    for _ in range(7):
        frozen_buf.push(26.0, 1013.0, 60.0)
    res_frozen = run_level1_edge_inference(frozen_buf, 26.0, 1013.0, 60.0)
    assert res_frozen["status"] == "anomaly_detected"
    assert res_frozen["anomaly_flag"] is True
    assert res_frozen["anomaly_type"] == "frozen_value"


def test_backend_edge_ingest_endpoint():
    buf = VirtualEdgeRingBuffer(capacity=128)
    with TestClient(app) as client:
        # Switch to dedicated edge testing mode
        client.post("/api/system-mode", json={"mode": "edge", "station_id": "AWS-CHN-024"})

        try:
            # 1. Send normal observation
            pkt1 = build_observation_packet(buf, "AWS-CHN-024", 1, 28.5, 1012.3, 62.0)
            res1 = client.post("/api/ingest/observation", json=pkt1)
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["accepted"] is True
            assert data1["event_id"] == pkt1["event_id"]
            assert data1["edge_status"] == "ok"

            # 2. Test Idempotency / Duplicate
            res_dup = client.post("/api/ingest/observation", json=pkt1)
            assert res_dup.status_code == 200
            assert res_dup.json()["status"] == "duplicate_acknowledged"

            # 3. Send Edge Anomaly (Dropout)
            pkt2 = build_observation_packet(buf, "AWS-CHN-024", 2, float("nan"), 1012.3, 62.0)
            res2 = client.post("/api/ingest/observation", json=pkt2)
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["accepted"] is True
            assert data2["edge_status"] == "anomaly_detected"

            # 4. Verify system current-reading endpoint reflects the edge update
            cur = client.get("/api/current-reading?station_id=AWS-CHN-024")
            assert cur.status_code == 200
            cur_data = cur.json()
            assert cur_data["station_id"] == "AWS-CHN-024"
            assert cur_data["source"] == "edge"
        finally:
            client.post("/api/system-mode", json={"mode": "live"})

print("Test suite defined successfully.")
