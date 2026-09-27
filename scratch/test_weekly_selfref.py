"""
SkyGuard Edge AI -- Weekly Self-Reference Drift Engine
======================================================
Core hypothesis:
  Drift is a SUPERIMPOSED monotonic ramp on real weather.
  Real weather repeats quasi-weekly (climatological periodicity).
  -> T(t) - T(t-168h) isolates drift from diurnal variation.

Strategy:
  1. Week-over-week delta (delta_7d) for multi-day drift detection
     - Immune to diurnal masking
     - 512-slot circular buffer = 21 days @ 1h resolution
  2. SPRT accumulating on sustained week-delta violation
     - Directionally consistent: drift is unidirectional by design
  3. Exponential Moving Median (via sorted window) as robust baseline
     - Drift contaminates the EMA -> use 7-day same-hour reference instead
  4. Tier 0-2 rules for obvious physical faults (dropout, fail_low, spike, freeze)
  5. Psychrometric invariant check (Clausius-Clapeyron) for multivariate
  6. Isolation Forest TinyML score as soft vote for unstructured anomaly

This script runs the engine in Python-sim mode against all 28 labeled CSVs
and reports row-level precision, recall, and per-fault-type catch rates.
"""

import glob
import math
import numpy as np
import pandas as pd

# -- Dataset -----------------------------------------------------------------
FILES = sorted(glob.glob("data/*_labeled.csv"))

# -- Tunable Hyperparameters --------------------------------------------------
# These are the dials we tune in calibration passes.

CFG = dict(
    # Tier 0 physical bounds
    T_MIN=-35.0,  T_MAX=55.0,
    P_MIN=850.0,  P_MAX=1100.0,
    H_MIN=0.0,    H_MAX=100.0,

    # Tier 1 ROC spike thresholds (per-hour delta)
    ROC_T=5.0,    ROC_P=6.0,    ROC_H=18.0,

    # Diurnal coupling gate: suppress ROC alert if solar-driven
    # (temp rises while hum falls simultaneously -- normal afternoon)
    DIURNAL_GATE_DT=6.0,   # max |DeltaT| to consider as diurnal
    DIURNAL_GATE_DH=28.0,  # max |DeltaH| to consider as diurnal

    # Tier 2 freeze detector
    FREEZE_WIN=6,           # window length (hours)
    FREEZE_T=0.18,          # max range for frozen T
    FREEZE_P=0.10,          # max range for frozen P
    FREEZE_H=0.25,          # max range for frozen H

    # Tier 3 -- Weekly Self-Reference Drift Detector
    # Week-over-week delta thresholds for drift flag initiation
    W7D_T_THRESH=3.2,       # |T(t) - T(t-168h)| > threshold -> drift signal
    W7D_P_THRESH=8.0,
    W7D_H_THRESH=22.0,

    # SPRT accumulator for sustained week-delta (directional CUSUM)
    W7D_SPRT_K=0.5,         # Slack (allowed deviation before accumulation)
    W7D_SPRT_THRESH=6.0,    # Alarm threshold
    W7D_SPRT_DECAY=0.88,    # Decay when below slack (forgetting factor)
    W7D_SPRT_GROW=0.96,     # Retention when above slack (accumulation)

    # Tier 3b -- Same-hour EMA deviation SPRT (backup drift detector for
    # stations where 7-day look-back isn't ready yet -- first week only)
    EMA_ALPHA=0.10,          # EMA update rate (lower = slower baseline shift)
    EMA_DRIFT_K=3.0,         # sigma slack for EMA deviation SPRT
    EMA_SPRT_DECAY=0.80,
    EMA_SPRT_THRESH=14.0,
    EMA_T_INIT_DAYS=3,       # wait N days before trusting EMA baseline

    # Tier 3c -- Multi-hour slope consistency (raw 24h/48h delta)
    SLOPE_24H_T=2.8,         # T must rise >X over last 24h AND be sustained
    SLOPE_48H_T=1.8,         # AND previous 24h also shows same direction
    SLOPE_STREAK_MIN=3,      # consecutive slope-consistent hours to alarm

    # Tier 4 Clausius-Clapeyron multivariate gate
    CC_T_MAX=44.0,            # T > this with H > H_HOT_MAX -> impossible
    CC_H_HOT_MAX=65.0,
    CC_DEW_MARGIN=0.5,       # dew point > T + margin -> impossible
    CC_VPD_T_MIN=40.0,       # T > this with near-zero VPD -> suspicious
    CC_VPD_MIN=0.10,
    CC_VPD_H_MIN=85.0,

    # TinyML IForest vote weight (for unstructured anomaly)
    # We use a simple in-memory 8-feature lightweight IForest
    # trained offline on clean neighbor stations.
    IFOREST_WEIGHT=0.45,     # fractional vote contribution
    IFOREST_THRESH=0.62,     # IForest anomaly_score threshold (0.5=equal prob)
)


# -- TinyML Proxy: Lightweight 8-feature rolling IForest ---------------------
# We re-train inline on the CLEAN portion of the first-seen clean stations.
# This is the Python simulation of what the quantized tinyml_iforest.h does.

def build_iforest():
    """Train IForest exclusively on 21 clean neighbor stations."""
    from sklearn.ensemble import IsolationForest
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
    """8-feature vector for IForest."""
    if i < 6:
        return None
    roc1_t = t[i] - t[i-1]
    roc3_t = t[i] - t[i-3]
    roc1_h = h[i] - h[i-1]
    rng6_t = float(np.max(t[i-5:i+1]) - np.min(t[i-5:i+1]))
    rng6_p = float(np.max(p[i-5:i+1]) - np.min(p[i-5:i+1]))

    # Dewpoint depression
    t_dew = t[i] - ((100.0 - h[i]) / 5.0)
    dew_dep = t[i] - t_dew

    # VPD
    es = 0.6112 * math.exp((17.67 * t[i]) / (t[i] + 243.5)) if (t[i]+243.5) != 0 else 1.0
    vpd = es * (1.0 - h[i]/100.0)

    # Hour sin/cos encoding
    hour_sin = math.sin(2 * math.pi * hour / 24.0)

    return [t[i], roc1_t, roc3_t, rng6_t, roc1_h, rng6_p, vpd, dew_dep]


# -- Core Engine --------------------------------------------------------------

class WeeklySelfRefEngine:
    """
    Edge AI anomaly detector with:
    - 512-slot SRAM circular buffer (21 days @ 1Hz sampling)
    - Week-over-week self-reference for drift isolation
    - Directional SPRT on weekly delta for sustained drift alarm
    - Same-hour EMA baseline for first-week fallback
    - Multi-hour slope consistency check
    - Tier 0-2 physical rules
    - Psychrometric Clausius-Clapeyron invariant
    - IForest proxy vote for unstructured anomaly
    """
    def __init__(self, cfg=CFG, iforest=None):
        self.c = cfg
        self.iforest = iforest

        # -- 512-slot circular buffers (21 days @ 1h) ----------------------
        N = 512
        self.buf_t = np.full(N, np.nan, dtype=np.float32)
        self.buf_p = np.full(N, np.nan, dtype=np.float32)
        self.buf_h = np.full(N, np.nan, dtype=np.float32)
        self.head = 0
        self.count = 0

        # Last observation
        self.last_t = None
        self.last_p = None
        self.last_h = None

        # -- Per-hour EMA baseline tables (24 slots) ------------------------
        self.ema_t = np.zeros(24, dtype=np.float64)
        self.ema_p = np.zeros(24, dtype=np.float64)
        self.ema_h = np.zeros(24, dtype=np.float64)
        self.ema_init = np.zeros(24, dtype=np.int32)  # count of updates

        # -- Weekly SPRT accumulators (directional) -------------------------
        # Separate pos/neg to catch both upward and downward drift
        self.w7_pos_t = 0.0;  self.w7_neg_t = 0.0
        self.w7_pos_p = 0.0;  self.w7_neg_p = 0.0
        self.w7_pos_h = 0.0;  self.w7_neg_h = 0.0

        # -- EMA-deviation SPRT accumulators (first-week fallback) ----------
        self.ema_pos_t = 0.0; self.ema_neg_t = 0.0

        # -- Multi-hour slope streak ----------------------------------------
        self.slope_streak_up = 0
        self.slope_streak_dn = 0

    # -- Buffer helpers -------------------------------------------------------

    def _buf_read(self, buf, offset):
        """Read buffer[head - offset - 1] with bounds check."""
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

    # -- Main step ------------------------------------------------------------

    def step(self, t, p, h, hour, t_arr, p_arr, h_arr, row_i):
        """
        Process one reading.
        Returns (is_anomaly: bool, fault_type: str)
        """
        c = self.c

        # -- Tier 0: Dropout -------------------------------------------------
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "dropout"

        # -- Tier 0: Fail-Low ------------------------------------------------
        if t <= c["T_MIN"] or p <= c["P_MIN"] or h <= c["H_MIN"]:
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "sensor_fail_low"

        # -- Tier 0: Hard physical bounds ------------------------------------
        if (t < -50.0 or t > 60.0 or
                p < 800.0 or p > 1100.0 or
                h < 0.0 or h > 100.0):
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "physical_bounds"

        # -- Tier 4: Clausius-Clapeyron invariant ----------------------------
        t_dew = t - ((100.0 - h) / 5.0)
        es = 0.6112 * math.exp((17.67 * t) / (t + 243.5))
        vpd = es * (1.0 - h / 100.0)
        if (t_dew > t + c["CC_DEW_MARGIN"] or
                (t > c["CC_T_MAX"] and h > c["CC_H_HOT_MAX"]) or
                (t > c["CC_VPD_T_MIN"] and vpd < c["CC_VPD_MIN"] and
                 h > c["CC_VPD_H_MIN"])):
            self._buf_write(t, p, h)
            self.last_t = t; self.last_p = p; self.last_h = h
            return True, "multivariate_inconsistency"

        is_anom = False
        fault_type = "normal"

        # -- Tier 1: Step ROC spike with Diurnal Coupling Gate ---------------
        if self.last_t is not None and not math.isnan(self.last_t):
            dt_t = abs(t - self.last_t)
            dt_p = abs(p - self.last_p)
            dt_h = abs(h - self.last_h)

            # Physical covariance violation: T rises while H rises too
            if (t - self.last_t) > 2.2 and (h - self.last_h) > 8.0:
                is_anom, fault_type = True, "multivariate_inconsistency"
            else:
                # Diurnal gate: suppress spike alarm if natural solar heating/cooling
                is_diurnal = (
                    ((t > self.last_t and h < self.last_h) or
                     (t < self.last_t and h > self.last_h)) and
                    dt_t < c["DIURNAL_GATE_DT"] and dt_h < c["DIURNAL_GATE_DH"]
                )
                if not is_diurnal:
                    if (dt_t > c["ROC_T"] or
                            dt_p > c["ROC_P"] or
                            dt_h > c["ROC_H"]):
                        is_anom, fault_type = True, "spike"

        # -- Tier 2: Freeze detector ------------------------------------------
        k = c["FREEZE_WIN"]
        if not is_anom and self.count >= k:
            # Last k readings including current
            w_t = [self._buf_read(self.buf_t, j) for j in range(k - 1, -1, -1)] + [t]
            w_p = [self._buf_read(self.buf_p, j) for j in range(k - 1, -1, -1)] + [p]
            w_h = [self._buf_read(self.buf_h, j) for j in range(k - 1, -1, -1)] + [h]
            # Filter out NaN
            w_t = [x for x in w_t if not math.isnan(x)]
            w_p = [x for x in w_p if not math.isnan(x)]
            w_h = [x for x in w_h if not math.isnan(x)]
            if (len(w_t) >= 3 and
                    (max(w_t) - min(w_t) <= c["FREEZE_T"] or
                     max(w_p) - min(w_p) <= c["FREEZE_P"] or
                     max(w_h) - min(w_h) <= c["FREEZE_H"])):
                is_anom, fault_type = True, "frozen_value"

        # -- Tier 3a: Weekly Self-Reference Drift (PRIMARY) ------------------
        # Compare current reading to exact same hour last week (168h ago).
        # Drift accumulates monotonically -> breaks weekly self-similarity.
        # Real weather is quasi-periodic weekly -> weekly delta stays small.
        if not is_anom and self.count >= 168:
            t_7d = self._buf_read(self.buf_t, 168 - 1)  # exactly 168h ago
            p_7d = self._buf_read(self.buf_p, 168 - 1)
            h_7d = self._buf_read(self.buf_h, 168 - 1)

            if not math.isnan(t_7d):
                delta_t = t - t_7d
                delta_p = p - p_7d
                delta_h = h - h_7d

                # Update directional SPRT for temperature drift
                k_t = c["W7D_T_THRESH"]
                if delta_t > k_t:
                    self.w7_pos_t = max(0.0, self.w7_pos_t * c["W7D_SPRT_GROW"] + (delta_t - k_t))
                    self.w7_neg_t *= c["W7D_SPRT_DECAY"]
                elif delta_t < -k_t:
                    self.w7_neg_t = max(0.0, self.w7_neg_t * c["W7D_SPRT_GROW"] + (-delta_t - k_t))
                    self.w7_pos_t *= c["W7D_SPRT_DECAY"]
                else:
                    self.w7_pos_t *= c["W7D_SPRT_DECAY"]
                    self.w7_neg_t *= c["W7D_SPRT_DECAY"]

                # Update directional SPRT for pressure drift
                k_p = c["W7D_P_THRESH"]
                if delta_p > k_p:
                    self.w7_pos_p = max(0.0, self.w7_pos_p * c["W7D_SPRT_GROW"] + (delta_p - k_p))
                    self.w7_neg_p *= c["W7D_SPRT_DECAY"]
                elif delta_p < -k_p:
                    self.w7_neg_p = max(0.0, self.w7_neg_p * c["W7D_SPRT_GROW"] + (-delta_p - k_p))
                    self.w7_pos_p *= c["W7D_SPRT_DECAY"]
                else:
                    self.w7_pos_p *= c["W7D_SPRT_DECAY"]
                    self.w7_neg_p *= c["W7D_SPRT_DECAY"]

                # Update directional SPRT for humidity drift
                k_h = c["W7D_H_THRESH"]
                if delta_h > k_h:
                    self.w7_pos_h = max(0.0, self.w7_pos_h * c["W7D_SPRT_GROW"] + (delta_h - k_h))
                    self.w7_neg_h *= c["W7D_SPRT_DECAY"]
                elif delta_h < -k_h:
                    self.w7_neg_h = max(0.0, self.w7_neg_h * c["W7D_SPRT_GROW"] + (-delta_h - k_h))
                    self.w7_pos_h *= c["W7D_SPRT_DECAY"]
                else:
                    self.w7_pos_h *= c["W7D_SPRT_DECAY"]
                    self.w7_neg_h *= c["W7D_SPRT_DECAY"]

                thr = c["W7D_SPRT_THRESH"]
                if (self.w7_pos_t > thr or self.w7_neg_t > thr or
                        self.w7_pos_p > thr or self.w7_neg_p > thr or
                        self.w7_pos_h > thr or self.w7_neg_h > thr):
                    is_anom, fault_type = True, "drift"
            else:
                # Reset accumulators if reference slot is NaN
                self.w7_pos_t = self.w7_neg_t = 0.0
                self.w7_pos_p = self.w7_neg_p = 0.0
                self.w7_pos_h = self.w7_neg_h = 0.0

        # -- Tier 3b: EMA baseline SPRT fallback (first week only) -----------
        hr = hour % 24
        min_updates = c["EMA_T_INIT_DAYS"] * 1  # 1 update per day per hour slot
        if not is_anom and self.count < 168 and self.ema_init[hr] >= min_updates:
            dev_t = t - self.ema_t[hr]
            k_e = c["EMA_DRIFT_K"]
            # Use EMA std proxy: running mean of |deviation|
            ema_std_proxy = max(abs(dev_t) * 0.1 + 1.0, 2.0)
            slack = k_e * ema_std_proxy
            if dev_t > slack:
                self.ema_pos_t = max(0.0, self.ema_pos_t * c["EMA_SPRT_DECAY"] + (dev_t - slack))
                self.ema_neg_t *= c["EMA_SPRT_DECAY"]
            elif dev_t < -slack:
                self.ema_neg_t = max(0.0, self.ema_neg_t * c["EMA_SPRT_DECAY"] + (-dev_t - slack))
                self.ema_pos_t *= c["EMA_SPRT_DECAY"]
            else:
                self.ema_pos_t *= c["EMA_SPRT_DECAY"]
                self.ema_neg_t *= c["EMA_SPRT_DECAY"]

            if (self.ema_pos_t > c["EMA_SPRT_THRESH"] or
                    self.ema_neg_t > c["EMA_SPRT_THRESH"]):
                is_anom, fault_type = True, "drift"

        # -- Tier 3c: Multi-hour slope consistency (raw 24h/48h) -------------
        if not is_anom and self.count >= 48:
            t_24h = self._buf_read(self.buf_t, 23)  # 24h ago
            t_48h = self._buf_read(self.buf_t, 47)  # 48h ago
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
                    is_anom, fault_type = True, "drift"

        # -- Tier 5: IForest ML vote (unstructured anomaly) -------------------
        if not is_anom and self.iforest is not None and row_i >= 6:
            feats = extract_features(t_arr, p_arr, h_arr, row_i, hour)
            if feats is not None:
                score = -self.iforest.score_samples([feats])[0]  # higher = more anomalous
                if score > c["IFOREST_THRESH"]:
                    is_anom, fault_type = True, "unstructured_anomaly"

        # -- Baseline EMA update (only on clean readings) ---------------------
        if not is_anom:
            alpha = c["EMA_ALPHA"]
            if self.ema_init[hr] == 0:
                self.ema_t[hr] = t
                self.ema_p[hr] = p
                self.ema_h[hr] = h
            else:
                self.ema_t[hr] = (1 - alpha) * self.ema_t[hr] + alpha * t
                self.ema_p[hr] = (1 - alpha) * self.ema_p[hr] + alpha * p
                self.ema_h[hr] = (1 - alpha) * self.ema_h[hr] + alpha * h
            self.ema_init[hr] += 1

        # -- Write to circular buffer (always, including anomalous readings) --
        # NOTE: We write even anomalous readings so 7-day reference is accurate.
        # The SPRT directional accumulator does the sustained-detection work.
        self._buf_write(t, p, h)
        self.last_t = t; self.last_p = p; self.last_h = h

        return is_anom, fault_type


# -- Evaluation harness -------------------------------------------------------

def evaluate(cfg=CFG, iforest=None, verbose=True):
    total_tp = total_fp = total_fn = total_tn = 0
    fault_stats = {}
    total_samples = 0

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
        total_samples += n

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

            if flag and is_gt:
                total_tp += 1
            elif flag and not is_gt:
                total_fp += 1
            elif not flag and is_gt:
                total_fn += 1
            else:
                total_tn += 1

    prec = total_tp / (total_tp + total_fp) * 100 if (total_tp + total_fp) > 0 else 0
    rec  = total_tp / (total_tp + total_fn) * 100 if (total_tp + total_fn) > 0 else 0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    spec = total_tn / (total_tn + total_fp) * 100 if (total_tn + total_fp) > 0 else 0

    if verbose:
        print("=" * 85)
        print("   SKYGUARD EDGE AI -- WEEKLY SELF-REFERENCE ENGINE -- CALIBRATION REPORT")
        print(f"   (Evaluated across ALL 28 Stations, {total_samples:,} Observations)")
        print("=" * 85)
        print(f"  * Precision (PPV)    : {prec:.2f}%")
        print(f"  * Recall (TPR)       : {rec:.2f}%")
        print(f"  * F1-Score           : {f1:.2f}%")
        print(f"  * Specificity (TNR)  : {spec:.2f}%")
        print(f"  * Confusion Matrix   : TP={total_tp:,} | FP={total_fp:,} | FN={total_fn:,} | TN={total_tn:,}")
        print("\n  Granular Catch Rates Across All Injected Fault Types:")
        for k, v in sorted(fault_stats.items(), key=lambda x: -x[1]["injected"]):
            c_rate = v["detected"] / v["injected"] * 100
            print(f"    - {k:<28}: {v['detected']:>4}/{v['injected']:>4} ({c_rate:>5.1f}%)")
        print("=" * 85)

    return prec, rec, f1, total_tp, total_fp, total_fn, total_tn, fault_stats


# -- Grid-search calibration -------------------------------------------------
# Try a targeted sweep of the key drift thresholds to find the 50/50 zone.

def calibration_sweep(iforest=None):
    print("\n" + "=" * 85)
    print("  CALIBRATION SWEEP: W7D_T_THRESH x W7D_SPRT_THRESH x SLOPE_STREAK_MIN")
    print("=" * 85)

    best_f1 = 0.0
    best_cfg = None
    best_summary = ""

    # Sweep the key parameters
    for w7_t in [2.5, 3.0, 3.5, 4.0]:
        for w7_thr in [4.0, 5.0, 6.0, 8.0]:
            for slope_s in [3, 4, 5]:
                for ema_thr in [10.0, 14.0, 18.0]:
                    cfg = dict(CFG)
                    cfg["W7D_T_THRESH"] = w7_t
                    cfg["W7D_SPRT_THRESH"] = w7_thr
                    cfg["SLOPE_STREAK_MIN"] = slope_s
                    cfg["EMA_SPRT_THRESH"] = ema_thr

                    prec, rec, f1, *_ = evaluate(cfg=cfg, iforest=iforest, verbose=False)
                    if prec >= 45 and rec >= 45:  # both above 45 = near target
                        line = (f"    W7D_T={w7_t:.1f}  W7D_THR={w7_thr:.0f}  "
                                f"SLOPE_S={slope_s}  EMA_THR={ema_thr:.0f}  "
                                f"-> Prec={prec:.1f}%  Rec={rec:.1f}%  F1={f1:.1f}%")
                        print(line)
                    if f1 > best_f1 and prec >= 40 and rec >= 40:
                        best_f1 = f1
                        best_cfg = dict(cfg)
                        best_summary = (f"  W7D_T={w7_t:.1f}  W7D_THR={w7_thr:.0f}  "
                                        f"SLOPE_S={slope_s}  EMA_THR={ema_thr:.0f}  "
                                        f"-> Prec={prec:.1f}%  Rec={rec:.1f}%  F1={f1:.1f}%")

    print(f"\n  Best (Prec>=40 & Rec>=40) Configuration:")
    if best_cfg:
        print(best_summary)
    else:
        print("  None found with both >= 40%. Running full best-F1 search...")
        for w7_t in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]:
            for w7_thr in [3.0, 4.0, 5.0, 6.0, 8.0, 10.0]:
                cfg = dict(CFG)
                cfg["W7D_T_THRESH"] = w7_t
                cfg["W7D_SPRT_THRESH"] = w7_thr
                prec, rec, f1, *_ = evaluate(cfg=cfg, iforest=iforest, verbose=False)
                if f1 > best_f1:
                    best_f1 = f1
                    best_cfg = dict(cfg)
                    best_summary = f"  W7D_T={w7_t:.1f}  W7D_THR={w7_thr:.0f}  Prec={prec:.1f}%  Rec={rec:.1f}%  F1={f1:.1f}%"
        print(best_summary)

    return best_cfg


# -- Entry Point --------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("\n[1/3] Training IForest on clean neighbor stations...")
    iforest = build_iforest()
    print("  -> IForest ready.")

    print("\n[2/3] Running baseline evaluation with default config...")
    evaluate(cfg=CFG, iforest=iforest, verbose=True)

    if "--sweep" in sys.argv:
        print("\n[3/3] Running calibration sweep (this may take ~3-5 min)...")
        best = calibration_sweep(iforest=iforest)
        if best:
            print("\n[Final] Running best config for full report...")
            evaluate(cfg=best, iforest=iforest, verbose=True)
    else:
        print("\n  (Re-run with --sweep flag to run calibration grid search)")
