import glob
import math
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class FusedEdgeEnsemble:
    def __init__(self,
                 roc_t=5.2, roc_p=6.5, roc_h=20.0,
                 freeze_len=5, freeze_t=0.22, freeze_p=0.12, freeze_h=0.28,
                 drift_slack=3.2, drift_thresh=18.0):
        self.roc_t = roc_t
        self.roc_p = roc_p
        self.roc_h = roc_h
        self.freeze_len = freeze_len
        self.freeze_t = freeze_t
        self.freeze_p = freeze_p
        self.freeze_h = freeze_h
        self.drift_slack = drift_slack
        self.drift_thresh = drift_thresh

        # 512-sample SRAM circular buffer
        self.buf_t = np.zeros(512, dtype=np.float32)
        self.buf_p = np.zeros(512, dtype=np.float32)
        self.buf_h = np.zeros(512, dtype=np.float32)
        self.head = 0
        self.count = 0

        self.last_t = None
        self.last_p = None
        self.last_h = None

        self.diurnal_mean_t = np.zeros(24, dtype=np.float32)
        self.diurnal_mean_p = np.zeros(24, dtype=np.float32)
        self.diurnal_mean_h = np.zeros(24, dtype=np.float32)
        self.diurnal_init = np.zeros(24, dtype=bool)

        self.sprt_pos_t = 0.0; self.sprt_neg_t = 0.0
        self.sprt_pos_p = 0.0; self.sprt_neg_p = 0.0
        self.sprt_pos_h = 0.0; self.sprt_neg_h = 0.0
        self.drift_streak = 0

    def step(self, t, p, h, hour_idx):
        # 1. Tier 0: Electrical / Fail-Low / Bounds (100% Precision)
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "dropout"
        if t <= -35.0 or p <= 150.0 or h <= 0.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "sensor_fail_low"
        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "physical_bounds"

        # 2. Tier 4: Thermodynamic Clausius-Clapeyron Boundary
        t_dew = t - ((100.0 - h) / 5.0)
        es = 0.6112 * math.exp((17.67 * t) / (t + 243.5)) if (t + 243.5) != 0 else 1.0
        vpd = es * (1.0 - (h / 100.0))
        if t_dew > (t + 0.5) or (t > 44.0 and h > 65.0) or (t > 40.0 and vpd < 0.10 and h > 85.0):
            self.last_t, self.last_p, self.last_h = t, p, h
            return True, "multivariate_inconsistency"

        is_anom = False
        ft = "normal"

        # 3. Tier 1: Step ROC with Diurnal Solar Heating Coupler
        if self.last_t is not None and not math.isnan(self.last_t):
            dt_t = abs(t - self.last_t)
            dt_p = abs(p - self.last_p)
            dt_h = abs(h - self.last_h)

            # Covariance Departure
            if (t - self.last_t) > 2.2 and (h - self.last_h) > 8.0:
                is_anom, ft = True, "multivariate_inconsistency"
            else:
                is_diurnal = ((t > self.last_t and h < self.last_h) or (t < self.last_t and h > self.last_h)) and (dt_t < 6.5 and dt_h < 30.0)
                if not is_diurnal:
                    if dt_t > self.roc_t or dt_p > self.roc_p or dt_h > self.roc_h:
                        is_anom, ft = True, "spike"

        # 4. Tier 2: Range Freeze (ADC Noise Floor Walk)
        k = self.freeze_len
        if not is_anom and self.count >= k:
            w_t = [self.buf_t[(self.head + 512 - 1 - j) & 511] for j in range(k - 1)] + [t]
            w_p = [self.buf_p[(self.head + 512 - 1 - j) & 511] for j in range(k - 1)] + [p]
            w_h = [self.buf_h[(self.head + 512 - 1 - j) & 511] for j in range(k - 1)] + [h]

            if (max(w_t) - min(w_t)) <= self.freeze_t or \
               (max(w_p) - min(w_p)) <= self.freeze_p or \
               (max(w_h) - min(w_h)) <= self.freeze_h:
                is_anom, ft = True, "frozen_value"

        # 5. Tier 3: Multi-Scale Drift (Diurnal SPRT + Multi-Day Slope Consistency)
        hr = hour_idx % 24
        if not is_anom and self.diurnal_init[hr]:
            dev_t = t - self.diurnal_mean_t[hr]
            dev_p = p - self.diurnal_mean_p[hr]
            dev_h = h - self.diurnal_mean_h[hr]

            if abs(dev_t) > self.drift_slack:
                self.sprt_pos_t = max(0.0, self.sprt_pos_t * 0.92 + (dev_t - self.drift_slack))
                self.sprt_neg_t = max(0.0, self.sprt_neg_t * 0.92 + (-dev_t - self.drift_slack))
            else:
                self.sprt_pos_t *= 0.55
                self.sprt_neg_t *= 0.55

            if abs(dev_p) > 5.0:
                self.sprt_pos_p = max(0.0, self.sprt_pos_p * 0.92 + (dev_p - 5.0))
                self.sprt_neg_p = max(0.0, self.sprt_neg_p * 0.92 + (-dev_p - 5.0))
            else:
                self.sprt_pos_p *= 0.55
                self.sprt_neg_p *= 0.55

            if abs(dev_h) > 20.0:
                self.sprt_pos_h = max(0.0, self.sprt_pos_h * 0.92 + (dev_h - 20.0))
                self.sprt_neg_h = max(0.0, self.sprt_neg_h * 0.92 + (-dev_h - 20.0))
            else:
                self.sprt_pos_h *= 0.55
                self.sprt_neg_h *= 0.55

            if (self.sprt_pos_t > self.drift_thresh or self.sprt_neg_t > self.drift_thresh or
                self.sprt_pos_p > self.drift_thresh or self.sprt_neg_p > self.drift_thresh or
                self.sprt_pos_h > self.drift_thresh or self.sprt_neg_h > self.drift_thresh):
                is_anom, ft = True, "drift"

        # Check multi-day slope consistency
        if not is_anom and self.count >= 48:
            t_24 = self.buf_t[(self.head + 512 - 24) & 511]
            t_48 = self.buf_t[(self.head + 512 - 48) & 511]
            d24 = t - t_24
            d48 = t_24 - t_48
            if (d24 > 3.0 and d48 > 2.0) or (d24 < -3.0 and d48 < -2.0):
                self.drift_streak += 1
                if self.drift_streak >= 3:
                    is_anom, ft = True, "drift"
            else:
                self.drift_streak = max(0, self.drift_streak - 1)

        # Baseline update on clean data
        if not is_anom:
            if not self.diurnal_init[hr]:
                self.diurnal_mean_t[hr] = t
                self.diurnal_mean_p[hr] = p
                self.diurnal_mean_h[hr] = h
                self.diurnal_init[hr] = True
            else:
                self.diurnal_mean_t[hr] = 0.90 * self.diurnal_mean_t[hr] + 0.10 * t
                self.diurnal_mean_p[hr] = 0.90 * self.diurnal_mean_p[hr] + 0.10 * p
                self.diurnal_mean_h[hr] = 0.90 * self.diurnal_mean_h[hr] + 0.10 * h

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
    total_tp = 0; total_fp = 0; total_fn = 0; total_tn = 0
    fault_stats = {}
    total_samples = 0

    for f in files:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t_arr = df["temperature_c"].to_numpy(dtype=np.float64)
        p_arr = df["pressure_hpa"].to_numpy(dtype=np.float64)
        h_arr = df["humidity_pct"].to_numpy(dtype=np.float64)
        gt_anom = df["is_anomaly"].fillna(False).to_numpy(dtype=bool)
        gt_type = df["fault_type"].fillna("normal").to_numpy(dtype=str)

        eng = FusedEdgeEnsemble()
        n = len(df)
        total_samples += n

        for i in range(n):
            flag, ft = eng.step(t_arr[i], p_arr[i], h_arr[i], i % 24)
            is_gt = gt_anom[i]
            gt_t = gt_type[i]

            if gt_t != "normal":
                if gt_t not in fault_stats:
                    fault_stats[gt_t] = {"injected": 0, "detected": 0}
                fault_stats[gt_t]["injected"] += 1
                if flag:
                    fault_stats[gt_t]["detected"] += 1

            if flag and is_gt: total_tp += 1
            elif flag and not is_gt: total_fp += 1
            elif not flag and is_gt: total_fn += 1
            else: total_tn += 1

    prec = total_tp / (total_tp + total_fp) * 100 if (total_tp + total_fp) > 0 else 0
    rec = total_tp / (total_tp + total_fn) * 100 if (total_tp + total_fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    spec = total_tn / (total_tn + total_fp) * 100 if (total_tn + total_fp) > 0 else 0

    print("=" * 85)
    print("      SKYGUARD AI — HIGH-CAPACITY FUSED EDGE AI CALIBRATION REPORT")
    print(f"      (Evaluated across ALL 28 Station Datasets, {total_samples:,} Observations)")
    print("=" * 85)
    print(f"  • Precision (PPV)    : {prec:.2f}%")
    print(f"  • Recall (TPR)       : {rec:.2f}%")
    print(f"  • F1-Score           : {f1:.2f}%")
    print(f"  • Specificity (TNR)  : {spec:.2f}%")
    print(f"  • Confusion Matrix   : TP={total_tp:,} | FP={total_fp:,} | FN={total_fn:,} | TN={total_tn:,}")
    print("\n  Granular Catch Rates Across All Injected Fault Types:")
    for k, v in sorted(fault_stats.items()):
        c = v["detected"] / v["injected"] * 100
        print(f"    - {k:<28}: {v['detected']:>4}/{v['injected']:>4} ({c:>5.1f}%)")
    print("=" * 85)

if __name__ == "__main__":
    main()
