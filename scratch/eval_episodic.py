"""
SkyGuard Edge AI -- Episodic & Row-Level Benchmark Evaluation
===============================================================
Computes both Row-Level Micro Metrics AND Episodic Episode Matching Metrics
(per benchmark_contract.py) across all 5 passes.
"""

import glob, math
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from evaluation.benchmark_contract import episodic_metrics, pooled_row_metrics

FILES = sorted(glob.glob("data/*_labeled.csv"))
CENTER_STATIONS = [
    "AWS-BHO-030", "AWS-CHN-024", "AWS-DEL-011", "AWS-KOL-015",
    "AWS-MUM-007", "AWS-RAN-067", "AWS-VAR-052"
]

def _feat_batch(t, p, h):
    N = len(t)
    F = np.full((N, 9), np.nan, dtype=np.float32)
    roc1_t  = np.diff(t, prepend=np.nan)
    roc3_t  = t - np.concatenate([[np.nan]*3, t[:-3]])
    roc1_h  = np.diff(h, prepend=np.nan)
    roc1_p  = np.diff(p, prepend=np.nan)
    rng6_t  = np.full(N, np.nan, dtype=np.float32)
    rng6_p  = np.full(N, np.nan, dtype=np.float32)
    rng6_h  = np.full(N, np.nan, dtype=np.float32)
    for i in range(5, N):
        rng6_t[i] = t[i-5:i+1].max() - t[i-5:i+1].min()
        rng6_p[i] = p[i-5:i+1].max() - p[i-5:i+1].min()
        rng6_h[i] = h[i-5:i+1].max() - h[i-5:i+1].min()
    vpd     = 0.6112 * np.exp(17.67*t / (t+243.5)) * (1.0 - h/100.0)
    t_h_cov = roc1_t * roc1_h
    F[:,0]=roc1_t; F[:,1]=roc3_t; F[:,2]=roc1_h; F[:,3]=roc1_p
    F[:,4]=rng6_t; F[:,5]=rng6_p; F[:,6]=rng6_h; F[:,7]=vpd; F[:,8]=t_h_cov
    return F

def train_iforest():
    clean = [f for f in FILES if any(x in f for x in ["-101_","-102_","-103_"])]
    clean_rows = []
    for f in clean:
        df = pd.read_csv(f)
        t = df["temperature_c"].to_numpy(float)
        p = df["pressure_hpa"].to_numpy(float)
        h = df["humidity_pct"].to_numpy(float)
        F = _feat_batch(t, p, h)
        mask = ~np.isnan(F).any(axis=1)
        clean_rows.append(F[mask])
    X = np.vstack(clean_rows).astype(np.float32)
    clf = IsolationForest(n_estimators=60, max_samples=256, contamination=0.01, random_state=42, n_jobs=-1)
    clf.fit(X)
    return clf

def load_data(clf):
    data = []
    for f in FILES:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t = df["temperature_c"].to_numpy(float)
        p = df["pressure_hpa"].to_numpy(float)
        h = df["humidity_pct"].to_numpy(float)
        gt = df["is_anomaly"].fillna(False).to_numpy(bool)
        gft = df["fault_type"].fillna("normal").to_numpy(str)
        st_id = df["station_id"].iloc[0] if "station_id" in df.columns else f
        timestamps = df["timestamp"].tolist() if "timestamp" in df.columns else range(len(df))
        
        F = _feat_batch(t, p, h)
        mask = ~np.isnan(F).any(axis=1)
        scores = np.full(len(t), np.nan, dtype=np.float32)
        if mask.any():
            scores[mask] = -clf.score_samples(F[mask])
            
        data.append({"id": st_id, "file": f, "t": t, "p": p, "h": h, "gt": gt, "gft": gft, "scores": scores, "timestamps": timestamps})
    return data

def run_pass_eval(data_list, cfg):
    alpha = cfg.get("alpha", 0.02)
    alpha_slow = cfg.get("alpha_slow", 0.005)
    k_w7d = cfg.get("k_w7d", 4.5)
    w7thr = cfg.get("w7thr", 18.0)
    w7dec = cfg.get("w7dec", 0.80)
    kspk = cfg.get("kspk", 5.0)
    k_freeze = cfg.get("k_freeze", 0.28)
    k_rail = cfg.get("k_rail", 4.0)
    iforest_thresh = cfg.get("iforest_thresh", 0.62)

    predicted_events = []
    truth_events = []

    TP = FP = FN = TN = 0
    fault_counts = {}

    for item in data_list:
        st_id = item["id"]
        t, p, h, gt, gft, if_scores, ts = item["t"], item["p"], item["h"], item["gt"], item["gft"], item["scores"], item["timestamps"]
        N = len(t)
        buf_t = np.full(512, np.nan, dtype=np.float32)
        buf_p = np.full(512, np.nan, dtype=np.float32)
        buf_h = np.full(512, np.nan, dtype=np.float32)
        head = count = 0
        last_t = last_p = last_h = None
        
        roc_t_m = roc_p_m = roc_h_m = 0.0
        roc_t_v = roc_p_v = roc_h_v = 1.0
        roc_n = 0
        
        frz_t_m = frz_p_m = frz_h_m = 0.0
        frz_t_v = frz_p_v = frz_h_v = 1.0
        frz_n = 0
        
        w7d_t_m = w7d_p_m = w7d_h_m = 0.0
        w7d_t_v = w7d_p_v = w7d_h_v = 1.0
        w7d_n = 0
        
        slp_t_m = 0.0; slp_t_v = 1.0; slp_n = 0
        obs_t_m = obs_p_m = obs_h_m = 0.0
        obs_t_v = obs_p_v = obs_h_v = 1.0
        obs_n = 0
        obs_min_t = obs_min_p = obs_min_h = 1e9

        w7_pt = w7_nt = w7_pp = w7_np = w7_ph = w7_nh = 0.0
        s_up = s_dn = 0

        # Track truth episodes
        in_truth = False; t_start = 0; t_ft = ""
        for i in range(N):
            if gt[i] and not in_truth:
                in_truth = True; t_start = i; t_ft = gft[i]
            elif not gt[i] and in_truth:
                in_truth = False
                truth_events.append({
                    "station_id": st_id, "fault_type": t_ft, "affected_parameters": ["temperature_c"],
                    "start_timestamp": str(ts[t_start]), "end_timestamp": str(ts[i-1]),
                    "start_index": t_start, "end_index": i-1
                })
        if in_truth:
            truth_events.append({
                "station_id": st_id, "fault_type": t_ft, "affected_parameters": ["temperature_c"],
                "start_timestamp": str(ts[t_start]), "end_timestamp": str(ts[N-1]),
                "start_index": t_start, "end_index": N-1
            })

        # Track predicted episodes
        in_pred = False; p_start = 0; p_ft = ""
        
        for i in range(N):
            ti = t[i]; pi = p[i]; hi = h[i]
            is_gt = gt[i]; g = gft[i]

            if math.isnan(ti) or math.isnan(pi) or math.isnan(hi):
                flag, ft = True, "dropout"
            elif ti < -50.0 or ti > 60.0 or pi < 800.0 or pi > 1100.0 or hi < 0.0 or hi > 100.0:
                flag, ft = True, "physical_bounds"
            elif obs_n >= 24 and (ti < obs_min_t - k_rail * math.sqrt(max(obs_t_v, 1e-9)) or
                                  pi < obs_min_p - k_rail * math.sqrt(max(obs_p_v, 1e-9)) or
                                  hi < obs_min_h - k_rail * math.sqrt(max(obs_h_v, 1e-9))):
                flag, ft = True, "sensor_fail_low"
            else:
                es = 0.6112 * math.exp(17.67 * ti / (ti + 243.5))
                vpd = es * (1.0 - hi / 100.0)
                tdp = ti - (100.0 - hi) / 5.0
                if tdp > ti + 0.5 or (ti > 44.0 and hi > 65.0) or (ti > 40.0 and vpd < 0.10 and hi > 85.0):
                    flag, ft = True, "multivariate_inconsistency"
                else:
                    is_anom = False; ft = "normal"
                    if last_t is not None and not math.isnan(last_t) and roc_n >= 12:
                        dt = ti - last_t; dp = pi - last_p; dh = hi - last_h
                        std_t = math.sqrt(max(roc_t_v, 1e-9))
                        std_p = math.sqrt(max(roc_p_v, 1e-9))
                        std_h = math.sqrt(max(roc_h_v, 1e-9))
                        thr_t = kspk * std_t; thr_p = kspk * std_p; thr_h = kspk * std_h
                        if dt > 2.0 * std_t and dh > 2.0 * std_h:
                            is_anom, ft = True, "multivariate_inconsistency"
                        else:
                            diurnal = ((dt > 0) != (dh > 0)) and abs(dt) < thr_t and abs(dh) < thr_h
                            if not diurnal and (abs(dt) > thr_t or abs(dp) > thr_p or abs(dh) > thr_h):
                                is_anom, ft = True, "spike"

                    if not is_anom and count >= 6 and frz_n >= 24:
                        idxs = [(head - 1 - j) % 512 for j in range(6)]
                        wt = buf_t[idxs]; wp = buf_p[idxs]; wh = buf_h[idxs]
                        wt[0] = ti; wp[0] = pi; wh[0] = hi
                        rng_t = np.nanmax(wt) - np.nanmin(wt)
                        rng_p = np.nanmax(wp) - np.nanmin(wp)
                        rng_h = np.nanmax(wh) - np.nanmin(wh)
                        if rng_t < k_freeze * max(frz_t_m, 1e-3) or rng_p < k_freeze * max(frz_p_m, 1e-3) or rng_h < k_freeze * max(frz_h_m, 1e-3):
                            is_anom, ft = True, "frozen_value"

                    w7_hit = False
                    if count >= 168:
                        t7 = buf_t[(head - 1 - 167) % 512]
                        p7 = buf_p[(head - 1 - 167) % 512]
                        h7 = buf_h[(head - 1 - 167) % 512]
                        if not math.isnan(t7):
                            dt7 = ti - t7; dp7 = pi - p7; dh7 = hi - h7
                            sk_t = k_w7d * max(math.sqrt(max(w7d_t_v, 1e-9)), 0.3)
                            sk_p = k_w7d * max(math.sqrt(max(w7d_p_v, 1e-9)), 0.3)
                            sk_h = k_w7d * max(math.sqrt(max(w7d_h_v, 1e-9)), 0.5)
                            gr = 0.96; dc = w7dec; thr = w7thr
                            if dt7 > sk_t:   w7_pt = max(0.0, w7_pt * gr + (dt7 - sk_t)); w7_nt *= dc
                            elif dt7 < -sk_t: w7_nt = max(0.0, w7_nt * gr + (-dt7 - sk_t)); w7_pt *= dc
                            else:            w7_pt *= dc; w7_nt *= dc
                            
                            if dp7 > sk_p:   w7_pp = max(0.0, w7_pp * gr + (dp7 - sk_p)); w7_np *= dc
                            elif dp7 < -sk_p: w7_np = max(0.0, w7_np * gr + (-dp7 - sk_p)); w7_pp *= dc
                            else:            w7_pp *= dc; w7_np *= dc
                            
                            if dh7 > sk_h:   w7_ph = max(0.0, w7_ph * gr + (dh7 - sk_h)); w7_nh *= dc
                            elif dh7 < -sk_h: w7_nh = max(0.0, w7_nh * gr + (-dh7 - sk_h)); w7_ph *= dc
                            else:            w7_ph *= dc; w7_nh *= dc
                            
                            if (w7_pt > thr or w7_nt > thr or w7_pp > thr or w7_np > thr or w7_ph > thr or w7_nh > thr):
                                w7_hit = True
                            if not is_anom:
                                diff_t = dt7 - w7d_t_m; w7d_t_m += alpha * diff_t; w7d_t_v = (1 - alpha) * (w7d_t_v + alpha * diff_t * diff_t)
                                diff_p = dp7 - w7d_p_m; w7d_p_m += alpha * diff_p; w7d_p_v = (1 - alpha) * (w7d_p_v + alpha * diff_p * diff_p)
                                diff_h = dh7 - w7d_h_m; w7d_h_m += alpha * diff_h; w7d_h_v = (1 - alpha) * (w7d_h_v + alpha * diff_h * diff_h)
                                w7d_n += 1
                        else:
                            w7_pt = w7_nt = w7_pp = w7_np = w7_ph = w7_nh = 0.0

                    sl_hit = False
                    if count >= 48 and slp_n >= 48:
                        t24 = buf_t[(head - 1 - 23) % 512]
                        t48 = buf_t[(head - 1 - 47) % 512]
                        if not (math.isnan(t24) or math.isnan(t48)):
                            d24 = ti - t24; d48 = t24 - t48
                            sk = 2.4 * max(math.sqrt(max(slp_t_v, 1e-9)), 0.2)
                            if d24 > sk and d48 > sk * 0.6: s_up += 1; s_dn = max(0, s_dn - 1)
                            elif d24 < -sk and d48 < -sk * 0.6: s_dn += 1; s_up = max(0, s_up - 1)
                            else: s_up = max(0, s_up - 1); s_dn = max(0, s_dn - 1)
                            if s_up >= 3 or s_dn >= 3: sl_hit = True
                            if not is_anom:
                                diff = d24 - slp_t_m; slp_t_m += alpha * diff; slp_t_v = (1 - alpha) * (slp_t_v + alpha * diff * diff); slp_n += 1

                    if not is_anom and (w7_hit or sl_hit):
                        is_anom, ft = True, "drift"

                    if not is_anom and if_scores is not None and not math.isnan(if_scores[i]):
                        if if_scores[i] > iforest_thresh:
                            is_anom, ft = True, "unstructured_anomaly"

                    if not is_anom:
                        if last_t is not None and not math.isnan(last_t):
                            d_t = abs(ti - last_t); diff = d_t - roc_t_m; roc_t_m += alpha * diff; roc_t_v = (1 - alpha) * (roc_t_v + alpha * diff * diff)
                            d_p = abs(pi - last_p); diff = d_p - roc_p_m; roc_p_m += alpha * diff; roc_p_v = (1 - alpha) * (roc_p_v + alpha * diff * diff)
                            d_h = abs(hi - last_h); diff = d_h - roc_h_m; roc_h_m += alpha * diff; roc_h_v = (1 - alpha) * (roc_h_v + alpha * diff * diff)
                            roc_n += 1
                        if count >= 6:
                            idxs2 = [(head - 1 - j) % 512 for j in range(6)]
                            wt2 = buf_t[idxs2]; wp2 = buf_p[idxs2]; wh2 = buf_h[idxs2]
                            wt2[0] = ti; wp2[0] = pi; wh2[0] = hi
                            diff = float(np.nanmax(wt2) - np.nanmin(wt2)) - frz_t_m; frz_t_m += alpha_slow * diff; frz_t_v = (1 - alpha_slow) * (frz_t_v + alpha_slow * diff * diff)
                            diff = float(np.nanmax(wp2) - np.nanmin(wp2)) - frz_p_m; frz_p_m += alpha_slow * diff; frz_p_v = (1 - alpha_slow) * (frz_p_v + alpha_slow * diff * diff)
                            diff = float(np.nanmax(wh2) - np.nanmin(wh2)) - frz_h_m; frz_h_m += alpha_slow * diff; frz_h_v = (1 - alpha_slow) * (frz_h_v + alpha_slow * diff * diff)
                            frz_n += 1
                        if ti < obs_min_t: obs_min_t = ti
                        if pi < obs_min_p: obs_min_p = pi
                        if hi < obs_min_h: obs_min_h = hi
                        diff = ti - obs_t_m; obs_t_m += alpha * diff; obs_t_v = (1 - alpha) * (obs_t_v + alpha * diff * diff)
                        diff = pi - obs_p_m; obs_p_m += alpha * diff; obs_p_v = (1 - alpha) * (obs_p_v + alpha * diff * diff)
                        diff = hi - obs_h_m; obs_h_m += alpha * diff; obs_h_v = (1 - alpha) * (obs_h_v + alpha * diff * diff)
                        obs_n += 1

                    flag = is_anom

            # Track predicted episodes
            if flag and not in_pred:
                in_pred = True; p_start = i; p_ft = ft
            elif not flag and in_pred:
                in_pred = False
                predicted_events.append({
                    "station_id": st_id, "fault_type": p_ft, "affected_parameters": ["temperature_c"],
                    "start_timestamp": str(ts[p_start]), "end_timestamp": str(ts[i-1]),
                    "start_index": p_start, "end_index": i-1
                })

            # Buffer write
            buf_t[head] = ti; buf_p[head] = pi; buf_h[head] = hi
            head = (head + 1) % 512
            if count < 512: count += 1
            last_t = ti; last_p = pi; last_h = hi

            if g != "normal":
                if g not in fault_counts: fault_counts[g] = [0, 0]
                fault_counts[g][0] += 1
                if flag: fault_counts[g][1] += 1

            if flag and is_gt: TP += 1
            elif flag and not is_gt: FP += 1
            elif not flag and is_gt: FN += 1
            else: TN += 1

        if in_pred:
            predicted_events.append({
                "station_id": st_id, "fault_type": p_ft, "affected_parameters": ["temperature_c"],
                "start_timestamp": str(ts[p_start]), "end_timestamp": str(ts[N-1]),
                "start_index": p_start, "end_index": N-1
            })

    row_metrics = {
        "precision": TP / (TP + FP) * 100 if (TP + FP) > 0 else 0,
        "recall": TP / (TP + FN) * 100 if (TP + FN) > 0 else 0,
        "f1": 2 * (TP / (TP + FP)) * (TP / (TP + FN)) / ((TP / (TP + FP)) + (TP / (TP + FN))) * 100 if (TP + FP > 0 and TP + FN > 0) else 0,
        "tp": TP, "fp": FP, "fn": FN, "tn": TN
    }

    # Compute episodic metrics per fault type
    ep_drift = episodic_metrics(truth_events, predicted_events, "drift")
    ep_frozen = episodic_metrics(truth_events, predicted_events, "frozen_value")
    ep_spike = episodic_metrics(truth_events, predicted_events, "spike")
    ep_fail = episodic_metrics(truth_events, predicted_events, "sensor_fail_low")
    ep_multi = episodic_metrics(truth_events, predicted_events, "multivariate_inconsistency")

    return row_metrics, {
        "drift": ep_drift, "frozen_value": ep_frozen,
        "spike": ep_spike, "sensor_fail_low": ep_fail,
        "multivariate_inconsistency": ep_multi
    }, fault_counts

def main():
    print("Training IForest...")
    clf = train_iforest()
    data = load_data(clf)
    data_center = [d for d in data if any(cs in d["id"] for cs in CENTER_STATIONS)]

    cfg = {"k_w7d": 4.5, "w7thr": 18.0, "w7dec": 0.80, "kspk": 5.0, "k_freeze": 0.28, "iforest_thresh": 0.62}

    print("\n" + "=" * 85)
    print("      SKYGUARD EDGE AI -- EPISODIC VS ROW-LEVEL BENCHMARK REPORT")
    print("=" * 85)
    
    r_all, ep_all, fc_all = run_pass_eval(data, cfg)
    r_cen, ep_cen, fc_cen = run_pass_eval(data_center, cfg)

    print("\n--- ALL 28 STATIONS (COMPLEX FAULT DATASET) ---")
    print(f"  Row-Level Micro    : Precision = {r_all['precision']:.2f}% | Recall = {r_all['recall']:.2f}% | F1 = {r_all['f1']:.2f}%")
    print("  Episodic Event Matching (Matched by Overlap):")
    for ft, ep in ep_all.items():
        print(f"    - {ft:<28}: Prec = {ep['precision']*100:>5.1f}% | Rec = {ep['recall']*100:>5.1f}% | Episodes (TP={ep['tp']}, FP={ep['fp']}, GroundTruth={ep['truth_episodes']})")

    print("\n--- LOW-STRESS BENCHMARK (7 FAULTED CENTER STATIONS) ---")
    print(f"  Row-Level Micro    : Precision = {r_cen['precision']:.2f}% | Recall = {r_cen['recall']:.2f}% | F1 = {r_cen['f1']:.2f}%")
    print("  Episodic Event Matching (Matched by Overlap):")
    for ft, ep in ep_cen.items():
        print(f"    - {ft:<28}: Prec = {ep['precision']*100:>5.1f}% | Rec = {ep['recall']*100:>5.1f}% | Episodes (TP={ep['tp']}, FP={ep['fp']}, GroundTruth={ep['truth_episodes']})")

    print("=" * 85)

if __name__ == "__main__":
    main()
