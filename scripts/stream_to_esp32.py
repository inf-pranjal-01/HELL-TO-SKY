"""
SkyGuard AI — Stream CSV Telemetry to ESP32 Edge Node over Serial

Usage:
    python scripts/stream_to_esp32.py --port COM3 --csv data/AWS-CHN-024.csv --interval 2.0
"""

import argparse
import json
import time
import pandas as pd
import serial
import serial.tools.list_ports

def list_available_ports():
    ports = serial.tools.list_ports.comports()
    print("\n--- Available COM Ports ---")
    for p in ports:
        print(f"  {p.device}: {p.description} (VID: {p.vid}, PID: {p.pid})")
    print("---------------------------\n")

def stream_csv(port: str, baudrate: int, csv_path: str, interval: float, max_rows: int):
    print(f"Opening Serial port {port} at {baudrate} baud...")
    ser = serial.Serial(port, baudrate=baudrate, timeout=1.0)
    time.sleep(2.0)  # Wait for ESP32 serial boot / reset

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}. Beginning streaming (interval: {interval}s)...")

    count = 0
    try:
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
            print(f"[{count+1}] Sent: {line.strip()}")

            # Read any responses or logs from ESP32
            start_wait = time.time()
            while time.time() - start_wait < interval:
                if ser.in_waiting:
                    out = ser.readline().decode("utf-8", errors="replace").strip()
                    if out:
                        print(f"  [ESP32] {out}")
                time.sleep(0.05)

            count += 1
    except KeyboardInterrupt:
        print("\nStreaming interrupted by user.")
    finally:
        ser.close()
        print("Serial port closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream CSV data to ESP32 over Serial.")
    parser.add_argument("--port", type=str, default=None, help="COM port (e.g., COM3, COM4, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--csv", type=str, default="data/AWS-CHN-024.csv", help="CSV file path")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval in seconds between rows")
    parser.add_argument("--max-rows", type=int, default=100, help="Max rows to stream (0 for all)")
    parser.add_argument("--list-ports", action="store_true", help="List available COM ports and exit")

    args = parser.parse_args()

    if args.list_ports or not args.port:
        list_available_ports()
        if not args.port:
            print("Please specify a port with --port <PORT_NAME>, for example: python scripts/stream_to_esp32.py --port COM3")
    else:
        stream_csv(args.port, args.baud, args.csv, args.interval, args.max_rows)
