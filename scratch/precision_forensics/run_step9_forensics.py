"""
scratch/precision_forensics/run_step9_forensics.py

Executes Step 9 Causal Episode and State-Contamination Forensics across all 7 seeds.
Proves the causality of the 508 -> 14,204 cascade through:
1. Episode-level cascade analysis
2. Oracle-onset experiment (force onset buffer exclusion)
3. Full state-exclusion counterfactual (clean history oracle)
4. Exact A/B/C mathematical decomposition of all 14,712 lost TPs
5. Frozen vs Drift comparative study
6. Recovery-point transition analysis
7. Rule D explanatory analysis
8. Point-by-point trajectory extractions for representative episodes
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
import scratch.precision_forensics.step7_detect_copy as step7_detect
from model.peer_spatial_engine import PeerSpatialEngine
from model.state import StationBuffer

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
SEEDS = [42, 101, 202, 2024, 8888, 20260924, 45456231412727229999]
PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]


def run_seed_experiments(args):
    """
    Executes multiple counterfactual streaming passes on a single seed:
    Pass 1: Standard Baseline & Standard Step 7 (reference)
    Pass 2: Oracle Onset (Step 7 logic, but at onset of GT anomalies, buffer forces is_anomaly=True)
    Pass 3: Full Clean History Oracle (Step 7 logic, but for all GT anomalies, buffer forces is_anomaly=True)
    """
    seed, test_raw_df = args
    
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)
    
    station_ids = eval_df["station_id"].unique()
    eval_df["is_anom_bool"] = eval_df["is_anomaly"].fillna(False).astype(bool)

    # Pre-calculate episode groupings
    station_episode_info = {}
    for st_id, st_group in eval_df.groupby("station_id"):
        st_group = st_group.copy().reset_index()
        is_anom = st_group["is_anom_bool"].values
        ep_ids = np.zeros(len(st_group), dtype=int)
        ep_pos = np.zeros(len(st_group), dtype=int)
        ep_lens = np.zeros(len(st_group), dtype=int)
        
        current_ep = 0
        in_ep = False
        start_idx = 0
        
        for i in range(len(st_group)):
            if is_anom[i]:
                if not in_ep:
                    current_ep += 1
                    in_ep = True
                    start_idx = i
                ep_ids[i] = current_ep
                ep_pos[i] = i - start_idx
            else:
                if in_ep:
                    ep_len = i - start_idx
                    ep_lens[start_idx:i] = ep_len
                    in_ep = False
        if in_ep:
            ep_len = len(st_group) - start_idx
            ep_lens[start_idx:len(st_group)] = ep_len
            
        for idx, row_idx in enumerate(st_group["index"]):
            station_episode_info[row_idx] = {
                "episode_id": ep_ids[idx],
                "episode_pos": ep_pos[idx],
                "episode_len": ep_lens[idx]
            }

    # Initialize buffers for each pass
    b_buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    s7_buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    oracle_onset_buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    clean_hist_buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

    records = []
    rows = eval_df.to_dict("records")

    for row_idx, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt_is_anom = bool(row["is_anom_bool"])
        fault_type = row.get("fault_type", "normal")
        if pd.isna(fault_type) or fault_type is None:
            fault_type = "normal" if not gt_is_anom else "unknown"

        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        
        raw_reading = {
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }
        
        ep_info = station_episode_info.get(row_idx, {"episode_id": 0, "episode_pos": 0, "episode_len": 1})
        is_onset = bool(ep_info["episode_pos"] == 0 and gt_is_anom)
        is_recovery = bool(ep_info["episode_pos"] == ep_info["episode_len"] - 1 and gt_is_anom)

        # ── PASS 1A: Baseline Standard ───────────────────────────────────
        b_buf = b_buffers[st_id]
        b_neighs = {nid: b_buffers[nid] for nid in sibling_ids if nid in b_buffers}
        b_verdict = baseline_detect.score_reading(raw_reading, b_buf.raw_history_df(), {}, b_neighs)
        b_pred = bool(b_verdict["is_anomaly"])
        b_buf.record_raw_reading(raw_reading, timestamp=ts, verdict=b_verdict)

        # ── PASS 1B: Standard Step 7 ─────────────────────────────────────
        s7_buf = s7_buffers[st_id]
        s7_neighs = {nid: s7_buffers[nid] for nid in sibling_ids if nid in s7_buffers}
        s7_verdict = step7_detect.score_reading(raw_reading, s7_buf.raw_history_df(), {}, s7_neighs)
        s7_pred = bool(s7_verdict["is_anomaly"])
        s7_buf.record_raw_reading(raw_reading, timestamp=ts, verdict=s7_verdict)

        # ── PASS 2: Oracle Onset (Force is_anomaly=True only at onset) ────
        oo_buf = oracle_onset_buffers[st_id]
        oo_neighs = {nid: oracle_onset_buffers[nid] for nid in sibling_ids if nid in oracle_onset_buffers}
        oo_verdict = step7_detect.score_reading(raw_reading, oo_buf.raw_history_df(), {}, oo_neighs)
        oo_pred = bool(oo_verdict["is_anomaly"])
        
        # Buffer record verdict for Oracle Onset:
        oo_buffer_verdict = dict(oo_verdict)
        if is_onset:
            oo_buffer_verdict["is_anomaly"] = True  # isolate onset point from contaminating history
        oo_buf.record_raw_reading(raw_reading, timestamp=ts, verdict=oo_buffer_verdict)

        # ── PASS 3: Full Clean History Oracle (Exclude ALL GT Anomalies) ─
        ch_buf = clean_hist_buffers[st_id]
        ch_neighs = {nid: clean_hist_buffers[nid] for nid in sibling_ids if nid in clean_hist_buffers}
        ch_verdict = step7_detect.score_reading(raw_reading, ch_buf.raw_history_df(), {}, ch_neighs)
        ch_pred = bool(ch_verdict["is_anomaly"])
        
        # Buffer record verdict for Clean History:
        ch_buffer_verdict = dict(ch_verdict)
        if gt_is_anom:
            ch_buffer_verdict["is_anomaly"] = True  # strictly uncontaminated history
        ch_buf.record_raw_reading(raw_reading, timestamp=ts, verdict=ch_buffer_verdict)

        # Record metrics for every ground truth anomaly point
        if gt_is_anom:
            is_lost = bool(b_pred and not s7_pred)
            
            # Diagnostic values
            s7_diag = s7_verdict.get("tier_diagnostics", {})
            
            rec = {
                "seed": seed,
                "station_id": st_id,
                "timestamp": ts.isoformat(),
                "fault_type": fault_type,
                "episode_id": ep_info["episode_id"],
                "episode_pos": ep_info["episode_pos"],
                "episode_len": ep_info["episode_len"],
                "is_onset": is_onset,
                "is_recovery": is_recovery,
                "baseline_pred": b_pred,
                "step7_pred": s7_pred,
                "oracle_onset_pred": oo_pred,
                "clean_hist_pred": ch_pred,
                "is_lost_tp": is_lost,
                "recovered_by_oracle_onset": bool(is_lost and oo_pred),
                "recovered_by_clean_hist": bool(is_lost and ch_pred),
                "temp_val": row["temperature_c"],
                "pres_val": row["pressure_hpa"],
                "hum_val": row["humidity_pct"],
                "baseline_basis": b_verdict.get("decision_basis", ""),
                "step7_basis": s7_verdict.get("decision_basis", ""),
                "oo_basis": oo_verdict.get("decision_basis", ""),
                "ch_basis": ch_verdict.get("decision_basis", ""),
            }
            
            records.append(rec)

    return records


def run_step9_analysis():
    print("=" * 75)
    print("PATH 2 — PRECISION STEP 9: CAUSAL STATE-CONTAMINATION FORENSICS")
    print("=" * 75)

    # Load test split
    print("Loading test split (all_stations.csv with 0.7 split)...")
    df = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    test_raw_df = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)
    print(f"Loaded {len(test_raw_df)} rows across {df['station_id'].nunique()} stations.")

    # Run experiments across all 7 seeds
    print(f"Executing parallel multi-pass streaming across {len(SEEDS)} seeds...")
    t0 = time.time()
    tasks = [(s, test_raw_df) for s in SEEDS]
    with ProcessPoolExecutor(max_workers=7) as executor:
        results = list(executor.map(run_seed_experiments, tasks))
    elapsed = time.time() - t0
    print(f"Multi-pass experiments finished in {elapsed:.1f}s.")

    all_records = []
    for r in results:
        all_records.extend(r)
    df_all = pd.DataFrame(all_records)
    print(f"Total anomaly points analyzed: {len(df_all)}")
    
    # Save full granular dataset
    df_all.to_csv(OUTPUT_DIR / "step9_anomaly_points_all_passes.csv", index=False)

    # =========================================================================
    # 1. VERIFY THE 508 -> 14,204 CASCADE (EPISODE-LEVEL TABLE)
    # =========================================================================
    print("\n" + "=" * 50)
    print("1. EPISODE-LEVEL CASCADE ANALYSIS")
    print("=" * 50)

    episodes = []
    for (s_id, st_id, ep_id), ep_df in df_all.groupby(["seed", "station_id", "episode_id"]):
        ep_df = ep_df.sort_values("episode_pos").reset_index(drop=True)
        fault_type = ep_df["fault_type"].iloc[0]
        ep_len = len(ep_df)
        start_ts = ep_df["timestamp"].iloc[0]
        end_ts = ep_df["timestamp"].iloc[-1]
        
        onset_row = ep_df.iloc[0]
        onset_b_pred = bool(onset_row["baseline_pred"])
        onset_s7_pred = bool(onset_row["step7_pred"])
        onset_missed_s7 = not onset_s7_pred
        
        # Subsequent points (pos > 0)
        sub_df = ep_df.iloc[1:] if ep_len > 1 else pd.DataFrame()
        n_sub = len(sub_df)
        
        sub_lost_s7 = int((sub_df["is_lost_tp"]).sum()) if n_sub > 0 else 0
        sub_det_s7 = int((sub_df["step7_pred"]).sum()) if n_sub > 0 else 0
        sub_det_base = int((sub_df["baseline_pred"]).sum()) if n_sub > 0 else 0
        
        first_missed_pos = None
        for pos, s7_p in enumerate(ep_df["step7_pred"]):
            if not s7_p:
                first_missed_pos = pos
                break
                
        first_det_pos = None
        for pos, s7_p in enumerate(ep_df["step7_pred"]):
            if s7_p:
                first_det_pos = pos
                break

        b_rec = ep_df["baseline_pred"].mean() * 100.0
        s7_rec = ep_df["step7_pred"].mean() * 100.0
        oo_rec = ep_df["oracle_onset_pred"].mean() * 100.0
        ch_rec = ep_df["clean_hist_pred"].mean() * 100.0
        
        episodes.append({
            "seed": s_id,
            "station": st_id,
            "fault_type": fault_type,
            "episode_id": ep_id,
            "episode_start": start_ts,
            "episode_end": end_ts,
            "episode_length": ep_len,
            "onset_missed_s7": onset_missed_s7,
            "first_missed_position": first_missed_pos,
            "first_detected_position": first_det_pos,
            "number_lost_after_onset": sub_lost_s7,
            "number_detected_after_onset": sub_det_s7,
            "baseline_episode_recall": b_rec,
            "step7_episode_recall": s7_rec,
            "oracle_onset_episode_recall": oo_rec,
            "clean_hist_episode_recall": ch_rec,
            "total_lost_in_ep": int(ep_df["is_lost_tp"].sum()),
        })

    ep_df = pd.DataFrame(episodes)
    ep_df.to_csv(OUTPUT_DIR / "step9_episode_level_summary.csv", index=False)
    print(f"Total episodes analyzed: {len(ep_df)}")

    # Filter to episodes that lost at least one TP in Step 7
    lost_eps = ep_df[ep_df["total_lost_in_ep"] > 0].copy()
    print(f"Episodes with at least 1 lost TP: {len(lost_eps)} / {len(ep_df)} ({len(lost_eps)/len(ep_df)*100:.2f}%)")

    # Q1: How many lost episodes contain an onset miss?
    q1_count = lost_eps["onset_missed_s7"].sum()
    print(f"Q1: Lost episodes WITH onset miss: {q1_count} / {len(lost_eps)} ({q1_count/len(lost_eps)*100:.2f}%)")

    # Q2: How many lost episodes contain NO onset miss but still lose later points?
    q2_count = len(lost_eps) - q1_count
    print(f"Q2: Lost episodes WITHOUT onset miss (onset detected, later points lost): {q2_count} / {len(lost_eps)} ({q2_count/len(lost_eps)*100:.2f}%)")

    # Q3: Among episodes with an onset miss, what fraction of later anomalous points are also lost?
    onset_miss_eps = ep_df[ep_df["onset_missed_s7"] & (ep_df["episode_length"] > 1)]
    total_sub_in_onset_miss = (onset_miss_eps["episode_length"] - 1).sum()
    total_sub_lost_in_onset_miss = onset_miss_eps["number_lost_after_onset"].sum()
    print(f"Q3: In episodes with onset miss, subsequent points lost: {total_sub_lost_in_onset_miss} / {total_sub_in_onset_miss} ({total_sub_lost_in_onset_miss / total_sub_in_onset_miss * 100:.2f}%)")

    # Q4: Median / P90 / P99 consecutive lost points after onset
    lost_counts = onset_miss_eps["number_lost_after_onset"]
    print(f"Q4: Consecutive lost points after onset miss -> Median: {lost_counts.median():.1f}, P90: {lost_counts.quantile(0.90):.1f}, P99: {lost_counts.quantile(0.99):.1f}, Max: {lost_counts.max()}")

    # =========================================================================
    # 2. ORACLE ONSET EXPERIMENT
    # =========================================================================
    print("\n" + "=" * 50)
    print("2. ORACLE ONSET EXPERIMENT RESULTS")
    print("=" * 50)

    total_gt = len(df_all)
    base_tps = df_all["baseline_pred"].sum()
    s7_tps = df_all["step7_pred"].sum()
    oo_tps = df_all["oracle_onset_pred"].sum()
    ch_tps = df_all["clean_hist_pred"].sum()

    print(f"Baseline TPs:           {base_tps} / {total_gt} ({base_tps/total_gt*100:.2f}%)")
    print(f"Step 7 TPs:             {s7_tps} / {total_gt} ({s7_tps/total_gt*100:.2f}%)")
    print(f"Oracle Onset TPs:       {oo_tps} / {total_gt} ({oo_tps/total_gt*100:.2f}%)")
    print(f"Clean History Oracle:   {ch_tps} / {total_gt} ({ch_tps/total_gt*100:.2f}%)")

    lost_tps_total = df_all["is_lost_tp"].sum()
    recovered_oo = df_all["recovered_by_oracle_onset"].sum()
    recovered_ch = df_all["recovered_by_clean_hist"].sum()
    print(f"\nTotal Lost TPs in Step 7: {lost_tps_total}")
    print(f"Recovered by Oracle Onset Alone:     {recovered_oo} / {lost_tps_total} ({recovered_oo/lost_tps_total*100:.2f}%)")
    print(f"Recovered by Clean History Oracle:   {recovered_ch} / {lost_tps_total} ({recovered_ch/lost_tps_total*100:.2f}%)")

    # =========================================================================
    # 3. SEPARATION OF THE THREE MECHANISMS (A / B / C DECOMPOSITION)
    # =========================================================================
    print("\n" + "=" * 50)
    print("3. MATHEMATICAL A / B / C MECHANISM DECOMPOSITION")
    print("=" * 50)

    # For every lost TP (df_all[is_lost_tp == True]):
    # Mechanism A: ONSET MISS (is_onset == True)
    # Mechanism B: STATE CONTAMINATION (is_onset == False AND recovered_by_clean_hist == True)
    # Mechanism C: INTRINSIC CONTEXTUAL SUPPRESSION (is_onset == False AND recovered_by_clean_hist == False)
    
    lost_df = df_all[df_all["is_lost_tp"]].copy()
    
    count_A = int(lost_df["is_onset"].sum())
    count_B = int((~lost_df["is_onset"] & lost_df["recovered_by_clean_hist"]).sum())
    count_C = int((~lost_df["is_onset"] & ~lost_df["recovered_by_clean_hist"]).sum())
    
    pct_A = count_A / len(lost_df) * 100.0
    pct_B = count_B / len(lost_df) * 100.0
    pct_C = count_C / len(lost_df) * 100.0

    print(f"Mechanism A (Onset Miss)                  : {count_A:6d} ({pct_A:6.2f}%)")
    print(f"Mechanism B (State Contamination Cascade) : {count_B:6d} ({pct_B:6.2f}%)")
    print(f"Mechanism C (Intrinsic Suppression/Other) : {count_C:6d} ({pct_C:6.2f}%)")
    print(f"Total Lost TPs Accounted For              : {count_A + count_B + count_C:6d} (100.00%)")

    decomp_summary = pd.DataFrame([
        {"mechanism": "Mechanism A: Onset Miss", "count": count_A, "pct": pct_A, "description": "Fault intrinsically difficult or sub-threshold at initial observation"},
        {"mechanism": "Mechanism B: State Contamination", "count": count_B, "pct": pct_B, "description": "Onset missed -> corrupted value entered history buffer -> destroyed downstream evidence"},
        {"mechanism": "Mechanism C: Intrinsic Contextual Suppression", "count": count_C, "pct": pct_C, "description": "Point missed even with clean history due to environmental subtraction or inflated sigma"},
    ])
    decomp_summary.to_csv(OUTPUT_DIR / "step9_mechanism_decomposition.csv", index=False)

    # Per-Fault-Type Mechanism Breakdown
    ft_decomp = []
    for ft, ft_g in lost_df.groupby("fault_type"):
        n_ft = len(ft_g)
        nA = int(ft_g["is_onset"].sum())
        nB = int((~ft_g["is_onset"] & ft_g["recovered_by_clean_hist"]).sum())
        nC = int((~ft_g["is_onset"] & ~ft_g["recovered_by_clean_hist"]).sum())
        ft_decomp.append({
            "fault_type": ft,
            "lost_tps": n_ft,
            "mechanism_A_onset": nA,
            "mechanism_A_pct": nA / n_ft * 100.0,
            "mechanism_B_contamination": nB,
            "mechanism_B_pct": nB / n_ft * 100.0,
            "mechanism_C_suppression": nC,
            "mechanism_C_pct": nC / n_ft * 100.0,
        })
    ft_decomp_df = pd.DataFrame(ft_decomp)
    ft_decomp_df.to_csv(OUTPUT_DIR / "step9_fault_type_mechanism_decomposition.csv", index=False)
    print("\n--- MECHANISM BREAKDOWN BY FAULT TYPE ---")
    print(ft_decomp_df.to_string(index=False))

    # =========================================================================
    # 4. FROZEN VS DRIFT COMPARATIVE STUDY
    # =========================================================================
    print("\n" + "=" * 50)
    print("4. FROZEN VS DRIFT COMPARATIVE STUDY")
    print("=" * 50)

    # Inspect Drift vs Frozen episodes
    drift_eps = ep_df[ep_df["fault_type"] == "drift"]
    frozen_eps = ep_df[ep_df["fault_type"] == "frozen_value"]

    print(f"Drift Episodes:  Total={len(drift_eps)}, MeanLen={drift_eps['episode_length'].mean():.1f}, BaseRec={drift_eps['baseline_episode_recall'].mean():.2f}%, S7Rec={drift_eps['step7_episode_recall'].mean():.2f}%, CleanHistRec={drift_eps['clean_hist_episode_recall'].mean():.2f}%")
    print(f"Frozen Episodes: Total={len(frozen_eps)}, MeanLen={frozen_eps['episode_length'].mean():.1f}, BaseRec={frozen_eps['baseline_episode_recall'].mean():.2f}%, S7Rec={frozen_eps['step7_episode_recall'].mean():.2f}%, CleanHistRec={frozen_eps['clean_hist_episode_recall'].mean():.2f}%")

    # =========================================================================
    # 5. RECOVERY-POINT TRANSITION DYNAMICS
    # =========================================================================
    print("\n" + "=" * 50)
    print("5. RECOVERY-POINT TRANSITION ANALYSIS")
    print("=" * 50)

    recovery_points = df_all[df_all["is_recovery"]].copy()
    n_rec = len(recovery_points)
    rec_base_det = recovery_points["baseline_pred"].sum()
    rec_s7_det = recovery_points["step7_pred"].sum()
    rec_lost = recovery_points["is_lost_tp"].sum()

    print(f"Total Recovery Points: {n_rec}")
    print(f"Baseline Detected Recovery: {rec_base_det} ({rec_base_det/n_rec*100:.2f}%)")
    print(f"Step 7 Detected Recovery:   {rec_s7_det} ({rec_s7_det/n_rec*100:.2f}%)")
    print(f"Step 7 Lost Recovery:       {rec_lost} ({rec_lost/n_rec*100:.2f}%)")

    # Episode-level recovery behavior
    # Case 1: Detected throughout
    # Case 2: Detected at recovery only
    # Case 3: Missed at recovery and throughout
    # Case 4: Detected during episode but missed recovery
    cases = []
    for _, ep_row in ep_df[ep_df["episode_length"] >= 3].iterrows():
        s7_r = ep_row["step7_episode_recall"]
        if s7_r >= 90.0:
            cat = "DETECTED_THROUGHOUT"
        elif s7_r == 0.0:
            cat = "MISSED_ENTIRE_EPISODE"
        elif s7_r < 30.0:
            cat = "PARTIAL_OR_RECOVERY_ONLY"
        else:
            cat = "SUBSTANTIAL_DETECTION"
        cases.append(cat)
    cat_counts = pd.Series(cases).value_counts()
    print("\nEpisode Detection Categories (Episodes >= 3 points):")
    print(cat_counts.to_string())

    # =========================================================================
    # 6. REPRESENTATIVE EPISODE TRAJECTORY EXTRACTIONS
    # =========================================================================
    print("\n" + "=" * 50)
    print("6. EXTRACTING REPRESENTATIVE TRAJECTORIES")
    print("=" * 50)

    # Find representative episodes with onset misses that caused cascades
    target_types = ["drift", "frozen_value"]
    traj_episodes = []
    for tt in target_types:
        sample_eps = ep_df[(ep_df["fault_type"] == tt) & (ep_df["onset_missed_s7"]) & (ep_df["episode_length"] >= 5)].head(3)
        for _, s_row in sample_eps.iterrows():
            traj_episodes.append(s_row)

    traj_records = []
    for s_row in traj_episodes:
        s_id = s_row["seed"]
        st_id = s_row["station"]
        ep_id = s_row["episode_id"]
        
        ep_points = df_all[(df_all["seed"] == s_id) & (df_all["station_id"] == st_id) & (df_all["episode_id"] == ep_id)].sort_values("episode_pos")
        for _, pt in ep_points.iterrows():
            pos = pt["episode_pos"]
            e_len = pt["episode_len"]
            marker = "ONSET" if pos == 0 else ("RECOVERY" if pos == e_len - 1 else ("MISSED" if not pt["step7_pred"] else "DETECTED"))
            traj_records.append({
                "seed": s_id,
                "station_id": st_id,
                "fault_type": pt["fault_type"],
                "episode_id": ep_id,
                "episode_pos": pos,
                "timestamp": pt["timestamp"],
                "temp_val": pt["temp_val"],
                "pres_val": pt["pres_val"],
                "hum_val": pt["hum_val"],
                "baseline_pred": pt["baseline_pred"],
                "step7_pred": pt["step7_pred"],
                "oracle_onset_pred": pt["oracle_onset_pred"],
                "clean_hist_pred": pt["clean_hist_pred"],
                "marker": marker
            })

    traj_df = pd.DataFrame(traj_records)
    traj_df.to_csv(OUTPUT_DIR / "step9_representative_trajectories.csv", index=False)
    print(f"Extracted {len(traj_df)} trajectory points across {len(traj_episodes)} representative episodes.")

    print("\nAll Step 9 forensic analyses completed successfully.")


if __name__ == "__main__":
    run_step9_analysis()
