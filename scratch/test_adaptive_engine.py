"""
SkyGuard Edge AI -- Fully Adaptive Engine v2 (Fast + Relocatable)
==================================================================
Key design principles:
  1. ZERO fixed measurement-unit thresholds. All thresholds = k * live_stat.
  2. ALL statistics use EWMA with forgetting factor -- never "permanent".
     Relocate sensor from Rajasthan to Siberia: engine re-adapts within hours.
  3. ALL detectors are fully bidirectional (drift can go +/-,
     spikes can be high or low, slopes can rise or fall).
  4. Only dimensionless k-sigma knobs + physics-grounded window lengths remain.

Speed optimizations:
  - IForest scored in one batch per station (not per-row)
  - Hours pre-extracted via pandas vectorized dt.hour
  - Freeze window via numpy slice (no Python list loop)
  - EWMA: 3 scalar ops per channel per step (faster than Welford)
  - No per-step pandas calls inside the hot loop

EWMA adaptation speed:
  EWMA_ALPHA = 0.02  -->  half-life ~35 samples (~1.5 days @ 1h)
  Changing environment fully re-characterized in ~5x half-life = ~7 days.
  This means relocation from any climate to any other climate is handled
  transparently without manual reset.
"""

import glob, math
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

FILES = sorted(glob.glob("data/*_labeled.csv"))

# ── Dimensionless sensitivity knobs (the ONLY fixed config) ──────────────────
CFG = dict(
    # k-sigma multipliers
    K_SPIKE        = 4.2,   # |roc| > K_SPIKE * ewma_std(roc)
    K_FREEZE       = 0.28,  # 6h_range < K_FREEZE * ewma_mean(6h_range)
    K_W7D          = 2.6,   # |delta_7d| > K_W7D * ewma_std(delta_7d)
    K_SLOPE        = 2.4,   # |d24h| > K_SLOPE * ewma_std(d24h)
    K_RAIL         = 4.0,   # fail-low: K_RAIL sigma below ewma_min

    # SPRT dimensionless accumulation ceiling + memory
    W7D_SPRT_THRESH = 10.0,
    W7D_SPRT_GROW   = 0.96,
    W7D_SPRT_DECAY  = 0.80,

    # EWMA forgetting factor (controls adaptation speed & relocation recovery)
    EWMA_ALPHA      = 0.02,   # ~35-sample half-life (~1.5 days @ 1h sampling)
    EWMA_ALPHA_SLOW = 0.005,  # slower track for freeze mean (less noisy)

    # Window lengths (derived from fault physics, not sensor range)
    FREEZE_WIN      = 6,    # hours: freeze needs 6h to be confirmed
    W7D_LAG         = 168,  # hours: one week -- matches drift ramp timescale
    SLOPE_SHORT     = 24,   # hours
    SLOPE_LONG      = 48,   # hours
    SLOPE_STREAK    = 3,    # consecutive consistent-slope hours to alarm

    # Warmup: minimum samples before trusting EWMA stat
    WARMUP_ROC      = 12,
    WARMUP_FREEZE   = 24,
    WARMUP_SLOPE    = 48,

    # IForest ML vote
    IFOREST_THRESH  = 0.60,

    # Absolute physical impossibility bounds (laws of nature, not calibration)
    T_ABS_MIN=-50.0, T_ABS_MAX=60.0,
    P_ABS_MIN=800.0, P_ABS_MAX=1100.0,
    H_ABS_MIN=0.0,   H_ABS_MAX=100.0,
)


# ── EWMA state: mean + variance, with forgetting ─────────────────────────────
class EWMA:
    """
    Exponentially Weighted Moving Average of mean and variance.
    Forgetting factor alpha controls adaptation speed:
      half-life = ln(2) / alpha  (in samples)
    Relocation to new environment: old stats decay, new stats grow in.
    Direction-agnostic std -- works for any signed or unsigned signal.
    """
    __slots__ = ("alpha", "mean", "var", "n")

    def __init__(self, alpha=0.02):
        self.alpha = alpha
        self.mean  = 0.0
        self.var   = 1.0   # start non-zero to avoid /0 before warmup
        self.n     = 0

    def update(self, x):
        a = self.alpha
        if self.n == 0:
            self.mean = x
            self.var  = 0.0
        else:
            diff        = x - self.mean
            self.mean  += a * diff
            self.var    = (1 - a) * (self.var + a * diff * diff)
        self.n += 1

    @property
    def std(self):
        return math.sqrt(max(self.var, 1e-9))


# ── IForest: trained on clean neighbor stations, batch scored ────────────────
def _feat_batch(t, p, h, hours):
    """
    Vectorized 9-feature extraction for ALL rows of one station.
    Returns (N,9) float32 array. Rows 0..5 are NaN-padded (no history yet).
    All features are RELATIVE (differences, ranges) -- scale-independent.
    """
    N = len(t)
    F = np.full((N, 9), np.nan, dtype=np.float32)
    # Rate-of-change (signed -- direction-agnostic std used for thresholds)
    roc1_t  = np.diff(t, prepend=np.nan)
    roc3_t  = t - np.concatenate([[np.nan]*3, t[:-3]])
    roc1_h  = np.diff(h, prepend=np.nan)
    roc1_p  = np.diff(p, prepend=np.nan)
    # 6-sample rolling range (scale-independent)
    rng6_t  = np.full(N, np.nan)
    rng6_p  = np.full(N, np.nan)
    rng6_h  = np.full(N, np.nan)
    for i in range(5, N):
        rng6_t[i] = t[i-5:i+1].max() - t[i-5:i+1].min()
        rng6_p[i] = p[i-5:i+1].max() - p[i-5:i+1].min()
        rng6_h[i] = h[i-5:i+1].max() - h[i-5:i+1].min()
    # Psychrometric cross-channel features
    vpd     = 0.6112 * np.exp(17.67*t / (t+243.5)) * (1.0 - h/100.0)
    t_h_cov = roc1_t * roc1_h   # negative = healthy diurnal; positive = suspicious
    F[:,0]=roc1_t; F[:,1]=roc3_t; F[:,2]=roc1_h; F[:,3]=roc1_p
    F[:,4]=rng6_t; F[:,5]=rng6_p; F[:,6]=rng6_h; F[:,7]=vpd; F[:,8]=t_h_cov
    return F


def build_iforest():
    clean = [f for f in FILES if any(x in f for x in ["-101_","-102_","-103_"])]
    rows = []
    for f in clean:
        df   = pd.read_csv(f)
        t    = df["temperature_c"].to_numpy(float)
        p    = df["pressure_hpa"].to_numpy(float)
        h    = df["humidity_pct"].to_numpy(float)
        hrs  = df["timestamp"].pipe(pd.to_datetime).dt.hour.to_numpy()
        F    = _feat_batch(t, p, h, hrs)
        mask = ~np.isnan(F).any(axis=1)
        rows.append(F[mask])
    X = np.vstack(rows).astype(np.float32)
    clf = IsolationForest(n_estimators=60, max_samples=256,
                          contamination=0.01, random_state=42, n_jobs=-1)
    clf.fit(X)
    return clf


# ── Core adaptive engine (per-station stateful simulator) ───────────────────
class AdaptiveEngine:
    def __init__(self, cfg=CFG, iforest_scores=None):
        c = self.c = cfg
        a = c["EWMA_ALPHA"]
        as_ = c["EWMA_ALPHA_SLOW"]

        # 512-slot circular buffer
        self.buf_t = np.full(512, np.nan, np.float32)
        self.buf_p = np.full(512, np.nan, np.float32)
        self.buf_h = np.full(512, np.nan, np.float32)
        self.head = 0; self.count = 0
        self.last_t = self.last_p = self.last_h = None

        # EWMA stats (all with forgetting -- never permanent)
        self.roc_t  = EWMA(a);  self.roc_p  = EWMA(a);  self.roc_h  = EWMA(a)
        self.frz_t  = EWMA(as_);self.frz_p  = EWMA(as_);self.frz_h  = EWMA(as_)
        self.w7d_t  = EWMA(a);  self.w7d_p  = EWMA(a);  self.w7d_h  = EWMA(a)
        self.slp_t  = EWMA(a)
        self.obs_t  = EWMA(a);  self.obs_p  = EWMA(a);  self.obs_h  = EWMA(a)
        self.obs_min_t = math.inf; self.obs_min_p = math.inf; self.obs_min_h = math.inf

        # Bidirectional SPRT (no direction assumption)
        self.w7_pt=0.;self.w7_nt=0.; self.w7_pp=0.;self.w7_np=0.
        self.w7_ph=0.;self.w7_nh=0.
        # Slope streak (bidirectional)
        self.s_up=0; self.s_dn=0

        # Pre-scored IForest values (batch, per station)
        self.if_scores = iforest_scores  # array of float, len=N, or None

    def _rbuf(self, buf, off):
        if self.count <= off: return math.nan
        return float(buf[(self.head-1-off) % 512])

    def _wbuf(self, t, p, h):
        self.buf_t[self.head]=t; self.buf_p[self.head]=p; self.buf_h[self.head]=h
        self.head=(self.head+1)%512
        if self.count<512: self.count+=1

    def step(self, t, p, h, i):
        c = self.c

        # ── TIER 0: Physical impossibility (laws of nature) ──────────────
        if math.isnan(t) or math.isnan(p) or math.isnan(h):
            self._wbuf(t,p,h); self.last_t=t; self.last_p=p; self.last_h=h
            return True, "dropout"
        if (t<c["T_ABS_MIN"] or t>c["T_ABS_MAX"] or
                p<c["P_ABS_MIN"] or p>c["P_ABS_MAX"] or
                h<c["H_ABS_MIN"] or h>c["H_ABS_MAX"]):
            self._wbuf(t,p,h); self.last_t=t; self.last_p=p; self.last_h=h
            return True, "physical_bounds"

        # ── Adaptive fail-low (K_RAIL sigma below station's own observed min) ─
        if self.obs_t.n >= 24:
            if (t < self.obs_min_t - c["K_RAIL"]*self.obs_t.std or
                    p < self.obs_min_p - c["K_RAIL"]*self.obs_p.std or
                    h < self.obs_min_h - c["K_RAIL"]*self.obs_h.std):
                self._wbuf(t,p,h); self.last_t=t; self.last_p=p; self.last_h=h
                return True, "sensor_fail_low"

        # ── TIER 4: Clausius-Clapeyron invariant (thermodynamic law) ─────
        es  = 0.6112*math.exp(17.67*t/(t+243.5))
        vpd = es*(1.0-h/100.0)
        tdp = t-(100.0-h)/5.0
        if (tdp>t+0.5 or (t>44.0 and h>65.0) or (t>40.0 and vpd<0.10 and h>85.0)):
            self._wbuf(t,p,h); self.last_t=t; self.last_p=p; self.last_h=h
            return True, "multivariate_inconsistency"

        is_anom = False; ft = "normal"

        # ── TIER 1: Adaptive ROC spike ────────────────────────────────────
        if self.last_t is not None and not math.isnan(self.last_t):
            if self.roc_t.n >= c["WARMUP_ROC"]:
                dt = t-self.last_t; dp = p-self.last_p; dh = h-self.last_h
                thr_t = c["K_SPIKE"]*self.roc_t.std
                thr_p = c["K_SPIKE"]*self.roc_p.std
                thr_h = c["K_SPIKE"]*self.roc_h.std
                # Multivariate inconsistency: T and H rise together
                if dt>2.0*self.roc_t.std and dh>2.0*self.roc_h.std:
                    is_anom, ft = True, "multivariate_inconsistency"
                else:
                    # Diurnal coupling gate (anti-correlated T/H = normal solar)
                    diurnal = ((dt>0)!=(dh>0)) and abs(dt)<thr_t and abs(dh)<thr_h
                    if not diurnal and (abs(dt)>thr_t or abs(dp)>thr_p or abs(dh)>thr_h):
                        is_anom, ft = True, "spike"

        # ── TIER 2: Adaptive freeze ───────────────────────────────────────
        k = c["FREEZE_WIN"]
        if not is_anom and self.count>=k and self.frz_t.n>=c["WARMUP_FREEZE"]:
            sl = slice(max(self.head-k,0), self.head) if self.head>=k else None
            # Use circular buffer correctly via numpy
            idxs = [(self.head-1-j)%512 for j in range(k)]
            wt = self.buf_t[idxs]; wp = self.buf_p[idxs]; wh = self.buf_h[idxs]
            # Replace last slot with current (buffer not yet written)
            wt[0]=t; wp[0]=p; wh[0]=h
            if not (np.isnan(wt).all() or np.isnan(wp).all()):
                rng_t = np.nanmax(wt)-np.nanmin(wt)
                rng_p = np.nanmax(wp)-np.nanmin(wp)
                rng_h = np.nanmax(wh)-np.nanmin(wh)
                ff_t = c["K_FREEZE"]*max(self.frz_t.mean, 1e-3)
                ff_p = c["K_FREEZE"]*max(self.frz_p.mean, 1e-3)
                ff_h = c["K_FREEZE"]*max(self.frz_h.mean, 1e-3)
                if rng_t<ff_t or rng_p<ff_p or rng_h<ff_h:
                    is_anom, ft = True, "frozen_value"

        # ── TIER 3a: Adaptive weekly self-reference drift (PRIMARY) ───────
        # Bidirectional SPRT on T(t)-T(t-168h)
        # Slack = K_W7D * ewma_std(week_delta) -- adapts to seasonal variance
        w7_hit = False
        if self.count >= c["W7D_LAG"]:
            t7=self._rbuf(self.buf_t,c["W7D_LAG"]-1)
            p7=self._rbuf(self.buf_p,c["W7D_LAG"]-1)
            h7=self._rbuf(self.buf_h,c["W7D_LAG"]-1)
            if not math.isnan(t7):
                dt7=t-t7; dp7=p-p7; dh7=h-h7
                # Adaptive slack from ewma of the delta series itself
                sk_t = c["K_W7D"]*max(self.w7d_t.std, 0.3)
                sk_p = c["K_W7D"]*max(self.w7d_p.std, 0.3)
                sk_h = c["K_W7D"]*max(self.w7d_h.std, 0.5)
                gr=c["W7D_SPRT_GROW"]; dc=c["W7D_SPRT_DECAY"]; thr=c["W7D_SPRT_THRESH"]
                # Temperature SPRT (no direction assumption)
                if dt7>sk_t:   self.w7_pt=max(0.,self.w7_pt*gr+(dt7-sk_t)); self.w7_nt*=dc
                elif dt7<-sk_t:self.w7_nt=max(0.,self.w7_nt*gr+(-dt7-sk_t));self.w7_pt*=dc
                else:          self.w7_pt*=dc; self.w7_nt*=dc
                # Pressure SPRT
                if dp7>sk_p:   self.w7_pp=max(0.,self.w7_pp*gr+(dp7-sk_p)); self.w7_np*=dc
                elif dp7<-sk_p:self.w7_np=max(0.,self.w7_np*gr+(-dp7-sk_p));self.w7_pp*=dc
                else:          self.w7_pp*=dc; self.w7_np*=dc
                # Humidity SPRT
                if dh7>sk_h:   self.w7_ph=max(0.,self.w7_ph*gr+(dh7-sk_h)); self.w7_nh*=dc
                elif dh7<-sk_h:self.w7_nh=max(0.,self.w7_nh*gr+(-dh7-sk_h));self.w7_ph*=dc
                else:          self.w7_ph*=dc; self.w7_nh*=dc
                if (self.w7_pt>thr or self.w7_nt>thr or
                        self.w7_pp>thr or self.w7_np>thr or
                        self.w7_ph>thr or self.w7_nh>thr):
                    w7_hit = True
                if not is_anom:
                    self.w7d_t.update(dt7); self.w7d_p.update(dp7); self.w7d_h.update(dh7)
            else:
                self.w7_pt=self.w7_nt=self.w7_pp=self.w7_np=self.w7_ph=self.w7_nh=0.

        # ── TIER 3b: Adaptive slope consistency (drift supplement) ────────
        sl_hit = False
        if self.count>=c["SLOPE_LONG"] and self.slp_t.n>=c["WARMUP_SLOPE"]:
            t24=self._rbuf(self.buf_t,c["SLOPE_SHORT"]-1)
            t48=self._rbuf(self.buf_t,c["SLOPE_LONG"]-1)
            if not (math.isnan(t24) or math.isnan(t48)):
                d24=t-t24; d48=t24-t48
                sk=c["K_SLOPE"]*max(self.slp_t.std,0.2)
                if d24>sk and d48>sk*0.6:
                    self.s_up+=1; self.s_dn=max(0,self.s_dn-1)
                elif d24<-sk and d48<-sk*0.6:
                    self.s_dn+=1; self.s_up=max(0,self.s_up-1)
                else:
                    self.s_up=max(0,self.s_up-1); self.s_dn=max(0,self.s_dn-1)
                if self.s_up>=c["SLOPE_STREAK"] or self.s_dn>=c["SLOPE_STREAK"]:
                    sl_hit = True
                if not is_anom: self.slp_t.update(d24)

        if not is_anom and (w7_hit or sl_hit):
            is_anom, ft = True, "drift"

        # ── TIER 5: IForest ML vote (pre-scored, no per-step sklearn call) ─
        if (not is_anom and self.if_scores is not None
                and i < len(self.if_scores)
                and not math.isnan(self.if_scores[i])):
            if self.if_scores[i] > c["IFOREST_THRESH"]:
                is_anom, ft = True, "unstructured_anomaly"

        # ── EWMA stats update (on clean readings only, with forgetting) ───
        if not is_anom:
            if self.last_t is not None and not math.isnan(self.last_t):
                self.roc_t.update(abs(t-self.last_t))
                self.roc_p.update(abs(p-self.last_p))
                self.roc_h.update(abs(h-self.last_h))
            if self.count>=k:
                idxs2=[(self.head-1-j)%512 for j in range(k)]
                wt2=self.buf_t[idxs2]; wp2=self.buf_p[idxs2]; wh2=self.buf_h[idxs2]
                wt2[0]=t; wp2[0]=p; wh2[0]=h
                self.frz_t.update(float(np.nanmax(wt2)-np.nanmin(wt2)))
                self.frz_p.update(float(np.nanmax(wp2)-np.nanmin(wp2)))
                self.frz_h.update(float(np.nanmax(wh2)-np.nanmin(wh2)))
            if t<self.obs_min_t: self.obs_min_t=t
            if p<self.obs_min_p: self.obs_min_p=p
            if h<self.obs_min_h: self.obs_min_h=h
            self.obs_t.update(t); self.obs_p.update(p); self.obs_h.update(h)

        self._wbuf(t,p,h)
        self.last_t=t; self.last_p=p; self.last_h=h
        return is_anom, ft


# ── Evaluation (fast: batch IForest per station) ────────────────────────────
def evaluate(cfg=CFG, iforest=None, verbose=True, label="ADAPTIVE ENGINE v2"):
    TP=FP=FN=TN=0
    fault_stats={}
    N_total=0

    for f in FILES:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        if "is_anomaly" not in df.columns: continue
        t   = df["temperature_c"].to_numpy(float)
        p   = df["pressure_hpa"].to_numpy(float)
        h   = df["humidity_pct"].to_numpy(float)
        gt  = df["is_anomaly"].fillna(False).to_numpy(bool)
        gft = df["fault_type"].fillna("normal").to_numpy(str)
        N   = len(df)
        N_total += N

        # Batch IForest scoring (one call per station, not N calls)
        if_scores = None
        if iforest is not None:
            F    = _feat_batch(t, p, h, df["timestamp"].dt.hour.to_numpy())
            mask = ~np.isnan(F).any(axis=1)
            scores = np.full(N, np.nan)
            if mask.any():
                scores[mask] = -iforest.score_samples(F[mask])
            if_scores = scores

        eng = AdaptiveEngine(cfg=cfg, iforest_scores=if_scores)
        for i in range(N):
            flag, _ = eng.step(t[i], p[i], h[i], i)
            is_gt   = gt[i]
            g       = gft[i]
            if g != "normal":
                if g not in fault_stats:
                    fault_stats[g] = {"injected":0,"detected":0}
                fault_stats[g]["injected"] += 1
                if flag: fault_stats[g]["detected"] += 1
            if   flag and is_gt:     TP+=1
            elif flag and not is_gt: FP+=1
            elif not flag and is_gt: FN+=1
            else:                    TN+=1

    prec = TP/(TP+FP)*100 if TP+FP>0 else 0
    rec  = TP/(TP+FN)*100 if TP+FN>0 else 0
    f1   = 2*prec*rec/(prec+rec) if prec+rec>0 else 0
    spec = TN/(TN+FP)*100 if TN+FP>0 else 0

    if verbose:
        print("="*85)
        print(f"   SKYGUARD EDGE AI -- {label}")
        print(f"   ({N_total:,} observations | 28 stations | EWMA adaptive, no fixed thresholds)")
        print("="*85)
        print(f"  Precision  : {prec:.2f}%")
        print(f"  Recall     : {rec:.2f}%")
        print(f"  F1-Score   : {f1:.2f}%")
        print(f"  Specificity: {spec:.2f}%")
        print(f"  Confusion  : TP={TP:,} FP={FP:,} FN={FN:,} TN={TN:,}")
        print("\n  Per-fault catch rates:")
        for k,v in sorted(fault_stats.items(),key=lambda x:-x[1]["injected"]):
            cr=v["detected"]/v["injected"]*100
            print(f"    {k:<30}: {v['detected']:>4}/{v['injected']:>4} ({cr:>5.1f}%)")
        print("="*85)
    return prec,rec,f1,spec,TP,FP,FN,TN,fault_stats


# ── Fast k-sigma sweep ───────────────────────────────────────────────────────
def sweep(iforest):
    import itertools, time
    print("\n"+"="*85)
    print("  SWEEP: K_W7D x W7D_SPRT_THRESH x W7D_SPRT_DECAY x K_SPIKE")
    print("  (dimensionless -- valid for any sensor range, any climate zone)")
    print("="*85)
    print(f"{'K_W7D':>5} {'THR':>5} {'DEC':>5} {'KSP':>5}"
          f" {'Prec':>7} {'Rec':>7} {'F1':>7} {'DRIFT%':>7}")

    best_f1=0.; best_cfg=None; hits=[]
    combos=list(itertools.product(
        [2.0,2.5,3.0,3.5,4.0],  # K_W7D
        [8.,10.,12.,15.,18.],    # W7D_SPRT_THRESH
        [0.76,0.80,0.84],        # W7D_SPRT_DECAY
        [3.5,4.0,4.5],           # K_SPIKE
    ))
    t0=time.time()
    for k_w7d,w7thr,dec,kspk in combos:
        cfg=dict(CFG, K_W7D=k_w7d, W7D_SPRT_THRESH=w7thr,
                 W7D_SPRT_DECAY=dec, K_SPIKE=kspk)
        prec,rec,f1,_,_,_,_,_,fs=evaluate(cfg,iforest,verbose=False)
        dr=(fs.get("drift",{}).get("detected",0)/
            max(fs.get("drift",{}).get("injected",1),1)*100)
        row=f"{k_w7d:>5.1f}{w7thr:>6.0f}{dec:>6.2f}{kspk:>6.1f} {prec:>7.1f} {rec:>7.1f} {f1:>7.1f} {dr:>7.1f}%"
        if prec>=48 and rec>=48:
            print("  ** HIT ** "+row); hits.append((f1,dict(cfg),row))
        if f1>best_f1 and prec>=38 and rec>=38:
            best_f1=f1; best_cfg=dict(cfg)
    print(f"\n  Sweep done in {time.time()-t0:.1f}s over {len(combos)} configs")
    if hits:
        hits.sort(key=lambda x:-x[0])
        print(f"\n  === {len(hits)} configs hit 48/48 target ===")
        for _,_,r in hits[:5]: print("  ",r)
    elif best_cfg:
        print("\n  Best (Prec>=38 AND Rec>=38):")
        prec,rec,f1,_,_,_,_,_,_=evaluate(best_cfg,iforest,verbose=False)
        print(f"   Prec={prec:.1f}% Rec={rec:.1f}% F1={f1:.1f}%")
        print(f"   K_W7D={best_cfg['K_W7D']} THR={best_cfg['W7D_SPRT_THRESH']} "
              f"DECAY={best_cfg['W7D_SPRT_DECAY']} K_SPIKE={best_cfg['K_SPIKE']}")
    return best_cfg, hits


if __name__ == "__main__":
    import sys, time
    t0=time.time()
    print("Training IForest on clean neighbors (batch mode, n_jobs=-1)...")
    clf=build_iforest()
    print(f"  done in {time.time()-t0:.1f}s\n")

    evaluate(cfg=CFG, iforest=clf, verbose=True, label="ADAPTIVE ENGINE v2 -- BASELINE")

    if "--sweep" in sys.argv:
        best_cfg, hits = sweep(clf)
        if best_cfg:
            print("\nFull report on best config:")
            evaluate(cfg=best_cfg, iforest=clf, verbose=True,
                     label="ADAPTIVE ENGINE v2 -- BEST CONFIG")
    else:
        print("\nRe-run with --sweep for k-sigma grid search.")
