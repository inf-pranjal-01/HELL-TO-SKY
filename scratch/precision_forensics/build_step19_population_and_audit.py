"""
scratch/precision_forensics/build_step19_population_and_audit.py

Step 19: Full Lost-TP Population Analysis & Multi-Seed Forensic Audit.
Generates:
1. scratch/precision_forensics/step19_lost_tp_population.csv
2. Complete fault-type and channel classification breakdowns across all 7 seeds.
3. Representative drift trajectories (T, P, H) comparing Step 16 vs Step 18 vs Step 19.
4. Precision and Recall reconciliation tables.
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
from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.seasonal_baseline import get_expected_roc
from model.sequential_sprt import SequentialSPRT
from model.cross_channel_covariance import CrossChannelEngine
from model.state import StationBuffer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]
PREFIX_MAP = {"temperature_c": "temp", "pressure_hpa": "pressure", "humidity_pct": "humidity"}
WALD_UPPER_ALERT, WALD_LOWER_NORMAL = SequentialSPRT.get_wald_boundaries(alpha=0.002, beta=0.05)

COV_DELTA_1H = np.array([
    [ 1.779049, -0.016319, -6.494229],
    [-0.016319,  0.452587,  0.250640],
    [-6.494229,  0.250640, 32.893058]
], dtype=float)
INV_COV_DELTA_1H = np.linalg.pinv(COV_DELTA_1H + 1e-5 * np.eye(3))


def audit_single_seed(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    
    # We run 3 parallel detectors:
    # 1. Step 16 Baseline
    # 2. Step 18 Untouched
    # 3. Step 19 Candidate
    buf_16 = {st_id: StationBuffer(st_id) for st_id in station_ids}
    buf_18 = {st_id: StationBuffer(st_id) for st_id in station_ids}
    buf_19 = {st_id: StationBuffer(st_id) for st_id in station_ids}
    cusum_19 = {st_id: {p: {"pos": 0.0, "neg": 0.0} for p in PARAMS} for st_id in station_ids}

    lost_tps = []
    seed_stats = {
        "step16": {"tp": 0, "fp": 0, "fn": 0, "fault_tp": {}, "channel_tp": {}},
        "step18": {"tp": 0, "fp": 0, "fn": 0, "fault_tp": {}, "channel_tp": {}},
        "step19": {"tp": 0, "fp": 0, "fn": 0, "fault_tp": {}, "channel_tp": {}},
    }

    rows = eval_df.to_dict("records")
    for row in rows:
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type", "unknown") if gt else None
        cluster_id = row.get("cluster_id", "unknown")

        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)

        # ── 1. STEP 16 EVALUATION ──
        h_16 = buf_16[st_id].raw_history_df()
        n_16 = {nid: buf_16[nid].raw_history_df() for nid in sibling_ids if nid in buf_16}
        
        pt_16 = None
        if not h_16.empty and "timestamp" in h_16.columns:
            vts = pd.to_datetime(h_16["timestamp"], utc=True, errors="coerce").dropna()
            if not vts.empty: pt_16 = vts.iloc[-1]
        dt_16 = max(0.1, (ts - pt_16).total_seconds() / 3600.0) if pt_16 is not None else 1.0
        sol_16 = calculate_solar_hour(ts, st_id)

        # Step 16 T0
        is_rail_16, _, _ = baseline_detect._check_hardware_rail(row)
        is_phys_16, _ = CrossChannelEngine.check_physical_invariants(row.get("temperature_c"), row.get("pressure_hpa"), row.get("humidity_pct"))
        v_16 = {"is_anomaly": False, "tier": -1, "basis": "NORMAL"}

        if is_rail_16: v_16 = {"is_anomaly": True, "tier": 0, "basis": "TIER_0_HARD_RAIL"}
        elif is_phys_16: v_16 = {"is_anomaly": True, "tier": 0, "basis": "TIER_0_PHYSICAL_BOUND"}
        else:
            t1_16 = []
            innov_16 = {}
            unc_16 = {}
            for p in PARAMS:
                val = float(row[p])
                pv = None
                if not h_16.empty and p in h_16.columns:
                    vps = pd.to_numeric(h_16[p], errors="coerce").dropna()
                    if not vps.empty: pv = float(vps.iloc[-1])
                fl = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                if pv is not None:
                    jm = abs(val - pv)
                    if jm >= 2.5 * fl:
                        sj = math.sqrt(2.0 * (fl**2) + (fl**2) * dt_16)
                        zj = jm / max(1e-4, sj)
                        lj = float(0.5 * (zj**2) - math.log(max(1.1, sj / fl)))
                        if lj >= 5.86 and zj >= 3.0: t1_16.append({"tier": 1, "llr": lj, "basis": "TIER_1_SPIKE"})
                f_l, _, f_d = baseline_detect.evaluate_frozen_evidence(p, h_16, val, None, 0)
                if f_d["is_frozen"]: t1_16.append({"tier": 1, "llr": f_l, "basis": "TIER_1_FROZEN"})

                exp_v, _ = compute_dynamic_expectation(st_id, p, ts, h_16)
                sig_t, _ = UncertaintyBudget.compute_composite_predictive_uncertainty(p, sol_16, dt_16, h_16, 0.0)
                innov_16[p] = val - exp_v
                unc_16[p] = sig_t

            if t1_16:
                st = max(t1_16, key=lambda e: e["llr"])
                v_16 = {"is_anomaly": True, "tier": 1, "basis": st["basis"]}
            else:
                # Step 16 T3 static Mahalanobis
                d_sq, _, cc_d = CrossChannelEngine.compute_mahalanobis_distance(
                    innov_16["temperature_c"] / unc_16["temperature_c"],
                    innov_16["pressure_hpa"] / unc_16["pressure_hpa"],
                    innov_16["humidity_pct"] / unc_16["humidity_pct"]
                )
                if cc_d["is_multivariate_outlier"]:
                    v_16 = {"is_anomaly": True, "tier": 3, "basis": "TIER_3_STATIC_MAHALANOBIS", "d_sq": d_sq}

        buf_16[st_id].record_raw_reading(row, timestamp=ts, verdict=v_16)

        # ── 2. STEP 18 EVALUATION ──
        h_18 = buf_18[st_id].raw_history_df()
        pt_18 = None
        if not h_18.empty and "timestamp" in h_18.columns:
            vts = pd.to_datetime(h_18["timestamp"], utc=True, errors="coerce").dropna()
            if not vts.empty: pt_18 = vts.iloc[-1]
        dt_18 = max(0.1, (ts - pt_18).total_seconds() / 3600.0) if pt_18 is not None else 1.0
        sol_18 = calculate_solar_hour(ts, st_id)

        is_rail_18, _, _ = baseline_detect._check_hardware_rail(row)
        is_phys_18, _ = CrossChannelEngine.check_physical_invariants(row.get("temperature_c"), row.get("pressure_hpa"), row.get("humidity_pct"))
        v_18 = {"is_anomaly": False, "tier": -1, "basis": "NORMAL"}

        if is_rail_18: v_18 = {"is_anomaly": True, "tier": 0, "basis": "TIER_0_HARD_RAIL"}
        elif is_phys_18: v_18 = {"is_anomaly": True, "tier": 0, "basis": "TIER_0_PHYSICAL_BOUND"}
        else:
            t1_18 = []
            dy_18 = {}
            for p in PARAMS:
                val = float(row[p])
                pv = None
                if not h_18.empty and p in h_18.columns:
                    vps = pd.to_numeric(h_18[p], errors="coerce").dropna()
                    if not vps.empty: pv = float(vps.iloc[-1])
                dy_18[p] = (val - pv) if pv is not None else None
                fl = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                if pv is not None:
                    jm = abs(val - pv)
                    if jm >= 2.5 * fl:
                        sj = math.sqrt(2.0 * (fl**2) + (fl**2) * dt_18)
                        zj = jm / max(1e-4, sj)
                        lj = float(0.5 * (zj**2) - math.log(max(1.1, sj / fl)))
                        if lj >= 5.86 and zj >= 3.0: t1_18.append({"tier": 1, "llr": lj, "basis": "TIER_1_SPIKE"})
                f_l, _, f_d = baseline_detect.evaluate_frozen_evidence(p, h_18, val, None, 0)
                if f_d["is_frozen"]: t1_18.append({"tier": 1, "llr": f_l, "basis": "TIER_1_FROZEN"})

            if t1_18:
                st = max(t1_18, key=lambda e: e["llr"])
                v_18 = {"is_anomaly": True, "tier": 1, "basis": st["basis"]}
            else:
                # Step 18 Instantaneous Covariance Tier 3
                if all(dy_18[p] is not None for p in PARAMS) and dt_18 <= 2.5:
                    dy_vec = np.array([dy_18[p] for p in PARAMS], dtype=float)
                    cov_dt = COV_DELTA_1H * dt_18
                    inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
                    d_sq_inst = float(dy_vec.T @ inv_cov_dt @ dy_vec)
                    if d_sq_inst > 16.27:
                        v_18 = {"is_anomaly": True, "tier": 3, "basis": "TIER_3_INSTANT_COV", "d_sq": d_sq_inst}

        buf_18[st_id].record_raw_reading(row, timestamp=ts, verdict=v_18)

        # ── 3. STEP 19 CANDIDATE EVALUATION ──
        h_19 = buf_19[st_id].raw_history_df()
        pt_19 = None
        if not h_19.empty and "timestamp" in h_19.columns:
            vts = pd.to_datetime(h_19["timestamp"], utc=True, errors="coerce").dropna()
            if not vts.empty: pt_19 = vts.iloc[-1]
        dt_19 = max(0.1, (ts - pt_19).total_seconds() / 3600.0) if pt_19 is not None else 1.0
        sol_19 = calculate_solar_hour(ts, st_id)

        is_rail_19, _, _ = baseline_detect._check_hardware_rail(row)
        is_phys_19, _ = CrossChannelEngine.check_physical_invariants(row.get("temperature_c"), row.get("pressure_hpa"), row.get("humidity_pct"))
        v_19 = {"is_anomaly": False, "tier": -1, "basis": "NORMAL"}

        if is_rail_19: v_19 = {"is_anomaly": True, "tier": 0, "basis": "TIER_0_HARD_RAIL"}
        elif is_phys_19: v_19 = {"is_anomaly": True, "tier": 0, "basis": "TIER_0_PHYSICAL_BOUND"}
        else:
            t1_19 = []
            dy_19 = {}
            prior_19 = {}
            for p in PARAMS:
                val = float(row[p])
                pv = None
                if not h_19.empty and p in h_19.columns:
                    vps = pd.to_numeric(h_19[p], errors="coerce").dropna()
                    if not vps.empty: pv = float(vps.iloc[-1])
                prior_19[p] = pv
                dy_19[p] = (val - pv) if pv is not None else None
                fl = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                if pv is not None:
                    jm = abs(val - pv)
                    if jm >= 2.5 * fl:
                        sj = math.sqrt(2.0 * (fl**2) + (fl**2) * dt_19)
                        zj = jm / max(1e-4, sj)
                        lj = float(0.5 * (zj**2) - math.log(max(1.1, sj / fl)))
                        if lj >= 5.86 and zj >= 3.0: t1_19.append({"tier": 1, "llr": lj, "basis": "TIER_1_SPIKE"})
                f_l, _, f_d = baseline_detect.evaluate_frozen_evidence(p, h_19, val, None, 0)
                if f_d["is_frozen"]: t1_19.append({"tier": 1, "llr": f_l, "basis": "TIER_1_FROZEN"})

            if t1_19:
                st = max(t1_19, key=lambda e: e["llr"])
                v_19 = {"is_anomaly": True, "tier": 1, "basis": st["basis"]}
            else:
                # Tier 2 ROC CUSUM
                t2_19 = []
                for p in PARAMS:
                    val = float(row[p])
                    pv = prior_19[p]
                    if pv is not None and dt_19 <= 3.0:
                        raw_roc = (val - pv) / dt_19
                        exp_roc = get_expected_roc(st_id, PREFIX_MAP[p], int(sol_19) % 24)
                        roc_res = raw_roc - exp_roc
                        
                        fl = SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                        sig_roc = math.sqrt(2.0 * (fl**2) + (fl**2) * dt_19) / dt_19
                        z_roc = roc_res / max(1e-4, sig_roc)
                        decay = math.exp(-dt_19 / 24.0)
                        allowance = 0.5
                        
                        sp = max(0.0, cusum_19[st_id][p]["pos"] * decay + (z_roc - allowance))
                        sn = max(0.0, cusum_19[st_id][p]["neg"] * decay + (-z_roc - allowance))
                        cusum_19[st_id][p]["pos"] = sp
                        cusum_19[st_id][p]["neg"] = sn
                        if max(sp, sn) >= 5.86:
                            t2_19.append({"tier": 2, "llr": max(sp, sn), "basis": "TIER_2_ROC_CUSUM", "param": p})
                    else:
                        decay = math.exp(-dt_19 / 24.0)
                        cusum_19[st_id][p]["pos"] *= decay
                        cusum_19[st_id][p]["neg"] *= decay

                if t2_19:
                    st = max(t2_19, key=lambda e: e["llr"])
                    v_19 = {"is_anomaly": True, "tier": 2, "basis": st["basis"]}
                else:
                    # Tier 3 Untouched Step 18 Instantaneous Covariance
                    if all(dy_19[p] is not None for p in PARAMS) and dt_19 <= 2.5:
                        dy_vec = np.array([dy_19[p] for p in PARAMS], dtype=float)
                        cov_dt = COV_DELTA_1H * dt_19
                        inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
                        d_sq_inst = float(dy_vec.T @ inv_cov_dt @ dy_vec)
                        if d_sq_inst > 16.27:
                            v_19 = {"is_anomaly": True, "tier": 3, "basis": "TIER_3_INSTANT_COV", "d_sq": d_sq_inst}

        buf_19[st_id].record_raw_reading(row, timestamp=ts, verdict=v_19)
        if v_19["is_anomaly"] and v_19["tier"] == 2:
            for p in PARAMS:
                if cusum_19[st_id][p]["pos"] >= 5.86: cusum_19[st_id][p]["pos"] = 0.0
                if cusum_19[st_id][p]["neg"] >= 5.86: cusum_19[st_id][p]["neg"] = 0.0

        # Update stats
        for k, v in [("step16", v_16), ("step18", v_18), ("step19", v_19)]:
            is_p = v["is_anomaly"]
            if is_p and gt:
                seed_stats[k]["tp"] += 1
                if gt_type:
                    seed_stats[k]["fault_tp"][gt_type] = seed_stats[k]["fault_tp"].get(gt_type, 0) + 1
            elif is_p and not gt:
                seed_stats[k]["fp"] += 1
            elif not is_p and gt:
                seed_stats[k]["fn"] += 1

        # Check for Lost TP (Detected in Step 16, missed in Step 18)
        if gt and v_16["is_anomaly"] and not v_18["is_anomaly"]:
            lost_tps.append({
                "seed": seed,
                "station_id": st_id,
                "cluster_id": cluster_id,
                "timestamp": str(ts),
                "fault_type": gt_type,
                "temperature_c": row["temperature_c"],
                "pressure_hpa": row["pressure_hpa"],
                "humidity_pct": row["humidity_pct"],
                "dt_hours": dt_16,
                "v16_tier": v_16.get("tier"),
                "v16_basis": v_16.get("basis"),
                "v18_tier": v_18.get("tier"),
                "v18_basis": v_18.get("basis"),
                "v19_tier": v_19.get("tier"),
                "v19_basis": v_19.get("basis"),
                "v19_recovered": bool(v_19["is_anomaly"])
            })

    return {
        "seed": seed,
        "stats": seed_stats,
        "lost_tps": lost_tps
    }


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 19: FULL LOST-TP AUDIT & POPULATION EXTRACTION (7 SEEDS)")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(audit_single_seed, tasks))

    all_lost_tps = []
    for r in results:
        all_lost_tps.extend(r["lost_tps"])

    df_lost = pd.DataFrame(all_lost_tps)
    df_lost.to_csv(OUTPUT_DIR / "step19_lost_tp_population.csv", index=False)
    print(f"Total Lost TPs across 7 seeds: {len(df_lost)} (Mean {len(df_lost)/7:.1f} per seed)")
    print(f"Saved population to {OUTPUT_DIR / 'step19_lost_tp_population.csv'}")

    print("\n--- Lost TP Breakdown by Fault Type across All 7 Seeds ---")
    print(df_lost["fault_type"].value_counts())
    print(df_lost["fault_type"].value_counts(normalize=True) * 100.0)

    print("\n--- Lost TP Recovery Rate in Step 19 Candidate ---")
    print(df_lost.groupby("fault_type")["v19_recovered"].value_counts().unstack().fillna(0))

    # Compile benchmark summaries
    summary_rows = []
    for k in ["step16", "step18", "step19"]:
        precs = []
        recs = []
        f1s = []
        tps = []
        fps = []
        fns = []
        for r in results:
            s = r["stats"][k]
            p = s["tp"] / (s["tp"] + s["fp"]) * 100.0 if (s["tp"] + s["fp"]) > 0 else 0.0
            rc = s["tp"] / (s["tp"] + s["fn"]) * 100.0 if (s["tp"] + s["fn"]) > 0 else 0.0
            f = 2 * p * rc / (p + rc) if (p + rc) > 0 else 0.0
            precs.append(p)
            recs.append(rc)
            f1s.append(f)
            tps.append(s["tp"])
            fps.append(s["fp"])
            fns.append(s["fn"])

        summary_rows.append({
            "config": k,
            "macro_precision": np.mean(precs),
            "macro_recall": np.mean(recs),
            "macro_f1": np.mean(f1s),
            "mean_tp": np.mean(tps),
            "mean_fp": np.mean(fps),
            "mean_fn": np.mean(fns),
            "std_precision": np.std(precs),
            "std_recall": np.std(recs),
            "std_f1": np.std(f1s)
        })

    sum_df = pd.DataFrame(summary_rows)
    print("\n" + "=" * 80)
    print("STEP 19 COMPREHENSIVE BENCHMARK SUMMARY")
    print("=" * 80)
    print(sum_df.to_string(index=False))
    sum_df.to_csv(OUTPUT_DIR / "step19_macro_summary.csv", index=False)


if __name__ == "__main__":
    main()
