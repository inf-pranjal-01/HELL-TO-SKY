import glob
import math
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class MultiDaySlopeEdgeEngine:
    def __init__(self):
        self.buf_t = np.zeros(512, dtype=np.float32)
        self.buf_p = np.zeros(512, dtype=np.float32)
        self.buf_h = np.zeros(512, dtype=np.float32)
        self.head = 0
        self.count = 0

        self.last_t = None
        self.last_p = None
        self.last_h = None

        self.drift_streak_t = 0
        self.drift_streak_p = 0

    def step(self, t, p, h):
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "dropout"
        if t <= -35.0 or p <= 150.0 or h <= 0.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "sensor_fail_low"
        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "physical_bounds"

        t_dew = t - ((100.0 - h) / 5.0)
        if t_dew > (t + 0.5) or (t > 44.0 and h > 65.0):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "multivariate_inconsistency"

        is_anom = False
        ft = "normal"

        if self.last_t is not None and not math.isnan(self.last_t):
            dt_t = abs(t - self.last_t)
            dt_p = abs(p - self.last_p)
            dt_h = abs(h - self.last_h)

            if (t - self.last_t) > 2.2 and (h - self.last_h) > 8.0:
                is_anom, ft = True, "multivariate_inconsistency"
            else:
                is_diurnal = ((t > self.last_t and h < self.last_h) or (t < self.last_t and h > self.last_h)) and (dt_t < 6.5 and dt_h < 30.0)
                if not is_diurnal:
                    if dt_t > 5.5 or dt_p > 7.0 or dt_h > 22.0:
                        is_anom, ft = True, "spike"

        # Freeze
        if not is_anom and self.count >= 5:
            w_t = [self.buf_t[(self.head + 512 - 1 - j) & 511] for j in range(4)] + [t]
            w_p = [self.buf_p[(self.head + 512 - 1 - j) & 511] for j in range(4)] + [p]
            w_h = [self.buf_h[(self.head + 512 - 1 - j) & 511] for j in range(4)] + [h]

            if (max(w_t) - min(w_t)) <= 0.22 or (max(w_p) - min(w_p)) <= 0.12 or (max(w_h) - min(w_h)) <= 0.28:
                is_anom, ft = True, "frozen_value"

        # 24h & 48h Same-Hour Drift Delta
        if not is_anom and self.count >= 48:
            t_24 = self.buf_t[(self.head + 512 - 24) & 511]
            t_48 = self.buf_t[(self.head + 512 - 48) & 511]
            
            delta_24 = t - t_24
            delta_48 = t_24 - t_48
            
            if (delta_24 > 3.0 and delta_48 > 2.0) or (delta_24 < -3.0 and delta_48 < -2.0):
                self.drift_streak_t += 1
            else:
                self.drift_streak_t = max(0, self.drift_streak_t - 1)

            if self.drift_streak_t >= 3:
                is_anom, ft = True, "drift"

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

        eng = MultiDaySlopeEdgeEngine()
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
    print(f"Precision: {prec:.2f}% | Recall: {rec:.2f}% | F1: {f1:.2f}% | Specificity: {spec:.2f}%")
    print(f"TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    for k, v in sorted(fault_stats.items()):
        c = v["detected"] / v["injected"] * 100
        print(f"  {k:<28}: {v['detected']}/{v['injected']} ({c:.1f}%)")

if __name__ == "__main__":
    main()
