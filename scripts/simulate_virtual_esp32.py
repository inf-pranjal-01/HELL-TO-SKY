"""
SkyGuard AI — Virtual ESP32 Hardware Emulator & Telemetry Streamer

Simulates the physical ESP32 DevKit V1 edge microcontroller running the
Level 1 C++ Edge AI Engine. Emulates live hardware packet streaming over Wi-Fi
to the Central FastAPI Backend (POST /api/ingest/observation).

No physical ESP32 hardware or COM serial port required.

Features:
1. Live UTC Timestamping: Guarantees immediate frontend chart rendering and WebSocket updates.
2. Continuous Labeled Telemetry Stream: Loops through real AWS sensor datasets.
3. Interactive Anomaly Injection: Trigger spikes, frozen sensors, ground collapse, and thermodynamic violations on the fly.
4. Watchdog Timeout Verification: Simulates edge disconnect to test the 35s auto-exit to Live Mode.

Usage:
    python scripts/simulate_virtual_esp32.py
    python scripts/simulate_virtual_esp32.py --station AWS-CHN-024 --interval 2.0
    python scripts/simulate_virtual_esp32.py --mode inject
    python scripts/simulate_virtual_esp32.py --test-timeout
    python scripts/simulate_virtual_esp32.py --interactive
"""

import argparse
import json
import math
import sys
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
import pandas as pd

# Ensure UTF-8 output encoding across Windows shells
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# Level 1 Physical Meteorological Invariants
EDGE_TEMP_MIN = -40.0
EDGE_TEMP_MAX = 60.0
EDGE_PRES_MIN = 800.0
EDGE_PRES_MAX = 1100.0
EDGE_HUM_MIN = 0.0
EDGE_HUM_MAX = 100.0

EDGE_TEMP_FAIL_LOW = -50.0
EDGE_PRES_FAIL_LOW = 300.0
EDGE_HUM_FAIL_LOW = 0.0

ROC_TEMP_MAX = 4.0
ROC_PRES_MAX = 6.0
ROC_HUM_MAX = 20.0
FROZEN_WINDOW_LEN = 5


class VirtualEdgeBuffer:
    def __init__(self, capacity=64):
        self.capacity = capacity
        self.samples = []

    def push(self, temp_c, pres_hpa, hum_pct):
        if temp_c is not None and pres_hpa is not None and hum_pct is not None:
            self.samples.append({"temp_c": temp_c, "pres_hpa": pres_hpa, "hum_pct": hum_pct})
            if len(self.samples) > self.capacity:
                self.samples.pop(0)


def evaluate_edge_l1(buf: VirtualEdgeBuffer, t, p, h) -> dict:
    """Simulates on-device Level 1 C++ firmware inference (<20 microseconds)."""
    # 1. Tier 1: Dropout
    if t is None or p is None or h is None or math.isnan(t) or math.isnan(p) or math.isnan(h):
        return {
            "status": "CERTAIN_FAULT",
            "is_anomaly": True,
            "tier_fired": 1,
            "anomaly_type": "dropout",
            "confidence_llr": 4.50,
            "latency_ms": 0.008,
        }

    # 2. Tier 2: Ground Collapse / Sensor Fail Low
    if t <= EDGE_TEMP_FAIL_LOW or p <= EDGE_PRES_FAIL_LOW or h <= EDGE_HUM_FAIL_LOW:
        return {
            "status": "CERTAIN_FAULT",
            "is_anomaly": True,
            "tier_fired": 2,
            "anomaly_type": "sensor_fail_low",
            "confidence_llr": 4.20,
            "latency_ms": 0.011,
        }

    # 3. Tier 3: Physical Surface Meteorological Bounds
    if (t < EDGE_TEMP_MIN or t > EDGE_TEMP_MAX or
        p < EDGE_PRES_MIN or p > EDGE_PRES_MAX or
        h < EDGE_HUM_MIN or h > EDGE_HUM_MAX):
        return {
            "status": "CERTAIN_FAULT",
            "is_anomaly": True,
            "tier_fired": 3,
            "anomaly_type": "physical_bounds",
            "confidence_llr": 3.80,
            "latency_ms": 0.012,
        }

    # 4. Tier 4: Thermodynamic Clausius-Clapeyron Violation
    if t > 42.0 and h > 65.0:
        return {
            "status": "EDGE_ADVISORY",
            "is_anomaly": True,
            "tier_fired": 4,
            "anomaly_type": "multivariate_inconsistency",
            "confidence_llr": 2.90,
            "latency_ms": 0.014,
        }

    # 5. Temporal Rate of Change & Frozen Value
    if buf and len(buf.samples) > 0:
        prev = buf.samples[-1]
        dt = abs(t - prev["temp_c"])
        dp = abs(p - prev["pres_hpa"])
        dh = abs(h - prev["hum_pct"])

        if dt > ROC_TEMP_MAX or dp > ROC_PRES_MAX or dh > ROC_HUM_MAX:
            return {
                "status": "EDGE_ADVISORY",
                "is_anomaly": True,
                "tier_fired": 5,
                "anomaly_type": "spike",
                "confidence_llr": 2.50,
                "latency_ms": 0.016,
            }

        if len(buf.samples) >= FROZEN_WINDOW_LEN:
            recent = buf.samples[-FROZEN_WINDOW_LEN:]
            if (all(abs(t - s["temp_c"]) < 0.001 for s in recent) or
                all(abs(p - s["pres_hpa"]) < 0.001 for s in recent) or
                all(abs(h - s["hum_pct"]) < 0.001 for s in recent)):
                return {
                    "status": "EDGE_ADVISORY",
                    "is_anomaly": True,
                    "tier_fired": 5,
                    "anomaly_type": "frozen_value",
                    "confidence_llr": 2.70,
                    "latency_ms": 0.018,
                }

    buf.push(t, p, h)
    return {
        "status": "SAFE_FORWARD",
        "is_anomaly": False,
        "tier_fired": 5,
        "anomaly_type": "none",
        "confidence_llr": 0.05,
        "latency_ms": 0.015,
    }


def send_observation_packet(endpoint_url: str, packet: dict) -> tuple[int, dict, float]:
    """Posts observation packet to Central Backend over HTTP."""
    t0 = time.perf_counter()
    req_data = json.dumps(packet).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body, elapsed_ms
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"error": str(e)}
        return e.code, body, elapsed_ms
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return 0, {"error": str(e)}, elapsed_ms


def stream_dataset(
    endpoint_url: str,
    station_id: str,
    csv_path: str,
    interval: float,
    max_packets: int = 0,
    faults_only: bool = False,
    use_dataset: bool = False,
):
    mode_label = "Historical CSV Dataset Replay" if use_dataset else "Live Real-Time Physical Sensor Emulation"
    print("┌────────────────────────────────────────────────────────────────────────┐")
    print("│         SkyGuard AI — Virtual ESP32 Edge Telemetry Streamer            │")
    print("│       Continuous-Time Causal Edge AI Engine • Live Ingestion           │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print(f"│  Target Station   : {station_id:<51} │")
    print(f"│  Stream Mode      : {mode_label:<51} │")
    print(f"│  Ingestion URL    : {endpoint_url:<51} │")
    print(f"│  Pacing Interval  : {f'{interval}s per packet':<51} │")
    print("└────────────────────────────────────────────────────────────────────────┘\n")

    if not Path(csv_path).exists():
        # Fallback to synthetic if CSV does not exist
        print(f"[Notice] CSV '{csv_path}' not found. Generating real-time synthetic weather stream.\n")
        df = None
    else:
        df = pd.read_csv(csv_path)
        if faults_only and "is_anomaly" in df.columns:
            df = df[df["is_anomaly"] == True].copy()
            print(f"  ✓ Filtered {len(df)} fault-injected ground truth rows.\n")
        else:
            print(f"  ✓ Loaded {len(df)} telemetry rows from dataset.\n")

    buf = VirtualEdgeBuffer(capacity=64)
    count = 0
    df_idx = 0
    total_rows = len(df) if df is not None else 0

    # Realistic physical baseline matching current Indian regional climates
    station_baselines = {
        "AWS-CHN-024": {"temp": 32.5, "pres": 1012.0, "hum": 62.0},
        "AWS-DEL-011": {"temp": 34.0, "pres": 1008.0, "hum": 45.0},
        "AWS-MUM-007": {"temp": 31.0, "pres": 1011.5, "hum": 75.0},
        "AWS-KOL-015": {"temp": 31.5, "pres": 1010.0, "hum": 70.0},
        "AWS-BHO-030": {"temp": 30.0, "pres": 1013.0, "hum": 55.0},
        "AWS-VAR-052": {"temp": 32.0, "pres": 1009.5, "hum": 58.0},
    }
    base = station_baselines.get(station_id, {"temp": 31.0, "pres": 1011.0, "hum": 60.0})
    curr_temp = base["temp"]
    curr_pres = base["pres"]
    curr_hum = base["hum"]

    print("══════════════════════════════════════════════════════════════════════════")
    print(f"  STREAMING LIVE EDGE PACKETS TO SKYGUARD AI BACKEND (PACING: {interval}s)")
    print("  Press Ctrl+C at any time to pause or exit.")
    print("══════════════════════════════════════════════════════════════════════════\n")

    try:
        while True:
            count += 1
            if max_packets > 0 and count > max_packets:
                print(f"\n[Completed] Finished streaming target of {max_packets} packets.")
                break

            now_ts = pd.Timestamp.now(tz="UTC").isoformat()

            if use_dataset and df is not None and total_rows > 0:
                row = df.iloc[df_idx % total_rows]
                df_idx += 1
                t_val = None if pd.isna(row.get("temperature_c")) else float(row.get("temperature_c"))
                p_val = None if pd.isna(row.get("pressure_hpa")) else float(row.get("pressure_hpa"))
                h_val = None if pd.isna(row.get("humidity_pct")) else float(row.get("humidity_pct"))
                gt_anom = bool(row.get("is_anomaly", False)) if "is_anomaly" in row else False
                gt_fault = str(row.get("fault_type", "nominal")) if pd.notna(row.get("fault_type")) else "nominal"
            else:
                # Realistic physical high-frequency sensor signal with subtle micro-fluctuations (clean blue baseline)
                # Sensor transducer Brownian micro-drift within +/- 0.05 degC per reading
                micro_t = (math.sin(count * 0.15) * 0.2) + ((count % 7) * 0.02 - 0.06)
                micro_p = (math.cos(count * 0.12) * 0.1) + ((count % 5) * 0.02 - 0.04)
                micro_h = (math.sin(count * 0.10) * 0.4) + ((count % 9) * 0.05 - 0.20)
                
                t_val = round(curr_temp + micro_t, 2)
                p_val = round(curr_pres + micro_p, 1)
                h_val = round(curr_hum + micro_h, 1)
                gt_anom = False
                gt_fault = "nominal"

            # Execute simulated Level 1 edge inference
            edge_l1 = evaluate_edge_l1(buf, t_val, p_val, h_val)

            packet = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "station_id": station_id,
                "device_id": "esp32-devkit-v1-virtual",
                "observed_at": now_ts,
                "sequence_number": count,
                "readings": {
                    "temperature_c": t_val,
                    "pressure_hpa": p_val,
                    "humidity_pct": h_val,
                },
                "edge_inference": {
                    "status": edge_l1["status"],
                    "decision": edge_l1["status"],
                    "is_anomaly": edge_l1["is_anomaly"],
                    "tier_fired": edge_l1["tier_fired"],
                    "anomaly_type": edge_l1["anomaly_type"],
                    "confidence_llr": edge_l1["confidence_llr"],
                    "latency_ms": edge_l1["latency_ms"],
                    "source": "esp32_virtual_emulator",
                },
            }

            status_code, resp_body, rtt_ms = send_observation_packet(endpoint_url, packet)

            t_disp = f"{t_val:.1f}°C" if t_val is not None else "N/A"
            p_disp = f"{p_val:.1f} hPa" if p_val is not None else "N/A"
            h_disp = f"{h_val:.1f}%" if h_val is not None else "N/A"

            status_icon = "🟢" if not edge_l1["is_anomaly"] else "⚠️"
            print(f"┌─ [Packet #{count:04d}] ── {station_id} @ {now_ts} ── {rtt_ms:.1f}ms RTT")
            print(f"│  Readings  : Temp: {t_disp:<8} | Pres: {p_disp:<11} | RH: {h_disp:<7}")
            print(f"│  Edge L1   : {status_icon} {edge_l1['status']:<14} | Tier: {edge_l1['tier_fired']} | Fault: {edge_l1['anomaly_type']:<15} | LLR: {edge_l1['confidence_llr']:.2f}")
            if status_code == 200:
                print(f"│  Central L2: ✓ Ingested (200 OK) ── WebSocket Broadcast Active")
            else:
                print(f"│  Central L2: ✗ HTTP {status_code}: {resp_body.get('error', resp_body)}")
            print("└────────────────────────────────────────────────────────────────────────\n")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[Streamer] Stream paused by user. System will enter watchdog auto-exit if inactive for >35s.")


def run_timeout_test(endpoint_url: str, station_id: str, interval: float = 2.0):
    print("┌────────────────────────────────────────────────────────────────────────┐")
    print("│         SkyGuard AI — Inactivity Watchdog Timeout Verification         │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print("│  1. Streams 4 packets to arm ESP32 Edge Ingestion Mode.               │")
    print("│  2. Pauses transmission for 38 seconds.                                │")
    print("│  3. Frontend will display countdown and auto-switch back to Live Mode. │")
    print("└────────────────────────────────────────────────────────────────────────┘\n")

    buf = VirtualEdgeBuffer(capacity=16)
    print("==> [Phase 1/2] Sending 4 edge packets to establish ESP32 Mode...")
    for i in range(1, 5):
        now_ts = pd.Timestamp.now(tz="UTC").isoformat()
        packet = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "station_id": station_id,
            "device_id": "esp32-devkit-v1-virtual",
            "observed_at": now_ts,
            "sequence_number": i,
            "readings": {"temperature_c": 30.0 + i * 0.2, "pressure_hpa": 1011.5, "humidity_pct": 65.0},
            "edge_inference": {
                "status": "SAFE_FORWARD",
                "is_anomaly": False,
                "tier_fired": 5,
                "anomaly_type": "none",
                "confidence_llr": 0.05,
                "latency_ms": 0.015,
                "source": "esp32_virtual_emulator",
            }
        }
        send_observation_packet(endpoint_url, packet)
        print(f"  ✓ Packet #{i} sent successfully.")
        time.sleep(interval)

    print("\n==> [Phase 2/2] Packets stopped! Watch your browser dashboard (http://localhost:5173).")
    print("    Waiting 38 seconds for the 35s Inactivity Watchdog to trigger auto-exit...")
    for sec in range(38, 0, -1):
        sys.stdout.write(f"\r    ⏱️ Inactivity Watchdog Countdown: {sec:02d}s remaining... ")
        sys.stdout.flush()
        time.sleep(1.0)
    print("\n\n✓ 38 seconds elapsed! Check the frontend: System should now be back in Live Mode with notification banner.\n")


def run_interactive_injector(endpoint_url: str, station_id: str):
    print("┌────────────────────────────────────────────────────────────────────────┐")
    print("│         SkyGuard AI — Interactive ESP32 Edge Anomaly Injector          │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print("│  Press the corresponding number to inject an instant fault reading:    │")
    print("│  [1] Nominal Clean Reading (30.5°C, 1012 hPa, 65%)                     │")
    print("│  [2] Temperature Spike (+16°C Step Jump to 46.5°C)                     │")
    print("│  [3] Pressure Drop / Spike (-25 hPa Step Drop to 987 hPa)              │")
    print("│  [4] Frozen Sensor / Stuck Value (Send 6 identical readings)           │")
    print("│  [5] Physical Out-of-Bounds (68.0°C Extreme Heat)                      │")
    print("│  [6] Ground Collapse / Sensor Fail Low (-50.0°C)                       │")
    print("│  [7] Thermodynamic Clausius-Clapeyron Violation (45°C + 90% RH)        │")
    print("│  [8] Sensor Dropout / Missing Telemetry (NaN / Null)                   │")
    print("│  [q] Quit                                                              │")
    print("└────────────────────────────────────────────────────────────────────────┘\n")

    buf = VirtualEdgeBuffer(capacity=64)
    seq = 1

    while True:
        try:
            choice = input("Select fault injection command [1-8, q]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive injector.")
            break

        if choice == "q":
            print("Exiting interactive injector.")
            break

        now_ts = pd.Timestamp.now(tz="UTC").isoformat()
        t, p, h = 30.5, 1012.0, 65.0
        desc = "Nominal Clean Reading"

        if choice == "1":
            t, p, h = 30.5, 1012.0, 65.0
            desc = "Nominal Reading"
        elif choice == "2":
            t, p, h = 46.5, 1012.0, 65.0
            desc = "Temperature Spike (+16°C)"
        elif choice == "3":
            t, p, h = 30.5, 987.0, 65.0
            desc = "Pressure Step Drop (-25 hPa)"
        elif choice == "4":
            desc = "Frozen Stuck Values (Sending 6 packets)"
            for _ in range(6):
                now_ts = pd.Timestamp.now(tz="UTC").isoformat()
                edge_l1 = evaluate_edge_l1(buf, 28.0, 1013.0, 70.0)
                pkt = {
                    "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                    "station_id": station_id,
                    "device_id": "esp32-devkit-v1-virtual",
                    "observed_at": now_ts,
                    "sequence_number": seq,
                    "readings": {"temperature_c": 28.0, "pressure_hpa": 1013.0, "humidity_pct": 70.0},
                    "edge_inference": edge_l1,
                }
                send_observation_packet(endpoint_url, pkt)
                seq += 1
                time.sleep(0.3)
            print("  ✓ Injected 6 frozen readings successfully.\n")
            continue
        elif choice == "5":
            t, p, h = 68.0, 1012.0, 65.0
            desc = "Physical Out-of-Bounds (68°C)"
        elif choice == "6":
            t, p, h = -50.0, 1012.0, 65.0
            desc = "Sensor Fail Low / Ground Collapse (-50°C)"
        elif choice == "7":
            t, p, h = 45.0, 1012.0, 90.0
            desc = "Thermodynamic Inconsistency (45°C + 90% RH)"
        elif choice == "8":
            t, p, h = None, 1012.0, 65.0
            desc = "Sensor Dropout (Null Temperature)"
        else:
            print("Invalid selection. Choose [1-8] or 'q'.")
            continue

        edge_l1 = evaluate_edge_l1(buf, t, p, h)
        packet = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "station_id": station_id,
            "device_id": "esp32-devkit-v1-virtual",
            "observed_at": now_ts,
            "sequence_number": seq,
            "readings": {"temperature_c": t, "pressure_hpa": p, "humidity_pct": h},
            "edge_inference": edge_l1,
        }
        seq += 1

        code, body, rtt = send_observation_packet(endpoint_url, packet)
        print(f"  ✓ Injected: {desc} ── HTTP {code} ── {rtt:.1f}ms (Edge L1: {edge_l1['status']}, Type: {edge_l1['anomaly_type']})\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkyGuard AI — Virtual ESP32 Hardware Telemetry Emulator")
    parser.add_argument("--station", type=str, default="AWS-CHN-024", help="Target Station ID (default: AWS-CHN-024)")
    parser.add_argument("--url", type=str, default="http://localhost:8000/api/ingest/observation", help="FastAPI Ingestion Endpoint")
    parser.add_argument("--interval", type=float, default=2.0, help="Streaming interval in seconds (default: 2.0)")
    parser.add_argument("--csv", type=str, default="data/AWS-CHN-024_labeled.csv", help="Path to labeled dataset CSV")
    parser.add_argument("--dataset", action="store_true", help="Stream raw rows from CSV dataset instead of live real-time weather")
    parser.add_argument("--packets", type=int, default=0, help="Maximum number of packets to stream (0 for continuous)")
    parser.add_argument("--faults-only", action="store_true", help="Stream only anomaly/fault rows from the dataset")
    parser.add_argument("--test-timeout", action="store_true", help="Test the 35-second Inactivity Watchdog Auto-Exit")
    parser.add_argument("--interactive", action="store_true", help="Run interactive fault injection keyboard console")

    args = parser.parse_args()

    if args.test_timeout:
        run_timeout_test(args.url, args.station, args.interval)
    elif args.interactive:
        run_interactive_injector(args.url, args.station)
    else:
        stream_dataset(args.url, args.station, args.csv, args.interval, args.packets, args.faults_only, use_dataset=args.dataset or args.faults_only)
