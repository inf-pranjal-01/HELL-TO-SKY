"""
scratch/precision_forensics/experiment_step19_roc_cusum.py

Evaluates ROC-based CUSUM drift detection in Tier 2 alongside untouched Step 18 Tier 3 across all 7 seeds.
"""

import sys
import math
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import data.anomaly_injector as injector
import model.detect as baseline_detect
from model.peer_spatial_engine import PeerSpatialEngine
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS
from model.dynamic_expectation import calculate_solar_hour
from model.seasonal_baseline import get_expected_roc
from model.cross_channel_covariance import CrossChannelEngine
from model.state import StationBuffer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]
PREFIX_MAP = {"temperature_c": "temp", "pressure_hpa": "pressure", "humidity_pct": "humidity"}

COV_DELTA_1H = np.array([
    [ 1.779049, -0.016319, -6.494229],
    [-0.016319,  0.452587,  0.250640],
    [-6.494229,  0.250640, 32.893058]
], dtype=float)


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
    
    cusum_state = {
        st_id: {p: {"pos": 0.0, "neg": 0.0} for p in PARAMS}
        for st_id in station_ids
    }

    tp = fp = fn = tn = 0
    tier_counts = {}
    fault_tp = {}
    fault_fn = {}

    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type", "unknown") if gt else None

        buf = buffers[st_id]
        hist_df = buf.raw_history_df()

        prior_time = None
        if not hist_df.empty and "timestamp" in hist_df.columns:
            valid_ts = pd.to_datetime(hist_df["timestamp"], utc=True, errors="coerce").dropna()
            if not valid_ts.empty:
                prior_time = valid_ts.iloc[-1]
        dt_hours = max(0.1, (ts - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
        solar_hour = calculate_solar_hour(ts, st_id)

        # Tier 0
        is_rail, rail_p, rail_reason = baseline_detect._check_hardware_rail(row)
        is_phys, _ = CrossChannelEngine.check_physical_invariants(row.get("temperature_c"), row.get("pressure_hpa"), row.get("humidity_pct"))

        verdict = {"is_anomaly": False, "fault_type": None, "tier": -1}
        if is_rail:
            verdict = {"is_anomaly": True, "fault_type": "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low", "tier": 0}
        elif is_phys:
            verdict = {"is_anomaly": True, "fault_type": "physical_bounds", "tier": 0}
        else:
            dy_vals = {}
            prior_vals = {}
            for param in PARAMS:
                val = float(row[param])
                p_val = None
                if not hist_df.empty and param in hist_df.columns:
                    vp = pd.to_numeric(hist_df[param], errors="coerce").dropna()
                    if not vp.empty:
                        p_val = float(vp.iloc[-1])
                prior_vals[param] = p_val
                dy_vals[param] = (val - p_val) if p_val is not None else None

            # Tier 1
            t1_ev = []
            for param in PARAMS:
                val = float(row[param])
                sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
                p_val = prior_vals[param]

                if p_val is not None:
                    jump_mag = abs(val - p_val)
                    if jump_mag >= 2.5 * sensor_floor:
                        sig_j = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
                        z_j = jump_mag / max(1e-4, sig_j)
                        llr_j = float(0.5 * (z_j ** 2) - math.log(max(1.1, sig_j / sensor_floor)))
                        if llr_j >= 5.86 and z_j >= 3.0:
                            t1_ev.append({"tier": 1, "type": "spike", "parameter": param, "llr": llr_j})

                f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(param, hist_df, val, None, 0)
                if f_diag["is_frozen"]:
                    t1_ev.append({"tier": 1, "type": "frozen_value", "parameter": param, "llr": f_llr})

            if t1_ev:
                st = max(t1_ev, key=lambda e: e["llr"])
                verdict = {"is_anomaly": True, "fault_type": st["type"], "tier": 1}
            else:
                # Tier 2: ROC-based CUSUM
                t2_ev = []
                for param in PARAMS:
                    val = float(row[param])
                    p_val = prior_vals[param]
                    if p_val is not None and dt_hours <= 3.0:
                        raw_roc = (val - p_val) / dt_hours
                        exp_roc = get_expected_roc(st_id, PREFIX_MAP[param], int(solar_hour) % 24)
                        roc_res = raw_roc - exp_roc
                        
                        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
                        sig_roc = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours) / dt_hours
                        z_roc = roc_res / max(1e-4, sig_roc)
                        
                        decay = math.exp(-dt_hours / 24.0)
                        allowance = 0.5
                        
                        s_p = max(0.0, cusum_state[st_id][param]["pos"] * decay + (z_roc - allowance))
                        s_n = max(0.0, cusum_state[st_id][param]["neg"] * decay + (-z_roc - allowance))
                        cusum_state[st_id][param]["pos"] = s_p
                        cusum_state[st_id][param]["neg"] = s_n
                        
                        if max(s_p, s_n) >= 5.86:
                            t2_ev.append({"tier": 2, "type": "drift", "parameter": param, "llr": max(s_p, s_n)})
                    else:
                        decay = math.exp(-dt_hours / 24.0)
                        cusum_state[st_id][param]["pos"] *= decay
                        cusum_state[st_id][param]["neg"] *= decay

                if t2_ev:
                    st = max(t2_ev, key=lambda e: e["llr"])
                    verdict = {"is_anomaly": True, "fault_type": "drift", "tier": 2}
                else:
                    # Tier 3 Instantaneous Covariance Mahalanobis (Untouched Step 18)
                    if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
                        dy_vec = np.array([dy_vals[p] for p in PARAMS], dtype=float)
                        cov_dt = COV_DELTA_1H * dt_hours
                        inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
                        d_sq = float(dy_vec.T @ inv_cov_dt @ dy_vec)
                        if d_sq > 16.27:
                            verdict = {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "tier": 3}

        buf.record_raw_reading(row, timestamp=ts, verdict=verdict)

        if verdict["is_anomaly"] and verdict["tier"] == 2:
            for p in PARAMS:
                if cusum_state[st_id][p]["pos"] >= 5.86:
                    cusum_state[st_id][p]["pos"] = 0.0
                if cusum_state[st_id][p]["neg"] >= 5.86:
                    cusum_state[st_id][p]["neg"] = 0.0

        is_pred = verdict["is_anomaly"]
        tier_k = f"tier{verdict.get('tier', -1)}"
        tier_counts[tier_k] = tier_counts.get(tier_k, 0) + 1

        if is_pred and gt:
            tp += 1
            if gt_type:
                fault_tp[gt_type] = fault_tp.get(gt_type, 0) + 1
        elif is_pred and not gt:
            fp += 1
        elif not is_pred and gt:
            fn += 1
            if gt_type:
                fault_fn[gt_type] = fault_fn.get(gt_type, 0) + 1
        else:
            tn += 1

    prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "seed": seed, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "prec": prec, "rec": rec, "f1": f1,
        "tier_counts": tier_counts,
        "fault_tp": fault_tp, "fault_fn": fault_fn
    }


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 19 EXPERIMENT: RATE-OF-CHANGE CUSUM DRIFT RECOVERY")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(eval_seed, tasks))

    df_res = pd.DataFrame(results)
    macro_p = df_res["prec"].mean()
    macro_r = df_res["rec"].mean()
    macro_f1 = df_res["f1"].mean()
    mean_tp = df_res["tp"].mean()
    mean_fp = df_res["fp"].mean()
    mean_fn = df_res["fn"].mean()

    print("\n" + "=" * 80)
    print("STEP 19 RESULTS ACROSS 7 LOCKED SEEDS")
    print("=" * 80)
    print(df_res[["seed", "prec", "rec", "f1", "tp", "fp", "fn"]].to_string(index=False))
    print("\n" + "=" * 80)
    print(f"Macro Precision = {macro_p:.2f}% (Step 16: 72.61%, Step 18: 73.45%)")
    print(f"Macro Recall    = {macro_r:.2f}% (Step 16: 97.73%, Step 18: 94.39%)")
    print(f"Macro F1        = {macro_f1:.2f}% (Step 16: 83.31%, Step 18: 82.61%)")
    print(f"Mean FP         = {mean_fp:.1f} (Step 16: 4816.6, Step 18: 4456.7)")
    print(f"Mean TP         = {mean_tp:.1f} | Mean FN = {mean_fn:.1f}")

    print("\n--- Average Detections by Tier ---")
    for tk in ["tier0", "tier1", "tier2", "tier3"]:
        m_t = np.mean([r["tier_counts"].get(tk, 0) for r in results])
        print(f"{tk}: {m_t:.1f}")


if __name__ == "__main__":
    main()
