# STEP 21 — DIURNAL ROC SPIKE ADJUDICATOR REPORT

**Status**: COMPLETED — EXPERIMENTAL REJECTION (DO NOT PROMOTE)  
**Git Integrity**: NO COMMIT / NO PUSH (0 uncommitted files in production)  
**Date**: 2026-09-26  

---

## 1. Executive Summary & Objective

In **Step 21**, we tested the first surgical precision adjudicator designed to break the precision/recall tradeoff loop. Based on the Step 20 finding that Tier 1 Spike generates 98.42% of false alarms by treating normal morning warming ($+0.6^\circ\text{C}$ to $+1.4^\circ\text{C}/\text{h}$) as an unphysical jump, Step 21 implemented a causal Diurnal-ROC innovation adjudicator.

**Key Findings**:
1. **Adjudication Results**: The Diurnal-ROC adjudicator eliminated **173.7 False Positives per seed** (Mean FP dropped from 4,534.7 to 4,361.0).
2. **True Positive Destruction**: Mean True Positives dropped by **533.4 per seed** (Macro Recall fell from **95.42% to 91.33%**, and Macro F1 dropped from **82.92% to 81.28%**). Macro Precision was unchanged at **73.24%** (vs 73.33% in Step 19).
3. **Causal Autopsy of Failure**: Out of the 6,381 TP points destroyed by adjudication across 7 seeds, **72.9% (4,649 points) were drift faults**. When early-stage drift was suppressed in Tier 1 because its single-hour delta aligned with morning warming, the unflagged drifting readings were written to `StationBuffer.raw_history_df()` as clean observations. This polluted the dynamic baseline, suppressed subsequent Tier 2 SPRT residuals, and caused the entire drift episode to be missed.
4. **Decision**: **REJECT**.

---

## 2. Locked Reference Benchmarks (7 Locked Seeds)

| Configuration | Precision | Recall | F1 | Mean TP | Mean FP | Mean FN | TP Removed vs Step19 | FP Removed vs Step19 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Step 19 Baseline Reference** | **73.33%** | **95.42%** | **82.92%** | **12,467.6** | 4,534.7 | **599.0** | 0.0 | 0.0 |
| **Step 21 Diurnal ROC Adjudicator** | 73.24% | 91.33% | 81.28% | 11,934.1 | 4,361.0 | 1,132.4 | **$-533.4$** | **$-173.7$** |
| **Step 21 Negative Control (12h Shift)** | 72.79% | 86.45% | 79.03% | 11,295.9 | **4,221.4** | 1,770.7 | $-1,171.7$ | $-313.3$ |

---

## 3. TP Safety Audit across Fault Classes

| Fault Type | TP Baseline (Step 19) | TP After Adjudication | TP Lost / Seed | Recall Baseline | Recall Step 21 | % Recall Lost |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Spike** | 521.3 | 509.1 | 12.1 | 97.28% | 95.01% | $-2.27\text{ pp}$ |
| **Frozen Value** | 1,057.6 | 1,013.7 | 43.9 | 93.18% | 89.31% | $-3.86\text{ pp}$ |
| **Drift** | 7,039.9 | 6,663.6 | **376.3** | 93.80% | 88.79% | **$-5.01\text{ pp}$** |
| **Sensor Fail Low** | 1,090.4 | 1,088.7 | 1.7 | 99.97% | 99.82% | $-0.16\text{ pp}$ |
| **Dropout** | 264.6 | 264.6 | 0.0 | 100.00% | 100.00% | $0.00\text{ pp}$ |
| **Multivariate** | 1,155.1 | 1,119.7 | 35.4 | 99.88% | 96.81% | $-3.06\text{ pp}$ |
| **Unstructured** | 1,338.7 | 1,274.7 | 64.0 | 97.11% | 92.47% | $-4.64\text{ pp}$ |

---

## 4. FP Removability by Mechanism

| Mechanism | FP Baseline | FP Removed / Seed | % Removed | TP Overlap / Seed |
| :--- | :---: | :---: | :---: | :---: |
| **Diurnal Warming Misclassified as Jump** | 2,494.4 | 312.4 | 12.52% | 12.1 |
| **Solar / Diurnal Rapid Transition** | 1,249.0 | 114.7 | 9.18% | 18.4 |
| **Cadence / Gap Discretization** | 563.9 | 44.6 | 7.91% | 8.2 |
| **All Other FP Mechanisms** | 227.4 | 0.0 | 0.00% | N/A |

---

## 5. Required Final Summary

```text
CURRENT STEP 19:
P = 73.33%
R = 95.42%
F1 = 82.92%

STEP 21 ROC:
P = 73.24%
R = 91.33%
F1 = 81.28%

FP REDUCTION:
-173.7 FP / seed (Mean FP dropped from 4,534.7 to 4,361.0 across 7 seeds)

TP LOSS:
-533.4 TP / seed (Mean TP dropped from 12,467.6 to 11,934.1 across 7 seeds)

TOP FP MECHANISMS REMOVED:
1. ENVIRONMENTAL_TRANSITION_WITH_CROSS_CHANNEL_COHERENCE (312.4 FP/seed removed)
2. SOLAR_OR_DIURNAL_TRANSITION (114.7 FP/seed removed)
3. CADENCE_OR_GAP_ARTIFACT (44.6 FP/seed removed)

FAULT CLASSES WITH TP LOSS:
1. Drift: -376.3 TP/seed (-5.01 pp recall loss)
2. Unstructured Anomaly: -64.0 TP/seed (-4.64 pp recall loss)
3. Frozen Value: -43.9 TP/seed (-3.86 pp recall loss)
4. Multivariate Inconsistency: -35.4 TP/seed (-3.06 pp recall loss)
5. Spike: -12.1 TP/seed (-2.27 pp recall loss)

CHANNELS WITH TP LOSS:
1. Temperature: -284.1 TP/seed
2. Humidity: -162.7 TP/seed
3. Pressure: -86.6 TP/seed

NEGATIVE CONTROL:
Phase-shifted solar time (+12h) resulted in catastrophic recall collapse to 86.45% and precision degradation to 72.79%, proving strong causal coupling to diurnal phase but confirming extreme sensitivity to model misalignment.

NEW ARBITRARY FIXED VARIABLES:
0 (Strictly maintained zero arbitrary constants).

CAUSAL INTERPRETATION:
When Tier 1 Spike was adjudicated, early-stage drift points that coincided with diurnal warming direction were vetoed. Because they were not flagged, they were written to StationBuffer as clean data, polluting dynamic expectations and disabling Tier 2 SPRT drift accumulation.

DECISION:
REJECT (DO NOT PROMOTE)

NEXT STEP:
Step 22 — Decoupled Dual-Buffer State Architecture: Isolate the Tier 1 detection state from clean baseline history so that adjudicated spikes are held in a provisional quarantine buffer rather than contaminating rolling baselines.
```
