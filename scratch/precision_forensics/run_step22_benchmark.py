"""
scratch/precision_forensics/run_step22_benchmark.py

Step 22: Decoupled Dual-Buffer State Architecture Benchmark.
Evaluates:
- Config A: Locked Step 19 Reference
- Config B: Locked Step 21 Reference (Single buffer: adjudicated spikes enter trusted history -> contaminated baseline)
- Config C: Step 22 Decoupled Dual Buffer (Raw history for physical continuity, Trusted Clean history for dynamic expectations)

Outputs:
- step22_macro_summary.csv
- step22_transition_audit.csv
- step22_episode_audit.csv
- step22_state_trace.csv
"""

import sys
import math
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import deque
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import data.anomaly_injector as injector
import model.detect as baseline_detect
from model.peer_spatial_engine import PeerSpatialEngine
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS
from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.seasonal_baseline import get_expected_roc
from model.cross_channel_covariance import CrossChannelEngine

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


class DualStationBuffer:
    """
    Decoupled Dual-Buffer State Architecture:
    - stream_raw: contains every observation chronologically (used for dt and y_{t-1}).
    - stream_trusted: contains only trusted clean observations (used for dynamic expectations).
    - stream_provisional: records candidate observations that were suppressed/adjudicated.
    """
    def __init__(self, station_id: str, maxlen: int = 200):
        self.station_id = station_id
        self._raw_rows = deque(maxlen=maxlen)
        self._trusted_rows = deque(maxlen=maxlen)
        self._provisional_rows = deque(maxlen=maxlen)
        self._cached_raw_df = None
        self._cached_trusted_df = None
        self._raw_dirty = True
        self._trusted_dirty = True

    def raw_history_df(self) -> pd.DataFrame:
        if self._raw_dirty:
            self._cached_raw_df = pd.DataFrame(list(self._raw_rows))
            self._raw_dirty = False
        return self._cached_raw_df

    def trusted_history_df(self) -> pd.DataFrame:
        if self._trusted_dirty:
            self._cached_trusted_df = pd.DataFrame(list(self._trusted_rows))
            self._trusted_dirty = False
        return self._cached_trusted_df

    def record_reading(self, raw_reading: dict, timestamp: pd.Timestamp, verdict: dict, is_dual_buffer: bool = True):
        row = dict(raw_reading)
        row["station_id"] = self.station_id
        row["timestamp"] = timestamp

        # Always append to raw history for causal physical continuity
        self._raw_rows.append(row)
        self._raw_dirty = True

        is_anomaly = bool(verdict.get("is_anomaly", False))
        is_provisional = bool(verdict.get("is_provisional", False))

        if is_dual_buffer:
            # Step 22 Dual-Buffer Rule:
            # Only record to trusted history if it is neither an anomaly nor a provisional/adjudicated candidate
            if not is_anomaly and not is_provisional:
                self._trusted_rows.append(row)
                self._trusted_dirty = True
            elif is_provisional:
                self._provisional_rows.append(row)
        else:
            # Step 21 Single-Buffer Rule (Contamination Control):
            # If not anomaly, immediately admitted into trusted history regardless of provisional status
            if not is_anomaly:
                self._trusted_rows.append(row)
                self._trusted_dirty = True


def score_observation(
    config_name: str,
    raw_reading: dict,
    station_buf: DualStationBuffer,
    neighbor_bufs: dict,
    cusum_state: dict,
    station_id: str,
    ts: pd.Timestamp
) -> dict:
    """
    Evaluates detector stream for a given configuration:
    - config_a: Step 19 (Single buffer, no Diurnal ROC spike adjudicator)
    - config_b: Step 21 (Single buffer, Diurnal ROC adjudicator with baseline contamination)
    - config_c: Step 22 (Dual buffer: raw history for dt/prior, trusted history for dynamic expectation)
    """
    is_dual = (config_name == "config_c")
    use_roc_adj = (config_name in ["config_b", "config_c"])

    # Physical continuity (dt and prior_val) MUST read from RAW history
    raw_hist = station_buf.raw_history_df()

    # Dynamic expectation reads from TRUSTED history in dual buffer mode, or raw in single buffer mode
    clean_hist = station_buf.trusted_history_df() if is_dual else raw_hist

    prior_time = None
    if not raw_hist.empty and "timestamp" in raw_hist.columns:
        valid_ts = pd.to_datetime(raw_hist["timestamp"], utc=True, errors="coerce").dropna()
        if not valid_ts.empty:
            prior_time = valid_ts.iloc[-1]

    dt_hours = max(0.1, (ts - prior_time).total_seconds() / 3600.0) if prior_time is not None else 1.0
    solar_hour = calculate_solar_hour(ts, station_id)

    # ── Tier 0: Hard Invariants
    is_rail, rail_p, rail_reason = baseline_detect._check_hardware_rail(raw_reading)
    is_phys, _ = CrossChannelEngine.check_physical_invariants(raw_reading.get("temperature_c"), raw_reading.get("pressure_hpa"), raw_reading.get("humidity_pct"))

    if is_rail:
        return {"is_anomaly": True, "fault_type": "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low", "tier": 0, "basis": "TIER_0_HARD_RAIL", "is_provisional": False}
    if is_phys:
        return {"is_anomaly": True, "fault_type": "physical_bounds", "tier": 0, "basis": "TIER_0_PHYSICAL_BOUND", "is_provisional": False}

    prior_vals = {}
    dy_vals = {}
    for p in PARAMS:
        val = float(raw_reading[p])
        pv = None
        if not raw_hist.empty and p in raw_hist.columns:
            vps = pd.to_numeric(raw_hist[p], errors="coerce").dropna()
            if not vps.empty:
                pv = float(vps.iloc[-1])
        prior_vals[p] = pv
        dy_vals[p] = (val - pv) if pv is not None else None

    # ── Tier 1: Specialist Faults (Spike Jump & Frozen)
    tier1_evidence = []
    is_adjudicated_provisional = False
    adjudicated_param = None

    for p in PARAMS:
        val = float(raw_reading[p])
        sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
        pv = prior_vals[p]

        if pv is not None:
            raw_jump_mag = abs(val - pv)
            sig_jump = math.sqrt(2.0 * (sensor_floor ** 2) + (sensor_floor ** 2) * dt_hours)
            z_jump = raw_jump_mag / max(1e-4, sig_jump)
            llr_jump = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sig_jump / sensor_floor)))

            if raw_jump_mag >= 2.5 * sensor_floor and z_jump >= 3.0 and llr_jump >= WALD_UPPER_ALERT:
                # Raw spike candidate generated
                is_spike_fired = True

                if use_roc_adj:
                    # Diurnal ROC Adjudicator
                    exp_roc = get_expected_roc(station_id, PREFIX_MAP[p], int(solar_hour) % 24)
                    expected_env_delta = exp_roc * dt_hours
                    raw_delta = val - pv
                    delta_unexplained = raw_delta - expected_env_delta
                    mag_unexplained = abs(delta_unexplained)
                    z_unexplained = mag_unexplained / max(1e-4, sig_jump)

                    # Explained by diurnal movement?
                    is_explained = (
                        (raw_delta * expected_env_delta > 0) and
                        (abs(raw_delta) <= abs(expected_env_delta) + 2.5 * sensor_floor or z_unexplained < 3.0)
                    )

                    if is_explained:
                        is_spike_fired = False
                        is_adjudicated_provisional = True
                        adjudicated_param = p

                if is_spike_fired:
                    tier1_evidence.append({
                        "tier": 1, "type": "spike", "parameter": p, "llr": llr_jump,
                        "basis": f"TIER_1_SPIKE_{p.upper()}"
                    })

        # Frozen sensor check (reads clean history to avoid corrupted frozen baselines)
        f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(p, clean_hist, val, None, 0)
        if f_diag["is_frozen"]:
            tier1_evidence.append({
                "tier": 1, "type": "frozen_value", "parameter": p, "llr": f_llr,
                "basis": f"TIER_1_FROZEN_{p.upper()}"
            })

    if tier1_evidence:
        st = max(tier1_evidence, key=lambda e: e["llr"])
        return {"is_anomaly": True, "fault_type": st["type"], "tier": 1, "basis": st["basis"], "param": st.get("parameter"), "is_provisional": False}

    # ── Tier 2: ROC CUSUM Drift (Step 19 Architecture)
    tier2_evidence = []
    drift_expectations = {}
    drift_residuals = {}

    for p in PARAMS:
        val = float(raw_reading[p])
        pv = prior_vals[p]

        # Dynamic expectation computed from TRUSTED clean history
        exp_val, _ = compute_dynamic_expectation(station_id, p, ts, clean_hist)
        drift_expectations[p] = exp_val
        drift_residuals[p] = val - exp_val

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
        return {"is_anomaly": True, "fault_type": "drift", "tier": 2, "basis": st["basis"], "param": st.get("parameter"), "is_provisional": False}

    # ── Tier 3: Instantaneous Covariance Mahalanobis (Step 18 Architecture)
    if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
        dy_vec = np.array([dy_vals[p] for p in PARAMS], dtype=float)
        cov_dt = COV_DELTA_1H * dt_hours
        inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
        d_sq_inst = float(dy_vec.T @ inv_cov_dt @ dy_vec)
        if d_sq_inst > 16.27:
            return {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "tier": 3, "basis": "TIER_3_INSTANT_COV", "d_sq": d_sq_inst, "is_provisional": False}

    return {
        "is_anomaly": False, "fault_type": None, "tier": -1, "basis": "NORMAL",
        "is_provisional": is_adjudicated_provisional, "adjudicated_param": adjudicated_param,
        "exp_val_t": drift_expectations.get("temperature_c"),
        "res_t": drift_residuals.get("temperature_c")
    }


def eval_seed_step22(args):
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

    state_traces = []

    for cfg in configs:
        buffers = {st_id: DualStationBuffer(st_id) for st_id in station_ids}
        cusum_state = {st_id: {p: {"pos": 0.0, "neg": 0.0} for p in PARAMS} for st_id in station_ids}

        tp = fp = fn = tn = 0
        tier_counts = {}
        fault_tp = {}
        fault_fn = {}
        channel_tp = {}
        channel_fp = {}
        predictions = []

        is_dual = (cfg == "config_c")

        for idx, row in enumerate(rows):
            st_id = row["station_id"]
            ts = row["timestamp"]
            gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
            gt_type = row.get("fault_type", "unknown") if gt else None

            sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
            buf = buffers[st_id]
            neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}

            verdict = score_observation(cfg, row, buf, neighbor_bufs, cusum_state, st_id, ts)
            buf.record_reading(row, timestamp=ts, verdict=verdict, is_dual_buffer=is_dual)

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

            # Log sample state trace for seed 42 on drift faults
            if seed == 42 and st_id == "AWS-CHN-024" and gt_type == "drift" and cfg in ["config_b", "config_c"]:
                state_traces.append({
                    "config": cfg, "timestamp": str(ts), "val_t": row["temperature_c"],
                    "exp_val_t": verdict.get("exp_val_t"), "res_t": verdict.get("res_t"),
                    "is_pred": is_pred, "tier": tier_num, "is_provisional": verdict.get("is_provisional", False)
                })

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

    # Transition Analysis (Config B -> Config C)
    preds_b = results["config_b"]["predictions"]
    preds_c = results["config_c"]["predictions"]

    transitions = []
    for idx, row in enumerate(rows):
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type", "unknown") if gt else None
        pb = preds_b[idx]
        pc = preds_c[idx]

        if pb != pc:
            t_type = "UNKNOWN"
            if pb and not pc and not gt: t_type = "FP_REMOVED"
            elif pb and not pc and gt: t_type = "TP_REMOVED"
            elif not pb and pc and gt: t_type = "TP_RECOVERED"
            elif not pb and pc and not gt: t_type = "FP_ADDED"

            transitions.append({
                "seed": seed, "station_id": row["station_id"], "timestamp": str(row["timestamp"]),
                "transition_type": t_type, "gt_is_anomaly": gt, "gt_fault_type": gt_type,
                "pred_b": pb, "pred_c": pc
            })

    return {
        "seed": seed,
        "results": results,
        "transitions": transitions,
        "state_traces": state_traces
    }


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 22: DECOUPLED DUAL-BUFFER STATE ARCHITECTURE BENCHMARK (7 LOCKED SEEDS)")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        worker_outputs = list(executor.map(eval_seed_step22, tasks))

    cfg_keys = ["config_a", "config_b", "config_c"]
    cfg_names = {
        "config_a": "Step 19 Baseline Reference",
        "config_b": "Step 21 Reference (Single Buffer / Contaminated)",
        "config_c": "Step 22 Decoupled Dual Buffer (Raw vs Trusted Clean)"
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
    print("STEP 22 MACRO BENCHMARK RESULTS ACROSS 7 LOCKED SEEDS")
    print("=" * 80)
    print(macro_df[["config_name", "macro_precision", "macro_recall", "macro_f1", "mean_tp", "mean_fp", "mean_fn"]].to_string(index=False))

    print("\n" + "=" * 80)
    print("PER-SEED BREAKDOWN")
    print("=" * 80)
    for cfg in cfg_keys:
        print(f"\n--- {cfg_names[cfg]} ---")
        print(all_seeds_df[all_seeds_df["config_id"] == cfg][["seed", "precision", "recall", "f1", "tp", "fp", "fn"]].to_string(index=False))

    # Compile Transition Audit (Config B -> Config C)
    all_transitions = []
    all_traces = []
    for w in worker_outputs:
        all_transitions.extend(w["transitions"])
        all_traces.extend(w["state_traces"])

    df_trans = pd.DataFrame(all_transitions)
    df_trans.to_csv(OUTPUT_DIR / "step22_transition_audit.csv", index=False)

    df_traces = pd.DataFrame(all_traces)
    df_traces.to_csv(OUTPUT_DIR / "step22_state_trace.csv", index=False)

    print("\n" + "=" * 80)
    print("STEP 22 TRANSITION AUDIT (Config B Contaminated -> Config C Dual Buffer)")
    print("=" * 80)
    t_counts = df_trans["transition_type"].value_counts()
    print(pd.DataFrame({"Count": t_counts, "Mean_per_seed": t_counts / 7.0}).to_string())

    print("\n--- TP Recovered by Fault Type ---")
    df_tp_rec = df_trans[df_trans["transition_type"] == "TP_RECOVERED"]
    print(df_tp_rec["gt_fault_type"].value_counts())

    # Per-Fault Recall Comparison
    print("\n" + "=" * 80)
    print("PER-FAULT RECALL AUDIT (Step 19 vs Step 21 vs Step 22)")
    print("=" * 80)
    fault_names = ["spike", "frozen_value", "drift", "sensor_fail_low", "dropout", "multivariate_inconsistency", "unstructured_anomaly"]
    fault_audit_rows = []
    for fn in fault_names:
        tp_19 = np.mean([w["results"]["config_a"]["fault_tp"].get(fn, 0) for w in worker_outputs])
        tp_21 = np.mean([w["results"]["config_b"]["fault_tp"].get(fn, 0) for w in worker_outputs])
        tp_22 = np.mean([w["results"]["config_c"]["fault_tp"].get(fn, 0) for w in worker_outputs])

        fn_19 = np.mean([w["results"]["config_a"]["fault_fn"].get(fn, 0) for w in worker_outputs])
        fn_21 = np.mean([w["results"]["config_b"]["fault_fn"].get(fn, 0) for w in worker_outputs])
        fn_22 = np.mean([w["results"]["config_c"]["fault_fn"].get(fn, 0) for w in worker_outputs])

        rec_19 = tp_19 / (tp_19 + fn_19) * 100.0 if (tp_19 + fn_19) > 0 else 0.0
        rec_21 = tp_21 / (tp_21 + fn_21) * 100.0 if (tp_21 + fn_21) > 0 else 0.0
        rec_22 = tp_22 / (tp_22 + fn_22) * 100.0 if (tp_22 + fn_22) > 0 else 0.0

        fault_audit_rows.append({
            "Fault_Type": fn,
            "TP_Step19": tp_19, "TP_Step21": tp_21, "TP_Step22": tp_22,
            "Recall_Step19": rec_19, "Recall_Step21": rec_21, "Recall_Step22": rec_22,
            "Recovery_TP": tp_22 - tp_21,
            "Recovery_Recall_pp": rec_22 - rec_21
        })
    df_faults = pd.DataFrame(fault_audit_rows)
    print(df_faults.to_string(index=False))
    df_faults.to_csv(OUTPUT_DIR / "step22_episode_audit.csv", index=False)

    macro_df.to_csv(OUTPUT_DIR / "step22_macro_summary.csv", index=False)
    print(f"\nOutputs saved to {OUTPUT_DIR}")
    print(f"Total benchmark runtime: {time.time() - t0:.2f} seconds!")


if __name__ == "__main__":
    main()
