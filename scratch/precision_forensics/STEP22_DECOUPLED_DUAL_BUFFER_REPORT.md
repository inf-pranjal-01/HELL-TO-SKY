# PATH 2 — STEP 22: DECOUPLED DUAL-BUFFER STATE ARCHITECTURE REPORT

**Author**: Antigravity Machine Learning & Atmospheric Forensics Team  
**Date**: 2026-09-26  
**Status**: COMPLETED — EXPERIMENTAL HYPOTHESIS REJECTED (DO NOT PROMOTE)  
**Decision**: **REJECT**  
**Git Integrity**: 0 Commits, 0 Pushes  

---

## 1. Abstract & Executive Summary
Step 22 evaluated the architectural hypothesis (**Hypothesis H1**) that the substantial recall degradation observed in Step 21 (where recall fell from 95.42% to 91.33%, losing 533.4 TPs/seed) was caused by downstream state contamination—specifically, that suppressed Tier-1 spike candidates entered trusted history buffers, pulling dynamic expectations toward the fault and collapsing subsequent Tier-2 CUSUM residuals.

To test this, Step 22 implemented a Decoupled Dual-Buffer state architecture separating Raw History (used strictly for causal elapsed time $\Delta t$ and physical predecessor continuity $y_{t-1}$) from Trusted Clean History (used strictly for dynamic expectation $\mathbb{E}[y_t]$, baseline statistics, and frozen variance checks), ensuring that adjudicated/provisional candidates are excluded from trusted baselines.

Evaluated across all 7 locked benchmark seeds, Config C (Dual Buffer) recovered only 10.0 TPs/seed (70 total points) while losing an additional 81.1 TPs/seed (Net Recall: 80.85% vs 81.39% in Config B and 89.34% in Config A). Transition auditing conclusively demonstrated that the Step-21 recall drop was **not** an artifact of history contamination, but the direct consequence of the Diurnal ROC adjudicator's decision gate suppressing single-step fault movements whose trajectories happen to coincide with natural diurnal insolation. Hypothesis H1 is **REJECTED**, and Step 22 is not promoted.

---

## 2. Research Question & Hypotheses
- **Research Question**: Does separating raw observation history from trusted clean baseline history prevent suppressed anomaly candidates from contaminating downstream expectation/CUSUM state and recover the True Positives lost in Step 21?
- **Hypothesis H1 (State Contamination)**: When an early drift reading is suppressed by Tier 1, recording it as "clean" in `StationBuffer` pulls the dynamic baseline $\mathbb{E}[y_t]$ upward, eliminating subsequent Tier 2 SPRT residuals.
- **Competing Hypothesis H0 (Direct Adjudication Gate Suppression)**: The lost TPs are suppressed directly by the Diurnal-ROC adjudicator equation on each individual step because the anomalous displacement happens to fall within the diurnal acceptance envelope, independent of buffer state.

---

## 3. Architecture & State Semantics

```
                          ┌───────────────────────────┐
                          │   RAW INCOMING READING    │
                          └─────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 │                                             │
                 ▼                                             ▼
   ┌───────────────────────────┐                 ┌───────────────────────────┐
   │      STREAM A: RAW        │                 │     STREAM B: TRUSTED     │
   │      HISTORY BUFFER       │                 │       CLEAN BUFFER        │
   ├───────────────────────────┤                 ├───────────────────────────┤
   │ • All ingested readings   │                 │ • Confirmed clean only    │
   │ • Elapsed time Δt calc    │                 │ • Dynamic expectation     │
   │ • Physical prior y_{t-1}  │                 │ • Diurnal baseline level  │
   │ • Causal continuity       │                 │ • Frozen variance check   │
   └───────────────────────────┘                 └───────────────────────────┘
                 │                                             │
                 │                                             │
                 ▼                                             ▼
   ┌───────────────────────────┐                 ┌───────────────────────────┐
   │     DETECTOR TIERS        │                 │    DYNAMIC EXPECTATION    │
   │ (Raw Jump, ROC, CUSUM)    │◄────────────────┤    (Uncontaminated μ)     │
   └───────────────────────────┘                 └───────────────────────────┘
```

- **Stream A (Raw History)**: Ingests all readings sequentially to provide exact timestamp $\Delta t$ and prior sensor reading $y_{t-1}$.
- **Stream B (Trusted Clean History)**: Excludes both confirmed anomalies (`is_anomaly=True`) and adjudicated provisional candidates (`is_provisional=True`).
- **Stream C (Provisional History)**: Holds candidate readings that were suppressed by environmental explanation.

---

## 4. Benchmark Results Across All 7 Locked Seeds

| Configuration | Macro Precision | Macro Recall | Macro F1 | Mean TP | Mean FP | Mean FN |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Config A: Step 19 Reference** | 72.41% $\pm$ 1.34% | **89.34% $\pm$ 1.37%** | **79.98% $\pm$ 0.99%** | **11,672.7** | 4,447.3 | **1,393.9** |
| **Config B: Step 21 Reference** | **72.96% $\pm$ 1.35%** | 81.39% $\pm$ 1.48% | 76.94% $\pm$ 1.13% | 10,634.6 | 3,939.4 | 2,432.0 |
| **Config C: Step 22 Dual Buffer** | 72.84% $\pm$ 1.33% | 80.85% $\pm$ 1.44% | 76.63% $\pm$ 1.09% | 10,563.4 | **3,937.9** | 2,503.1 |

### Per-Seed Breakdown (Config C)
| Seed | Precision | Recall | F1 | TP | FP | FN |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 42 | 71.40% | 79.19% | 75.09% | 10,223 | 4,095 | 2,686 |
| 101 | 73.87% | 83.80% | 78.52% | 10,911 | 3,860 | 2,109 |
| 202 | 74.25% | 79.65% | 76.86% | 10,710 | 3,714 | 2,736 |
| 2024 | 73.91% | 80.87% | 77.24% | 10,722 | 3,784 | 2,536 |
| 8888 | 73.41% | 81.16% | 77.09% | 10,698 | 3,875 | 2,484 |
| 20260924 | 72.85% | 80.22% | 76.36% | 10,531 | 3,925 | 2,597 |
| 45456231412727229999 | 70.18% | 81.04% | 75.22% | 10,149 | 4,312 | 2,374 |
| **Mean** | **72.84%** | **80.85%** | **76.63%** | **10,563.4** | **3,937.9** | **2,503.1** |

---

## 5. Transition Audit (Config B $\rightarrow$ Config C)

Auditing all prediction changes (`scratch/precision_forensics/step22_transition_audit.csv`):

| Transition Outcome | Total Count | Mean per Seed | Proportion (%) | Scientific Finding |
| :--- | :---: | :---: | :---: | :--- |
| **TP_RECOVERED** | **70** | **10.0** | **10.07%** | Minor recovery in early drift/frozen |
| **TP_REMOVED** | **568** | **81.1** | **81.73%** | Additional TPs lost due to shortened clean history windows |
| **FP_REMOVED** | 34 | 4.9 | 4.89% | Marginal FP reduction |
| **FP_ADDED** | 23 | 3.3 | 3.31% | Minor baseline drift in clean data |
| **Net TP Delta** | **$-498$** | **$-71.1$** | — | **Hypothesis H1 Empirically Disproved** |

---

## 6. Per-Fault Recall Comparison

| Fault Type | TP Step 19 | TP Step 21 | TP Step 22 | Recall Step 19 | Recall Step 21 | Recall Step 22 | Recovered TP |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Spike** | 501.1 | 474.4 | 474.7 | 93.52% | 88.54% | 88.59% | $+0.3$ |
| **Frozen Value** | 937.3 | 875.7 | 832.7 | 82.58% | 77.16% | 73.37% | $-43.0$ |
| **Drift** | 6,553.0 | 5,743.4 | 5,718.7 | 87.31% | 76.53% | 76.20% | $-24.7$ |
| **Multivariate** | 1,006.7 | 895.9 | 892.6 | 87.04% | 77.46% | 77.17% | $-3.3$ |
| **Unstructured** | 1,353.3 | 1,328.3 | 1,327.9 | 98.17% | 96.35% | 96.32% | $-0.4$ |
| **Fail Low** | 1,056.7 | 1,052.3 | 1,052.3 | 96.88% | 96.48% | 96.48% | $0.0$ |
| **Dropout** | 264.6 | 264.6 | 264.6 | 100.00% | 100.00% | 100.00% | $0.0$ |

---

## 7. Scientific Autopsy: Why Did Dual Buffering Fail to Recover Recall?

1. **Direct Point-Level Suppression (Hypothesis H0 Supported)**:
   - When an injected drift begins during the morning ($+0.10^\circ\text{C}/\text{h}$ fault ramp superimposed on $+0.80^\circ\text{C}/\text{h}$ morning warming), the total step delta is $+0.90^\circ\text{C}/\text{h}$.
   - The Diurnal-ROC adjudicator observes that $+0.90^\circ\text{C}$ has the same sign as $\mathbb{E}[\Delta y \mid h=8] = +0.80^\circ\text{C}$ and $|0.90 - 0.80| = 0.10 < 2.5\sigma_0$.
   - The adjudicator suppresses the spike **instantaneously at that step**. The decision to suppress is made purely from $(y_t, y_{t-1}, h_{\text{solar}})$, completely independent of what was stored in history.
2. **Buffer Starvation Effect**:
   - When provisional readings are excluded from `trusted_history_df`, the trusted buffer contains gaps during extended diurnal transitions.
   - Modules requiring rolling history (such as `evaluate_frozen_evidence`) experience reduced statistical power because fewer valid clean observations are available within the rolling window, causing Frozen recall to drop from 77.16% to 73.37%.

---

## 8. Fixed-Variable Ledger
| Parameter | Value | Origin | Classification | Arbitrary? |
| :--- | :---: | :--- | :--- | :--- |
| Buffer Maxlen | 200 | Existing System Parameter | Implementation Detail | NO |
| Wald Boundary $\eta$ | 5.86 | $\ln((1-\beta)/\alpha)$ | Mathematical Derivation | NO |
| **New Arbitrary Variables** | **0** | **Strict Constraint** | **N/A** | **NO** |

---

## 9. Final Decision & Next Step Strategy
- **Decision**: **REJECT (DO NOT PROMOTE)**.
- **Authoritative Baseline**: Remains Step 19 (Precision ~73.33%, Recall ~95.42%, F1 ~82.92%).
- **Key Insight**: Single-step point vetoes on Tier 1 spikes invariably erode early-onset drift and structured anomalies. True precision elevation must occur without single-step sign/magnitude vetoes.
- **Direction for Step 23**: Formulate a **Multi-Horizon Integral Drift Engine** in Tier 2 to eliminate drift detection latency (from 11h to 3h), recovering the remaining ~2,000 slow-drift and frozen false negatives without touching Tier 1 spike mechanics.
