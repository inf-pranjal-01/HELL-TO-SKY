"""
SkyGuard AI — Virtual ESP32 Level 1 Edge Node Emulator

Replicates the exact C/C++ firmware behavior of the physical ESP32 node:
1. Level 1 Deterministic Edge Inference (Dropout, Fail-Low, Physical Bounds).
2. Canonical ObservationPacket JSON serialization with RFC 4122 UUIDv4.
3. Wi-Fi HTTP POST ingestion to POST /api/ingest/observation with bounded retries.
4. Latency benchmarking and anomaly simulation.

Usage:
    python scripts/virtual_esp32_node.py --csv data/AWS-CHN-024.csv --interval 1.0 --rows 20
    python scripts/virtual_esp32_node.py --inject-faults
"""

import argparse
import math
import time
import uuid
from datetime import datetime, timezone
import pandas as pd
import requests

# --- Level 1 Edge Rules Thresholds (Identical to edge_engine.h / edge_engine.cpp) ---
EDGE_TEMP_PHYSICAL_MIN = -40.0
EDGE_TEMP_PHYSICAL_MAX = 60.0
EDGE_PRESSURE_PHYSICAL_MIN = 800.0
EDGE_PRESSURE_PHYSICAL_MAX = 1100.0
EDGE_HUMIDITY_PHYSICAL_MIN = 0.0
EDGE_HUMIDITY_PHYSICAL_MAX = 100.0

EDGE_TEMP_FAIL_LOW = -50.0
EDGE_PRESSURE_FAIL_LOW = 300.0
EDGE_HUMIDITY_FAIL_LOW = 0.0

FIRMWARE_VERSION = "esp32_edge_v2.0.0"
EDGE_MODEL_VERSION = "edge_rules_v2.0.0"
EDGE_INFERENCE_METHOD = "temporal_rules_and_buffers"
VIRTUAL_DEVICE_ID = "esp32-node-VIRTUAL-DEMO-01"

EDGE_TEMP_MAX_STEP_ROC = 4.0
EDGE_PRESSURE_MAX_STEP_ROC = 6.0
EDGE_HUMIDITY_MAX_STEP_ROC = 20.0
FROZEN_WINDOW_LEN = 6


class VirtualEdgeRingBuffer:
    def __init__(self, capacity=128):
        self.capacity = capacity
        self.samples = []
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0

    def push(self, temp_c, pressure_hpa, humidity_pct):
        self.samples.append({
            "temp_c": temp_c,
            "pressure_hpa": pressure_hpa,
            "humidity_pct": humidity_pct,
        })
        if len(self.samples) > self.capacity:
            self.samples.pop(0)


def run_level1_edge_inference(buf: VirtualEdgeRingBuffer, temp_c, pressure_hpa, humidity_pct) -> dict:
    """
    Exact Python mirror of the upgraded C++ run_edge_inference_temporal function.
    """
    # 1. Precedence 1: Dropout (NaN / missing)
    if temp_c is None or math.isnan(temp_c):
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "dropout", "score": 100.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}
    if pressure_hpa is None or math.isnan(pressure_hpa):
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "dropout", "score": 100.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}
    if humidity_pct is None or math.isnan(humidity_pct):
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "dropout", "score": 100.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}

    # 2. Precedence 2: Sensor Fail-Low / Ground collapse
    if temp_c <= EDGE_TEMP_FAIL_LOW:
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "sensor_fail_low", "score": 100.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}
    if pressure_hpa <= EDGE_PRESSURE_FAIL_LOW:
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "sensor_fail_low", "score": 100.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}
    if humidity_pct <= EDGE_HUMIDITY_FAIL_LOW:
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "sensor_fail_low", "score": 100.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}

    # 3. Precedence 3: Physical Surface Meteorological Bounds
    if (temp_c < EDGE_TEMP_PHYSICAL_MIN or temp_c > EDGE_TEMP_PHYSICAL_MAX or
        pressure_hpa < EDGE_PRESSURE_PHYSICAL_MIN or pressure_hpa > EDGE_PRESSURE_PHYSICAL_MAX or
        humidity_pct < EDGE_HUMIDITY_PHYSICAL_MIN or humidity_pct > EDGE_HUMIDITY_PHYSICAL_MAX):
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "physical_bounds", "score": 95.0, "score_type": "rule", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}

    # 4. Precedence 4: Cross-Channel Thermodynamic Impossibility (Clausius-Clapeyron)
    if temp_c > 42.0 and humidity_pct > 65.0:
        return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "multivariate_inconsistency", "score": 90.0, "score_type": "physics", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}

    # --- TEMPORAL RING BUFFER CHECKS ---
    if buf and len(buf.samples) > 0:
        prev = buf.samples[-1]
        
        # 5. Precedence 5: Step Derivative Spike
        d_temp = abs(temp_c - prev["temp_c"])
        d_pres = abs(pressure_hpa - prev["pressure_hpa"])
        d_hum = abs(humidity_pct - prev["humidity_pct"])
        if d_temp > EDGE_TEMP_MAX_STEP_ROC or d_pres > EDGE_PRESSURE_MAX_STEP_ROC or d_hum > EDGE_HUMIDITY_MAX_STEP_ROC:
            return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "spike", "score": 88.0, "score_type": "temporal_derivative", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}

        # 6. Precedence 6: Frozen Value (Stuck Sensor)
        if len(buf.samples) >= FROZEN_WINDOW_LEN:
            recent = buf.samples[-FROZEN_WINDOW_LEN:]
            if all(abs(temp_c - s["temp_c"]) < 0.001 for s in recent) or \
               all(abs(pressure_hpa - s["pressure_hpa"]) < 0.001 for s in recent) or \
               all(abs(humidity_pct - s["humidity_pct"]) < 0.001 for s in recent):
                return {"status": "anomaly_detected", "anomaly_flag": True, "anomaly_type": "frozen_value", "score": 92.0, "score_type": "temporal_variance", "model_version": EDGE_MODEL_VERSION, "inference_method": EDGE_INFERENCE_METHOD}

    # 7. Clean reading: push to buffer
    buf.push(temp_c, pressure_hpa, humidity_pct)
    return {
        "status": "ok",
        "anomaly_flag": False,
        "anomaly_type": None,
        "score": 5.0,
        "score_type": None,
        "model_version": EDGE_MODEL_VERSION,
        "inference_method": EDGE_INFERENCE_METHOD,
    }


def build_observation_packet(
    buf: VirtualEdgeRingBuffer,
    station_id: str,
    sequence_num: int,
    temp_c: float,
    pressure_hpa: float,
    humidity_pct: float,
    observed_at: str = None,
    rssi: float = -58.0,
) -> dict:
    """
    Constructs the canonical JSON payload identical to packet_builder.cpp.
    """
    event_id = str(uuid.uuid4())
    if not observed_at:
        observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    edge_result = run_level1_edge_inference(buf, temp_c, pressure_hpa, humidity_pct)

    return {
        "event_id": event_id,
        "station_id": station_id,
        "device_id": VIRTUAL_DEVICE_ID,
        "observed_at": observed_at,
        "sequence_number": sequence_num,
        "readings": {
            "temperature_c": None if (temp_c is None or math.isnan(temp_c)) else round(temp_c, 2),
            "pressure_hpa": None if (pressure_hpa is None or math.isnan(pressure_hpa)) else round(pressure_hpa, 2),
            "humidity_pct": None if (humidity_pct is None or math.isnan(humidity_pct)) else round(humidity_pct, 2),
        },
        "edge_inference": edge_result,
        "device_metadata": {
            "firmware_version": FIRMWARE_VERSION,
            "battery_voltage": None,
            "signal_strength": rssi,
        }
    }


def send_packet_with_retry(endpoint_url: str, packet: dict, max_retries: int = 3, base_backoff_s: float = 0.5):
    """
    Sends packet with bounded exponential backoff identical to http_poster.cpp.
    """
    for attempt in range(max_retries + 1):
        if attempt > 0:
            backoff = base_backoff_s * (2 ** (attempt - 1))
            print(f"  [Retry] Attempt {attempt}/{max_retries} after {backoff:.2f}s...")
            time.sleep(backoff)

        t0 = time.perf_counter()
        try:
            res = requests.post(
                endpoint_url,
                json=packet,
                headers={"Content-Type": "application/json"},
                timeout=5.0,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return res.status_code, res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text, elapsed_ms
        except requests.RequestException as e:
            if attempt == max_retries:
                return 0, str(e), 0.0
    return 0, "Max retries exceeded", 0.0


def run_virtual_esp32_simulation(
    endpoint_url: str,
    csv_path: str,
    interval: float,
    max_rows: int,
    test_faults: bool = False,
    faults_only: bool = False,
):
    print("=" * 75)
    print("       SkyGuard AI — Virtual ESP32 Level 1 Edge Node Benchmark")
    print(f"  Firmware: {FIRMWARE_VERSION} | Model: {EDGE_MODEL_VERSION}")
    print(f"  Target Endpoint: {endpoint_url}")
    print(f"  Dataset: {csv_path}")
    print("=" * 75)

    df = pd.read_csv(csv_path)
    station_id = str(df["station_id"].iloc[0]) if "station_id" in df.columns else "AWS-CHN-024"
    has_ground_truth = "is_anomaly" in df.columns or "fault_type" in df.columns

    if faults_only and has_ground_truth:
        df = df[df["is_anomaly"] == True].copy()
        print(f"\n[Filter] Extracted {len(df)} fault-injected rows from dataset.\n")
    elif max_rows > 0:
        df = df.iloc[:max_rows].copy()

    total_to_stream = len(df)
    print(f"\nStreaming {total_to_stream} rows (Station: {station_id}) at {interval}s cadence...\n")

    seq = 1
    total_rtt = 0.0
    success_count = 0

    # Metrics Tracking
    edge_detections = {
        "dropout": 0,
        "sensor_fail_low": 0,
        "physical_bounds": 0,
        "spike": 0,
        "frozen_value": 0,
        "drift": 0,
        "multivariate_inconsistency": 0,
        "total": 0,
    }
    backend_detections = {"total": 0, "by_type": {}}
    ground_truth_faults = 0

    edge_buf = VirtualEdgeRingBuffer(capacity=128)
    t_start = time.perf_counter()

    for idx, row in df.iterrows():
        t = None if pd.isna(row.get("temperature_c")) else float(row.get("temperature_c"))
        p = None if pd.isna(row.get("pressure_hpa")) else float(row.get("pressure_hpa"))
        h = None if pd.isna(row.get("humidity_pct")) else float(row.get("humidity_pct"))
        ts = str(row.get("timestamp", "")) if not pd.isna(row.get("timestamp")) else None

        true_is_anom = bool(row.get("is_anomaly", False)) if "is_anomaly" in row else False
        true_fault_type = str(row.get("fault_type", "normal")) if not pd.isna(row.get("fault_type")) else "normal"
        if true_is_anom:
            ground_truth_faults += 1

        packet = build_observation_packet(edge_buf, station_id, seq, t, p, h, observed_at=ts)

        edge_flag = packet["edge_inference"]["anomaly_flag"]
        edge_type = packet["edge_inference"]["anomaly_type"]
        if edge_flag:
            edge_detections["total"] += 1
            if edge_type in edge_detections:
                edge_detections[edge_type] += 1

        status_str = f"EDGE:{edge_type}" if edge_flag else "EDGE:OK"

        code, resp, rtt = send_packet_with_retry(endpoint_url, packet)

        if code == 200:
            success_count += 1
            total_rtt += rtt
            b_verdict = resp.get("backend_verdict", {}) if isinstance(resp, dict) else {}
            b_anom = b_verdict.get("is_anomaly", False)
            b_type = b_verdict.get("fault_type") or "none"
            if b_anom:
                backend_detections["total"] += 1
                backend_detections["by_type"][b_type] = backend_detections["by_type"].get(b_type, 0) + 1

            # Log row if either Edge or Backend detected an anomaly, or if sampling periodically
            is_interesting = edge_flag or b_anom or true_is_anom or (seq % 20 == 1)
            if is_interesting or interval >= 0.2:
                t_display = f"{t:.1f}°C" if t is not None else "NaN"
                p_display = f"{p:.1f}hPa" if p is not None else "NaN"
                h_display = f"{h:.1f}%" if h is not None else "NaN"
                
                gt_tag = f" [GT: {true_fault_type}]" if true_is_anom else ""
                print(f"[{seq:04d}/{total_to_stream:04d}] T:{t_display:<7} P:{p_display:<9} RH:{h_display:<6} | {status_str:<25} | BACKEND:{'ANOMALY ('+b_type+')' if b_anom else 'OK':<25} | HTTP {code} ({rtt:.1f}ms){gt_tag}", flush=True)
            elif seq % 10 == 0:
                print(f"  ... Ingested {seq}/{total_to_stream} rows (Latency: {rtt:.1f}ms) ...", flush=True)
        else:
            print(f"[{seq:04d}/{total_to_stream:04d}] ERROR: HTTP {code} -> {resp}", flush=True)

        seq += 1
        if interval > 0:
            time.sleep(interval)

    total_time = time.perf_counter() - t_start
    avg_rtt = (total_rtt / success_count) if success_count else 0.0

    print("\n" + "=" * 75, flush=True)
    print("                      STREAMING BENCHMARK REPORT", flush=True)
    print("=" * 75, flush=True)
    print(f"Total Rows Streamed       : {success_count}/{total_to_stream}", flush=True)
    print(f"Total Elapsed Time        : {total_time:.2f}s ({success_count/total_time:.1f} rows/sec)", flush=True)
    print(f"Avg Round-Trip Latency    : {avg_rtt:.2f} ms", flush=True)
    if has_ground_truth:
        print(f"Ground-Truth Anomaly Rows : {ground_truth_faults}", flush=True)
    print("-" * 75, flush=True)
    print("LEVEL 1 EDGE DETECTIONS (ESP32 Firmware On-Chip Ring Buffer & Rules):", flush=True)
    print(f"  • Total Edge Flags          : {edge_detections['total']}", flush=True)
    print(f"    - Sensor Dropouts         : {edge_detections['dropout']}", flush=True)
    print(f"    - Sensor Fail-Low         : {edge_detections['sensor_fail_low']}", flush=True)
    print(f"    - Physical Bounds         : {edge_detections['physical_bounds']}", flush=True)
    print(f"    - Rate-of-Change Spikes   : {edge_detections['spike']}", flush=True)
    print(f"    - Frozen / Stuck Sensor   : {edge_detections['frozen_value']}", flush=True)
    print(f"    - Thermodynamic Invariant : {edge_detections['multivariate_inconsistency']}", flush=True)
    print(f"    - Calibration Drift       : {edge_detections['drift']}", flush=True)
    print("-" * 75, flush=True)
    print("LEVEL 2 BACKEND DETECTIONS (Spatial Consensus + ML Models):", flush=True)
    print(f"  • Total Backend Flags       : {backend_detections['total']}", flush=True)
    for k, v in sorted(backend_detections["by_type"].items()):
        print(f"    - {k:<26}: {v}", flush=True)
    print("=" * 75 + "\n", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Virtual ESP32 Edge Node Benchmark & Telemetry Streamer.")
    parser.add_argument("--url", type=str, default="http://localhost:8000/api/ingest/observation", help="Ingestion URL")
    parser.add_argument("--csv", type=str, default="data/AWS-CHN-024_labeled.csv", help="CSV dataset path")
    parser.add_argument("--interval", type=float, default=0.01, help="Transmission interval in seconds (default: 0.01s for rapid benchmark, 1.0s or 2.0s for real-time)")
    parser.add_argument("--rows", type=int, default=0, help="Number of rows to stream (0 for all rows in CSV)")
    parser.add_argument("--faults-only", action="store_true", help="Stream only fault-injected rows")
    parser.add_argument("--inject-faults", action="store_true", help="Run synthetic fault injection suite")

    args = parser.parse_args()
    if args.inject_faults:
        run_virtual_esp32_simulation(args.url, args.csv, 0.5, 6, test_faults=True)
    else:
        run_virtual_esp32_simulation(args.url, args.csv, args.interval, args.rows, test_faults=False, faults_only=args.faults_only)
