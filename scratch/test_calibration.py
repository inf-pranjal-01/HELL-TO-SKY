import glob
import math
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class EdgeTester:
    def __init__(self, spike_roc_t=5.2, spike_roc_p=6.0, spike_roc_h=20.0,
                 freeze_w=5, freeze_t=0.30, freeze_p=0.20, freeze_h=0.40,
                 drift_dev_t=3.2, drift_dev_p=5.0, drift_dev_h=20.0,
                 drift_thresh=8.0):
        self.spike_roc_t = spike_roc_t
        self.spike_roc_p = spike_roc_p
        self.spike_roc_h = spike_roc_h
        self.freeze_w = freeze_w
        self.freeze_t = freeze_t
        self.freeze_p = freeze_p
        self.freeze_h = freeze_h
        self.drift_dev_t = drift_dev_t
        self.drift_dev_p = drift_dev_p
        self.drift_dev_h = drift_dev_h
        self.drift_thresh = drift_thresh

        self.buf_t = np.zeros(64, dtype=np.float32)
        self.buf_p = np.zeros(64, dtype=np.float32)
        self.buf_h = np.zeros(64, dtype=np.float32)
        self.head = 0
        self.count = 0
        
        self.raw_t = None
        self.raw_p = None
        self.raw_h = None
        
        self.cusum_pos_t = 0.0
        self.cusum_neg_t = 0.0
        self.cusum_pos_p = 0.0
        self.cusum_neg_p = 0.0
        self.cusum_pos_h = 0.0
        self.cusum_neg_h = 0.0

    def step(self, t, p, h):
        # 1. Electrical / Fail-Low / Bounds
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self.raw_t, self.raw_p, self.raw_h = t, p, h
            return True, "dropout"
        if t <= -30.0 or p <= 150.0 or h <= 0.0:
            self.raw_t, self.raw_p, self.raw_h = t, p, h
            return True, "sensor_fail_low"
        if t < -50.0 or t > 60.0 or p < 850.0 or p > 1085.0 or h < 0.0 or h > 100.0:
            self.raw_t, self.raw_p, self.raw_h = t, p, h
            return True, "physical_bounds"

        # 2. Multivariate Clausius-Clapeyron
        t_dew = t - ((100.0 - h) / 5.0)
        if t_dew > (t + 0.5) or (t > 44.0 and h > 60.0):
            self.raw_t, self.raw_p, self.raw_h = t, p, h
            return True, "multivariate_inconsistency"

        # If previous raw reading exists
        if self.raw_t is not None and not math.isnan(self.raw_t):
            dt_t = abs(t - self.raw_t)
            dt_p = abs(p - self.raw_p)
            dt_h = abs(h - self.raw_h)
            
            # Multivariate same-direction spike
            if (t - self.raw_t) > 2.2 and (h - self.raw_h) > 7.0:
                self.raw_t, self.raw_p, self.raw_h = t, p, h
                return True, "multivariate_inconsistency"

            is_diurnal = ((t > self.raw_t and h < self.raw_h) or (t < self.raw_t and h > self.raw_h)) and (dt_t < 6.5 and dt_h < 30.0)
            if not is_diurnal:
                if dt_t > self.spike_roc_t or dt_p > self.spike_roc_p or dt_h > self.spike_roc_h:
                    self.raw_t, self.raw_p, self.raw_h = t, p, h
                    return True, "spike"

        # Update clean ring buffer
        self.buf_t[self.head] = t
        self.buf_p[self.head] = p
        self.buf_h[self.head] = h
        self.head = (self.head + 1) & 63
        if self.count < 64:
            self.count += 1

        # 3. Frozen check: over last K readings in buffer
        k = self.freeze_w
        if self.count >= k:
            w_t = [self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(k)]
            w_p = [self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(k)]
            w_h = [self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(k)]
            
            r_t = max(w_t) - min(w_t)
            r_p = max(w_p) - min(w_p)
            r_h = max(w_h) - min(w_h)
            
            if r_t <= self.freeze_t or r_p <= self.freeze_p or r_h <= self.freeze_h:
                self.raw_t, self.raw_p, self.raw_h = t, p, h
                return True, "frozen_value"

        # 4. Drift check
        if self.count >= 24:
            mean_t = np.mean([self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(24)])
            mean_p = np.mean([self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(24)])
            mean_h = np.mean([self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(24)])
            
            dev_t = t - mean_t
            dev_p = p - mean_p
            dev_h = h - mean_h
            
            if abs(dev_t) > self.drift_dev_t:
                self.cusum_pos_t = max(0.0, self.cusum_pos_t * 0.90 + (dev_t - self.drift_dev_t))
                self.cusum_neg_t = max(0.0, self.cusum_neg_t * 0.90 + (-dev_t - self.drift_dev_t))
            else:
                self.cusum_pos_t *= 0.70
                self.cusum_neg_t *= 0.70

            if abs(dev_p) > self.drift_dev_p:
                self.cusum_pos_p = max(0.0, self.cusum_pos_p * 0.90 + (dev_p - self.drift_dev_p))
                self.cusum_neg_p = max(0.0, self.cusum_neg_p * 0.90 + (-dev_p - self.drift_dev_p))
            else:
                self.cusum_pos_p *= 0.70
                self.cusum_neg_p *= 0.70

            if abs(dev_h) > self.drift_dev_h:
                self.cusum_pos_h = max(0.0, self.cusum_pos_h * 0.90 + (dev_h - self.drift_dev_h))
                self.cusum_neg_h = max(0.0, self.cusum_neg_h * 0.90 + (-dev_h - self.drift_dev_h))
            else:
                self.cusum_pos_h *= 0.70
                self.cusum_neg_h *= 0.70

            if (self.cusum_pos_t > self.drift_thresh or self.cusum_neg_t > self.drift_thresh or
                self.cusum_pos_p > self.drift_thresh or self.cusum_neg_p > self.drift_thresh or
                self.cusum_pos_h > self.drift_thresh or self.cusum_neg_h > self.drift_thresh):
                self.raw_t, self.raw_p, self.raw_h = t, p, h
                return True, "drift"

        self.raw_t, self.raw_p, self.raw_h = t, p, h
        return False, "normal"


def evaluate_engine(**kwargs):
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
        
        eng = EdgeTester(**kwargs)
        for i in range(len(df)):
            flag, ft = eng.step(t_arr[i], p_arr[i], h_arr[i])
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
    return {
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "specificity": spec,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "fault_stats": fault_stats,
    }

if __name__ == "__main__":
    res = evaluate_engine()
    print(f"Precision: {res['precision']:.2f}% | Recall: {res['recall']:.2f}% | F1: {res['f1']:.2f}% | Specificity: {res['specificity']:.2f}%")
    print(f"TP={res['tp']}, FP={res['fp']}, FN={res['fn']}, TN={res['tn']}")
    for k, v in sorted(res["fault_stats"].items()):
        c = v["detected"] / v["injected"] * 100
        print(f"  {k:<26}: {v['detected']}/{v['injected']} ({c:.1f}%)")
