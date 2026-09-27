"""
SkyGuard Edge AI -- Standalone TinyML Isolation Forest Evaluation
==================================================================
Evaluates the performance of the quantized TinyML Isolation Forest ALONE
(without physical rules, without SPRT, without psychrometric invariants).
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
    clf = IsolationForest(n_estimators=30, max_samples=256, contamination=0.02, random_state=42, n_jobs=-1)
    clf.fit(X)
    return clf

def evaluate_tinyml_alone(clf, file_list, thresh=0.58):
    TP = FP = FN = TN = 0
    fault_stats = {}
    total_obs = 0

    for f in file_list:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t = df["temperature_c"].to_numpy(float)
        p = df["pressure_hpa"].to_numpy(float)
        h = df["humidity_pct"].to_numpy(float)
        gt = df["is_anomaly"].fillna(False).to_numpy(bool)
        gft = df["fault_type"].fillna("normal").to_numpy(str)
        N = len(t)
        total_obs += N

        F = _feat_batch(t, p, h)
        mask = ~np.isnan(F).any(axis=1)
        scores = np.full(N, np.nan, dtype=np.float32)
        if mask.any():
            scores[mask] = -clf.score_samples(F[mask])

        for i in range(N):
            flag = False
            if not math.isnan(scores[i]) and scores[i] > thresh:
                flag = True
            
            is_gt = gt[i]; g = gft[i]

            if g != "normal":
                if g not in fault_stats: fault_stats[g] = [0, 0]
                fault_stats[g][0] += 1
                if flag: fault_stats[g][1] += 1

            if flag and is_gt: TP += 1
            elif flag and not is_gt: FP += 1
            elif not flag and is_gt: FN += 1
            else: TN += 1

    prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0.0
    rec = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    spec = TN / (TN + FP) * 100 if (TN + FP) > 0 else 0.0
    return prec, rec, f1, spec, TP, FP, FN, TN, fault_stats, total_obs

def main():
    print("Training Standalone TinyML Isolation Forest (30 trees)...")
    clf = train_iforest()

    print("\n" + "=" * 85)
    print("      SKYGUARD EDGE AI -- STANDALONE TINYML-ONLY BENCHMARK REPORT")
    print("      (Evaluating Isolation Forest ALONE without physical rules or SPRT)")
    print("=" * 85)

    print("\n--- ALL 28 STATIONS (60,480 OBSERVATIONS) ---")
    p28, r28, f28, s28, tp28, fp28, fn28, tn28, fc28, n28 = evaluate_tinyml_alone(clf, FILES, thresh=0.58)
    print(f"  • Precision (PPV)    : {p28:.2f}%")
    print(f"  • Recall (TPR)       : {r28:.2f}%")
    print(f"  • F1-Score           : {f28:.2f}%")
    print(f"  • Specificity (TNR)  : {s28:.2f}%")
    print(f"  • Confusion Matrix   : TP={tp28:,} | FP={fp28:,} | FN={fn28:,} | TN={tn28:,}")

    print("\n--- 7 FAULTED CENTER STATIONS ---")
    p7, r7, f7, s7, tp7, fp7, fn7, tn7, fc7, n7 = evaluate_tinyml_alone(clf, CENTER_FILES, thresh=0.58)
    print(f"  • Precision (PPV)    : {p7:.2f}%")
    print(f"  • Recall (TPR)       : {r7:.2f}%")
    print(f"  • F1-Score           : {f7:.2f}%")
    print(f"  • Specificity (TNR)  : {s7:.2f}%")
    print(f"  • Confusion Matrix   : TP={tp7:,} | FP={fp7:,} | FN={fn7:,} | TN={tn7:,}")
    print("\n  Granular Catch Rates of TinyML Model Alone Across Fault Classes:")
    for k, v in sorted(fc7.items(), key=lambda x: -x[1][0]):
        c_rate = v[1] / max(v[0], 1) * 100
        print(f"    - {k:<28}: {v[1]:>4}/{v[0]:>4} ({c_rate:>5.1f}%)")

    print("\n" + "=" * 85)
    print("      THRESH SWEEP FOR STANDALONE TINYML MODEL")
    print("=" * 85)
    print(f"{'THRESH':>8} | {'Prec (28st)':>12} {'Rec (28st)':>12} {'F1 (28st)':>12} | {'Prec (7st)':>12} {'Rec (7st)':>12} {'F1 (7st)':>12}")
    print("-" * 85)
    for th in [0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70]:
        p28, r28, f28, _, _, _, _, _, _, _ = evaluate_tinyml_alone(clf, FILES, thresh=th)
        p7, r7, f7, _, _, _, _, _, _, _ = evaluate_tinyml_alone(clf, CENTER_FILES, thresh=th)
        print(f"{th:>8.2f} | {p28:>11.2f}% {r28:>11.2f}% {f28:>11.2f}% | {p7:>11.2f}% {r7:>11.2f}% {f7:>11.2f}%")
    print("=" * 85)

if __name__ == "__main__":
    main()
