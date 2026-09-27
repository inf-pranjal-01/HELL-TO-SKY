import glob
import math
import time
import numpy as np
import pandas as pd

files = sorted(glob.glob("data/*_labeled.csv"))

class MultiTierEdgeEngine:
    def __init__(self,
                 spike_roc_t=5.5, spike_roc_p=7.0, spike_roc_h=22.0,
                 freeze_window=5, freeze_r_t=0.25, freeze_r_p=0.18, freeze_r_h=0.35,
                 drift_tau=24.0, drift_shift=1.2, drift_thresh=14.0,
                 mv_t_thresh=42.0, mv_rh_thresh=65.0, mv_anti_jump=True):
        self.spike_roc_t = spike_roc_t
        self.spike_roc_p = spike_roc_p
        self.spike_roc_h = spike_roc_h
        
        self.freeze_window = freeze_window
        self.freeze_r_t = freeze_r_t
        self.freeze_r_p = freeze_r_p
        self.freeze_r_h = freeze_r_h
        
        self.drift_tau = drift_tau
        self.drift_shift = drift_shift
        self.drift_thresh = drift_thresh
        
        self.mv_t_thresh = mv_t_thresh
        self.mv_rh_thresh = mv_rh_thresh
        self.mv_anti_jump = mv_anti_jump

        # State
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
        
        self.last_res_t = 0.0
        self.last_res_p = 0.0
        self.last_res_h = 0.0
        
        self.welford_mean_t = 0.0
        self.welford_m2_t = 0.0
        self.welford_count_t = 0
        
        self.welford_mean_p = 0.0
        self.welford_m2_p = 0.0
        self.welford_count_p = 0
        
        self.welford_mean_h = 0.0
        self.welford_m2_h = 0.0
        self.welford_count_h = 0

    def _update_welford(self, t, p, h):
        # Temp
        self.welford_count_t += 1
        d_t = t - self.welford_mean_t
        self.welford_mean_t += d_t / self.welford_count_t
        self.welford_m2_t += d_t * (t - self.welford_mean_t)
        # Pres
        self.welford_count_p += 1
        d_p = p - self.welford_mean_p
        self.welford_mean_p += d_p / self.welford_count_p
        self.welford_m2_p += d_p * (p - self.welford_mean_p)
        # Hum
        self.welford_count_h += 1
        d_h = h - self.welford_mean_h
        self.welford_mean_h += d_h / self.welford_count_h
        self.welford_m2_h += d_h * (h - self.welford_mean_h)

    def detect(self, t, p, h) -> tuple[bool, str]:
        # Tier 0: Electrical Invariants & Bounds
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
            return True, "dropout"
        if t <= -35.0 or p <= 150.0 or h <= 0.0:
            self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
            return True, "sensor_fail_low"
        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
            return True, "physical_bounds"

        # Tier 3: Psychrometric Invariants (Lawrence dewpoint + Clausius-Clapeyron)
        t_dew = t - ((100.0 - h) / 5.0)
        if t_dew > (t + 0.5) or (t > self.mv_t_thresh and h > self.mv_rh_thresh):
            self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
            return True, "multivariate_inconsistency"

        # Step ROC and Jump checks
        if self.last_raw_t is not None and not math.isnan(self.last_raw_t):
            dt_t = abs(t - self.last_raw_t)
            dt_p = abs(p - self.last_raw_p)
            dt_h = abs(h - self.last_raw_h)

            # Multivariate coupled same-direction jump
            if self.mv_anti_jump and (t - self.last_raw_t) > 2.0 and (h - self.last_raw_h) > 6.5:
                self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
                return True, "multivariate_inconsistency"

            # Diurnal anti-spike check
            is_diurnal = ((t > self.last_raw_t and h < self.last_raw_h) or
                          (t < self.last_raw_t and h > self.last_raw_h)) and (dt_t < 6.5 and dt_h < 30.0)
            if not is_diurnal:
                if dt_t > self.spike_roc_t or dt_p > self.spike_roc_p or dt_h > self.spike_roc_h:
                    self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
                    return True, "spike"

        # Tier 1: Freeze check (Variance / range collapse over K readings)
        k = self.freeze_window
        if self.count >= k:
            w_t = [self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(k)]
            w_p = [self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(k)]
            w_h = [self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(k)]

            if ((max(w_t) - min(w_t)) <= self.freeze_r_t and abs(t - w_t[0]) <= self.freeze_r_t) or \
               ((max(w_p) - min(w_p)) <= self.freeze_r_p and abs(p - w_p[0]) <= self.freeze_r_p) or \
               ((max(w_h) - min(w_h)) <= self.freeze_r_h and abs(h - w_h[0]) <= self.freeze_r_h):
                self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
                return True, "frozen_value"

        # Tier 2: Persistent Drift (Pre-Whitened SPRT)
        if self.count >= 24:
            # 24h rolling baseline
            mean_24_t = np.mean([self.buf_t[(self.head + 64 - 1 - j) & 63] for j in range(24)])
            mean_24_p = np.mean([self.buf_p[(self.head + 64 - 1 - j) & 63] for j in range(24)])
            mean_24_h = np.mean([self.buf_h[(self.head + 64 - 1 - j) & 63] for j in range(24)])
            
            # Autoregressive decorrelation factor
            rho = math.exp(-1.0 / self.drift_tau)
            
            # Temp channel SPRT
            raw_res_t = t - mean_24_t
            innov_t = raw_res_t - rho * self.last_res_t
            self.last_res_t = raw_res_t
            
            # SPRT update
            delta = self.drift_shift
            inc_pos = delta * (innov_t - 0.5 * delta)
            inc_neg = -delta * (innov_t + 0.5 * delta)
            
            if abs(raw_res_t) > 3.0:
                self.sprt_pos_t = max(0.0, self.sprt_pos_t * 0.94 + inc_pos)
                self.sprt_neg_t = max(0.0, self.sprt_neg_t * 0.94 + inc_neg)
            else:
                self.sprt_pos_t *= 0.75
                self.sprt_neg_t *= 0.75

            # Pres channel SPRT
            raw_res_p = p - mean_24_p
            innov_p = raw_res_p - rho * self.last_res_p
            self.last_res_p = raw_res_p
            if abs(raw_res_p) > 4.5:
                self.sprt_pos_p = max(0.0, self.sprt_pos_p * 0.94 + delta * (innov_p - 0.5 * delta))
                self.sprt_neg_p = max(0.0, self.sprt_neg_p * 0.94 - delta * (innov_p + 0.5 * delta))
            else:
                self.sprt_pos_p *= 0.75
                self.sprt_neg_p *= 0.75

            # Hum channel SPRT
            raw_res_h = h - mean_24_h
            innov_h = raw_res_h - rho * self.last_res_h
            self.last_res_h = raw_res_h
            if abs(raw_res_h) > 18.0:
                self.sprt_pos_h = max(0.0, self.sprt_pos_h * 0.94 + delta * (innov_h - 0.5 * delta))
                self.sprt_neg_h = max(0.0, self.sprt_neg_h * 0.94 - delta * (innov_h + 0.5 * delta))
            else:
                self.sprt_pos_h *= 0.75
                self.sprt_neg_h *= 0.75

            if (self.sprt_pos_t > self.drift_thresh or self.sprt_neg_t > self.drift_thresh or
                self.sprt_pos_p > self.drift_thresh or self.sprt_neg_p > self.drift_thresh or
                self.sprt_pos_h > self.drift_thresh or self.sprt_neg_h > self.drift_thresh):
                self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
                return True, "drift"

        # Tier 4: Nominal Commit
        self.buf_t[self.head] = t
        self.buf_p[self.head] = p
        self.buf_h[self.head] = h
        self.head = (self.head + 1) & 63
        if self.count < 64:
            self.count += 1
        self._update_welford(t, p, h)
        self.last_raw_t, self.last_raw_p, self.last_raw_h = t, p, h
        return False, "normal"


def eval_cfg(name, **kwargs):
    tp, fp, fn, tn = 0, 0, 0, 0
    fault_stats = {}
    t0 = time.perf_counter()
    for f in files:
        df = pd.read_csv(f)
        if "is_anomaly" not in df.columns: continue
        t_arr = df["temperature_c"].to_numpy(dtype=np.float64)
        p_arr = df["pressure_hpa"].to_numpy(dtype=np.float64)
        h_arr = df["humidity_pct"].to_numpy(dtype=np.float64)
        gt_anom = df["is_anomaly"].fillna(False).to_numpy(dtype=bool)
        gt_type = df["fault_type"].fillna("normal").to_numpy(dtype=str)
        
        eng = MultiTierEdgeEngine(**kwargs)
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
    dt = time.perf_counter() - t0
    prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    spec = tn / (tn + fp) * 100 if (tn + fp) > 0 else 0
    print(f"[{name}] (Time: {dt:.2f}s)")
    print(f"  Precision: {prec:.2f}% | Recall: {rec:.2f}% | F1: {f1:.2f}% | Specificity: {spec:.2f}%")
    print(f"  TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    for k, v in sorted(fault_stats.items()):
        c = v["detected"] / v["injected"] * 100
        print(f"    {k:<26}: {v['detected']}/{v['injected']} ({c:.1f}%)")
    return {"name": name, "precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}

if __name__ == "__main__":
    eval_cfg("Test 1 - Base", drift_thresh=14.0)
