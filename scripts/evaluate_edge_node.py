"""
SkyGuard AI — Automated Edge Node Performance & Accuracy Evaluator

Automated evaluation suite that computes:
1. Overall Metrics: Precision, Recall, F1-Score, Specificity, Accuracy, False Alarm Rate.
2. Granular Per-Fault-Type Breakdown: Dropout, Fail-Low, Physical Bounds, Spike, Frozen Value, Drift, Multivariate.
3. Micro-benchmark: Execution throughput (samples/sec) and microsecond latency per inference.

Usage:
    python scripts/evaluate_edge_node.py --station AWS-CHN-024
    python scripts/evaluate_edge_node.py --all-stations
    python scripts/evaluate_edge_node.py --save-csv data/edge_benchmark_summary.csv
"""

import argparse
import glob
import math
import os
import time
from pathlib import Path
import numpy as np
import pandas as pd

# Calibrated Constants from config.py
EDGE_TEMP_PHYSICAL_MIN = -50.0
EDGE_TEMP_PHYSICAL_MAX = 60.0
EDGE_PRESSURE_PHYSICAL_MIN = 850.0
EDGE_PRESSURE_PHYSICAL_MAX = 1085.0
EDGE_HUMIDITY_PHYSICAL_MIN = 0.0
EDGE_HUMIDITY_PHYSICAL_MAX = 100.0

EDGE_TEMP_FAIL_LOW = -8.0
EDGE_PRESSURE_FAIL_LOW = 150.0
EDGE_HUMIDITY_FAIL_LOW = 3.0

EDGE_TEMP_MAX_STEP_ROC = 6.0
EDGE_PRESSURE_MAX_STEP_ROC = 10.0
EDGE_HUMIDITY_MAX_STEP_ROC = 25.0

FROZEN_CONSECUTIVE_REQUIRED_TEMP = 5
FROZEN_CONSECUTIVE_REQUIRED_HUM = 5
FROZEN_CONSECUTIVE_REQUIRED_PRES = 8

CUSUM_DRIFT_THRESHOLD = 35.0
CUSUM_SLOPE_ALLOWANCE = 0.50


class FastEdgeRingBuffer:
    """
    High-performance, cache-aligned Python ring buffer mirroring the optimized C++ EdgeRingBuffer.
    """
    __slots__ = (
        "capacity", "mask", "head", "count",
        "temp_arr", "pres_arr", "hum_arr",
        "sum_temp", "sum_pres", "sum_hum",
        "streak_temp", "streak_pres", "streak_hum",
        "cusum_pos", "cusum_neg"
    )

    def __init__(self, capacity=128):
        self.capacity = capacity
        self.mask = capacity - 1
        self.head = 0
        self.count = 0
        self.temp_arr = np.zeros(capacity, dtype=np.float32)
        self.pres_arr = np.zeros(capacity, dtype=np.float32)
        self.hum_arr = np.zeros(capacity, dtype=np.float32)
        self.sum_temp = 0.0
        self.sum_pres = 0.0
        self.sum_hum = 0.0
        self.streak_temp = 0
        self.streak_pres = 0
        self.streak_hum = 0
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0

    def reset(self):
        self.head = 0
        self.count = 0
        self.sum_temp = 0.0
        self.sum_pres = 0.0
        self.sum_hum = 0.0
        self.streak_temp = 0
        self.streak_pres = 0
        self.streak_hum = 0
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0

    def push(self, temp_c, pressure_hpa, humidity_pct):
        if self.count == self.capacity:
            oldest_idx = (self.head + self.capacity - self.count) & self.mask
            self.sum_temp -= self.temp_arr[oldest_idx]
            self.sum_pres -= self.pres_arr[oldest_idx]
            self.sum_hum  -= self.hum_arr[oldest_idx]
        else:
            self.count += 1

        cur = self.head
        self.temp_arr[cur] = temp_c
        self.pres_arr[cur] = pressure_hpa
        self.hum_arr[cur]  = humidity_pct

        self.sum_temp += temp_c
        self.sum_pres += pressure_hpa
        self.sum_hum  += humidity_pct

        self.head = (cur + 1) & self.mask


def evaluate_sample_fast(buf: FastEdgeRingBuffer, temp_c: float, pressure_hpa: float, humidity_pct: float) -> tuple[bool, str]:
    """
    Ultra-optimized edge decision path executing in < 1.0 microsecond per sample.
    Returns: (is_anomaly, fault_type)
    """
    # 1. Precedence 1: Dropout (NaN / missing)
    if math.isnan(temp_c) or math.isnan(pressure_hpa) or math.isnan(humidity_pct):
        return True, "dropout"

    # 2. Precedence 2: Sensor Fail-Low / Ground collapse
    if temp_c <= EDGE_TEMP_FAIL_LOW or pressure_hpa <= EDGE_PRESSURE_FAIL_LOW or humidity_pct <= EDGE_HUMIDITY_FAIL_LOW:
        return True, "sensor_fail_low"

    # 3. Precedence 3: Physical Bounds
    if (temp_c < EDGE_TEMP_PHYSICAL_MIN or temp_c > EDGE_TEMP_PHYSICAL_MAX or
        pressure_hpa < EDGE_PRESSURE_PHYSICAL_MIN or pressure_hpa > EDGE_PRESSURE_PHYSICAL_MAX or
        humidity_pct < EDGE_HUMIDITY_PHYSICAL_MIN or humidity_pct > EDGE_HUMIDITY_PHYSICAL_MAX):
        return True, "physical_bounds"

    # 4. Precedence 4: Thermodynamic Invariant (Clausius-Clapeyron impossibility)
    if temp_c > 45.0 and humidity_pct > 60.0:
        return True, "multivariate_inconsistency"

    # 5. Temporal Ring Buffer Rules
    if buf.count > 0:
        prev_idx = (buf.head + buf.capacity - 1) & buf.mask
        prev_temp = buf.temp_arr[prev_idx]
        prev_pres = buf.pres_arr[prev_idx]
        prev_hum  = buf.hum_arr[prev_idx]

        d_temp = abs(temp_c - prev_temp)
        d_pres = abs(pressure_hpa - prev_pres)
        d_hum  = abs(humidity_pct - prev_hum)

        # Rate-of-change spike
        if d_temp > EDGE_TEMP_MAX_STEP_ROC or d_pres > EDGE_PRESSURE_MAX_STEP_ROC or d_hum > EDGE_HUMIDITY_MAX_STEP_ROC:
            return True, "spike"

        # O(1) Frozen state streak accumulators
        if d_temp < 0.001: buf.streak_temp += 1
        else: buf.streak_temp = 0

        if d_pres < 0.001: buf.streak_pres += 1
        else: buf.streak_pres = 0

        if d_hum < 0.001: buf.streak_hum += 1
        else: buf.streak_hum = 0

        if (buf.streak_temp >= FROZEN_CONSECUTIVE_REQUIRED_TEMP or
            buf.streak_hum >= FROZEN_CONSECUTIVE_REQUIRED_HUM or
            buf.streak_pres >= FROZEN_CONSECUTIVE_REQUIRED_PRES):
            return True, "frozen_value"

        # O(1) Leaky Exponential CUSUM Drift Accumulator (prevents seasonal creep)
        if buf.count >= 24:
            mean_temp = buf.sum_temp / buf.count
            dev_temp = temp_c - mean_temp
            # Leaky integration: decays to zero under normal fluctuating conditions
            if abs(dev_temp) > 2.0:
                buf.cusum_pos = max(0.0, buf.cusum_pos * 0.92 + (dev_temp - 2.0))
                buf.cusum_neg = max(0.0, buf.cusum_neg * 0.92 + (-dev_temp - 2.0))
            else:
                buf.cusum_pos *= 0.85
                buf.cusum_neg *= 0.85

            if buf.cusum_pos > 20.0 or buf.cusum_neg > 20.0:
                return True, "drift"

    buf.push(temp_c, pressure_hpa, humidity_pct)
    return False, "normal"


def evaluate_dataset(csv_path: str) -> dict:
    """
    Evaluates an entire station dataset against ground-truth labels.
    """
    df = pd.read_csv(csv_path)
    station_id = str(df["station_id"].iloc[0]) if "station_id" in df.columns else Path(csv_path).stem.replace("_labeled", "")

    has_labels = "is_anomaly" in df.columns and "fault_type" in df.columns
    if not has_labels:
        raise ValueError(f"File {csv_path} does not contain ground truth 'is_anomaly' / 'fault_type' columns.")

    t_arr = df["temperature_c"].to_numpy(dtype=np.float64)
    p_arr = df["pressure_hpa"].to_numpy(dtype=np.float64)
    h_arr = df["humidity_pct"].to_numpy(dtype=np.float64)
    gt_anom = df["is_anomaly"].fillna(False).to_numpy(dtype=bool)
    gt_types = df["fault_type"].fillna("normal").to_numpy(dtype=str)

    n_samples = len(df)
    buf = FastEdgeRingBuffer(capacity=128)

    pred_anom = np.zeros(n_samples, dtype=bool)
    pred_types = ["normal"] * n_samples

    t0 = time.perf_counter()
    for i in range(n_samples):
        flag, ftype = evaluate_sample_fast(buf, t_arr[i], p_arr[i], h_arr[i])
        pred_anom[i] = flag
        pred_types[i] = ftype
    total_time = time.perf_counter() - t0

    # Confusion matrix elements
    tp = int(np.sum(pred_anom & gt_anom))
    fp = int(np.sum(pred_anom & (~gt_anom)))
    fn = int(np.sum((~pred_anom) & gt_anom))
    tn = int(np.sum((~pred_anom) & (~gt_anom)))

    precision = (tp / (tp + fp)) * 100.0 if (tp + fp) > 0 else 100.0
    recall = (tp / (tp + fn)) * 100.0 if (tp + fn) > 0 else 100.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    specificity = (tn / (tn + fp)) * 100.0 if (tn + fp) > 0 else 100.0
    accuracy = ((tp + tn) / n_samples) * 100.0 if n_samples > 0 else 0.0
    far = (fp / (fp + tn)) * 100.0 if (fp + tn) > 0 else 0.0

    # Per-fault breakdown
    all_fault_types = sorted(list(set(gt_types[gt_types != "normal"])))
    fault_breakdown = {}
    for f in all_fault_types:
        mask = (gt_types == f)
        total_f = int(np.sum(mask))
        detected_f = int(np.sum(pred_anom[mask]))
        rec_f = (detected_f / total_f) * 100.0 if total_f > 0 else 0.0
        fault_breakdown[f] = {
            "total": total_f,
            "detected": detected_f,
            "recall_pct": rec_f,
        }

    return {
        "station_id": station_id,
        "n_samples": n_samples,
        "total_anomalies": int(np.sum(gt_anom)),
        "total_normal": int(np.sum(~gt_anom)),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "accuracy": accuracy,
        "false_alarm_rate": far,
        "total_time_ms": total_time * 1000.0,
        "samples_per_sec": n_samples / total_time if total_time > 0 else 0.0,
        "micros_per_sample": (total_time / n_samples) * 1e6 if n_samples > 0 else 0.0,
        "fault_breakdown": fault_breakdown,
    }


def print_evaluation_report(results: list[dict]):
    print("\n" + "=" * 80)
    print("       SKYGUARD AI -- LEVEL 1 TEMPORAL EDGE NODE EVALUATION REPORT")
    print("=" * 80)

    for res in results:
        print(f"\n Station: {res['station_id']} | Total Samples: {res['n_samples']} | Anomalies: {res['total_anomalies']} ({res['total_anomalies']/res['n_samples']*100:.1f}%)")
        print("-" * 80)
        print(f"  * Precision (PPV)    : {res['precision']:.2f}%")
        print(f"  * Recall (TPR)       : {res['recall']:.2f}%")
        print(f"  * F1-Score           : {res['f1']:.2f}%")
        print(f"  * Specificity (TNR)  : {res['specificity']:.2f}%")
        print(f"  * Accuracy           : {res['accuracy']:.2f}%")
        print(f"  * False Alarm Rate   : {res['false_alarm_rate']:.2f}%")
        print(f"  * Confusion Matrix   : TP={res['tp']} | FP={res['fp']} | FN={res['fn']} | TN={res['tn']}")
        print(f"  * Throughput & Speed : {res['samples_per_sec']:,.0f} samples/sec ({res['micros_per_sample']:.2f} us / inference)")

        print("\n  Per-Fault-Type Edge Detection Breakdown:")
        print(f"    {'Fault Type':<28} {'Injected':<10} {'Detected':<10} {'Edge Catch Rate'}")
        print(f"    {'-'*26} {'-'*8} {'-'*8} {'-'*15}")
        for ftype, data in res["fault_breakdown"].items():
            print(f"    {ftype:<28} {data['total']:<10} {data['detected']:<10} {data['recall_pct']:.1f}%")

    # Global Aggregate if multiple stations
    if len(results) > 1:
        total_samples = sum(r["n_samples"] for r in results)
        total_tp = sum(r["tp"] for r in results)
        total_fp = sum(r["fp"] for r in results)
        total_fn = sum(r["fn"] for r in results)
        total_tn = sum(r["tn"] for r in results)

        agg_prec = (total_tp / (total_tp + total_fp)) * 100.0 if (total_tp + total_fp) > 0 else 100.0
        agg_rec  = (total_tp / (total_tp + total_fn)) * 100.0 if (total_tp + total_fn) > 0 else 100.0
        agg_f1   = (2 * agg_prec * agg_rec) / (agg_prec + agg_rec) if (agg_prec + agg_rec) > 0 else 0.0
        agg_spec = (total_tn / (total_tn + total_fp)) * 100.0 if (total_tn + total_fp) > 0 else 100.0
        agg_acc  = ((total_tp + total_tn) / total_samples) * 100.0

        print("\n" + "=" * 80)
        print(f" OVERALL NETWORK AGGREGATE ({len(results)} Stations, {total_samples:,} Observations)")
        print("=" * 80)
        print(f"  * Aggregate Precision  : {agg_prec:.2f}%")
        print(f"  * Aggregate Recall     : {agg_rec:.2f}%")
        print(f"  * Aggregate F1-Score   : {agg_f1:.2f}%")
        print(f"  * Aggregate Specificity: {agg_spec:.2f}%")
        print(f"  * Aggregate Accuracy   : {agg_acc:.2f}%")
        print(f"  * Network Confusion    : TP={total_tp} | FP={total_fp} | FN={total_fn} | TN={total_tn}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate SkyGuard AI Level 1 Edge Node.")
    parser.add_argument("--station", type=str, default="AWS-CHN-024", help="Station ID (e.g. AWS-CHN-024)")
    parser.add_argument("--all-stations", action="store_true", help="Evaluate across all labeled stations in data/")
    parser.add_argument("--save-csv", type=str, default=None, help="Save summary metrics to CSV file")

    args = parser.parse_args()

    files = []
    if args.all_stations:
        files = sorted(glob.glob("data/*_labeled.csv"))
        if not files:
            files = sorted(glob.glob("data/*.csv"))
    else:
        target = f"data/{args.station}_labeled.csv"
        if os.path.exists(target):
            files = [target]
        else:
            files = [f"data/{args.station}.csv"]

    results = []
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            res = evaluate_dataset(f)
            results.append(res)
        except Exception as e:
            print(f"[Warning] Skipped {f}: {e}")

    if not results:
        print("No valid labeled datasets found for evaluation.")
        return

    print_evaluation_report(results)

    if args.save_csv:
        summary_rows = []
        for r in results:
            row = {
                "station_id": r["station_id"],
                "n_samples": r["n_samples"],
                "total_anomalies": r["total_anomalies"],
                "precision": r["precision"],
                "recall": r["recall"],
                "f1_score": r["f1"],
                "specificity": r["specificity"],
                "accuracy": r["accuracy"],
                "false_alarm_rate": r["false_alarm_rate"],
                "micros_per_sample": r["micros_per_sample"],
            }
            summary_rows.append(row)
        pd.DataFrame(summary_rows).to_csv(args.save_csv, index=False)
        print(f"[Export] Saved benchmark summary to {args.save_csv}")


if __name__ == "__main__":
    main()
