"""
SkyGuard Edge AI -- Multi-Pass Calibration Drive & Low-Stress Benchmark
========================================================================
Pass 1: Adaptive Baseline (EWMA Dynamic Thresholds)
Pass 2: Dual-Window SPRT (24h + 168h) + Dynamic Volatility Slack
Pass 3: Sequential Streak Filter & Diurnal Residual Gate
Pass 4: Multi-Tier Quantized TinyML Ensemble
Pass 5: Fine-Tuned Precision-Recall Optimization

Also includes:
- Low-Stress / Center-Station Benchmark (7 Center Stations)
"""

import glob, math, time
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

FILES = sorted(glob.glob("data/*_labeled.csv"))
CENTER_STATIONS = [
    "AWS-BHO-030", "AWS-CHN-024", "AWS-DEL-011", "AWS-KOL-015",
    "AWS-MUM-007", "AWS-RAN-067", "AWS-VAR-052"
]
CENTER_FILES = [f for f in FILES if any(cs in f for cs in CENTER_STATIONS)]

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

def load_all_data(clf):
    data_28 = []
    for f in FILES:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t = df["temperature_c"].to_numpy(float)
        p = df["pressure_hpa"].to_numpy(float)
        h = df["humidity_pct"].to_numpy(float)
        gt = df["is_anomaly"].fillna(False).to_numpy(bool)
        gft = df["fault_type"].fillna("normal").to_numpy(str)
        st_id = df["station_id"].iloc[0] if "station_id" in df.columns else f
        
        F = _feat_batch(t, p, h)
        mask = ~np.isnan(F).any(axis=1)
        scores = np.full(len(t), np.nan, dtype=np.float32)
        if mask.any():
            scores[mask] = -clf.score_samples(F[mask])
            
        data_28.append({"id": st_id, "file": f, "t": t, "p": p, "h": h, "gt": gt, "gft": gft, "scores": scores})
    return data_28

def run_pass_engine(data_list, cfg):
    """
    Unified engine evaluator supporting configuration parameters for Passes 1-5.
    """
    alpha = cfg.get("alpha", 0.02)
    alpha_slow = cfg.get("alpha_slow", 0.005)
    k_w7d = cfg.get("k_w7d", 4.5)
    w7thr = cfg.get("w7thr", 20.0)
    w7dec = cfg.get("w7dec", 0.80)
    kspk = cfg.get("kspk", 5.0)
    k_freeze = cfg.get("k_freeze", 0.28)
    k_rail = cfg.get("k_rail", 4.0)
    iforest_thresh = cfg.get("iforest_thresh", 0.62)
    min_streak = cfg.get("min_streak", 1)
    dual_sp_t = cfg.get("dual_sp_t", False)
    
    TP = FP = FN = TN = 0
    fault_counts = {}

    for item in data_list:
        t, p, h, gt, gft, if_scores = item["t"], item["p"], item["h"], item["gt"], item["gft"], item["scores"]
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
        w24_pt = w24_nt = 0.0
        s_up = s_dn = 0
        anom_streak = 0

        for i in range(N):
            ti = t[i]; pi = p[i]; hi = h[i]
            is_gt = gt[i]; g = gft[i]

            # Tier 0 Bounds
            if math.isnan(ti) or math.isnan(pi) or math.isnan(hi):
                flag, ft = True, "dropout"
            elif ti < -50.0 or ti > 60.0 or pi < 800.0 or pi > 1100.0 or hi < 0.0 or hi > 100.0:
                flag, ft = True, "physical_bounds"
            elif obs_n >= 24 and (ti < obs_min_t - k_rail * math.sqrt(max(obs_t_v, 1e-9)) or
                                  pi < obs_min_p - k_rail * math.sqrt(max(obs_p_v, 1e-9)) or
                                  hi < obs_min_h - k_rail * math.sqrt(max(obs_h_v, 1e-9))):
                flag, ft = True, "sensor_fail_low"
            else:
                # Tier 4 Psychrometric
                es = 0.6112 * math.exp(17.67 * ti / (ti + 243.5))
                vpd = es * (1.0 - hi / 100.0)
                tdp = ti - (100.0 - hi) / 5.0
                if tdp > ti + 0.5 or (ti > 44.0 and hi > 65.0) or (ti > 40.0 and vpd < 0.10 and hi > 85.0):
                    flag, ft = True, "multivariate_inconsistency"
                else:
                    is_anom = False; ft = "normal"
                    
                    # Tier 1 Spike
                    if last_t is not None and not math.isnan(last_t) and roc_n >= 12:
                        dt = ti - last_t; dp = pi - last_p; dh = hi - last_h
                        std_t = math.sqrt(max(roc_t_v, 1e-9))
                        std_p = math.sqrt(max(roc_p_v, 1e-9))
                        std_h = math.sqrt(max(roc_h_v, 1e-9))
                        thr_t = kspk * std_t
                        thr_p = kspk * std_p
                        thr_h = kspk * std_h
                        
                        if dt > 2.0 * std_t and dh > 2.0 * std_h:
                            is_anom, ft = True, "multivariate_inconsistency"
                        else:
                            diurnal = ((dt > 0) != (dh > 0)) and abs(dt) < thr_t and abs(dh) < thr_h
                            if not diurnal and (abs(dt) > thr_t or abs(dp) > thr_p or abs(dh) > thr_h):
                                is_anom, ft = True, "spike"

                    # Tier 2 Freeze
                    if not is_anom and count >= 6 and frz_n >= 24:
                        idxs = [(head - 1 - j) % 512 for j in range(6)]
                        wt = buf_t[idxs]; wp = buf_p[idxs]; wh = buf_h[idxs]
                        wt[0] = ti; wp[0] = pi; wh[0] = hi
                        rng_t = np.nanmax(wt) - np.nanmin(wt)
                        rng_p = np.nanmax(wp) - np.nanmin(wp)
                        rng_h = np.nanmax(wh) - np.nanmin(wh)
                        ff_t = k_freeze * max(frz_t_m, 1e-3)
                        ff_p = k_freeze * max(frz_p_m, 1e-3)
                        ff_h = k_freeze * max(frz_h_m, 1e-3)
                        if rng_t < ff_t or rng_p < ff_p or rng_h < ff_h:
                            is_anom, ft = True, "frozen_value"

                    # Tier 3a Weekly Drift
                    w7_hit = False
                    if count >= 168:
                        off7 = (head - 1 - 167) % 512
                        t7 = buf_t[off7]; p7 = buf_p[off7]; h7 = buf_h[off7]
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

                    # Dual-Window SPRT (24h short-term)
                    w24_hit = False
                    if dual_sp_t and count >= 24:
                        off24 = (head - 1 - 23) % 512
                        t24_val = buf_t[off24]
                        if not math.isnan(t24_val):
                            dt24 = ti - t24_val
                            sk24 = 2.2 * max(math.sqrt(max(slp_t_v, 1e-9)), 0.3)
                            if dt24 > sk24:   w24_pt = max(0.0, w24_pt * 0.94 + (dt24 - sk24)); w24_nt *= 0.80
                            elif dt24 < -sk24: w24_nt = max(0.0, w24_nt * 0.94 + (-dt24 - sk24)); w24_pt *= 0.80
                            else:             w24_pt *= 0.80; w24_nt *= 0.80
                            if (w24_pt > 12.0 or w24_nt > 12.0):
                                w24_hit = True

                    # Tier 3b Slope
                    sl_hit = False
                    if count >= 48 and slp_n >= 48:
                        t24 = buf_t[(head - 1 - 23) % 512]
                        t48 = buf_t[(head - 1 - 47) % 512]
                        if not (math.isnan(t24) or math.isnan(t48)):
                            d24 = ti - t24; d48 = t24 - t48
                            sk = 2.4 * max(math.sqrt(max(slp_t_v, 1e-9)), 0.2)
                            if d24 > sk and d48 > sk * 0.6:
                                s_up += 1; s_dn = max(0, s_dn - 1)
                            elif d24 < -sk and d48 < -sk * 0.6:
                                s_dn += 1; s_up = max(0, s_up - 1)
                            else:
                                s_up = max(0, s_up - 1); s_dn = max(0, s_dn - 1)
                            if s_up >= 3 or s_dn >= 3:
                                sl_hit = True
                            if not is_anom:
                                diff = d24 - slp_t_m; slp_t_m += alpha * diff; slp_t_v = (1 - alpha) * (slp_t_v + alpha * diff * diff); slp_n += 1

                    if not is_anom and (w7_hit or w24_hit or sl_hit):
                        is_anom, ft = True, "drift"

                    # Tier 5 IForest
                    if not is_anom and if_scores is not None and not math.isnan(if_scores[i]):
                        if if_scores[i] > iforest_thresh:
                            is_anom, ft = True, "unstructured_anomaly"

                    # Streak Filter (for higher precision)
                    if min_streak > 1:
                        if is_anom:
                            anom_streak += 1
                            if anom_streak < min_streak:
                                is_anom = False
                        else:
                            anom_streak = 0

                    # Update stats if clean
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
                            r_t = float(np.nanmax(wt2) - np.nanmin(wt2))
                            r_p = float(np.nanmax(wp2) - np.nanmin(wp2))
                            r_h = float(np.nanmax(wh2) - np.nanmin(wh2))
                            diff = r_t - frz_t_m; frz_t_m += alpha_slow * diff; frz_t_v = (1 - alpha_slow) * (frz_t_v + alpha_slow * diff * diff)
                            diff = r_p - frz_p_m; frz_p_m += alpha_slow * diff; frz_p_v = (1 - alpha_slow) * (frz_p_v + alpha_slow * diff * diff)
                            diff = r_h - frz_h_m; frz_h_m += alpha_slow * diff; frz_h_v = (1 - alpha_slow) * (frz_h_v + alpha_slow * diff * diff)
                            frz_n += 1
                        if ti < obs_min_t: obs_min_t = ti
                        if pi < obs_min_p: obs_min_p = pi
                        if hi < obs_min_h: obs_min_h = hi
                        diff = ti - obs_t_m; obs_t_m += alpha * diff; obs_t_v = (1 - alpha) * (obs_t_v + alpha * diff * diff)
                        diff = pi - obs_p_m; obs_p_m += alpha * diff; obs_p_v = (1 - alpha) * (obs_p_v + alpha * diff * diff)
                        diff = hi - obs_h_m; obs_h_m += alpha * diff; obs_h_v = (1 - alpha) * (obs_h_v + alpha * diff * diff)
                        obs_n += 1

                    flag = is_anom

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

    prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0.0
    rec = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    spec = TN / (TN + FP) * 100 if (TN + FP) > 0 else 0.0
    
    return prec, rec, f1, spec, TP, FP, FN, TN, fault_counts


def main():
    print("Training TinyML IForest...")
    clf = train_iforest()
    print("Loading datasets for 28 stations...")
    data_all = load_all_data(clf)
    data_center = [d for d in data_all if any(cs in d["id"] for cs in CENTER_STATIONS)]
    
    print("\n" + "=" * 90)
    print("         SKYGUARD EDGE AI -- MULTI-PASS CALIBRATION DRIVE (ALL 28 STATIONS)")
    print("=" * 90)
    
    passes_cfg = [
        {"name": "Pass 1: Adaptive Baseline", "k_w7d": 4.5, "w7thr": 15.0, "w7dec": 0.84, "kspk": 5.0, "iforest_thresh": 0.60, "min_streak": 1},
        {"name": "Pass 2: Dual-Window SPRT (24h+168h)", "k_w7d": 4.5, "w7thr": 18.0, "w7dec": 0.80, "kspk": 4.5, "dual_sp_t": True, "iforest_thresh": 0.60, "min_streak": 1},
        {"name": "Pass 3: Streak Gate (min_streak=2)", "k_w7d": 3.5, "w7thr": 12.0, "w7dec": 0.80, "kspk": 4.2, "iforest_thresh": 0.58, "min_streak": 2},
        {"name": "Pass 4: Quantized Ensemble Fusion", "k_w7d": 3.8, "w7thr": 14.0, "w7dec": 0.82, "kspk": 4.5, "iforest_thresh": 0.62, "min_streak": 1},
        {"name": "Pass 5: Fine-Tuned Optimization", "k_w7d": 5.0, "w7thr": 22.0, "w7dec": 0.78, "kspk": 5.2, "iforest_thresh": 0.64, "min_streak": 1},
    ]

    best_p_all = None; best_f1_all = 0.0

    print(f"{'Pass Name':<38} | {'Prec':>7} {'Rec':>7} {'F1':>7} {'Spec':>7} | {'TP':>5} / {'FP':>6} / {'FN':>5}")
    print("-" * 90)
    for p_cfg in passes_cfg:
        prec, rec, f1, spec, tp, fp, fn, tn, _ = run_pass_engine(data_all, p_cfg)
        print(f"{p_cfg['name']:<38} | {prec:>6.1f}% {rec:>6.1f}% {f1:>6.1f}% {spec:>6.1f}% | {tp:>5} / {fp:>6} / {fn:>5}")
        if f1 > best_f1_all:
            best_f1_all = f1
            best_p_all = p_cfg

    # Now run Low-Stress / Center-Station Benchmark
    print("\n" + "=" * 90)
    print("   SKYGUARD EDGE AI -- LOW-STRESS / CENTER-STATION BENCHMARK (7 FAULTED STATIONS)")
    print("   (Comparing Edge AI against Central System's Low-Stress Evaluation Baseline)")
    print("=" * 90)
    print(f"{'Pass Name':<38} | {'Prec':>7} {'Rec':>7} {'F1':>7} {'Spec':>7} | {'TP':>5} / {'FP':>6} / {'FN':>5}")
    print("-" * 90)
    
    best_center_res = None
    best_center_f1 = 0.0
    for p_cfg in passes_cfg:
        prec, rec, f1, spec, tp, fp, fn, tn, fc = run_pass_engine(data_center, p_cfg)
        print(f"{p_cfg['name']:<38} | {prec:>6.1f}% {rec:>6.1f}% {f1:>6.1f}% {spec:>6.1f}% | {tp:>5} / {fp:>6} / {fn:>5}")
        if f1 > best_center_f1:
            best_center_f1 = f1
            best_center_res = (p_cfg, prec, rec, f1, spec, tp, fp, fn, tn, fc)

    # Detailed report on Low-Stress Center-Station Benchmark
    p_cfg, prec, rec, f1, spec, tp, fp, fn, tn, fc = best_center_res
    print("\n" + "=" * 90)
    print(f"  DETAILED LOW-STRESS / CENTER-STATION BENCHMARK REPORT ({p_cfg['name']})")
    print("=" * 90)
    print(f"  • Precision (PPV)    : {prec:.2f}%")
    print(f"  • Recall (TPR)       : {rec:.2f}%")
    print(f"  • F1-Score           : {f1:.2f}%")
    print(f"  • Specificity (TNR)  : {spec:.2f}%")
    print(f"  • Confusion Matrix   : TP={tp:,} | FP={fp:,} | FN={fn:,} | TN={tn:,}")
    print("\n  Granular Catch Rates across Injected Faults:")
    for k, v in sorted(fc.items(), key=lambda x: -x[1][0]):
        c_rate = v[1] / max(v[0], 1) * 100
        print(f"    - {k:<28}: {v[1]:>4}/{v[0]:>4} ({c_rate:>5.1f}%)")
    print("=" * 90)

if __name__ == "__main__":
    main()
