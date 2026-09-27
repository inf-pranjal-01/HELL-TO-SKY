"""
scratch/precision_forensics/reproduce_baseline.py

Reproduces the authoritative 7-seed baseline benchmark on pristine restored code.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import data.anomaly_injector as injector
from model.detect import score_reading
from model.peer_spatial_engine import PeerSpatialEngine
from model.state import StationBuffer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]


def eval_seed(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)
    
    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    tp = fp = fn = tn = 0
    
    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        buf = buffers[st_id]
        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
        hist_df = buf.raw_history_df()
        
        raw_reading = {
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }
        verdict = score_reading(raw_reading, hist_df, {}, neighbor_bufs)
        is_pred = bool(verdict["is_anomaly"])
        gt_is_anom = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        
        if is_pred and gt_is_anom:
            tp += 1
        elif is_pred and not gt_is_anom:
            fp += 1
        elif not is_pred and gt_is_anom:
            fn += 1
        else:
            tn += 1
        
        buf.record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)
        
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return {
        "seed": seed, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": p, "recall": r, "f1": f1
    }


if __name__ == "__main__":
    df = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    test_raw_df = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    print("==================================================================", flush=True)
    print("REPRODUCING AUTHORITATIVE 7-SEED BASELINE BENCHMARK", flush=True)
    print("==================================================================", flush=True)

    tasks = [(s, test_raw_df) for s in SEEDS]
    with ProcessPoolExecutor(max_workers=7) as executor:
        results = list(executor.map(eval_seed, tasks))
    
    for res in results:
        print(f"Seed {str(res['seed']):20s} | TP: {res['tp']:5d} | FP: {res['fp']:5d} | FN: {res['fn']:4d} | Prec: {res['precision']*100:6.2f}% | Rec: {res['recall']*100:6.2f}% | F1: {res['f1']*100:6.2f}%")
    
    df_res = pd.DataFrame(results)
    mp = df_res["precision"].mean()
    mr = df_res["recall"].mean()
    mf = df_res["f1"].mean()
    print(f"\nRESTORED BASELINE MACRO: Precision = {mp*100:.2f}% | Recall = {mr*100:.2f}% | F1 = {mf*100:.2f}%")
