"""
SkyGuard Edge AI -- Hybrid Episodic Scorecard Audit
===================================================
Re-evaluates our dynamic adaptive engine using the authoritative Hybrid Episodic Scorecard
(Episodic Incident Matching for continuous faults like drift/freeze/spike-decay,
Row-by-Row matching for instantaneous faults like dropout/fail-low/unstructured).
"""

import glob, math
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

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
    clf = IsolationForest(n_estimators=80, max_samples=256, contamination=0.008, random_state=42, n_jobs=-1)
    clf.fit(X)
    return clf

def evaluate_hybrid(cfg, clf, file_list):
    alpha = cfg.get("alpha", 0.02)
    k_w7d = cfg.get("k_w7d", 4.5)
    w7thr = cfg.get("w7thr", 18.0)
    w7dec = cfg.get("w7dec", 0.80)
    kspk = cfg.get("kspk", 5.0)
    k_freeze = cfg.get("k_freeze", 0.28)
    k_rail = cfg.get("k_rail", 4.0)
    iforest_thresh = cfg.get("iforest_thresh", 0.62)

    total_inst_tp = total_inst_fp = total_inst_fn = 0
    total_ep_tp = total_ep_fp = total_ep_fn = 0

    episodic_types = {"drift", "frozen_value", "spike"}
    instantaneous_types = {"dropout", "sensor_fail_low", "multivariate_inconsistency", "unstructured_anomaly"}

    ep_stats = {ft: {"truth": 0, "caught": 0, "fp": 0} for ft in episodic_types}
    inst_stats = {ft: {"tp": 0, "fp": 0, "fn": 0} for ft in instantaneous_types}

    for f in file_list:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t = df["temperature_c"].to_numpy(float)
        p = df["pressure_hpa"].to_numpy(float)
        h = df["humidity_pct"].to_numpy(float)
        gt = df["is_anomaly"].fillna(False).to_numpy(bool)
        gft = df["fault_type"].fillna("normal").to_numpy(str)
        ts = df["timestamp"].pipe(pd.to_datetime).dt.hour.to_numpy()
        N = len(t)

        F = _feat_batch(t, p, h)
        mask = ~np.isnan(F).any(axis=1)
        scores = np.full(N, np.nan, dtype=np.float32)
        if mask.any(): scores[mask] = -clf.score_samples(F[mask])

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
        obs_min_t = obs_min_p = obs_min_h = 1e9
        obs_t_m = obs_p_m = obs_h_m = 0.0
        obs_t_v = obs_p_v = obs_h_v = 1.0
        obs_n = 0
        w7_pt = w7_nt = w7_pp = w7_np = w7_ph = w7_nh = 0.0
        s_up = s_dn = 0

        pred_flags = np.zeros(N, dtype=bool)
        pred_types = np.full(N, "normal", dtype=object)

        for i in range(N):
            ti = t[i]; pi = p[i]; hi = h[i]
            hr = ts[i] % 24

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
                        std_t = math.sqrt(max(roc_t_v, 1e-9)); std_p = math.sqrt(max(roc_p_v, 1e-9)); std_h = math.sqrt(max(roc_h_v, 1e-9))
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
                        if np.nanmax(wt) - np.nanmin(wt) < k_freeze * max(frz_t_m, 1e-3) or \
                           np.nanmax(wp) - np.nanmin(wp) < k_freeze * max(frz_p_m, 1e-3) or \
                           np.nanmax(wh) - np.nanmin(wh) < k_freeze * max(frz_h_m, 1e-3):
                            is_anom, ft = True, "frozen_value"

                    w7_hit = False
                    if count >= 168:
                        t7 = buf_t[(head - 1 - 167) % 512]; p7 = buf_p[(head - 1 - 167) % 512]; h7 = buf_h[(head - 1 - 167) % 512]
                        if not math.isnan(t7):
                            dt7 = ti - t7; dp7 = pi - p7; dh7 = hi - h7
                            sk_t = k_w7d * max(math.sqrt(max(w7d_t_v, 1e-9)), 0.3)
                            sk_p = k_w7d * max(math.sqrt(max(w7d_p_v, 1e-9)), 0.3)
                            sk_h = k_w7d * max(math.sqrt(max(w7d_h_v, 1e-9)), 0.5)
                            gr = 0.96; dc = w7dec; thr = w7thr
                            if dt7 > sk_t:   w7_pt = max(0.0, w7_pt * gr + (dt7 - sk_t)); w7_nt *= dc
                            elif dt7 < -sk_t: w7_nt = max(0.0, w7_nt * gr + (-dt7 - sk_t)); w7_pt *= dc
                            else:            w7_pt *= dc; w7_nt *= dc
                            if (w7_pt > thr or w7_nt > thr): w7_hit = True
                            if not is_anom:
                                diff_t = dt7 - w7d_t_m; w7d_t_m += alpha * diff_t; w7d_t_v = (1 - alpha) * (w7d_t_v + alpha * diff_t * diff_t)

                    sl_hit = False
                    if count >= 48 and slp_n >= 48:
                        t24 = buf_t[(head - 1 - 23) % 512]; t48 = buf_t[(head - 1 - 47) % 512]
                        if not (math.isnan(t24) or math.isnan(t48)):
                            d24 = ti - t24; d48 = t24 - t48
                            sk = 2.4 * max(math.sqrt(max(slp_t_v, 1e-9)), 0.2)
                            if d24 > sk and d48 > sk * 0.6: s_up += 1; s_dn = max(0, s_dn - 1)
                            elif d24 < -sk and d48 < -sk * 0.6: s_dn += 1; s_up = max(0, s_up - 1)
                            else: s_up = max(0, s_up - 1); s_dn = max(0, s_dn - 1)
                            if s_up >= 3 or s_dn >= 3: sl_hit = True

                    if not is_anom and (w7_hit or sl_hit): is_anom, ft = True, "drift"

                    if not is_anom and scores is not None and not math.isnan(scores[i]):
                        if scores[i] > iforest_thresh: is_anom, ft = True, "unstructured_anomaly"

                    if not is_anom:
                        if last_t is not None and not math.isnan(last_t):
                            d_t = abs(ti - last_t); diff = d_t - roc_t_m; roc_t_m += alpha * diff; roc_t_v = (1 - alpha) * (roc_t_v + alpha * diff * diff)
                            roc_n += 1
                        if ti < obs_min_t: obs_min_t = ti
                        if pi < obs_min_p: obs_min_p = pi
                        if hi < obs_min_h: obs_min_h = hi
                        diff = ti - obs_t_m; obs_t_m += alpha * diff; obs_t_v = (1 - alpha) * (obs_t_v + alpha * diff * diff)
                        obs_n += 1

                    flag = is_anom

            pred_flags[i] = flag
            pred_types[i] = ft
            buf_t[head] = ti; buf_p[head] = pi; buf_h[head] = hi
            head = (head + 1) % 512
            if count < 512: count += 1
            last_t, last_p, last_h = ti, pi, hi

        # Evaluate Instantaneous faults row-by-row
        for ft in instantaneous_types:
            mask_gt = gt & (gft == ft)
            mask_pred = pred_flags & (pred_types == ft)
            tp_cnt = int((mask_gt & mask_pred).sum())
            fp_cnt = int((~gt & mask_pred).sum())
            fn_cnt = int((mask_gt & ~pred_flags).sum())

            inst_stats[ft]["tp"] += tp_cnt
            inst_stats[ft]["fp"] += fp_cnt
            inst_stats[ft]["fn"] += fn_cnt
            total_inst_tp += tp_cnt
            total_inst_fp += fp_cnt
            total_inst_fn += fn_cnt

        # Evaluate Episodic faults per incident
        for ft in episodic_types:
            mask_true = gt & (gft == ft)
            if mask_true.any():
                blocks = (~mask_true).cumsum()[mask_true]
                for _, grp in df[mask_true].groupby(blocks):
                    ep_stats[ft]["truth"] += 1
                    if pred_flags[grp.index].any():
                        ep_stats[ft]["caught"] += 1
                        total_ep_tp += 1
                    else:
                        total_ep_fn += 1

            mask_pred_fp = pred_flags & (pred_types == ft) & ~gt
            if mask_pred_fp.any():
                blocks_fp = (~mask_pred_fp).cumsum()[mask_pred_fp]
                num_fp_episodes = len(df[mask_pred_fp].groupby(blocks_fp))
                ep_stats[ft]["fp"] += num_fp_episodes
                total_ep_fp += num_fp_episodes

    comb_tp = total_inst_tp + total_ep_tp
    comb_fp = total_inst_fp + total_ep_fp
    comb_fn = total_inst_fn + total_ep_fn

    prec_hyb = comb_tp / (comb_tp + comb_fp) * 100 if (comb_tp + comb_fp) > 0 else 0.0
    rec_hyb = comb_tp / (comb_tp + comb_fn) * 100 if (comb_tp + comb_fn) > 0 else 0.0
    f1_hyb = 2 * prec_hyb * rec_hyb / (prec_hyb + rec_hyb) if (prec_hyb + rec_hyb) > 0 else 0.0

    return prec_hyb, rec_hyb, f1_hyb, comb_tp, comb_fp, comb_fn, ep_stats, inst_stats


def main():
    print("Training IForest...")
    clf = train_iforest()
    center_files = [f for f in FILES if any(cs in f for cs in CENTER_STATIONS)]

    cfg = {"k_w7d": 4.5, "w7thr": 18.0, "w7dec": 0.80, "kspk": 5.0, "k_freeze": 0.28, "iforest_thresh": 0.62}

    p_hyb, r_hyb, f1_hyb, tp, fp, fn, ep_s, inst_s = evaluate_hybrid(cfg, clf, center_files)

    print("\n" + "=" * 90)
    print("      SKYGUARD EDGE AI -- AUTHORITATIVE HYBRID EPISODIC SCORECARD")
    print("=" * 90)
    print(f"  • Overall Hybrid Precision  : {p_hyb:.2f}%")
    print(f"  • Overall Hybrid Recall     : {r_hyb:.2f}%")
    print(f"  • Overall Hybrid F1-Score   : {f1_hyb:.2f}%")
    print(f"  • Hybrid Confusion Matrix   : TP={tp:,} | FP={fp:,} | FN={fn:,}")
    print("\n  Granular Breakdown Across All Fault Types:")
    print(f"  {'Fault Type':<32} {'Type Category':<15} {'Recall':<10} {'Precision':<10}")
    print("  " + "-" * 75)

    for ft, s in sorted(ep_s.items()):
        rec = s["caught"] / s["truth"] * 100 if s["truth"] > 0 else 0
        prec = s["caught"] / (s["caught"] + s["fp"]) * 100 if (s["caught"] + s["fp"]) > 0 else 0
        print(f"  {ft:<32} {'Episodic':<15} {rec:>5.1f}%     {prec:>5.1f}%")

    for ft, s in sorted(inst_s.items()):
        rec = s["tp"] / (s["tp"] + s["fn"]) * 100 if (s["tp"] + s["fn"]) > 0 else 0
        prec = s["tp"] / (s["tp"] + s["fp"]) * 100 if (s["tp"] + s["fp"]) > 0 else 0
        print(f"  {ft:<32} {'Instantaneous':<15} {rec:>5.1f}%     {prec:>5.1f}%")
    print("=" * 90)

if __name__ == "__main__":
    main()
