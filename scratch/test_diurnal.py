import glob
import math
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class DiurnalHarmonicEdgeEngine:
    def __init__(self):
        # 24-slot diurnal hour baselines (O(1) memory: 24*3*4 = 288 bytes)
        self.hourly_sum_t = np.zeros(24, dtype=np.float32)
        self.hourly_count_t = np.zeros(24, dtype=np.int32)
        self.hourly_sum_p = np.zeros(24, dtype=np.float32)
        self.hourly_count_p = np.zeros(24, dtype=np.int32)
        self.hourly_sum_h = np.zeros(24, dtype=np.float32)
        self.hourly_count_h = np.zeros(24, dtype=np.int32)

        self.buf_t = np.zeros(64, dtype=np.float32)
        self.buf_p = np.zeros(64, dtype=np.float32)
        self.buf_h = np.zeros(64, dtype=np.float32)
        self.head = 0
        self.count = 0
        
        self.last_t = None
        self.last_p = None
        self.last_h = None
        
        self.sprt_pos_t = 0.0; self.sprt_neg_t = 0.0
        self.sprt_pos_p = 0.0; self.sprt_neg_p = 0.0
        self.sprt_pos_h = 0.0; self.sprt_neg_h = 0.0

    def step(self, t, p, h, hour_idx):
        # Tier 0: Hard limits
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "dropout"
        if t <= -35.0 or p <= 150.0 or h <= 0.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "sensor_fail_low"
        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "physical_bounds"

        # Tier 3: Clausius Clapeyron
        t_dew = t - ((100.0 - h) / 5.0)
        if t_dew > (t + 0.5) or (t > 44.0 and h > 60.0):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "multivariate_inconsistency"

        is_anom = False
        ft = "normal"

        # Step ROC Spike
        if self.last_t is not None and not math.isnan(self.last_t):
            dt_t = abs(t - self.last_t)
            dt_p = abs(p - self.last_p)
            dt_h = abs(h - self.last_h)

            if (t - self.last_t) > 2.0 and (h - self.last_h) > 6.5:
                is_anom, ft = True, "multivariate_inconsistency"
            else:
                is_diurnal = ((t > self.last_t and h < self.last_h) or (t < self.last_t and h > self.last_h)) and (dt_t < 6.5 and dt_h < 30.0)
                if not is_diurnal:
                    if dt_t > 5.5 or dt_p > 7.0 or dt_h > 22.0:
                        is_anom, ft = True, "spike"

        # Freeze
        if not is_anom and self.count >= 5:
            w_t = [self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(4)] + [t]
            w_p = [self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(4)] + [p]
            w_h = [self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(4)] + [h]
            if (max(w_t) - min(w_t)) <= 0.25 or (max(w_p) - min(w_p)) <= 0.15 or (max(w_h) - min(w_h)) <= 0.35:
                is_anom, ft = True, "frozen_value"

        # Drift via Diurnal Residual
        hr = hour_idx % 24
        if not is_anom and self.hourly_count_t[hr] >= 3:
            hr_mean_t = self.hourly_sum_t[hr] / self.hourly_count_t[hr]
            hr_mean_p = self.hourly_sum_p[hr] / self.hourly_count_p[hr]
            hr_mean_h = self.hourly_sum_h[hr] / self.hourly_count_h[hr]
            
            dev_t = t - hr_mean_t
            dev_p = p - hr_mean_p
            dev_h = h - hr_mean_h
            
            if abs(dev_t) > 3.0:
                self.sprt_pos_t = max(0.0, self.sprt_pos_t * 0.90 + (dev_t - 3.0))
                self.sprt_neg_t = max(0.0, self.sprt_neg_t * 0.90 + (-dev_t - 3.0))
            else:
                self.sprt_pos_t *= 0.70; self.sprt_neg_t *= 0.70

            if abs(dev_p) > 4.5:
                self.sprt_pos_p = max(0.0, self.sprt_pos_p * 0.90 + (dev_p - 4.5))
                self.sprt_neg_p = max(0.0, self.sprt_neg_p * 0.90 + (-dev_p - 4.5))
            else:
                self.sprt_pos_p *= 0.70; self.sprt_neg_p *= 0.70

            if abs(dev_h) > 18.0:
                self.sprt_pos_h = max(0.0, self.sprt_pos_h * 0.90 + (dev_h - 18.0))
                self.sprt_neg_h = max(0.0, self.sprt_neg_h * 0.90 + (-dev_h - 18.0))
            else:
                self.sprt_pos_h *= 0.70; self.sprt_neg_h *= 0.70

            if (self.sprt_pos_t > 12.0 or self.sprt_neg_t > 12.0 or
                self.sprt_pos_p > 12.0 or self.sprt_neg_p > 12.0 or
                self.sprt_pos_h > 12.0 or self.sprt_neg_h > 12.0):
                is_anom, ft = True, "drift"

        # Commit to hourly baseline only if not anomalous
        if not is_anom:
            self.hourly_sum_t[hr] += t; self.hourly_count_t[hr] += 1
            self.hourly_sum_p[hr] += p; self.hourly_count_p[hr] += 1
            self.hourly_sum_h[hr] += h; self.hourly_count_h[hr] += 1

        self.buf_t[self.head] = t
        self.buf_p[self.head] = p
        self.buf_h[self.head] = h
        self.head = (self.head + 1) & 63
        if self.count < 64: self.count += 1
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
        
        eng = DiurnalHarmonicEdgeEngine()
        for i in range(len(df)):
            flag, ft = eng.step(t_arr[i], p_arr[i], h_arr[i], i % 24)
            is_gt = gt_anom[i]
            gt_t = gt_type[i]
            
            if gt_t != "normal":
                if gt_t not in fault_stats: fault_stats[gt_t] = {"injected": 0, "detected": 0}
                fault_stats[gt_t]["injected"] += 1
                if flag: fault_stats[gt_t]["detected"] += 1
                
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
