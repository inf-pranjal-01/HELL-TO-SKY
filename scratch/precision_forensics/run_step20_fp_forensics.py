"""
scratch/precision_forensics/run_step20_fp_forensics.py

Step 20: Comprehensive False-Positive Mechanism Map & TP Safety Audit.
Extracts:
1. Complete Step-19 False Positive population (all 7 seeds, ~31,743 total FP observations).
2. Diagnostic telemetry: peer consensus, cross-channel coherence, diurnal phase, temporal persistence.
3. Classifies mutually exclusive root-cause mechanisms (Taxonomy A-L).
4. Evaluates TP Safety: measures TP overlap for every proposed rejection mechanism.
5. Generates step20_fp_population.csv and step20_fp_removability_matrix.csv.
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
from model.cross_channel_covariance import CrossChannelEngine, compute_dewpoint_c
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
INV_COV_DELTA_1H = np.linalg.pinv(COV_DELTA_1H + 1e-5 * np.eye(3))


def evaluate_and_extract_fps_for_seed(args):
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    cusum_state = {st_id: {p: {"pos": 0.0, "neg": 0.0} for p in PARAMS} for st_id in station_ids}

    fps = []
    tps = []
    fns = []

    # Map entire dataframe for future temporal context lookups (offline forensics only)
    df_by_station = {sid: grp.sort_values("timestamp").reset_index(drop=True) for sid, grp in eval_df.groupby("station_id")}

    rows = eval_df.to_dict("records")
    for idx, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt = bool(row["is_anomaly"]) if pd.notna(row["is_anomaly"]) else False
        gt_type = row.get("fault_type", "unknown") if gt else None
        cluster_id = row.get("cluster_id", "unknown")

        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        buf = buffers[st_id]
        neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
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
        is_phys, phys_reason = CrossChannelEngine.check_physical_invariants(row.get("temperature_c"), row.get("pressure_hpa"), row.get("humidity_pct"))

        verdict = {"is_anomaly": False, "fault_type": None, "tier": -1, "basis": "NORMAL"}
        diagnostics = {}

        if is_rail:
            verdict = {"is_anomaly": True, "fault_type": "dropout" if "dropout" in (rail_reason or "") else "sensor_fail_low", "tier": 0, "basis": "TIER_0_HARD_RAIL"}
        elif is_phys:
            verdict = {"is_anomaly": True, "fault_type": "physical_bounds", "tier": 0, "basis": "TIER_0_PHYSICAL_BOUND"}
        else:
            dy_vals = {}
            prior_vals = {}
            expectations = {}
            uncertainties = {}
            innovations = {}
            peer_medians = {}
            peer_dispersions = {}
            peer_rocs = {}

            for param in PARAMS:
                val = float(row[param])
                p_val = None
                if not hist_df.empty and param in hist_df.columns:
                    vp = pd.to_numeric(hist_df[param], errors="coerce").dropna()
                    if not vp.empty:
                        p_val = float(vp.iloc[-1])
                prior_vals[param] = p_val
                dy_vals[param] = (val - p_val) if p_val is not None else None

                p_med, p_disp, n_p = PeerSpatialEngine.compute_robust_peer_consensus(st_id, param, ts, neighbor_bufs)
                peer_medians[param] = p_med
                peer_dispersions[param] = p_disp

                exp_val, _ = compute_dynamic_expectation(st_id, param, ts, hist_df)
                expectations[param] = exp_val
                innovations[param] = val - exp_val

                sig_tot, _ = UncertaintyBudget.compute_composite_predictive_uncertainty(param, solar_hour, dt_hours, hist_df, p_disp or 0.0)
                uncertainties[param] = sig_tot

                # Compute peer ROC consensus
                p_rocs = []
                for nid, nbuf in neighbor_bufs.items():
                    nhist = nbuf.raw_history_df()
                    if len(nhist) >= 2 and param in nhist.columns:
                        n_vals = pd.to_numeric(nhist[param], errors="coerce").dropna().values
                        if len(n_vals) >= 2:
                            p_rocs.append(float(n_vals[-1] - n_vals[-2]))
                peer_rocs[param] = np.median(p_rocs) if p_rocs else 0.0

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
                        llr_j = float(0.5 * (zj := z_j)**2 - math.log(max(1.1, sig_j / sensor_floor)))
                        if llr_j >= 5.86 and z_j >= 3.0:
                            t1_ev.append({"tier": 1, "type": "spike", "parameter": param, "llr": llr_j, "basis": f"TIER_1_SPIKE_{param.upper()}", "jump_mag": jump_mag, "z_j": z_j})

                f_llr, f_reason, f_diag = baseline_detect.evaluate_frozen_evidence(param, hist_df, val, peer_dispersions[param], len(neighbor_bufs))
                if f_diag["is_frozen"]:
                    t1_ev.append({"tier": 1, "type": "frozen_value", "parameter": param, "llr": f_llr, "basis": f"TIER_1_FROZEN_{param.upper()}"})

            if t1_ev:
                st = max(t1_ev, key=lambda e: e["llr"])
                verdict = {"is_anomaly": True, "fault_type": st["type"], "tier": 1, "basis": st["basis"], "param": st.get("parameter")}
                diagnostics = st
            else:
                # Tier 2 ROC CUSUM
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
                        
                        sp = max(0.0, cusum_state[st_id][param]["pos"] * decay + (z_roc - allowance))
                        sn = max(0.0, cusum_state[st_id][param]["neg"] * decay + (-z_roc - allowance))
                        cusum_state[st_id][param]["pos"] = sp
                        cusum_state[st_id][param]["neg"] = sn
                        if max(sp, sn) >= 5.86:
                            t2_ev.append({"tier": 2, "type": "drift", "parameter": param, "llr": max(sp, sn), "basis": f"TIER_2_DRIFT_{param.upper()}", "cusum_llr": max(sp, sn)})
                    else:
                        decay = math.exp(-dt_hours / 24.0)
                        cusum_state[st_id][param]["pos"] *= decay
                        cusum_state[st_id][param]["neg"] *= decay

                if t2_ev:
                    st = max(t2_ev, key=lambda e: e["llr"])
                    verdict = {"is_anomaly": True, "fault_type": "drift", "tier": 2, "basis": st["basis"], "param": st.get("parameter")}
                    diagnostics = st
                else:
                    # Tier 3 Untouched Step 18 Instantaneous Covariance
                    if all(dy_vals[p] is not None for p in PARAMS) and dt_hours <= 2.5:
                        dy_vec = np.array([dy_vals[p] for p in PARAMS], dtype=float)
                        cov_dt = COV_DELTA_1H * dt_hours
                        inv_cov_dt = np.linalg.pinv(cov_dt + 1e-5 * np.eye(3))
                        d_sq_inst = float(dy_vec.T @ inv_cov_dt @ dy_vec)
                        if d_sq_inst > 16.27:
                            verdict = {"is_anomaly": True, "fault_type": "multivariate_inconsistency", "tier": 3, "basis": "TIER_3_INSTANT_COV", "d_sq": d_sq_inst}
                            diagnostics = {"d_sq": d_sq_inst}

        buf.record_raw_reading(row, timestamp=ts, verdict=verdict)
        if verdict["is_anomaly"] and verdict["tier"] == 2:
            for p in PARAMS:
                if cusum_state[st_id][p]["pos"] >= 5.86: cusum_state[st_id][p]["pos"] = 0.0
                if cusum_state[st_id][p]["neg"] >= 5.86: cusum_state[st_id][p]["neg"] = 0.0

        is_pred = verdict["is_anomaly"]

        # Contextual feature extraction for point
        # Look ahead 3 hours offline to assess natural continuation/recovery (forensic only)
        st_df = df_by_station[st_id]
        curr_row_idx = st_df[st_df["timestamp"] == ts].index[0]
        subsequent_3h = st_df.iloc[curr_row_idx+1:curr_row_idx+4] if curr_row_idx + 1 < len(st_df) else pd.DataFrame()

        # Check subsequent trajectory
        subsequent_delta_t = (subsequent_3h["temperature_c"].iloc[-1] - row["temperature_c"]) if len(subsequent_3h) > 0 else 0.0
        subsequent_delta_p = (subsequent_3h["pressure_hpa"].iloc[-1] - row["pressure_hpa"]) if len(subsequent_3h) > 0 else 0.0
        subsequent_delta_h = (subsequent_3h["humidity_pct"].iloc[-1] - row["humidity_pct"]) if len(subsequent_3h) > 0 else 0.0

        # Peer agreement: did peers move in same direction?
        # Check if target dy and peer_roc have same sign and significant magnitude
        flagged_param = verdict.get("param", "temperature_c") if verdict.get("param") in PARAMS else "temperature_c"
        target_dy = dy_vals.get(flagged_param, 0.0) or 0.0
        peer_dy = peer_rocs.get(flagged_param, 0.0)
        peer_agrees = (target_dy * peer_dy > 0) and (abs(peer_dy) > 0.5 * abs(target_dy))

        # Cross-channel thermodynamic coherence: dT and dRH opposite sign
        dy_t = dy_vals.get("temperature_c", 0.0) or 0.0
        dy_h = dy_vals.get("humidity_pct", 0.0) or 0.0
        thermo_coherent = (dy_t * dy_h < 0) or (abs(dy_t) < 0.2 and abs(dy_h) < 1.0)

        # Diurnal transition: near sunrise (hours 5-8) or sunset/cooling (hours 17-20)
        solar_h_int = int(solar_hour) % 24
        is_diurnal_transition = (5 <= solar_h_int <= 8) or (17 <= solar_h_int <= 20)

        # Cadence/Gap
        is_gap_artifact = dt_hours > 2.0

        # Mechanism Classification (Taxonomy A-L)
        mechanism = "UNKNOWN"
        if verdict["tier"] == 1 and "SPIKE" in verdict["basis"]:
            if peer_agrees and thermo_coherent:
                mechanism = "PEER-CONSISTENT_MOVEMENT"
            elif thermo_coherent and is_diurnal_transition:
                mechanism = "SOLAR_OR_DIURNAL_TRANSITION"
            elif thermo_coherent and not peer_agrees:
                mechanism = "ENVIRONMENTAL_TRANSITION_WITH_CROSS_CHANNEL_COHERENCE"
            elif is_gap_artifact:
                mechanism = "CADENCE_OR_GAP_ARTIFACT"
            elif abs(target_dy) <= 2.5 * SENSOR_QUANTIZATION_FLOORS.get(flagged_param, 0.1):
                mechanism = "SENSOR_QUANTIZATION_OR_MEASUREMENT_FLOOR_EFFECT"
            else:
                mechanism = "ENVIRONMENTAL_TRANSITION"

        elif verdict["tier"] == 1 and "FROZEN" in verdict["basis"]:
            p_disp_val = peer_dispersions.get(flagged_param)
            if p_disp_val is not None and p_disp_val < 0.2:
                mechanism = "PEER_MODEL_MISMATCH"
            else:
                mechanism = "CONTEXTUAL_EXPECTATION_MISMATCH"

        elif verdict["tier"] == 2:
            if peer_agrees:
                mechanism = "PEER-CONSISTENT_MOVEMENT"
            else:
                mechanism = "DRIFT_CUSUM_FALSE_ALARM"

        elif verdict["tier"] == 3:
            if thermo_coherent:
                mechanism = "CROSS_CHANNEL_MODEL_MISMATCH"
            else:
                mechanism = "ENVIRONMENTAL_TRANSITION"

        point_record = {
            "seed": seed, "station_id": st_id, "cluster_id": cluster_id, "timestamp": str(ts),
            "tier": verdict["tier"], "decision_basis": verdict["basis"], "flagged_param": flagged_param,
            "val_t": row["temperature_c"], "val_p": row["pressure_hpa"], "val_h": row["humidity_pct"],
            "dy_t": dy_t, "dy_p": dy_vals.get("pressure_hpa", 0.0), "dy_h": dy_h,
            "dt_hours": dt_hours, "solar_hour": solar_hour,
            "peer_dy": peer_dy, "peer_agrees": bool(peer_agrees),
            "thermo_coherent": bool(thermo_coherent),
            "is_diurnal_transition": bool(is_diurnal_transition),
            "is_gap_artifact": bool(is_gap_artifact),
            "mechanism": mechanism,
            "gt_is_anomaly": gt, "gt_fault_type": gt_type
        }

        if is_pred and not gt:
            fps.append(point_record)
        elif is_pred and gt:
            tps.append(point_record)
        elif not is_pred and gt:
            fns.append(point_record)

    return {"seed": seed, "fps": fps, "tps": tps, "fns": fns}


def main():
    t0 = time.time()
    print("=" * 80)
    print("STEP 20: COMPLETE FALSE-POSITIVE MECHANISM MAP & TP-SAFETY AUDIT")
    print("=" * 80)

    all_stations_file = DATA_DIR / "all_stations.csv"
    df = pd.read_csv(all_stations_file, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    df_test_raw = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    tasks = [(seed, df_test_raw) for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=min(7, len(SEEDS))) as executor:
        results = list(executor.map(evaluate_and_extract_fps_for_seed, tasks))

    all_fps = []
    all_tps = []
    all_fns = []
    for r in results:
        all_fps.extend(r["fps"])
        all_tps.extend(r["tps"])
        all_fns.extend(r["fns"])

    df_fp = pd.DataFrame(all_fps)
    df_tp = pd.DataFrame(all_tps)
    df_fn = pd.DataFrame(all_fns)

    df_fp.to_csv(OUTPUT_DIR / "step20_fp_population.csv", index=False)
    print(f"Extracted {len(df_fp)} total False Positives (Mean {len(df_fp)/7:.1f} per seed).")
    print(f"Extracted {len(df_tp)} total True Positives (Mean {len(df_tp)/7:.1f} per seed).")
    print(f"Saved complete FP population to {OUTPUT_DIR / 'step20_fp_population.csv'}")

    print("\n" + "=" * 80)
    print("STEP 20 FALSE POSITIVE MECHANISM TAXONOMY BREAKDOWN")
    print("=" * 80)
    mech_counts = df_fp["mechanism"].value_counts()
    mech_props = df_fp["mechanism"].value_counts(normalize=True) * 100.0
    mech_df = pd.DataFrame({"Count": mech_counts, "Proportion (%)": mech_props, "Mean_per_seed": mech_counts / 7.0})
    print(mech_df.to_string())

    # Tier Breakdown of FPs
    print("\n" + "=" * 80)
    print("FP BREAKDOWN BY DETECTOR TIER")
    print("=" * 80)
    tier_fp_df = pd.DataFrame({
        "Count": df_fp["tier"].value_counts(),
        "Proportion (%)": df_fp["tier"].value_counts(normalize=True) * 100.0,
        "Mean_per_seed": df_fp["tier"].value_counts() / 7.0
    })
    print(tier_fp_df.to_string())

    # ── TP SAFETY AUDIT ──
    print("\n" + "=" * 80)
    print("TP SAFETY AUDIT FOR PROPOSED REJECTION CONDITIONS")
    print("=" * 80)

    # Condition 1: Peer Agreement in Spike (Target moves with peer consensus)
    # Reject Spike if peer_agrees is True and thermo_coherent is True
    spike_fps_peer = df_fp[(df_fp["tier"] == 1) & (df_fp["peer_agrees"] == True) & (df_fp["thermo_coherent"] == True)]
    spike_tps_peer = df_tp[(df_tp["tier"] == 1) & (df_tp["peer_agrees"] == True) & (df_tp["thermo_coherent"] == True)]

    # Condition 2: Diurnal Solar Transition Coherence (Target spike occurs during diurnal heating/cooling and is thermo-coherent)
    spike_fps_diurnal = df_fp[(df_fp["tier"] == 1) & (df_fp["is_diurnal_transition"] == True) & (df_fp["thermo_coherent"] == True)]
    spike_tps_diurnal = df_tp[(df_tp["tier"] == 1) & (df_tp["is_diurnal_transition"] == True) & (df_tp["thermo_coherent"] == True)]

    # Condition 3: Cross-Channel Thermodynamic Coherence in Tier 3
    t3_fps_thermo = df_fp[(df_fp["tier"] == 3) & (df_fp["thermo_coherent"] == True)]
    t3_tps_thermo = df_tp[(df_tp["tier"] == 3) & (df_tp["thermo_coherent"] == True)]

    # Condition 4: CUSUM Peer Consistent Drift
    cusum_fps_peer = df_fp[(df_fp["tier"] == 2) & (df_fp["peer_agrees"] == True)]
    cusum_tps_peer = df_tp[(df_tp["tier"] == 2) & (df_tp["peer_agrees"] == True)]

    removability_records = [
        {
            "Mechanism": "PEER-CONSISTENT_MOVEMENT (Tier 1 Spike)",
            "FP_Removed_Total": len(spike_fps_peer),
            "FP_Removed_Per_Seed": len(spike_fps_peer) / 7.0,
            "FP_Proportion_Pct": len(spike_fps_peer) / len(df_fp) * 100.0,
            "TP_Destroyed_Total": len(spike_tps_peer),
            "TP_Destroyed_Per_Seed": len(spike_tps_peer) / 7.0,
            "TP_Overlap_Pct": len(spike_tps_peer) / len(df_tp) * 100.0,
            "Fault_Types_Affected": str(spike_tps_peer["gt_fault_type"].value_counts().to_dict()),
            "Safe_Candidate": len(spike_tps_peer) / max(1, len(df_tp)) < 0.005
        },
        {
            "Mechanism": "SOLAR_OR_DIURNAL_TRANSITION (Tier 1 Spike)",
            "FP_Removed_Total": len(spike_fps_diurnal),
            "FP_Removed_Per_Seed": len(spike_fps_diurnal) / 7.0,
            "FP_Proportion_Pct": len(spike_fps_diurnal) / len(df_fp) * 100.0,
            "TP_Destroyed_Total": len(spike_tps_diurnal),
            "TP_Destroyed_Per_Seed": len(spike_tps_diurnal) / 7.0,
            "TP_Overlap_Pct": len(spike_tps_diurnal) / len(df_tp) * 100.0,
            "Fault_Types_Affected": str(spike_tps_diurnal["gt_fault_type"].value_counts().to_dict()),
            "Safe_Candidate": False  # Injected spikes during solar transition would be suppressed!
        },
        {
            "Mechanism": "PEER-CONSISTENT_DRIFT (Tier 2 CUSUM)",
            "FP_Removed_Total": len(cusum_fps_peer),
            "FP_Removed_Per_Seed": len(cusum_fps_peer) / 7.0,
            "FP_Proportion_Pct": len(cusum_fps_peer) / len(df_fp) * 100.0,
            "TP_Destroyed_Total": len(cusum_tps_peer),
            "TP_Destroyed_Per_Seed": len(cusum_tps_peer) / 7.0,
            "TP_Overlap_Pct": len(cusum_tps_peer) / len(df_tp) * 100.0,
            "Fault_Types_Affected": str(cusum_tps_peer["gt_fault_type"].value_counts().to_dict()),
            "Safe_Candidate": len(cusum_tps_peer) == 0
        },
        {
            "Mechanism": "ENVIRONMENTAL_TRANSITION_COHERENCE (Tier 1)",
            "FP_Removed_Total": len(df_fp[df_fp["mechanism"] == "ENVIRONMENTAL_TRANSITION_WITH_CROSS_CHANNEL_COHERENCE"]),
            "FP_Removed_Per_Seed": len(df_fp[df_fp["mechanism"] == "ENVIRONMENTAL_TRANSITION_WITH_CROSS_CHANNEL_COHERENCE"]) / 7.0,
            "FP_Proportion_Pct": len(df_fp[df_fp["mechanism"] == "ENVIRONMENTAL_TRANSITION_WITH_CROSS_CHANNEL_COHERENCE"]) / len(df_fp) * 100.0,
            "TP_Destroyed_Total": len(df_tp[(df_tp["tier"] == 1) & (df_tp["thermo_coherent"] == True) & (df_tp["peer_agrees"] == False)]),
            "TP_Destroyed_Per_Seed": len(df_tp[(df_tp["tier"] == 1) & (df_tp["thermo_coherent"] == True) & (df_tp["peer_agrees"] == False)]) / 7.0,
            "TP_Overlap_Pct": len(df_tp[(df_tp["tier"] == 1) & (df_tp["thermo_coherent"] == True) & (df_tp["peer_agrees"] == False)]) / len(df_tp) * 100.0,
            "Fault_Types_Affected": "Many single-channel spikes happen to be thermo-coherent with background",
            "Safe_Candidate": False
        }
    ]

    rem_df = pd.DataFrame(removability_records)
    print(rem_df[["Mechanism", "FP_Removed_Per_Seed", "FP_Proportion_Pct", "TP_Destroyed_Per_Seed", "TP_Overlap_Pct", "Safe_Candidate"]].to_string())
    rem_df.to_csv(OUTPUT_DIR / "step20_fp_removability_matrix.csv", index=False)

    print(f"\nExecution completed in {time.time() - t0:.2f} seconds!")


if __name__ == "__main__":
    main()
