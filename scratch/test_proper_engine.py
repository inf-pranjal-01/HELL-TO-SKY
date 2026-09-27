import glob
import math
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class ProperDualBufferEngine:
    def __init__(self, spike_roc_t=5.0, spike_roc_p=6.0, spike_roc_h=20.0,
                 freeze_w=5, freeze_r_t=0.25, freeze_r_p=0.15, freeze_r_h=0.35,
                 drift_w=24, drift_t_slack=3.5, drift_p_slack=5.0, drift_h_slack=20.0,
                 drift_thresh=25.0):
        self.spike_roc_t = spike_roc_t
        self.spike_roc_p = spike_roc_p
        self.spike_roc_h = spike_roc_h
        self.freeze_w = freeze_w
        self.freeze_r_t = freeze_r_t
        self.freeze_r_p = freeze_r_p
        self.freeze_r_h = freeze_r_h
        self.drift_w = drift_w
        self.drift_t_slack = drift_t_slack
        self.drift_p_slack = drift_p_slack
        self.drift_h_slack = drift_h_slack
        self.drift_thresh = drift_thresh

        self.buf_t = np.zeros(64, dtype=np.float32)
        self.buf_p = np.zeros(64, dtype=np.float32)
        self.buf_h = np.zeros(64, dtype=np.float32)
        self.head = 0
        self.count = 0
        self.last_raw_t = None
        self.last_raw_p = None
        self.last_raw_h = None
        
        self.sprt_pos_t = 0.0
        self.sprt_neg_t = 0.0
        self.sprt_pos_p = 0.0
        self.sprt_neg_p = 0.0
        self.sprt_pos_h = 0.0
        self.sprt_neg_h = 0.0

    def detect(self, t, p, h):
        is_anom = False
        ft = "normal"

        # Tier 0: Electrical
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            is_anom, ft = True, "dropout"
        elif t <= -35.0 or p <= 150.0 or h <= 0.0:
            is_anom, ft = True, "sensor_fail_low"
        elif t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            is_anom, ft = True, "physical_bounds"
        elif (t - ((100.0 - h) / 5.0)) > (t + 0.5) or (t > 42.0 and h > 65.0):
            is_anom, ft = True, "multivariate_inconsistency"
        else:
            if self.last_raw_t is not None and not math.isnan(self.last_raw_t):
                dt_t = abs(t - self.last_raw_t)
                dt_p = abs(p - self.last_raw_p)
                dt_h = abs(h - self.last_raw_h)

                if (t - self.last_raw_t) > 2.0 and (h - self.last_raw_h) > 6.5:
                    is_anom, ft = True, "multivariate_inconsistency"
                else:
                    is_diurnal = ((t > self.last_raw_t and h < self.last_raw_h) or
                                  (t < self.last_raw_t and h > self.last_raw_h)) and (dt_t < 6.5 and dt_h < 30.0)
                    if not is_diurnal:
                        if dt_t > self.spike_roc_t or dt_p > self.spike_roc_p or dt_h > self.spike_roc_h:
                            is_anom, ft = True, "spike"

            # Freeze check
            if not is_anom and self.count >= self.freeze_w:
                w_t = [self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(self.freeze_w - 1)] + [t]
                w_p = [self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(self.freeze_w - 1)] + [p]
                w_h = [self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(self.freeze_w - 1)] + [h]
                
                if (max(w_t) - min(w_t)) <= self.freeze_r_t or \
                   (max(w_p) - min(w_p)) <= self.freeze_r_p or \
                   (max(w_h) - min(w_h)) <= self.freeze_r_h:
                    is_anom, ft = True, "frozen_value"

            # Drift check
            if not is_anom and self.count >= self.drift_w:
                m_t = np.mean([self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(self.drift_w)])
                m_p = np.mean([self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(self.drift_w)])
                m_h = np.mean([self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(self.drift_w)])
                
                dev_t = t - m_t
                dev_p = p - m_p
                dev_h = h - m_h
                
                if abs(dev_t) > self.drift_t_slack:
                    self.sprt_pos_t = max(0.0, self.sprt_pos_t * 0.90 + (dev_t - self.drift_t_slack))
                    self.sprt_neg_t = max(0.0, self.sprt_neg_t * 0.90 + (-dev_t - self.drift_t_slack))
                else:
                    self.sprt_pos_t *= 0.70
                    self.sprt_neg_t *= 0.70

                if abs(dev_p) > self.drift_p_slack:
                    self.sprt_pos_p = max(0.0, self.sprt_pos_p * 0.90 + (dev_p - self.drift_p_slack))
                    self.sprt_neg_p = max(0.0, self.sprt_neg_p * 0.90 + (-dev_p - self.drift_p_slack))
                else:
                    self.sprt_pos_p *= 0.70
                    self.sprt_neg_p *= 0.70

                if abs(dev_h) > self.drift_h_slack:
                    self.sprt_pos_h = max(0.0, self.sprt_pos_h * 0.90 + (dev_h - self.drift_h_slack))
                    self.sprt_neg_h = max(0.0, self.sprt_neg_h * 0.90 + (-dev_h - self.drift_h_slack))
                else:
                    self.sprt_pos_h *= 0.70
                    self.sprt_neg_h *= 0.70

                if (self.sprt_pos_t > self.drift_thresh or self.sprt_neg_t > self.drift_thresh or
                    self.sprt_pos_p > self.drift_thresh or self.sprt_neg_p > self.drift_thresh or
                    self.sprt_pos_h > self.drift_thresh or self.sprt_neg_h > self.drift_thresh):
                    is_anom, ft = True, "drift"

        # Always update raw buffer for continuous physical trajectory
        self.buf_t[self.head] = t
        self.buf_p[self.head] = p
        self.buf_h[self.head] = h
        self.head = (self.head + 1) & 63
        if self.count < 64:
            self.count += 1
        self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h

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
        
        eng = ProperDualBufferEngine()
        for i in range(len(df)):
            flag, ft = eng.detect(t_arr[i], p_arr[i], h_arr[i])
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
        print(f"  {k:<26}: {v['detected']}/{v['injected']} ({c:.1f}%)")

if __name__ == "__main__":
    main()
