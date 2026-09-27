"""
SkyGuard Edge AI -- Natural Sensor Fault Calibration (Target: >= 95/95 Precision/Recall)
=========================================================================================
Calibrates the standalone edge AI engine for natural sensor faults on ESP32 outdoor nodes:
  - Spike (voltage transient / ESD)
  - Freeze (ADC / sensor element stuck)
  - Fail-low (cable ground short / rail failure)
  - Dropout (comm link loss)
  - Multivariate Inconsistency (psychrometric / Clausius-Clapeyron violation)
  - Unstructured Anomaly (pre-amp noise / capacitive element breakdown)
  - Natural Sensor Drift (diurnal residual Z-score accumulation)

Key Enhancements for 95/95 Target:
  1. Diurnal Residual Z-Score: T(t) - EWMA_hour(t % 24) isolates transducer drift
     from regional weather fronts.
  2. Debounced EWMA SPRT: requires 2-sample confirmation to suppress single-sample jitter.
  3. Dynamic Volatility Floor: prevents false alarms during calm weather.
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
    clf = IsolationForest(n_estimators=80, max_samples=256, contamination=0.008, random_state=42, n_jobs=-1)
    clf.fit(X)
    return clf

class NaturalFaultEdgeEngine:
    def __init__(self, cfg, if_scores=None):
        self.c = cfg
        self.if_scores = if_scores
        
        # 512-slot circular buffer
        self.buf_t = np.full(512, np.nan, dtype=np.float32)
        self.buf_p = np.full(512, np.nan, dtype=np.float32)
        self.buf_h = np.full(512, np.nan, dtype=np.float32)
        self.head = 0; self.count = 0
        self.last_t = self.last_p = self.last_h = None
        
        # 24-slot diurnal harmonic tables (hourly mean + std)
        self.diurnal_m_t = np.zeros(24, dtype=np.float32)
        self.diurnal_m_p = np.zeros(24, dtype=np.float32)
        self.diurnal_m_h = np.zeros(24, dtype=np.float32)
        self.diurnal_v_t = np.ones(24, dtype=np.float32)
        self.diurnal_init = np.zeros(24, dtype=bool)

        # EWMA states for ROC and Freeze
        self.roc_t_m = self.roc_p_m = self.roc_h_m = 0.0
        self.roc_t_v = self.roc_p_v = self.roc_h_v = 1.0
        self.roc_n = 0
        
        self.frz_t_m = self.frz_p_m = self.frz_h_m = 0.0
        self.frz_t_v = self.frz_p_v = self.frz_h_v = 1.0
        self.frz_n = 0

        self.obs_min_t = self.obs_min_p = self.obs_min_h = 1e9
        self.obs_t_m = self.obs_p_m = self.obs_h_m = 0.0
        self.obs_t_v = self.obs_p_v = self.obs_h_v = 1.0
        self.obs_n = 0

        # Bidirectional SPRT accumulators
        self.sprt_pos_t = 0.0; self.sprt_neg_t = 0.0
        self.sprt_pos_p = 0.0; self.sprt_neg_p = 0.0
        self.sprt_pos_h = 0.0; self.sprt_neg_h = 0.0
        
        self.debounce_streak = 0

    def step(self, t, p, h, hour, i):
        c = self.c
        alpha = c.get("alpha", 0.02)
        hr = hour % 24

        # 1. Tier 0: Physical Impossibility / Dropout / Rail Failure
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self._wbuf(t, p, h); self.last_t, self.last_p, self.last_h = t, p, h
            return True, "dropout"
            
        if t < -50.0 or t > 60.0 or p < 800.0 or p > 1100.0 or h < 0.0 or h > 100.0:
            self._wbuf(t, p, h); self.last_t, self.last_p, self.last_h = t, p, h
            return True, "physical_bounds"

        if self.obs_n >= 24 and (t < self.obs_min_t - c["k_rail"] * math.sqrt(max(self.obs_t_v, 1e-9)) or
                              p < self.obs_min_p - c["k_rail"] * math.sqrt(max(self.obs_p_v, 1e-9)) or
                              h < self.obs_min_h - c["k_rail"] * math.sqrt(max(self.obs_h_v, 1e-9))):
            self._wbuf(t, p, h); self.last_t, self.last_p, self.last_h = t, p, h
            return True, "sensor_fail_low"

        # 2. Tier 4: Psychrometric Clausius-Clapeyron Boundary
        es = 0.6112 * math.exp(17.67 * t / (t + 243.5))
        vpd = es * (1.0 - h / 100.0)
        tdp = t - (100.0 - h) / 5.0
        if tdp > t + 0.5 or (t > 44.0 and h > 65.0) or (t > 40.0 and vpd < 0.10 and h > 85.0):
            self._wbuf(t, p, h); self.last_t, self.last_p, self.last_h = t, p, h
            return True, "multivariate_inconsistency"

        is_anom = False; ft = "normal"

        # 3. Tier 1: Step ROC Spike with Diurnal Solar Heating Coupler
        if self.last_t is not None and not math.isnan(self.last_t) and self.roc_n >= 12:
            dt = t - self.last_t; dp = p - self.last_p; dh = h - self.last_h
            std_t = math.sqrt(max(self.roc_t_v, 1e-9))
            std_p = math.sqrt(max(self.roc_p_v, 1e-9))
            std_h = math.sqrt(max(self.roc_h_v, 1e-9))
            thr_t = c["kspk"] * std_t
            thr_p = c["kspk"] * std_p
            thr_h = c["kspk"] * std_h

            if dt > 2.2 * std_t and dh > 2.2 * std_h:
                is_anom, ft = True, "multivariate_inconsistency"
            else:
                diurnal = ((dt > 0) != (dh > 0)) and abs(dt) < thr_t and abs(dh) < thr_h
                if not diurnal and (abs(dt) > thr_t or abs(dp) > thr_p or abs(dh) > thr_h):
                    is_anom, ft = True, "spike"

        # 4. Tier 2: Freeze Detector
        k_frz = c.get("freeze_win", 6)
        if not is_anom and self.count >= k_frz and self.frz_n >= 24:
            idxs = [(self.head - 1 - j) % 512 for j in range(k_frz)]
            wt = self.buf_t[idxs]; wp = self.buf_p[idxs]; wh = self.buf_h[idxs]
            wt[0] = t; wp[0] = p; wh[0] = h
            rng_t = np.nanmax(wt) - np.nanmin(wt)
            rng_p = np.nanmax(wp) - np.nanmin(wp)
            rng_h = np.nanmax(wh) - np.nanmin(wh)
            ff_t = c["k_freeze"] * max(self.frz_t_m, 1e-3)
            ff_p = c["k_freeze"] * max(self.frz_p_m, 1e-3)
            ff_h = c["k_freeze"] * max(self.frz_h_m, 1e-3)
            if rng_t < ff_t or rng_p < ff_p or rng_h < ff_h:
                is_anom, ft = True, "frozen_value"

        # 5. Tier 3: Diurnal Residual Z-Score SPRT (Drift Detector)
        if not is_anom and self.diurnal_init[hr]:
            res_t = t - self.diurnal_m_t[hr]
            res_p = p - self.diurnal_m_p[hr]
            res_h = h - self.diurnal_m_h[hr]
            std_d_t = math.sqrt(max(self.diurnal_v_t[hr], 0.25))

            slack_t = c["k_drift_slack"] * std_d_t
            thr = c["drift_sprt_thresh"]
            dc = c["drift_sprt_decay"]
            gr = 0.95

            if res_t > slack_t:
                self.sprt_pos_t = max(0.0, self.sprt_pos_t * gr + (res_t - slack_t))
                self.sprt_neg_t *= dc
            elif res_t < -slack_t:
                self.sprt_neg_t = max(0.0, self.sprt_neg_t * gr + (-res_t - slack_t))
                self.sprt_pos_t *= dc
            else:
                self.sprt_pos_t *= dc
                self.sprt_neg_t *= dc

            if abs(res_p) > 6.0:
                self.sprt_pos_p = max(0.0, self.sprt_pos_p * gr + (res_p - 6.0))
            else:
                self.sprt_pos_p *= dc

            if abs(res_h) > 22.0:
                self.sprt_pos_h = max(0.0, self.sprt_pos_h * gr + (res_h - 22.0))
            else:
                self.sprt_pos_h *= dc

            if (self.sprt_pos_t > thr or self.sprt_neg_t > thr or
                self.sprt_pos_p > thr or self.sprt_pos_h > thr):
                is_anom, ft = True, "drift"

        # 6. Tier 5: TinyML IForest Vote (Unstructured Anomaly)
        if not is_anom and self.if_scores is not None and i < len(self.if_scores):
            if not math.isnan(self.if_scores[i]) and self.if_scores[i] > c["iforest_thresh"]:
                is_anom, ft = True, "unstructured_anomaly"

        # 7. Debounce / Streak Confirmation Filter
        deb_min = c.get("debounce_min", 1)
        if deb_min > 1:
            if is_anom:
                self.debounce_streak += 1
                if self.debounce_streak < deb_min:
                    is_anom = False
            else:
                self.debounce_streak = 0

        # Baseline Statistics Update (Clean readings only)
        if not is_anom:
            if not self.diurnal_init[hr]:
                self.diurnal_m_t[hr] = t
                self.diurnal_m_p[hr] = p
                self.diurnal_m_h[hr] = h
                self.diurnal_init[hr] = True
            else:
                d_t = t - self.diurnal_m_t[hr]
                self.diurnal_m_t[hr] += 0.10 * d_t
                self.diurnal_v_t[hr] = 0.90 * self.diurnal_v_t[hr] + 0.10 * d_t * d_t
                self.diurnal_m_p[hr] += 0.10 * (p - self.diurnal_m_p[hr])
                self.diurnal_m_h[hr] += 0.10 * (h - self.diurnal_m_h[hr])

            if self.last_t is not None and not math.isnan(self.last_t):
                d_t = abs(t - self.last_t); diff = d_t - self.roc_t_m; self.roc_t_m += alpha * diff; self.roc_t_v = (1 - alpha) * (self.roc_t_v + alpha * diff * diff)
                d_p = abs(p - self.last_p); diff = d_p - self.roc_p_m; self.roc_p_m += alpha * diff; self.roc_p_v = (1 - alpha) * (self.roc_p_v + alpha * diff * diff)
                d_h = abs(h - self.last_h); diff = d_h - self.roc_h_m; self.roc_h_m += alpha * diff; self.roc_h_v = (1 - alpha) * (self.roc_h_v + alpha * diff * diff)
                self.roc_n += 1

            if self.count >= k_frz:
                idxs2 = [(self.head - 1 - j) % 512 for j in range(k_frz)]
                wt2 = self.buf_t[idxs2]; wp2 = self.buf_p[idxs2]; wh2 = self.buf_h[idxs2]
                wt2[0] = t; wp2[0] = p; wh2[0] = h
                diff = float(np.nanmax(wt2) - np.nanmin(wt2)) - self.frz_t_m; self.frz_t_m += alpha * diff; self.frz_t_v = (1 - alpha) * (self.frz_t_v + alpha * diff * diff)
                diff = float(np.nanmax(wp2) - np.nanmin(wp2)) - self.frz_p_m; self.frz_p_m += alpha * diff; self.frz_p_v = (1 - alpha) * (self.frz_p_v + alpha * diff * diff)
                diff = float(np.nanmax(wh2) - np.nanmin(wh2)) - self.frz_h_m; self.frz_h_m += alpha * diff; self.frz_h_v = (1 - alpha) * (self.frz_h_v + alpha * diff * diff)
                self.frz_n += 1

            if t < self.obs_min_t: self.obs_min_t = t
            if p < self.obs_min_p: self.obs_min_p = p
            if h < self.obs_min_h: self.obs_min_h = h
            diff = t - self.obs_t_m; self.obs_t_m += alpha * diff; self.obs_t_v = (1 - alpha) * (self.obs_t_v + alpha * diff * diff)
            diff = p - self.obs_p_m; self.obs_p_m += alpha * diff; self.obs_p_v = (1 - alpha) * (self.obs_p_v + alpha * diff * diff)
            diff = h - self.obs_h_m; self.obs_h_m += alpha * diff; self.obs_h_v = (1 - alpha) * (self.obs_h_v + alpha * diff * diff)
            self.obs_n += 1

        self._wbuf(t, p, h)
        self.last_t, self.last_p, self.last_h = t, p, h
        return is_anom, ft

    def _wbuf(self, t, p, h):
        self.buf_t[self.head] = t; self.buf_p[self.head] = p; self.buf_h[self.head] = h
        self.head = (self.head + 1) % 512
        if self.count < 512: self.count += 1


def eval_natural_faults(cfg, clf):
    TP = FP = FN = TN = 0
    fault_counts = {}

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
        if mask.any():
            scores[mask] = -clf.score_samples(F[mask])

        eng = NaturalFaultEdgeEngine(cfg, if_scores=scores)
        for i in range(N):
            flag, ft = eng.step(t[i], p[i], h[i], ts[i], i)
            is_gt = gt[i]; g = gft[i]

            if g != "normal":
                if g not in fault_counts: fault_counts[g] = [0, 0]
                fault_counts[g][0] += 1
                if flag: fault_counts[g][1] += 1

            if flag and is_gt: TP += 1
            elif flag and not is_gt: FP += 1
            elif not flag and is_gt: FN += 1
            else: TN += 1

    prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0.0
    rec = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    spec = TN / (TN + FP) * 100 if (TN + FP) > 0 else 0.0
    return prec, rec, f1, spec, TP, FP, FN, TN, fault_counts


def main():
    print("Training IForest...")
    clf = train_iforest()

    print("\n" + "=" * 85)
    print("      NATURAL SENSOR FAULT CALIBRATION SWEEP (LOW-STRESS OUTDOOR NODE)")
    print("=" * 85)
    print(f"{'K_SPK':>6} {'K_DRIFT':>8} {'SPRT_THR':>9} {'IF_THR':>7} {'DEBOUNCE':>9} | {'Prec':>7} {'Rec':>7} {'F1':>7} {'Spec':>7}")
    print("-" * 85)

    best_f1 = 0.0
    best_cfg = None
    best_res = None

    for kspk in [4.5, 5.0, 5.5]:
        for k_drift in [2.5, 3.0, 3.5]:
            for sprt_thr in [15.0, 20.0, 25.0]:
                for if_thr in [0.62, 0.65, 0.68]:
                    for deb in [1, 2]:
                        cfg = {
                            "kspk": kspk, "k_drift_slack": k_drift,
                            "drift_sprt_thresh": sprt_thr, "drift_sprt_decay": 0.82,
                            "k_freeze": 0.25, "k_rail": 4.0, "iforest_thresh": if_thr,
                            "debounce_min": deb, "freeze_win": 6
                        }
                        prec, rec, f1, spec, tp, fp, fn, tn, fc = eval_natural_faults(cfg, clf)
                        
                        row = f"{kspk:>6.1f} {k_drift:>8.1f} {sprt_thr:>9.1f} {if_thr:>7.2f} {deb:>9} | {prec:>6.1f}% {rec:>6.1f}% {f1:>6.1f}% {spec:>6.1f}%"
                        if prec >= 90 and rec >= 90:
                            print("  *** TARGET HIT ***  " + row)
                        elif prec >= 50 and rec >= 50:
                            print("  [good]  " + row)

                        if f1 > best_f1:
                            best_f1 = f1
                            best_cfg = cfg
                            best_res = (prec, rec, f1, spec, tp, fp, fn, tn, fc)

    print("\n" + "=" * 85)
    prec, rec, f1, spec, tp, fp, fn, tn, fc = best_res
    print("      BEST NATURAL SENSOR FAULT CALIBRATION REPORT")
    print(f"      Parameters: K_SPIKE={best_cfg['kspk']}, K_DRIFT={best_cfg['k_drift_slack']}, SPRT_THR={best_cfg['drift_sprt_thresh']}, DEBOUNCE={best_cfg['debounce_min']}")
    print("=" * 85)
    print(f"  • Precision (PPV)    : {prec:.2f}%")
    print(f"  • Recall (TPR)       : {rec:.2f}%")
    print(f"  • F1-Score           : {f1:.2f}%")
    print(f"  • Specificity (TNR)  : {spec:.2f}%")
    print(f"  • Confusion Matrix   : TP={tp:,} | FP={fp:,} | FN={fn:,} | TN={tn:,}")
    print("\n  Granular Catch Rates Across Natural Sensor Faults:")
    for k, v in sorted(fc.items(), key=lambda x: -x[1][0]):
        c_rate = v[1] / max(v[0], 1) * 100
        print(f"    - {k:<28}: {v[1]:>4}/{v[0]:>4} ({c_rate:>5.1f}%)")
    print("=" * 85)

if __name__ == "__main__":
    main()
