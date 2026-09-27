"""
SkyGuard AI — Stream CSV Telemetry to ESP32 Edge Node over Serial

Provides a dignified serial streaming interface for feeding meteorological data
into ESP32 microcontrollers.

Usage:
    python scripts/stream_to_esp32.py --port COM5 --csv data/AWS-CHN-024.csv --interval 2.0
"""

import argparse
import json
import time
import sys
from pathlib import Path
import pandas as pd
import serial
import serial.tools.list_ports


def list_available_ports():
    ports = serial.tools.list_ports.comports()
    print("\n┌─ Available Serial Ports ───────────────────────────────────────────────┐")
    for p in ports:
        print(f"│  {p.device:<8} : {p.description:<56} │")
    print("└────────────────────────────────────────────────────────────────────────┘\n")


def stream_csv(port: str, baudrate: int, csv_path: str, interval: float, max_rows: int):
    print("┌────────────────────────────────────────────────────────────────────────┐")
    print("│             SkyGuard AI — ESP32 Telemetry Serial Streamer              │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print(f"│  Target Port      : {port:<51} │")
    print(f"│  Baud Rate        : {baudrate:<51} │")
    print(f"│  CSV Dataset      : {csv_path:<51} │")
    print(f"│  Pacing Interval  : {f'{interval}s per observation':<51} │")
    print("└────────────────────────────────────────────────────────────────────────┘\n")

    if not Path(csv_path).exists():
        print(f"[Error] Telemetry file not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    total_rows = len(df) if not max_rows else min(len(df), max_rows)
    print(f"  ✓ Loaded {len(df)} rows from {csv_path}. Streaming {total_rows} frames...\n")

    try:
        ser = serial.Serial(port, baudrate=baudrate, timeout=1.0)
        time.sleep(1.5)  # Wait for ESP32 serial reset

        count = 0
        for idx, row in df.iterrows():
            if max_rows and count >= max_rows:
                break

            payload = {
                "station_id": str(row.get("station_id", "AWS-CHN-024")),
                "timestamp": str(row.get("timestamp", pd.Timestamp.now(tz="UTC").isoformat())),
                "temperature_c": None if pd.isna(row.get("temperature_c")) else float(row.get("temperature_c")),
                "pressure_hpa": None if pd.isna(row.get("pressure_hpa")) else float(row.get("pressure_hpa")),
                "humidity_pct": None if pd.isna(row.get("humidity_pct")) else float(row.get("humidity_pct")),
            }

            line = json.dumps(payload) + "\n"
            ser.write(line.encode("utf-8"))

            t_val = f"{payload['temperature_c']:.1f}°C" if payload['temperature_c'] is not None else "N/A"
            p_val = f"{payload['pressure_hpa']:.1f} hPa" if payload['pressure_hpa'] is not None else "N/A"
            rh_val = f"{payload['humidity_pct']:.1f}%" if payload['humidity_pct'] is not None else "N/A"

            count += 1
            print(f"┌─ [{count:03d}/{total_rows:03d}] Sent: Temp: {t_val:<8} | Pressure: {p_val:<11} | RH: {rh_val:<7}")

            start_wait = time.time()
            while time.time() - start_wait < interval:
                if ser.in_waiting:
                    out = ser.readline().decode("utf-8", errors="replace").strip()
                    if out:
                        print(f"│  ↳ [ESP32 Response] {out}")
                time.sleep(0.05)
            print("└────────────────────────────────────────────────────────────────────────")

    except KeyboardInterrupt:
        print("\n[Streamer] Streaming interrupted by operator.")
    except Exception as e:
        print(f"\n[Error] Serial port error: {e}")
    finally:
        try:
            ser.close()
            print("  ✓ Serial port closed cleanly.")
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream CSV data to ESP32 over Serial.")
    parser.add_argument("--port", type=str, default=None, help="COM port (e.g. COM3, COM4, COM5)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--csv", type=str, default="data/AWS-CHN-024.csv", help="CSV file path")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval in seconds between rows (default: 2.0)")
    parser.add_argument("--max-rows", type=int, default=0, help="Max rows to stream (0 for all)")
    parser.add_argument("--list-ports", action="store_true", help="List available COM ports and exit")

    args = parser.parse_args()

    if args.list_ports or not args.port:
        list_available_ports()
        if not args.port:
            print("Please specify a port with --port <PORT_NAME>, for example: python scripts/stream_to_esp32.py --port COM5")
    else:
        stream_csv(args.port, args.baud, args.csv, args.interval, args.max_rows)
