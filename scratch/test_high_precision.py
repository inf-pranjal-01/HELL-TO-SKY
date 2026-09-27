import glob
import math
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class HighPrecisionEdgeEngine:
    def __init__(self, roc_t=5.8, roc_p=7.5, roc_h=24.0,
                 freeze_len=6, freeze_t=0.08, freeze_p=0.06, freeze_h=0.12,
                 drift_threshold=28.0, drift_slack=4.0):
        self.roc_t = roc_t
        self.roc_p = roc_p
        self.roc_h = roc_h
        self.freeze_len = freeze_len
        self.freeze_t = freeze_t
        self.freeze_p = freeze_p
        self.freeze_h = freeze_h
        self.drift_threshold = drift_threshold
        self.drift_slack = drift_slack

        # 512-sample circular buffer
        self.buf_t = np.zeros(512, dtype=np.float32)
        self.buf_p = np.zeros(512, dtype=np.float32)
        self.buf_h = np.zeros(512, dtype=np.float32)
        self.head = 0
        self.count = 0

        # Rolling 24-hour diurnal table (exponentially decaying daily baseline)
        self.diurnal_mean_t = np.zeros(24, dtype=np.float32)
        self.diurnal_mean_p = np.zeros(24, dtype=np.float32)
        self.diurnal_mean_h = np.zeros(24, dtype=np.float32)
        self.diurnal_init = np.zeros(24, dtype=bool)

        self.last_t = None
        self.last_p = None
        self.last_h = None

        self.sprt_pos_t = 0.0; self.sprt_neg_t = 0.0
        self.sprt_pos_p = 0.0; self.sprt_neg_p = 0.0
        self.sprt_pos_h = 0.0; self.sprt_neg_h = 0.0

    def step(self, t, p, h, hour_idx):
        # 1. Tier 0: Electrical / Fail-Low / Bounds
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "dropout"
        if t <= -35.0 or p <= 150.0 or h <= 0.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "sensor_fail_low"
        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "physical_bounds"

        # 2. Tier 4: Psychrometric Invariants (Dewpoint & CC Limit)
        t_dew = t - ((100.0 - h) / 5.0)
        if t_dew > (t + 0.5) or (t > 44.0 and h > 70.0):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "multivariate_inconsistency"

        is_anom = False
        ft = "normal"

        # 3. Tier 1: Step ROC Spikes with Diurnal Coupling
        if self.last_t is not None and not math.isnan(self.last_t):
            dt_t = abs(t - self.last_t)
            dt_p = abs(p - self.last_p)
            dt_h = abs(h - self.last_h)

            if (t - self.last_t) > 2.5 and (h - self.last_h) > 10.0:
                is_anom, ft = True, "multivariate_inconsistency"
            else:
                is_diurnal = ((t > self.last_t and h < self.last_h) or (t < self.last_t and h > self.last_h)) and (dt_t < 6.5 and dt_h < 30.0)
                if not is_diurnal:
                    if dt_t > self.roc_t or dt_p > self.roc_p or dt_h > self.roc_h:
                        is_anom, ft = True, "spike"

        # 4. Tier 2: Freeze Check
        k = self.freeze_len
        if not is_anom and self.count >= k:
            w_t = [self.buf_t[(self.head + 512 - 1 - j) & 511] for j in range(k - 1)] + [t]
            w_p = [self.buf_p[(self.head + 512 - 1 - j) & 511] for j in range(k - 1)] + [p]
            w_h = [self.buf_h[(self.head + 512 - 1 - j) & 511] for j in range(k - 1)] + [h]

            r_t = max(w_t) - min(w_t)
            r_p = max(w_p) - min(w_p)
            r_h = max(w_h) - min(w_h)

            if r_t <= self.freeze_t or r_p <= self.freeze_p or r_h <= self.freeze_h:
                is_anom, ft = True, "frozen_value"

        # 5. Tier 3: Leaky Adaptive Diurnal SPRT Drift Filter
        hr = hour_idx % 24
        if not is_anom and self.diurnal_init[hr]:
            base_t = self.diurnal_mean_t[hr]
            base_p = self.diurnal_mean_p[hr]
            base_h = self.diurnal_mean_h[hr]

            dev_t = t - base_t
            dev_p = p - base_p
            dev_h = h - base_h

            if abs(dev_t) > self.drift_slack:
                self.sprt_pos_t = max(0.0, self.sprt_pos_t * 0.90 + (dev_t - self.drift_slack))
                self.sprt_neg_t = max(0.0, self.sprt_neg_t * 0.90 + (-dev_t - self.drift_slack))
            else:
                self.sprt_pos_t *= 0.50
                self.sprt_neg_t *= 0.50

            if abs(dev_p) > 5.5:
                self.sprt_pos_p = max(0.0, self.sprt_pos_p * 0.90 + (dev_p - 5.5))
                self.sprt_neg_p = max(0.0, self.sprt_neg_p * 0.90 + (-dev_p - 5.5))
            else:
                self.sprt_pos_p *= 0.50
                self.sprt_neg_p *= 0.50

            if abs(dev_h) > 22.0:
                self.sprt_pos_h = max(0.0, self.sprt_pos_h * 0.90 + (dev_h - 22.0))
                self.sprt_neg_h = max(0.0, self.sprt_neg_h * 0.90 + (-dev_h - 22.0))
            else:
                self.sprt_pos_h *= 0.50
                self.sprt_neg_h *= 0.50

            if (self.sprt_pos_t > self.drift_threshold or self.sprt_neg_t > self.drift_threshold or
                self.sprt_pos_p > self.drift_threshold or self.sprt_neg_p > self.drift_threshold or
                self.sprt_pos_h > self.drift_threshold or self.sprt_neg_h > self.drift_threshold):
                is_anom, ft = True, "drift"

        # Leaky update of diurnal baseline
        if not is_anom:
            if not self.diurnal_init[hr]:
                self.diurnal_mean_t[hr] = t
                self.diurnal_mean_p[hr] = p
                self.diurnal_mean_h[hr] = h
                self.diurnal_init[hr] = True
            else:
                self.diurnal_mean_t[hr] = 0.85 * self.diurnal_mean_t[hr] + 0.15 * t
                self.diurnal_mean_p[hr] = 0.85 * self.diurnal_mean_p[hr] + 0.15 * p
                self.diurnal_mean_h[hr] = 0.85 * self.diurnal_mean_h[hr] + 0.15 * h

        # Update 512-slot buffer
        self.buf_t[self.head] = t
        self.buf_p[self.head] = p
        self.buf_h[self.head] = h
        self.head = (self.head + 1) & 511
        if self.count < 512:
            self.count += 1
        self.last_t, self.last_p, self.last_h = t, p, h

        return is_anom, ft


def main():
    tp, fp, fn, tn = 0, 0, 0, 0
    fault_stats = {}
    for f in files:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t_arr = df["temperature_c"].to_numpy(dtype=np.float64)
        p_arr = df["pressure_hpa"].to_numpy(dtype=np.float64)
        h_arr = df["humidity_pct"].to_numpy(dtype=np.float64)
        gt_anom = df["is_anomaly"].fillna(False).to_numpy(dtype=bool)
        gt_type = df["fault_type"].fillna("normal").to_numpy(dtype=str)

        eng = HighPrecisionEdgeEngine()
        for i in range(len(df)):
            flag, ft = eng.step(t_arr[i], p_arr[i], h_arr[i], i % 24)
            is_gt = gt_anom[i]
            gt_t = gt_type[i]

            if gt_t != "normal":
                if gt_t not in fault_stats:
                    fault_stats[gt_t] = {"injected": 0, "detected": 0}
                fault_stats[gt_t]["injected"] += 1
                if flag:
                    fault_stats[gt_t]["detected"] += 1

            if flag and is_gt: tp += 1
            elif flag and not is_gt: fp += 1
            elif not flag and is_gt: fn += 1
            else: tn += 1

    prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    spec = tn / (tn + fp) * 100 if (tn + fp) > 0 else 0
    print(f"Precision: {prec:.2f}% | Recall: {rec:.2f}% | F1: {f1:.2f}% | Specificity: {spec:.2f}%")
    print(f"TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    for k, v in sorted(fault_stats.items()):
        c = v["detected"] / v["injected"] * 100
        print(f"  {k:<28}: {v['detected']}/{v['injected']} ({c:.1f}%)")

if __name__ == "__main__":
    main()
