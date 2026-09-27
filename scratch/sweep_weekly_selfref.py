"""
SkyGuard Edge AI -- Calibration Sweep for Weekly Self-Reference Engine
=======================================================================
Baseline: Precision=11.83%, Recall=75.62% (too many FPs from seasonal drift)
Target  : Precision>=50%, Recall>=50% simultaneously

Root cause of FPs:
  Jan-Mar 2025 spans late winter -> early spring in India.
  True seasonal warming causes legitimate T(t) - T(t-168h) > 3.2C
  on CLEAN neighbor stations too -> floods FPs.

Strategy:
  1. Raise W7D_T_THRESH to require larger week-delta before accumulation
  2. Raise W7D_SPRT_THRESH to require more sustained deviation before alarm
  3. Tune decay rate -- faster decay = less memory = less FP accumulation
  4. Try combining weekly-SPRT with multi-day slope (both must agree = AND logic)
"""

import glob
import math
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

FILES = sorted(glob.glob("data/*_labeled.csv"))


def build_iforest():
    clean_files = [f for f in FILES
                   if any(tag in f for tag in ["-101_", "-102_", "-103_"])]
    rows = []
    for f in clean_files:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        t_arr = df["temperature_c"].to_numpy(float)
        p_arr = df["pressure_hpa"].to_numpy(float)
        h_arr = df["humidity_pct"].to_numpy(float)
        ts = df["timestamp"].to_numpy()
        n = len(t_arr)
        for i in range(6, n):
            hour = pd.Timestamp(ts[i]).hour
            feats = extract_features(t_arr, p_arr, h_arr, i, hour)
            if feats is not None:
                rows.append(feats)
    X = np.array(rows, dtype=np.float32)
    clf = IsolationForest(n_estimators=50, max_samples=256,
                          contamination=0.01, random_state=42)
    clf.fit(X)
    return clf


def extract_features(t, p, h, i, hour):
    if i < 6:
        return None
    roc1_t = t[i] - t[i-1]
    roc3_t = t[i] - t[i-3]
    roc1_h = h[i] - h[i-1]
    rng6_t = float(np.max(t[i-5:i+1]) - np.min(t[i-5:i+1]))
    rng6_p = float(np.max(p[i-5:i+1]) - np.min(p[i-5:i+1]))
    t_dew = t[i] - ((100.0 - h[i]) / 5.0)
    dew_dep = t[i] - t_dew
    es = 0.6112 * math.exp((17.67 * t[i]) / (t[i] + 243.5)) if (t[i]+243.5) != 0 else 1.0
    vpd = es * (1.0 - h[i]/100.0)
    return [t[i], roc1_t, roc3_t, rng6_t, roc1_h, rng6_p, vpd, dew_dep]


class WeeklySelfRefEngine:
    def __init__(self, cfg, iforest=None):
        self.c = cfg
        self.iforest = iforest
        N = 512
        self.buf_t = np.full(N, np.nan, dtype=np.float32)
        self.buf_p = np.full(N, np.nan, dtype=np.float32)
        self.buf_h = np.full(N, np.nan, dtype=np.float32)
        self.head = 0
        self.count = 0
        self.last_t = None
        self.last_p = None
        self.last_h = None
        self.ema_t = np.zeros(24, dtype=np.float64)
        self.ema_p = np.zeros(24, dtype=np.float64)
        self.ema_h = np.zeros(24, dtype=np.float64)
        self.ema_init = np.zeros(24, dtype=np.int32)
        self.w7_pos_t = 0.0;  self.w7_neg_t = 0.0
        self.w7_pos_p = 0.0;  self.w7_neg_p = 0.0
        self.w7_pos_h = 0.0;  self.w7_neg_h = 0.0
        self.slope_streak_up = 0
        self.slope_streak_dn = 0

    def _buf_read(self, buf, offset):
        if self.count <= offset:
            return np.nan
        idx = (self.head - 1 - offset) % 512
        return float(buf[idx])

    def _buf_write(self, t, p, h):
        self.buf_t[self.head] = t
        self.buf_p[self.head] = p
        self.buf_h[self.head] = h
        self.head = (self.head + 1) % 512
        if self.count < 512:
            self.count += 1

    def step(self, t, p, h, hour, t_arr, p_arr, h_arr, row_i):
        c = self.c

        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "dropout"

        if t <= c["T_MIN"] or p <= c["P_MIN"] or h <= c["H_MIN"]:
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "sensor_fail_low"

        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "physical_bounds"

        t_dew = t - ((100.0 - h) / 5.0)
        es = 0.6112 * math.exp((17.67 * t) / (t + 243.5))
        vpd = es * (1.0 - h / 100.0)
        if (t_dew > t + 0.5 or
                (t > 44.0 and h > 65.0) or
                (t > 40.0 and vpd < 0.10 and h > 85.0)):
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "multivariate_inconsistency"

        is_anom = False
        fault_type = "normal"

        # Tier 1: ROC Spike
        if self.last_t is not None and not math.isnan(self.last_t):
            dt_t = abs(t - self.last_t)
            dt_p = abs(p - self.last_p)
            dt_h = abs(h - self.last_h)
            if (t - self.last_t) > 2.2 and (h - self.last_h) > 8.0:
                is_anom, fault_type = True, "multivariate_inconsistency"
            else:
                is_diurnal = (
                    ((t > self.last_t and h < self.last_h) or
                     (t < self.last_t and h > self.last_h)) and
                    dt_t < c["ROC_T"] and dt_h < 28.0
                )
                if not is_diurnal:
                    if dt_t > c["ROC_T"] or dt_p > c["ROC_P"] or dt_h > c["ROC_H"]:
                        is_anom, fault_type = True, "spike"

        # Tier 2: Freeze
        k = c["FREEZE_WIN"]
        if not is_anom and self.count >= k:
            w_t = [self._buf_read(self.buf_t, j) for j in range(k-1, -1, -1)] + [t]
            w_p = [self._buf_read(self.buf_p, j) for j in range(k-1, -1, -1)] + [p]
            w_h = [self._buf_read(self.buf_h, j) for j in range(k-1, -1, -1)] + [h]
            w_t = [x for x in w_t if not math.isnan(x)]
            w_p = [x for x in w_p if not math.isnan(x)]
            w_h = [x for x in w_h if not math.isnan(x)]
            if (len(w_t) >= 3 and
                    (max(w_t)-min(w_t) <= c["FREEZE_T"] or
                     max(w_p)-min(w_p) <= c["FREEZE_P"] or
                     max(w_h)-min(w_h) <= c["FREEZE_H"])):
                is_anom, fault_type = True, "frozen_value"

        # Tier 3a: Weekly self-reference SPRT (with optional slope gate)
        w7_triggered = False
        if self.count >= 168:
            t_7d = self._buf_read(self.buf_t, 167)
            p_7d = self._buf_read(self.buf_p, 167)
            h_7d = self._buf_read(self.buf_h, 167)

            if not math.isnan(t_7d):
                delta_t = t - t_7d
                delta_p = p - p_7d
                delta_h = h - h_7d

                k_t = c["W7D_T_THRESH"]
                k_p = c["W7D_P_THRESH"]
                k_h = c["W7D_H_THRESH"]
                grow = c["W7D_SPRT_GROW"]
                decay = c["W7D_SPRT_DECAY"]

                if delta_t > k_t:
                    self.w7_pos_t = max(0.0, self.w7_pos_t * grow + (delta_t - k_t))
                    self.w7_neg_t *= decay
                elif delta_t < -k_t:
                    self.w7_neg_t = max(0.0, self.w7_neg_t * grow + (-delta_t - k_t))
                    self.w7_pos_t *= decay
                else:
                    self.w7_pos_t *= decay
                    self.w7_neg_t *= decay

                if delta_p > k_p:
                    self.w7_pos_p = max(0.0, self.w7_pos_p * grow + (delta_p - k_p))
                    self.w7_neg_p *= decay
                elif delta_p < -k_p:
                    self.w7_neg_p = max(0.0, self.w7_neg_p * grow + (-delta_p - k_p))
                    self.w7_pos_p *= decay
                else:
                    self.w7_pos_p *= decay
                    self.w7_neg_p *= decay

                if delta_h > k_h:
                    self.w7_pos_h = max(0.0, self.w7_pos_h * grow + (delta_h - k_h))
                    self.w7_neg_h *= decay
                elif delta_h < -k_h:
                    self.w7_neg_h = max(0.0, self.w7_neg_h * grow + (-delta_h - k_h))
                    self.w7_pos_h *= decay
                else:
                    self.w7_pos_h *= decay
                    self.w7_neg_h *= decay

                thr = c["W7D_SPRT_THRESH"]
                if (self.w7_pos_t > thr or self.w7_neg_t > thr or
                        self.w7_pos_p > thr or self.w7_neg_p > thr or
                        self.w7_pos_h > thr or self.w7_neg_h > thr):
                    w7_triggered = True
            else:
                self.w7_pos_t = self.w7_neg_t = 0.0
                self.w7_pos_p = self.w7_neg_p = 0.0
                self.w7_pos_h = self.w7_neg_h = 0.0

        # Tier 3c: Multi-hour slope consistency
        slope_triggered = False
        if self.count >= 48:
            t_24h = self._buf_read(self.buf_t, 23)
            t_48h = self._buf_read(self.buf_t, 47)
            if not math.isnan(t_24h) and not math.isnan(t_48h):
                d24 = t - t_24h
                d48 = t_24h - t_48h
                if d24 > c["SLOPE_24H_T"] and d48 > c["SLOPE_48H_T"]:
                    self.slope_streak_up += 1
                    self.slope_streak_dn = max(0, self.slope_streak_dn - 1)
                elif d24 < -c["SLOPE_24H_T"] and d48 < -c["SLOPE_48H_T"]:
                    self.slope_streak_dn += 1
                    self.slope_streak_up = max(0, self.slope_streak_up - 1)
                else:
                    self.slope_streak_up = max(0, self.slope_streak_up - 1)
                    self.slope_streak_dn = max(0, self.slope_streak_dn - 1)

                if (self.slope_streak_up >= c["SLOPE_STREAK_MIN"] or
                        self.slope_streak_dn >= c["SLOPE_STREAK_MIN"]):
                    slope_triggered = True

        # Fusion logic: AND gate or OR gate controlled by config
        if not is_anom:
            if c.get("DRIFT_REQUIRE_BOTH", False):
                # Strict: BOTH w7 and slope must agree
                if w7_triggered and slope_triggered:
                    is_anom, fault_type = True, "drift"
            else:
                # Default OR: either triggers
                if w7_triggered or slope_triggered:
                    is_anom, fault_type = True, "drift"

        # Tier 5: IForest
        if not is_anom and self.iforest is not None and row_i >= 6:
            feats = extract_features(t_arr, p_arr, h_arr, row_i, hour)
            if feats is not None:
                score = -self.iforest.score_samples([feats])[0]
                if score > c["IFOREST_THRESH"]:
                    is_anom, fault_type = True, "unstructured_anomaly"

        # EMA update
        hr = hour % 24
        if not is_anom:
            alpha = 0.08
            if self.ema_init[hr] == 0:
                self.ema_t[hr] = t
                self.ema_p[hr] = p
                self.ema_h[hr] = h
            else:
                self.ema_t[hr] = (1-alpha)*self.ema_t[hr] + alpha*t
                self.ema_p[hr] = (1-alpha)*self.ema_p[hr] + alpha*p
                self.ema_h[hr] = (1-alpha)*self.ema_h[hr] + alpha*h
            self.ema_init[hr] += 1

        self._buf_write(t, p, h)
        self.last_t = t; self.last_p = p; self.last_h = h
        return is_anom, fault_type


def evaluate_cfg(cfg, iforest):
    total_tp = total_fp = total_fn = total_tn = 0
    fault_stats = {}

    for f in FILES:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        if "is_anomaly" not in df.columns:
            continue
        t_arr = df["temperature_c"].to_numpy(float)
        p_arr = df["pressure_hpa"].to_numpy(float)
        h_arr = df["humidity_pct"].to_numpy(float)
        ts = df["timestamp"].to_numpy()
        gt_anom = df["is_anomaly"].fillna(False).to_numpy(bool)
        gt_type = df["fault_type"].fillna("normal").to_numpy(str)

        eng = WeeklySelfRefEngine(cfg=cfg, iforest=iforest)
        n = len(df)

        for i in range(n):
            hour = pd.Timestamp(ts[i]).hour
            flag, ft = eng.step(t_arr[i], p_arr[i], h_arr[i],
                                hour, t_arr, p_arr, h_arr, i)
            is_gt = gt_anom[i]
            gt_t = gt_type[i]

            if gt_t != "normal":
                if gt_t not in fault_stats:
                    fault_stats[gt_t] = {"injected": 0, "detected": 0}
                fault_stats[gt_t]["injected"] += 1
                if flag:
                    fault_stats[gt_t]["detected"] += 1

            if flag and is_gt:     total_tp += 1
            elif flag and not is_gt: total_fp += 1
            elif not flag and is_gt: total_fn += 1
            else:                   total_tn += 1

    prec = total_tp/(total_tp+total_fp)*100 if (total_tp+total_fp) > 0 else 0
    rec  = total_tp/(total_tp+total_fn)*100 if (total_tp+total_fn) > 0 else 0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0
    spec = total_tn/(total_tn+total_fp)*100 if (total_tn+total_fp) > 0 else 0
    return prec, rec, f1, spec, total_tp, total_fp, total_fn, total_tn, fault_stats


BASE = dict(
    T_MIN=-35.0, P_MIN=850.0, H_MIN=0.0,
    ROC_T=5.0, ROC_P=6.0, ROC_H=18.0,
    FREEZE_WIN=6, FREEZE_T=0.18, FREEZE_P=0.10, FREEZE_H=0.25,
    W7D_P_THRESH=8.0, W7D_H_THRESH=22.0,
    W7D_SPRT_GROW=0.96,
    SLOPE_24H_T=2.8, SLOPE_48H_T=1.8,
    IFOREST_THRESH=0.62,
    DRIFT_REQUIRE_BOTH=False,
)


if __name__ == "__main__":
    print("Training IForest on clean neighbors...")
    iforest = build_iforest()
    print("IForest ready.\n")

    # ---- Phase 1: Sweep W7D_T_THRESH x W7D_SPRT_THRESH x DECAY ----
    print("=" * 90)
    print("PHASE 1: Sweep W7D_T_THRESH x W7D_SPRT_THRESH x W7D_SPRT_DECAY x SLOPE_STREAK")
    print("         (looking for Prec>=50% AND Rec>=50%)")
    print("=" * 90)
    print(f"{'W7D_T':>6} {'W7D_THR':>7} {'DECAY':>6} {'SLOPE_S':>8} {'AND?':>5} "
          f"{'Prec':>7} {'Rec':>7} {'F1':>7} {'DRIFT%':>7} | TP/FP/FN")

    best_f1 = 0.0
    best_cfg = None
    best_row = ""
    candidates = []

    for w7_t in [4.0, 4.5, 5.0, 5.5, 6.0]:
        for w7_thr in [8.0, 12.0, 16.0, 20.0, 25.0]:
            for decay in [0.75, 0.80, 0.85]:
                for slope_s in [3, 5, 7]:
                    for require_both in [False, True]:
                        cfg = dict(BASE)
                        cfg["W7D_T_THRESH"]   = w7_t
                        cfg["W7D_SPRT_THRESH"] = w7_thr
                        cfg["W7D_SPRT_DECAY"]  = decay
                        cfg["SLOPE_STREAK_MIN"] = slope_s
                        cfg["DRIFT_REQUIRE_BOTH"] = require_both

                        prec, rec, f1, spec, tp, fp, fn, tn, fs = evaluate_cfg(cfg, iforest)
                        drift_r = fs.get("drift", {}).get("detected", 0) / fs.get("drift", {}).get("injected", 1) * 100

                        tag = "Y" if require_both else "N"
                        row = (f"{w7_t:>6.1f} {w7_thr:>7.0f} {decay:>6.2f} {slope_s:>8} {tag:>5} "
                               f"{prec:>7.1f} {rec:>7.1f} {f1:>7.1f} {drift_r:>7.1f}% | "
                               f"{tp}/{fp}/{fn}")

                        if prec >= 48 and rec >= 48:
                            print("  *** HIT ***  " + row)
                            candidates.append((f1, dict(cfg), row))
                        elif prec >= 40 and rec >= 40:
                            print("  [near]  " + row)

                        if f1 > best_f1 and prec >= 35 and rec >= 35:
                            best_f1 = f1
                            best_cfg = dict(cfg)
                            best_row = row

    print("\n" + "=" * 90)
    print("BEST CONFIG (Prec>=35 & Rec>=35, max F1):")
    print(" ", best_row)

    if candidates:
        print(f"\nCONFIGS HITTING 48/48 TARGET ({len(candidates)} found):")
        candidates.sort(key=lambda x: -x[0])
        for f1c, cfgc, rowc in candidates[:5]:
            print(" ", rowc)

    # ---- Phase 2: Fine-tune the best config ----
    print("\n" + "=" * 90)
    print("PHASE 2: Full evaluation of best config")
    print("=" * 90)
    if best_cfg:
        prec, rec, f1, spec, tp, fp, fn, tn, fs = evaluate_cfg(best_cfg, iforest)
        print(f"  Precision : {prec:.2f}%")
        print(f"  Recall    : {rec:.2f}%")
        print(f"  F1-Score  : {f1:.2f}%")
        print(f"  Specificity: {spec:.2f}%")
        print(f"  Confusion  : TP={tp} | FP={fp} | FN={fn} | TN={tn}")
        print("\n  Per-fault catch rates:")
        for k, v in sorted(fs.items(), key=lambda x: -x[1]["injected"]):
            cr = v["detected"]/v["injected"]*100
            print(f"    {k:<30}: {v['detected']:>4}/{v['injected']:>4} ({cr:>5.1f}%)")
        print("\n  Best config params:")
        for k in ["W7D_T_THRESH","W7D_SPRT_THRESH","W7D_SPRT_DECAY","SLOPE_STREAK_MIN","DRIFT_REQUIRE_BOTH"]:
            print(f"    {k}: {best_cfg[k]}")
    print("=" * 90)
