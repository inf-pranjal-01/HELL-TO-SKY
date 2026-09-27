"""
scratch/precision_forensics/run_step21_benchmark.py

Step 21: Diurnal ROC Spike Adjudicator Benchmark.
Evaluates 3 controlled configurations across all 7 locked seeds:
- CONFIG A: Locked Step 19 Reference
- CONFIG B: Step 21 Diurnal ROC Spike Adjudicator (Raw spike generation + Causal Diurnal ROC Adjudication)
- CONFIG C: Negative Control (Permuted/Phase-Shifted Diurnal ROC destroying solar causality)

Performs:
1. Complete transition audit (FP removed, TP removed, unchanged).
2. Per-fault, per-channel, per-seed breakdown.
3. FP mechanism removal accounting.
4. Generates step21_transition_audit.csv and step21_macro_summary.csv.
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
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = 5.86, -2.99

COV_DELTA_1H = np.array([
    [ 1.779049, -0.016319, -6.494229],
    [-0.016319,  0.452587,  0.250640],
    [-6.494229,  0.250640, 32.893058]
], dtype=float)
INV_COV_DELTA_1H = np.linalg.pinv(COV_DELTA_1H + 1e-5 * np.eye(3))


def score_config_reading(
    config_name: str,
    raw_reading: dict,
    hist_df: pd.DataFrame,
    neighbor_bufs: dict,
    cusum_state: dict,
    station_id: str,
    ts: pd.Timestamp
) -> dict:
    """
    Evaluates detector stream for a given configuration:
    config_name:
      'config_a': Locked Step 19
      'config_b': Step 21 Diurnal ROC Adjudicator
      'config_c': Negative Control (Phase-shifted Solar Hour by 12h)
    """
    prior_time = None
    if not hist_df.empty and "timestamp" in hist_df.columns:
        valid_ts = pd.to_datetime(hist_df["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]
            
    dt_hours = max(0.1, (ts - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(ts, station_id)

    # In Config C (Negative Control), shift solar hour by +12.0 hours (anti-correlated diurnal phase)
    eval_solar_hour = solar_hour if config_name != "config_c" else ((solar_hour + 12.0) % 24.0)

    # ── Tier 0: Hard Invariants
    is_rail, rail_p, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    is_phys, _ = CrossChannelEngine.check_physical_invariants(raw_reading.get("temperature_c"), raw_reading.get("pressure_hpa"), raw_reading.get("humidity_pct"))

    if is_rail:
        return {"is_anomaly": True, "fault_type": "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low", "tier": 0, "basis": "TIER_0_HARD_RAIL"}
    if is_phys:
        return {"is_anomaly": True, "fault_type": "physical_bounds", "tier": 0, "basis": "TIER_0_PHYSICAL_BOUND"}

    prior_vals = {}
    dy_vals = {}
    for p in PARAMS:
        val = float(raw_reading[p])
        pv = None
        if not hist_df.empty and p in hist_df.columns:
            vps = pd.to_numeric(hist_df[p], errors="coerce").dropna()
            if not vps.empty:
                pv = float(vps.iloc[-1])
        prior_vals[p] = pv
        dy_vals[p] = (val - pv) if pv is not None else None

    # ── Tier 1: Specialist Faults (Spike Jump & Frozen)
    tier1_evidence = []
    for p in PARAMS:
        val = float(raw_reading[p])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
        pv = prior_vals[p]

        # 1. Raw Spike Candidate Generation (Untouched sensitive generator)
        if pv is not None:
            raw_jump_mag = abs(val - pv)
            sig_jump = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
            z_jump = raw_jump_mag / max(1e-4, sig_jump)
            llr_jump = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sig_jump / sensor_floor)))

            if raw_jump_mag >= 2.5 * sensor_floor and z_jump >= 3.0 and llr_jump >= WALD_UPPER_ALERT:
                # Raw spike candidate generated!
                is_spike_adjudicated = True
                adjudication_reason = f"Raw jump {raw_jump_mag:.2f} (z={z_jump:.2f})"

                if config_name in ["config_b", "config_c"]:
                    # ── DIURNAL ROC ADJUDICATOR ──
                    # Retrieve expected environmental rate of change for this solar hour
                    exp_roc = get_expected_roc(station_id, PREFIX_MAP[p], int(eval_solar_hour) % 24)
                    expected_env_delta = exp_roc * dt_hours
                    
                    # Compute unexplained movement innovation:
                    # delta_unexplained = observed_delta - expected_env_delta
                    raw_delta = val - pv
                    delta_unexplained = raw_delta - expected_env_delta
                    mag_unexplained = abs(delta_unexplained)
                    z_unexplained = mag_unexplained / max(1e-4, sig_jump)
                    
                    # Adjudication test:
                    # If the observed movement moves in the same direction as expected diurnal change
                    # and the unexplained residual is within normal noise (mag_unexplained < 2.5 * sensor_floor or z_unexplained < 3.0),
                    # the raw jump is fully explained by normal diurnal insolation/cooling.
                    is_explained_by_diurnal = (
                        (raw_delta * expected_env_delta > 0) and
                        (abs(raw_delta) <= abs(expected_env_delta) + 2.5 * sensor_floor or z_unexplained < 3.0)
                    )

                    if is_explained_by_diurnal:
                        is_spike_adjudicated = False
                        adjudication_reason = f"Adjudicated clean: Explained by diurnal ROC ({expected_env_delta:+.2f})"

                if is_spike_adjudicated:
                    tier1_evidence.append({
                        "tier": 1, "type": "spike", "parameter": p, "llr": llr_jump,
                        "confidence": min(98.0, 85.0 + llr_jump),
                        "reason": adjudication_reason, "basis": f"TIER_1_SPIKE_{p.upper()}"
                    })

        # 2. Frozen Value Check
        f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(p, hist_df, val, None, 0)
        if f_diag["is_frozen"]:
            tier1_evidence.append({
                "tier": 1, "type": "frozen_value", "parameter": p, "llr": f_llr,
                "confidence": min(98.0, 85.0 + f_llr), "reason": f_reason, "basis": f"TIER_1_FROZEN_{p.upper()}"
            })

    if tier1_evidence:
        st = max(tier1_evidence, key=lambda e: e["llr"])
        return {"is_anomaly": True, "fault_type": st["type"], "tier": 1, "basis": st["basis"], "param": st.get("parameter")}

    # ── Tier 2: ROC-based CUSUM Drift (Step 19 Architecture)
    tier2_evidence = []
    for p in PARAMS:
        val = float(raw_reading[p])
        pv = prior_vals[p]
        if pv is not None and dt_hours <= 3.0:
            raw_roc = (val - pv) / dt_hours
            exp_roc = get_expected_roc(station_id, PREFIX_MAP[p], int(solar_hour) % 24)
            roc_res = raw_roc - exp_roc
            
            sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
            sig_roc = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours) / dt_hours
            z_roc = roc_res / max(1e-4, sig_roc)
            decay = math.exp(-dt_hours / 24.0)
            allowance = 0.5
            
            sp = max(0.0, cusum_state[station_id][p]["pos"] * decay + (z_roc - allowance))
            sn = max(0.0, cusum_state[station_id][p]["neg"] * decay + (-z_roc - allowance))
            cusum_state[station_id][p]["pos"] = sp
            cusum_state[station_id][p]["neg"] = sn
            
            if max(sp, sn) >= WALD_UPPER_ALERT:
                tier2_evidence.append({"tier": 2, "type": "drift", "parameter": p, "llr": max(sp, sn), "basis": f"TIER_2_DRIFT_{p.upper()}"})
        else:
            decay = math.exp(-dt_hours / 24.0)
            cusum_state[station_id][p]["pos"] *= decay
            cusum_state[station_id][p]["neg"] *= decay

    if tier2_evidence:
        st = max(tier2_evidence, key=lambda e: e["llr"])
        return {"is_anomaly": True, "fault_type": "drift", "tier": 2, "basis": st["basis"], "param": st.get("parameter")}

    # ── Tier 3: Instantaneous Covariance Mahalanobis (Step 18 Architecture)
    if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
        dy_vec = np.array([dy_vals[p] for p in PARAMS], dtype=float)
        cov_dt = COV_DELTA_1H * dt_hours
        inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
        d_sq_inst = float(dy_vec.T @ inv_cov_dt @ dy_vec)
        if d_sq_inst > 16.27:
            return {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "tier": 3, "basis": "TIER_3_INSTANT_COV", "d_sq": d_sq_inst}

    return {"is_anomaly": False, "fault_type": None, "tier": -1, "basis": "NORMAL"}


def eval_seed_step21(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    configs = ["config_a", "config_b", "config_c"]
    
    results = {}
    rows = eval_df.to_dict("records")

    for cfg in configs:
        buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
        cusum_state = {st_id: {p: {"pos": 0.0, "neg": 0.0} for p in PARAMS} for st_id in station_ids}

        tp = fp = fn = tn = 0
        tier_counts = {}
        fault_tp = {}
        fault_fn = {}
        channel_tp = {}
        channel_fp = {}
        predictions = []

        for row in rows:
            st_id = row["station_id"]
            ts = row["timestamp"]
            gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
            gt_type = row.get("fault_type", "unknown") if gt else None

            sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
            buf = buffers[st_id]
            neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
            hist_df = buf.raw_history_df()

            verdict = score_config_reading(cfg, row, hist_df, neighbor_bufs, cusum_state, st_id, ts)
            buf.record_raw_reading(row, timestamp=ts, verdict=verdict)

            if verdict["is_anomaly"] and verdict["tier"] == 2:
                for p in PARAMS:
                    if cusum_state[st_id][p]["pos"] >= WALD_UPPER_ALERT: cusum_state[st_id][p]["pos"] = 0.0
                    if cusum_state[st_id][p]["neg"] >= WALD_UPPER_ALERT: cusum_state[st_id][p]["neg"] = 0.0

            is_pred = bool(verdict["is_anomaly"])
            tier_num = verdict.get("tier", -1)
            t_k = f"tier{tier_num}"
            flagged_p = verdict.get("param", "unknown")

            predictions.append(is_pred)

            if is_pred and gt:
                tp += 1
                tier_counts[t_k] = tier_counts.get(t_k, 0) + 1
                if gt_type: fault_tp[gt_type] = fault_tp.get(gt_type, 0) + 1
                if flagged_p in PARAMS: channel_tp[flagged_p] = channel_tp.get(flagged_p, 0) + 1
            elif is_pred and not gt:
                fp += 1
                tier_counts[t_k] = tier_counts.get(t_k, 0) + 1
                if flagged_p in PARAMS: channel_fp[flagged_p] = channel_fp.get(flagged_p, 0) + 1
            elif not is_pred and gt:
                fn += 1
                if gt_type: fault_fn[gt_type] = fault_fn.get(gt_type, 0) + 1
            else:
                tn += 1

        prec = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        results[cfg] = {
            "seed": seed, "config": cfg,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "prec": prec, "rec": rec, "f1": f1,
            "tier_counts": tier_counts,
            "fault_tp": fault_tp, "fault_fn": fault_fn,
            "channel_tp": channel_tp, "channel_fp": channel_fp,
            "predictions": predictions
        }

    # Transition Analysis (Config A -> Config B)
    preds_a = results["config_a"]["predictions"]
    preds_b = results["config_b"]["predictions"]
    preds_c = results["config_c"]["predictions"]

    transitions = []
    for idx, row in enumerate(rows):
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type", "unknown") if gt else None
        pa = preds_a[idx]
        pb = preds_b[idx]
        pc = preds_c[idx]

        if pa != pb:
            # Transition occurred
            t_type = "UNKNOWN"
            if pa and not pb and not gt:
                t_type = "FP_REMOVED"
            elif pa and not pb and gt:
                t_type = "TP_REMOVED"
            elif not pa and pb and gt:
                t_type = "TP_ADDED"
            elif not pa and pb and not gt:
                t_type = "FP_ADDED"

            transitions.append({
                "seed": seed, "station_id": row["station_id"], "timestamp": str(row["timestamp"]),
                "transition_type": t_type, "gt_is_anomaly": gt, "gt_fault_type": gt_type,
                "pred_a": pa, "pred_b": pb, "pred_c": pc
            })

    return {
        "seed": seed,
        "results": results,
        "transitions": transitions
    }


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 21: DIURNAL ROC SPIKE ADJUDICATOR BENCHMARK (7 LOCKED SEEDS)")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        worker_outputs = list(executor.map(eval_seed_step21, tasks))

    cfg_keys = ["config_a", "config_b", "config_c"]
    cfg_names = {
        "config_a": "Step 19 Baseline Reference",
        "config_b": "Step 21 Diurnal ROC Adjudicator",
        "config_c": "Step 21 Negative Control (Permuted 12h)"
    }

    macro_records = []
    all_seed_records = []

    for cfg in cfg_keys:
        runs = [w["results"][cfg] for w in worker_outputs]
        df_k = pd.DataFrame(runs)
        
        macro_p = df_k["prec"].mean()
        macro_r = df_k["rec"].mean()
        macro_f1 = df_k["f1"].mean()
        mean_tp = df_k["tp"].mean()
        mean_fp = df_k["fp"].mean()
        mean_fn = df_k["fn"].mean()

        macro_records.append({
            "config_id": cfg,
            "config_name": cfg_names[cfg],
            "macro_precision": macro_p,
            "macro_recall": macro_r,
            "macro_f1": macro_f1,
            "mean_tp": mean_tp,
            "mean_fp": mean_fp,
            "mean_fn": mean_fn,
            "std_precision": df_k["prec"].std(),
            "std_recall": df_k["rec"].std(),
            "std_f1": df_k["f1"].std()
        })

        for r in runs:
            all_seed_records.append({
                "config_id": cfg, "config_name": cfg_names[cfg], "seed": r["seed"],
                "tp": r["tp"], "fp": r["fp"], "fn": r["fn"], "tn": r["tn"],
                "precision": r["prec"], "recall": r["rec"], "f1": r["f1"]
            })

    macro_df = pd.DataFrame(macro_records)
    all_seeds_df = pd.DataFrame(all_seed_records)

    print("\n" + "=" * 80)
    print("STEP 21 MACRO BENCHMARK RESULTS ACROSS 7 LOCKED SEEDS")
    print("=" * 80)
    print(macro_df[["config_name", "macro_precision", "macro_recall", "macro_f1", "mean_tp", "mean_fp", "mean_fn"]].to_string(index=False))

    print("\n" + "=" * 80)
    print("PER-SEED BREAKDOWN")
    print("=" * 80)
    for cfg in cfg_keys:
        print(f"\n--- {cfg_names[cfg]} ---")
        print(all_seeds_df[all_seeds_df["config_id"] == cfg][["seed", "precision", "recall", "f1", "tp", "fp", "fn"]].to_string(index=False))

    # Compile Transition Audit
    all_transitions = []
    for w in worker_outputs:
        all_transitions.extend(w["transitions"])
    df_trans = pd.DataFrame(all_transitions)
    df_trans.to_csv(OUTPUT_DIR / "step21_transition_audit.csv", index=False)

    print("\n" + "=" * 80)
    print("STEP 21 TRANSITION AUDIT (Config A -> Config B)")
    print("=" * 80)
    t_counts = df_trans["transition_type"].value_counts()
    print(pd.DataFrame({"Count": t_counts, "Mean_per_seed": t_counts / 7.0}).to_string())

    print("\n--- TP Removed by Fault Type ---")
    df_tp_rem = df_trans[df_trans["transition_type"] == "TP_REMOVED"]
    print(df_tp_rem["gt_fault_type"].value_counts())

    # Per-Fault Recall Comparison (Config A vs Config B)
    print("\n" + "=" * 80)
    print("PER-FAULT RECALL AUDIT (Config A vs Config B)")
    print("=" * 80)
    fault_names = ["spike", "frozen_value", "drift", "sensor_fail_low", "dropout", "multivariate_inconsistency", "unstructured_anomaly"]
    fault_audit_rows = []
    for fn in fault_names:
        tp_a = np.mean([w["results"]["config_a"]["fault_tp"].get(fn, 0) for w in worker_outputs])
        tp_b = np.mean([w["results"]["config_b"]["fault_tp"].get(fn, 0) for w in worker_outputs])
        fn_a = np.mean([w["results"]["config_a"]["fault_fn"].get(fn, 0) for w in worker_outputs])
        fn_b = np.mean([w["results"]["config_b"]["fault_fn"].get(fn, 0) for w in worker_outputs])
        rec_a = tp_a / (tp_a + fn_a) * 100.0 if (tp_a + fn_a) > 0 else 0.0
        rec_b = tp_b / (tp_b + fn_b) * 100.0 if (tp_b + fn_b) > 0 else 0.0
        fault_audit_rows.append({
            "Fault_Type": fn,
            "TP_Step19": tp_a,
            "TP_Step21": tp_b,
            "TP_Lost": tp_a - tp_b,
            "Recall_Step19": rec_a,
            "Recall_Step21": rec_b,
            "Recall_Delta_pp": rec_b - rec_a
        })
    print(pd.DataFrame(fault_audit_rows).to_string(index=False))

    macro_df.to_csv(OUTPUT_DIR / "step21_macro_summary.csv", index=False)
    print(f"\nOutputs saved to {OUTPUT_DIR}")
    print(f"Total benchmark runtime: {time.time() - t0:.2f} seconds!")


if __name__ == "__main__":
    main()
