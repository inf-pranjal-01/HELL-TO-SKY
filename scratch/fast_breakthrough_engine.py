"""
SkyGuard Edge AI -- Fast Parallel Breakthrough Engine (Target: >= 50% Prec / >= 75% Rec)
=======================================================================================
"""

import glob, math, time
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from concurrent.futures import ProcessPoolExecutor

FILES = sorted(glob.glob("data/*_labeled.csv"))
CENTER_STATIONS = [
    "AWS-BHO-030", "AWS-CHN-024", "AWS-DEL-011", "AWS-KOL-015",
    "AWS-MUM-007", "AWS-RAN-067", "AWS-VAR-052"
]
CENTER_FILES = [f for f in FILES if any(cs in f for cs in CENTER_STATIONS)]

GLOBAL_DATA = []

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

def prepare():
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
    clf = IsolationForest(n_estimators=60, max_samples=256, contamination=0.008, random_state=42, n_jobs=-1)
    clf.fit(X)

    data = []
    for f in CENTER_FILES:
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
        if mask.any():
            scores[mask] = -clf.score_samples(F[mask])

        data.append((t, p, h, gt, gft, ts, scores))
    return data

def init_worker(data):
    global GLOBAL_DATA
    GLOBAL_DATA = data

def eval_single(params):
    (k_w7d, w7thr, if_thr, veto_anti_corr) = params
    alpha = 0.02
    kspk = 5.0
    k_freeze = 0.28
    k_rail = 4.0

    TP = FP = FN = TN = 0
    fault_counts = {}

    for (t, p, h, gt, gft, ts, scores) in GLOBAL_DATA:
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

        obs_min_t = obs_min_p = obs_min_h = 1e9
        obs_t_m = obs_p_m = obs_h_m = 0.0
        obs_t_v = obs_p_v = obs_h_v = 1.0
        obs_n = 0

        w7_pt = w7_nt = 0.0

        for i in range(N):
            ti = t[i]; pi = p[i]; hi = h[i]
            is_gt = gt[i]; g = gft[i]

            if math.isnan(ti) or math.isnan(pi) or math.isnan(hi):
                flag, ft = True, "dropout"
            elif ti <= -35.0 or pi <= 50.0 or hi <= 0.0 or ti < -50.0 or ti > 60.0 or pi < 800.0 or pi > 1100.0 or hi < 0.0 or hi > 100.0:
                flag, ft = True, "sensor_fail_low" if (ti <= -35.0 or pi <= 50.0 or hi <= 0.0) else "physical_bounds"
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
                        rng_t = np.nanmax(wt) - np.nanmin(wt)
                        rng_p = np.nanmax(wp) - np.nanmin(wp)
                        rng_h = np.nanmax(wh) - np.nanmin(wh)
                        if rng_t < k_freeze * max(frz_t_m, 1e-3) or rng_p < k_freeze * max(frz_p_m, 1e-3) or rng_h < k_freeze * max(frz_h_m, 1e-3):
                            is_anom, ft = True, "frozen_value"

                    w7_hit = False
                    if count >= 168:
                        off7 = (head - 1 - 167) % 512
                        t7 = buf_t[off7]; p7 = buf_p[off7]; h7 = buf_h[off7]
                        if not math.isnan(t7):
                            dt7 = ti - t7; dp7 = pi - p7; dh7 = hi - h7
                            sk_t = k_w7d * max(math.sqrt(max(w7d_t_v, 1e-9)), 0.4)

                            if dt7 > sk_t:
                                w7_pt = max(0.0, w7_pt * 0.96 + (dt7 - sk_t)); w7_nt = 0.0
                            elif dt7 < -sk_t:
                                w7_nt = max(0.0, w7_nt * 0.96 + (-dt7 - sk_t)); w7_pt = 0.0
                            else:
                                w7_pt = 0.0; w7_nt = 0.0

                            if (w7_pt > w7thr or w7_nt > w7thr):
                                is_weather_front = False
                                if veto_anti_corr and not math.isnan(h7):
                                    if (dt7 > 0 and dh7 < -4.0) or (dt7 < 0 and dh7 > 4.0):
                                        is_weather_front = True
                                if not is_weather_front:
                                    w7_hit = True

                            if not is_anom:
                                diff_t = dt7 - w7d_t_m; w7d_t_m += alpha * diff_t; w7d_t_v = (1 - alpha) * (w7d_t_v + alpha * diff_t * diff_t)
                        else:
                            w7_pt = w7_nt = 0.0

                    if not is_anom and w7_hit:
                        is_anom, ft = True, "drift"

                    if not is_anom and scores is not None and not math.isnan(scores[i]):
                        if scores[i] > if_thr:
                            is_anom, ft = True, "unstructured_anomaly"

                    if not is_anom:
                        if last_t is not None and not math.isnan(last_t):
                            d_t = abs(ti - last_t); diff = d_t - roc_t_m; roc_t_m += alpha * diff; roc_t_v = (1 - alpha) * (roc_t_v + alpha * diff * diff)
                            roc_n += 1
                        if count >= 6:
                            idxs2 = [(head - 1 - j) % 512 for j in range(6)]
                            wt2 = buf_t[idxs2]; wp2 = buf_p[idxs2]; wh2 = buf_h[idxs2]
                            wt2[0] = ti; wp2[0] = pi; wh2[0] = hi
                            diff = float(np.nanmax(wt2) - np.nanmin(wt2)) - frz_t_m; frz_t_m += alpha * diff; frz_t_v = (1 - alpha) * (frz_t_v + alpha * diff * diff)
                            frz_n += 1
                        if ti < obs_min_t: obs_min_t = ti
                        if pi < obs_min_p: obs_min_p = pi
                        if hi < obs_min_h: obs_min_h = hi
                        diff = ti - obs_t_m; obs_t_m += alpha * diff; obs_t_v = (1 - alpha) * (obs_t_v + alpha * diff * diff)
                        obs_n += 1

                    flag = is_anom

            buf_t[head] = ti; buf_p[head] = pi; buf_h[head] = hi
            head = (head + 1) % 512
            if count < 512: count += 1
            last_t, last_p, last_h = ti, pi, hi

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
    return params, prec, rec, f1, spec, TP, FP, FN, TN, fault_counts

def main():
    import itertools
    data = prepare()

    combos = list(itertools.product(
        [3.0, 3.5, 4.0, 4.5, 5.0],        # k_w7d
        [8.0, 10.0, 12.0, 15.0, 18.0],     # w7thr
        [0.62, 0.65, 0.68],               # if_thr
        [True, False]                     # veto_anti_corr
    ))

    t0 = time.time()
    with ProcessPoolExecutor(initializer=init_worker, initargs=(data,)) as executor:
        results = list(executor.map(eval_single, combos))

    t_elapsed = time.time() - t0
    print(f"Sweep done in {t_elapsed:.2f}s ({len(combos)/t_elapsed:.1f} evals/sec)")

    results.sort(key=lambda x: -x[3]) # sort by F1
    hits = [r for r in results if r[1] >= 50.0 and r[2] >= 75.0]

    print("=" * 85)
    print("      PSYCHROMETRIC VETO & INSTANT RESET BREAKTHROUGH RESULTS")
    print("=" * 85)
    print(f"Total evaluated configurations: {len(results)}")
    print(f"Configs achieving >= 50% Prec AND >= 75% Rec: {len(hits)}\n")
    print(f"{'K_W7D':>6} {'W7THR':>6} {'IF_THR':>7} {'VETO':>5} | {'Prec':>7} {'Rec':>7} {'F1':>7} | TP/FP/FN")
    print("-" * 85)

    top_list = hits[:10] if hits else results[:10]
    for r in top_list:
        p = r[0]
        prec, rec, f1, spec, tp, fp, fn, tn, _ = r[1:]
        tag = "*** TARGET HIT ***" if (prec >= 50.0 and rec >= 75.0) else ""
        print(f"{p[0]:>6.1f} {p[1]:>6.1f} {p[2]:>7.2f} {str(p[3]):>5} | {prec:>6.1f}% {rec:>6.1f}% {f1:>6.1f}% | {tp}/{fp}/{fn} {tag}")

    best = results[0] if not hits else hits[0]
    p, prec, rec, f1, spec, tp, fp, fn, tn, fc = best
    print("\n" + "=" * 85)
    print("      BEST BREAKTHROUGH CONFIGURATION DETAILED REPORT")
    print(f"      Parameters: K_W7D={p[0]}, W7THR={p[1]}, IF_THR={p[2]}, VETO={p[3]}")
    print("=" * 85)
    print(f"  • Precision (PPV)    : {prec:.2f}%")
    print(f"  • Recall (TPR)       : {rec:.2f}%")
    print(f"  • F1-Score           : {f1:.2f}%")
    print(f"  • Specificity (TNR)  : {spec:.2f}%")
    print(f"  • Confusion Matrix   : TP={tp:,} | FP={fp:,} | FN={fn:,} | TN={tn:,}")
    print("\n  Granular Catch Rates Across Injected Fault Classes:")
    for k, v in sorted(fc.items(), key=lambda x: -x[1][0]):
        c_rate = v[1] / max(v[0], 1) * 100
        print(f"    - {k:<28}: {v[1]:>4}/{v[0]:>4} ({c_rate:>5.1f}%)")
    print("=" * 85)

if __name__ == "__main__":
    main()
