"""
SkyGuard Edge AI -- High-Precision Debounced Engine
===================================================
Tests different debounce window lengths and persistence thresholds to push
precision toward 90%+ while keeping recall high.
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
CENTER_FILES = [f for f in FILES if any(cs in f for cs in CENTER_STATIONS)]


def _feat_batch(t, p, h):
    N = len(t)
    F = np.full((N, 9), np.nan, dtype=np.float32)
    roc1_t = np.diff(t, prepend=np.nan)
    roc3_t = t - np.concatenate([[np.nan]*3, t[:-3]])
    roc1_h = np.diff(h, prepend=np.nan)
    roc1_p = np.diff(p, prepend=np.nan)
    rng5_t = np.full(N, np.nan, dtype=np.float32)
    rng5_p = np.full(N, np.nan, dtype=np.float32)
    rng5_h = np.full(N, np.nan, dtype=np.float32)
    for i in range(4, N):
        rng5_t[i] = t[i-4:i+1].max() - t[i-4:i+1].min()
        rng5_p[i] = p[i-4:i+1].max() - p[i-4:i+1].min()
        rng5_h[i] = h[i-4:i+1].max() - h[i-4:i+1].min()
    vpd = 0.6112 * np.exp(17.67*t / (t+243.5)) * (1.0 - h/100.0)
    t_h_cov = roc1_t * roc1_h
    F[:,0]=roc1_t; F[:,1]=roc3_t; F[:,2]=roc1_h; F[:,3]=roc1_p
    F[:,4]=rng5_t; F[:,5]=rng5_p; F[:,6]=rng5_h; F[:,7]=vpd; F[:,8]=t_h_cov
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
    clf = IsolationForest(n_estimators=100, max_samples=256, contamination=0.005, random_state=42, n_jobs=-1)
    clf.fit(X)
    return clf


def run_sweep():
    print("Training IForest...")
    clf = train_iforest()

    print("\n" + "=" * 85)
    print("      DEBOUNCED HIGH-PRECISION SWEEP")
    print("=" * 85)
    print(f"{'DEBOUNCE':>8} {'SLACK_T':>8} {'SPRT_THR':>9} | {'Prec':>7} {'Rec':>7} {'F1':>7} {'Spec':>7}")
    print("-" * 85)

    for deb in [1, 2, 3, 4]:
        for slack_t in [3.0, 4.0, 5.0]:
            for sprt_thr in [15.0, 25.0, 35.0]:
                TP = FP = FN = TN = 0
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
                    if mask.any(): scores[mask] = -clf.score_samples(F[mask])

                    # Simulate engine
                    buf_t = np.full(512, np.nan, dtype=np.float32)
                    buf_p = np.full(512, np.nan, dtype=np.float32)
                    buf_h = np.full(512, np.nan, dtype=np.float32)
                    head = count = 0
                    last_t = last_p = last_h = None
                    diurnal_m_t = np.zeros(24, dtype=np.float32)
                    diurnal_init = np.zeros(24, dtype=bool)
                    sprt_pos_t = sprt_neg_t = 0.0
                    streak = 0

                    for i in range(N):
                        ti = t[i]; pi = p[i]; hi = h[i]
                        is_gt = gt[i]; g = gft[i]
                        hr = ts[i] % 24

                        if math.isnan(ti) or math.isnan(pi) or math.isnan(hi) or ti <= -35.0 or pi <= 50.0 or hi <= 0.0 or ti < -50.0 or ti > 60.0:
                            flag = True
                        else:
                            is_anom = False
                            if last_t is not None and not math.isnan(last_t):
                                dt = ti - last_t; dh = hi - last_h
                                if abs(dt) > 5.2 or abs(dh) > 20.0: is_anom = True
                            if not is_anom and count >= 5:
                                idxs = [(head - 1 - j) % 512 for j in range(5)]
                                wt = buf_t[idxs]; wt[0] = ti
                                if np.nanmax(wt) - np.nanmin(wt) <= 0.22: is_anom = True
                            if not is_anom and diurnal_init[hr]:
                                res_t = ti - diurnal_m_t[hr]
                                if res_t > slack_t: sprt_pos_t = max(0.0, sprt_pos_t * 0.95 + (res_t - slack_t))
                                elif res_t < -slack_t: sprt_neg_t = max(0.0, sprt_neg_t * 0.95 + (-res_t - slack_t))
                                else: sprt_pos_t *= 0.55; sprt_neg_t *= 0.55
                                if sprt_pos_t > sprt_thr or sprt_neg_t > sprt_thr: is_anom = True
                            if not is_anom and not math.isnan(scores[i]) and scores[i] > 0.65:
                                is_anom = True

                            if deb > 1:
                                if is_anom:
                                    streak += 1
                                    if streak < deb: is_anom = False
                                else: streak = 0
                            flag = is_anom

                        if not flag and diurnal_init[hr]:
                            diurnal_m_t[hr] += 0.015 * np.clip(ti - diurnal_m_t[hr], -3.0, 3.0)
                        elif not flag:
                            diurnal_m_t[hr] = ti; diurnal_init[hr] = True

                        buf_t[head] = ti; buf_p[head] = pi; buf_h[head] = hi
                        head = (head + 1) % 512
                        if count < 512: count += 1
                        last_t, last_p, last_h = ti, pi, hi

                        if flag and is_gt: TP += 1
                        elif flag and not is_gt: FP += 1
                        elif not flag and is_gt: FN += 1
                        else: TN += 1

                prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0
                rec = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
                spec = TN / (TN + FP) * 100 if (TN + FP) > 0 else 0

                row = f"{deb:>8} {slack_t:>8.1f} {sprt_thr:>9.1f} | {prec:>6.1f}% {rec:>6.1f}% {f1:>6.1f}% {spec:>6.1f}%"
                if prec >= 80 and rec >= 80: print("  *** EXCELLENT *** " + row)
                elif prec >= 50 and rec >= 50: print("  [good] " + row)
                else: print("  " + row)

if __name__ == "__main__":
    run_sweep()
