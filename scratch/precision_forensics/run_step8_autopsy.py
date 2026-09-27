"""
scratch/precision_forensics/run_step8_autopsy.py

Executes the exhaustive Step 8 Lost-True-Positive Forensic Autopsy across all 7 seeds.
Compares pristine Baseline detector against Step 7 detector, extracts every lost TP,
computes full distribution percentiles, fault-type and channel breakdowns,
suppression analysis, and offline evidence counterfactual ablations.
"""

import sys
import math
import json
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


def process_single_seed_autopsy(args):
    """
    Runs both baseline and step 7 detectors on identical injected streams for one seed,
    capturing fine-grained per-reading state, detections, and forensic diagnostics.
    """
    seed, test_raw_df = args
    injected_frames = []
    for station_id, group in test_raw_df.groupby("station_id", sort=False):
        injected_frames.append(injector.inject_anomalies(group.copy(), seed=seed))
    eval_df = pd.concat(injected_frames, ignore_index=True)
    eval_df["timestamp"] = pd.to_datetime(eval_df["timestamp"], utc=True)
    eval_df = eval_df.sort_values("timestamp").reset_index(drop=True)

    station_ids = eval_df["station_id"].unique()
    baseline_buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}
    step7_buffers = {st_id: StationBuffer(st_id) for st_id in station_ids}

    # Track episodes per station
    # episode grouping: consecutive is_anomaly==True points on same station
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

    records = []
    tp_base = fp_base = fn_base = 0
    tp_s7 = fp_s7 = fn_s7 = 0
    
    # Stream through timestamps
    rows = eval_df.to_dict("records")
    for row_idx, row in enumerate(rows):
        st_id = row["station_id"]
        ts = row["timestamp"]
        gt_is_anom = bool(row["is_anom_bool"])
        fault_type = row.get("fault_type", None)
        
        # Sibling peers
        sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
        
        # Baseline step
        b_buf = baseline_buffers[st_id]
        b_neighbor_bufs = {nid: baseline_buffers[nid] for nid in sibling_ids if nid in baseline_buffers}
        b_hist_df = b_buf.raw_history_df()
        
        raw_reading = {
            "station_id": st_id,
            "timestamp": ts,
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "humidity_pct": row["humidity_pct"],
        }
        
        b_verdict = baseline_detect.score_reading(raw_reading, b_hist_df, {}, b_neighbor_bufs)
        b_pred = bool(b_verdict["is_anomaly"])
        b_type = b_verdict.get("anomaly_type", "")
        
        # Step 7 step
        s7_buf = step7_buffers[st_id]
        s7_neighbor_bufs = {nid: step7_buffers[nid] for nid in sibling_ids if nid in step7_buffers}
        s7_hist_df = s7_buf.raw_history_df()
        
        s7_verdict = step7_detect.score_reading(raw_reading, s7_hist_df, {}, s7_neighbor_bufs)
        s7_pred = bool(s7_verdict["is_anomaly"])
        s7_type = s7_verdict.get("anomaly_type", "")
        
        # Update confusion matrices
        if b_pred and gt_is_anom:
            tp_base += 1
        elif b_pred and not gt_is_anom:
            fp_base += 1
        elif not b_pred and gt_is_anom:
            fn_base += 1
            
        if s7_pred and gt_is_anom:
            tp_s7 += 1
        elif s7_pred and not gt_is_anom:
            fp_s7 += 1
        elif not s7_pred and gt_is_anom:
            fn_s7 += 1

        # Extract detailed forensics for every ground truth anomaly
        if gt_is_anom:
            ep_info = station_episode_info.get(row_idx, {"episode_id": 0, "episode_pos": 0, "episode_len": 1})
            
            s7_diag = s7_verdict.get("tier_diagnostics", {})
            b_diag = b_verdict.get("tier_diagnostics", {})
            
            rec = {
                "seed": seed,
                "station_id": st_id,
                "timestamp": ts.isoformat(),
                "fault_type": fault_type if pd.notna(fault_type) else "unknown",
                "episode_id": ep_info["episode_id"],
                "episode_pos": ep_info["episode_pos"],
                "episode_len": ep_info["episode_len"],
                "is_onset": bool(ep_info["episode_pos"] == 0),
                "is_recovery": bool(ep_info["episode_pos"] == ep_info["episode_len"] - 1),
                "baseline_pred": b_pred,
                "baseline_type": b_type,
                "step7_pred": s7_pred,
                "step7_type": s7_type,
                "is_lost_tp": bool(b_pred and not s7_pred),
                "is_persistent_fn": bool(not b_pred and not s7_pred),
                "is_common_tp": bool(b_pred and s7_pred),
                "is_new_tp": bool(not b_pred and s7_pred),
            }
            
            for p in PARAMS:
                val = row[p]
                
                # Check baseline raw prior
                prior_b = None
                if not b_hist_df.empty and p in b_hist_df.columns:
                    v_list = pd.to_numeric(b_hist_df[p], errors="coerce").dropna().tolist()
                    if v_list:
                        prior_b = v_list[-1]
                        
                prior_s7 = None
                if not s7_hist_df.empty and p in s7_hist_df.columns:
                    v_list7 = pd.to_numeric(s7_hist_df[p], errors="coerce").dropna().tolist()
                    if v_list7:
                        prior_s7 = v_list7[-1]
                
                delta_b = (val - prior_b) if (prior_b is not None and pd.notna(prior_b) and pd.notna(val)) else 0.0
                delta_s7 = (val - prior_s7) if (prior_s7 is not None and pd.notna(prior_s7) and pd.notna(val)) else 0.0
                
                # Baseline sigma and z
                sensor_floor = baseline_detect.SENSOR_QUANTIZATION_FLOORS.get(p, 0.10)
                sigma_b = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * 1.0)
                z_b = abs(delta_b) / sigma_b
                
                # Step 7 diagnostics
                p_prefix = baseline_detect.PARAM_PREFIXES.get(p, p)
                spike_diag = s7_diag.get(f"{p_prefix}_spike_diagnostics", {})
                
                exp_delta = spike_diag.get("expected_delta", 0.0)
                residual = spike_diag.get("residual", delta_s7)
                sigma_s7 = spike_diag.get("sigma_jump", sigma_b)
                z_s7 = spike_diag.get("z_jump", 0.0)
                llr_s7 = spike_diag.get("jump_llr", 0.0)
                peer_disp = spike_diag.get("peer_dispersion", 0.0)
                
                mag_raw = abs(delta_s7)
                mag_res = abs(residual)
                if mag_raw > 1e-4:
                    suppression = 1.0 - (mag_res / mag_raw)
                else:
                    suppression = 0.0
                    
                sigma_inflation = (sigma_s7 / sigma_b) if sigma_b > 0 else 1.0
                
                rec[f"{p}_val"] = val
                rec[f"{p}_delta_raw"] = delta_s7
                rec[f"{p}_delta_expected"] = exp_delta
                rec[f"{p}_residual"] = residual
                rec[f"{p}_sigma_baseline"] = sigma_b
                rec[f"{p}_sigma_step7"] = sigma_s7
                rec[f"{p}_z_baseline"] = z_b
                rec[f"{p}_z_step7"] = z_s7
                rec[f"{p}_llr_step7"] = llr_s7
                rec[f"{p}_peer_dispersion"] = peer_disp
                rec[f"{p}_suppression_ratio"] = suppression
                rec[f"{p}_sigma_inflation_ratio"] = sigma_inflation
            
            records.append(rec)
            
        # Update buffers via official record_raw_reading
        b_buf.record_raw_reading(raw_reading, timestamp=ts, verdict=b_verdict)
        s7_buf.record_raw_reading(raw_reading, timestamp=ts, verdict=s7_verdict)
        
    prec_b = (tp_base / (tp_base + fp_base) * 100.0) if (tp_base + fp_base) > 0 else 0.0
    rec_b = (tp_base / (tp_base + fn_base) * 100.0) if (tp_base + fn_base) > 0 else 0.0
    f1_b = (2 * prec_b * rec_b / (prec_b + rec_b)) if (prec_b + rec_b) > 0 else 0.0

    prec_s7 = (tp_s7 / (tp_s7 + fp_s7) * 100.0) if (tp_s7 + fp_s7) > 0 else 0.0
    rec_s7 = (tp_s7 / (tp_s7 + fn_s7) * 100.0) if (tp_s7 + fn_s7) > 0 else 0.0
    f1_s7 = (2 * prec_s7 * rec_s7 / (prec_s7 + rec_s7)) if (prec_s7 + rec_s7) > 0 else 0.0

    summary = {
        "seed": seed,
        "base_tp": tp_base, "base_fp": fp_base, "base_fn": fn_base,
        "base_prec": prec_b, "base_rec": rec_b, "base_f1": f1_b,
        "s7_tp": tp_s7, "s7_fp": fp_s7, "s7_fn": fn_s7,
        "s7_prec": prec_s7, "s7_rec": rec_s7, "s7_f1": f1_s7,
        "lost_tps": tp_base - tp_s7
    }
    
    return summary, records


def run_full_autopsy():
    print("=" * 70)
    print("PATH 2 — PRECISION STEP 8: EXHAUSTIVE LOST-TP FORENSIC AUTOPSY")
    print("=" * 70)

    # Load test split raw frames identical to reproduce_baseline.py
    print("Loading test dataset frames (all_stations.csv with 0.7 split)...")
    df = pd.read_csv(DATA_DIR / "all_stations.csv", parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff_idx = int(len(df) * 0.7)
    test_raw_df = df[df["timestamp"] >= df.iloc[cutoff_idx]["timestamp"]].copy().reset_index(drop=True)

    print(f"Loaded {len(test_raw_df)} test rows across {df['station_id'].nunique()} stations.")

    # Execute in parallel
    print(f"Executing parallel autopsy across {len(SEEDS)} seeds...")
    t0 = time.time()
    
    tasks = [(s, test_raw_df) for s in SEEDS]
    with ProcessPoolExecutor(max_workers=7) as executor:
        results = list(executor.map(process_single_seed_autopsy, tasks))
        
    elapsed = time.time() - t0
    print(f"Autopsy completed in {elapsed:.1f}s.")

    summaries = [r[0] for r in results]
    all_anomaly_records = []
    for r in results:
        all_anomaly_records.extend(r[1])
        
    summary_df = pd.DataFrame(summaries)
    anom_df = pd.DataFrame(all_anomaly_records)
    
    print("\n--- SEED COMPARISON SUMMARY ---")
    for s in summaries:
        print(f"Seed {s['seed']:<20} | Base: TP={s['base_tp']}, Rec={s['base_rec']:.2f}%, F1={s['base_f1']:.2f}% | Step7: TP={s['s7_tp']}, Rec={s['s7_rec']:.2f}%, F1={s['s7_f1']:.2f}% | Lost TPs={s['lost_tps']}")
        
    macro_base_p = summary_df["base_prec"].mean()
    macro_base_r = summary_df["base_rec"].mean()
    macro_base_f1 = summary_df["base_f1"].mean()
    
    macro_s7_p = summary_df["s7_prec"].mean()
    macro_s7_r = summary_df["s7_rec"].mean()
    macro_s7_f1 = summary_df["s7_f1"].mean()
    
    print(f"\nBASE MACRO : Prec={macro_base_p:.2f}% | Rec={macro_base_r:.2f}% | F1={macro_base_f1:.2f}%")
    print(f"STEP7 MACRO: Prec={macro_s7_p:.2f}% | Rec={macro_s7_r:.2f}% | F1={macro_s7_f1:.2f}%")
    total_base_tps = anom_df['baseline_pred'].sum()
    total_lost_tps = anom_df['is_lost_tp'].sum()
    print(f"TOTAL LOST TPs ACROSS 7 SEEDS: {total_lost_tps} / {total_base_tps} ({total_lost_tps / total_base_tps * 100:.2f}%)")

    # 1. Save all anomalies dataset
    anom_df.to_csv(OUTPUT_DIR / "all_anomalies_comparison.csv", index=False)
    
    # 2. Extract lost TPs dataset
    lost_tp_df = anom_df[anom_df["is_lost_tp"]].copy()
    lost_tp_df.to_csv(OUTPUT_DIR / "lost_tp_dataset.csv", index=False)
    print(f"Saved {len(lost_tp_df)} lost TP records to lost_tp_dataset.csv")

    # 3. Breakdown by fault type
    ft_summary = anom_df.groupby("fault_type").agg(
        total_gt=("seed", "count"),
        baseline_tps=("baseline_pred", "sum"),
        step7_tps=("step7_pred", "sum"),
        lost_tps=("is_lost_tp", "sum")
    ).reset_index()
    ft_summary["baseline_recall"] = ft_summary["baseline_tps"] / ft_summary["total_gt"] * 100.0
    ft_summary["step7_recall"] = ft_summary["step7_tps"] / ft_summary["total_gt"] * 100.0
    ft_summary["lost_tp_share_pct"] = ft_summary["lost_tps"] / ft_summary["lost_tps"].sum() * 100.0
    ft_summary.to_csv(OUTPUT_DIR / "lost_tp_by_fault_type.csv", index=False)
    print("\n--- LOST TPs BY FAULT TYPE ---")
    print(ft_summary.to_string(index=False))

    # 4. Breakdown by episode position (onset vs mid vs recovery)
    pos_summary = anom_df.groupby("episode_pos").agg(
        total_gt=("seed", "count"),
        baseline_tps=("baseline_pred", "sum"),
        step7_tps=("step7_pred", "sum"),
        lost_tps=("is_lost_tp", "sum")
    ).reset_index()
    pos_summary["baseline_recall"] = pos_summary["baseline_tps"] / pos_summary["total_gt"] * 100.0
    pos_summary["step7_recall"] = pos_summary["step7_tps"] / pos_summary["total_gt"] * 100.0
    pos_summary["lost_tp_share_pct"] = pos_summary["lost_tps"] / pos_summary["lost_tps"].sum() * 100.0
    pos_summary.head(10).to_csv(OUTPUT_DIR / "lost_tp_by_episode_position.csv", index=False)
    print("\n--- LOST TPs BY EPISODE POSITION (First 5 Positions) ---")
    print(pos_summary.head(5).to_string(index=False))

    # Onset summary (pos == 0 vs pos > 0)
    onset_summary = anom_df.groupby("is_onset").agg(
        total_gt=("seed", "count"),
        baseline_tps=("baseline_pred", "sum"),
        step7_tps=("step7_pred", "sum"),
        lost_tps=("is_lost_tp", "sum")
    ).reset_index()
    onset_summary["baseline_recall"] = onset_summary["baseline_tps"] / onset_summary["total_gt"] * 100.0
    onset_summary["step7_recall"] = onset_summary["step7_tps"] / onset_summary["total_gt"] * 100.0
    onset_summary["lost_tp_pct_of_total_lost"] = onset_summary["lost_tps"] / onset_summary["lost_tps"].sum() * 100.0
    print("\n--- ONSET VS NON-ONSET BREAKDOWN ---")
    print(onset_summary.to_string(index=False))

    # Breakdown by channel
    channel_rows = []
    for p in PARAMS:
        # Check active ground truth impact on channel p (approximate via fault type or significant delta)
        p_lost = lost_tp_df[lost_tp_df[f"{p}_z_baseline"] >= 3.0]
        channel_rows.append({
            "param": p,
            "lost_tps_triggered_on_channel_in_baseline": len(p_lost),
            "mean_lost_baseline_z": float(p_lost[f"{p}_z_baseline"].mean()) if len(p_lost)>0 else 0.0,
            "mean_lost_step7_z": float(p_lost[f"{p}_z_step7"].mean()) if len(p_lost)>0 else 0.0,
            "mean_lost_baseline_sigma": float(p_lost[f"{p}_sigma_baseline"].mean()) if len(p_lost)>0 else 0.0,
            "mean_lost_step7_sigma": float(p_lost[f"{p}_sigma_step7"].mean()) if len(p_lost)>0 else 0.0,
        })
    ch_df = pd.DataFrame(channel_rows)
    ch_df.to_csv(OUTPUT_DIR / "lost_tp_by_channel.csv", index=False)
    print("\n--- LOST TPs BY CHANNEL ---")
    print(ch_df.to_string(index=False))

    # 5. Distribution percentiles for Common TPs, Lost TPs, and Persistent FNs
    metrics_to_quant = [
        "temperature_c_delta_raw", "temperature_c_residual", "temperature_c_z_baseline", "temperature_c_z_step7",
        "pressure_hpa_delta_raw", "pressure_hpa_residual", "pressure_hpa_z_baseline", "pressure_hpa_z_step7",
        "humidity_pct_delta_raw", "humidity_pct_residual", "humidity_pct_z_baseline", "humidity_pct_z_step7"
    ]
    
    subsets = {
        "Common_TPs": anom_df[anom_df["is_common_tp"]],
        "Lost_TPs": anom_df[anom_df["is_lost_tp"]],
        "Persistent_FNs": anom_df[anom_df["is_persistent_fn"]]
    }
    
    quant_rows = []
    quantiles = [0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    
    for subset_name, sub_df in subsets.items():
        for m in metrics_to_quant:
            vals = sub_df[m].abs().dropna()
            if len(vals) == 0:
                continue
            q_vals = vals.quantile(quantiles).to_dict()
            quant_rows.append({
                "subset": subset_name,
                "metric": m,
                "count": len(vals),
                "mean": float(vals.mean()),
                "p25": float(q_vals[0.25]),
                "median": float(q_vals[0.50]),
                "p75": float(q_vals[0.75]),
                "p90": float(q_vals[0.90]),
                "p95": float(q_vals[0.95]),
                "p99": float(q_vals[0.99]),
            })
            
    quant_df = pd.DataFrame(quant_rows)
    quant_df.to_csv(OUTPUT_DIR / "lost_tp_distribution_percentiles.csv", index=False)
    print("\nSaved distribution percentiles to lost_tp_distribution_percentiles.csv")

    # 6. Suppression vs Denominator Inflation Analysis
    supp_rows = []
    for p in PARAMS:
        p_lost = lost_tp_df[lost_tp_df[f"{p}_z_baseline"] >= 3.0]
        n_p_lost = len(p_lost)
        if n_p_lost == 0:
            continue
        
        # Reason 1: Denominator inflation alone (residual would have passed with sigma_baseline)
        z_with_base_sigma = p_lost[f"{p}_residual"].abs() / p_lost[f"{p}_sigma_baseline"]
        passed_with_base_sigma = (z_with_base_sigma >= 3.0)
        
        # Reason 2: Environmental subtraction erased signal (|residual| dropped below 3 * sigma_b)
        erased_by_subtraction = (z_with_base_sigma < 3.0) & (p_lost[f"{p}_z_baseline"] >= 3.0)
        
        # Reason 3: Denominator inflation prevented detection when residual was large enough
        blocked_by_sigma_inflation = passed_with_base_sigma & (p_lost[f"{p}_z_step7"] < 3.0)
        
        supp_rows.append({
            "param": p,
            "lost_tps_with_baseline_z_ge_3": n_p_lost,
            "blocked_by_sigma_inflation": int(blocked_by_sigma_inflation.sum()),
            "blocked_by_sigma_inflation_pct": float(blocked_by_sigma_inflation.mean() * 100.0),
            "erased_by_subtraction": int(erased_by_subtraction.sum()),
            "erased_by_subtraction_pct": float(erased_by_subtraction.mean() * 100.0),
            "mean_sigma_baseline": float(p_lost[f"{p}_sigma_baseline"].mean()),
            "mean_sigma_step7": float(p_lost[f"{p}_sigma_step7"].mean()),
            "mean_sigma_inflation_ratio": float(p_lost[f"{p}_sigma_inflation_ratio"].mean()),
            "mean_suppression_ratio": float(p_lost[f"{p}_suppression_ratio"].mean()),
        })
        
    supp_df = pd.DataFrame(supp_rows)
    supp_df.to_csv(OUTPUT_DIR / "suppression_analysis.csv", index=False)
    print("\n--- SUPPRESSION VS DENOMINATOR INFLATION BREAKDOWN ---")
    print(supp_df.to_string(index=False))

    # 7. Offline Evidence Counterfactual Ablations
    print("\n--- OFFLINE COUNTERFACTUAL ABLATIONS ---")
    ablation_results = []
    
    for s_id, s_group in anom_df.groupby("seed"):
        n_gt = len(s_group)
        
        # Rule A: Baseline (Raw Jump)
        tp_a = s_group["baseline_pred"].sum()
        # Rule B: Pure Step 7 (Contextual Innovation)
        tp_b = s_group["step7_pred"].sum()
        
        # Rule C: Contextual Innovation with Baseline Sigma
        rule_c_spike = (
            (s_group["temperature_c_residual"].abs() / s_group["temperature_c_sigma_baseline"] >= 3.0) |
            (s_group["pressure_hpa_residual"].abs() / s_group["pressure_hpa_sigma_baseline"] >= 3.0) |
            (s_group["humidity_pct_residual"].abs() / s_group["humidity_pct_sigma_baseline"] >= 3.0)
        )
        tp_c = (s_group["step7_pred"] | rule_c_spike).sum()
        
        # Rule D: Dual Evidence (Raw Jump OR Step 7)
        tp_d = (s_group["baseline_pred"] | s_group["step7_pred"]).sum()
        
        # Rule E: Contextual Innovation with Cold-Start Fallback (Onset points use baseline, mid use step 7)
        tp_e = (
            (s_group["is_onset"] & s_group["baseline_pred"]) |
            (~s_group["is_onset"] & s_group["step7_pred"])
        ).sum()
        
        ablation_results.append({
            "seed": s_id,
            "n_gt": n_gt,
            "rec_A_baseline": tp_a / n_gt * 100.0,
            "rec_B_step7": tp_b / n_gt * 100.0,
            "rec_C_uninflated_sigma": tp_c / n_gt * 100.0,
            "rec_D_dual_evidence": tp_d / n_gt * 100.0,
            "rec_E_coldstart_fallback": tp_e / n_gt * 100.0,
        })
        
    ab_df = pd.DataFrame(ablation_results)
    ab_df.to_csv(OUTPUT_DIR / "evidence_counterfactual_ablation.csv", index=False)
    print("\n--- COUNTERFACTUAL RECALL BY SEED ---")
    print(ab_df.to_string(index=False))
    
    mean_rec = ab_df.mean()
    print("\n--- COUNTERFACTUAL MACRO RECALL ---")
    print(f"Rule A (Baseline Raw Jump)               : {mean_rec['rec_A_baseline']:.2f}%")
    print(f"Rule B (Step 7 Pure Contextual)          : {mean_rec['rec_B_step7']:.2f}%")
    print(f"Rule C (Contextual + Uninflated Sigma)   : {mean_rec['rec_C_uninflated_sigma']:.2f}%")
    print(f"Rule D (Dual Evidence: Raw OR Contextual): {mean_rec['rec_D_dual_evidence']:.2f}%")
    print(f"Rule E (Contextual + Cold-Start Fallback): {mean_rec['rec_E_coldstart_fallback']:.2f}%")

    print("\nAll Step 8 forensic datasets generated successfully.")


if __name__ == "__main__":
    run_full_autopsy()
