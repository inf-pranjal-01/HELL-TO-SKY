# PATH 2 — STEP 21: DIURNAL ROC SPIKE ADJUDICATOR BENCHMARK REPORT

**Author**: Antigravity Machine Learning & Atmospheric Forensics Team  
**Date**: 2026-09-26  
**Status**: COMPLETED — EXPERIMENTAL REJECTION (DO NOT PROMOTE)  
**Decision**: **REJECT**  
**Git Integrity**: 0 Commits, 0 Pushes  

---

## 1. Abstract
Step 21 evaluated the first surgical precision adjudicator designed to break the precision/recall tradeoff loop. Based on the Step 20 forensic finding that Tier 1 Spike generated 98.42% of false alarms by comparing raw physical jumps against sensor noise floors without subtracting diurnal expectations $\mathbb{E}[\Delta y \mid h_{\text{solar}}]$, Step 21 implemented a causal Diurnal-ROC innovation adjudicator. While preserving raw jump sensitivity as the primary candidate generator, the adjudicator evaluated whether raw jumps were explained by normal diurnal insolation. Evaluated across all 7 locked seeds alongside a phase-inverted negative control, the candidate reduced False Positives by 173.7 FP/seed (4,534.7 $\rightarrow$ 4,361.0), but caused significant True Positive destruction: Mean TP dropped by 533.4/seed (Recall dropped from 95.42% to 91.33%, and F1 fell from 82.92% to 81.28%). Forensic transition auditing revealed that 70.4% of lost TPs were drift points that had previously been caught by Tier 1; suppressing these spikes caused unflagged drift readings to enter `StationBuffer`, contaminating rolling baselines and crippling Tier 2 CUSUM. Following the strict decision protocol, Step 21 is **REJECTED**.

---

## 2. Research Question
Can an independent causal Diurnal-ROC environmental explanation adjudicator safely reject Tier-1 diurnal-warming false alarms without suppressing genuine sensor faults or causing cascade state contamination?

---

## 3. Motivation
Step 20 identified that normal morning warming ($+0.6^\circ\text{C}$ to $+1.4^\circ\text{C}/\text{h}$) regularly exceeds the $3.0\sigma_{\text{jump}} = 0.52^\circ\text{C}$ quantization threshold, generating 2,494 false alarms per seed. Step 21 aimed to adjudicate these jumps without reducing initial detector sensitivity.

---

## 4. Locked Baseline References (7 Locked Seeds)
- **Step 16 Baseline**: Precision = 72.60%, Recall = 97.81%, F1 = 83.33%
- **Step 18 Untouched**: Precision = 73.41%, Recall = 94.44%, F1 = 82.60%
- **Step 19 Reference**: Precision = 73.33%, Recall = 95.42%, F1 = 82.92% (Mean TP = 12,467.6, Mean FP = 4,534.7, Mean FN = 599.0)

---

## 5. Mathematical Formulation of the Adjudicator

### 5.1. Raw Spike Candidate Generation (Untouched)
For each parameter $p \in \{\text{T}, \text{P}, \text{RH}\}$:
$$|y_t - y_{t-\Delta t}| \ge 2.5 \sigma_0(p) \quad \text{AND} \quad z_{\text{jump}} \ge 3.0 \quad \text{AND} \quad \text{LLR}_{\text{jump}} \ge 5.86$$
where $\sigma_{\text{jump}}(p, \Delta t) = \sqrt{2 \sigma_0^2(p) + \sigma_0^2(p) \Delta t}$.

### 5.2. Diurnal ROC Innovation Adjudication
For generated candidates:
$$\Delta y_{\text{expected}} = \mathbb{E}\left[\left.\frac{\Delta y}{\Delta t}\right| h_{\text{solar}}\right] \cdot \Delta t$$
$$\Delta y_{\text{unexplained}} = (y_t - y_{t-\Delta t}) - \Delta y_{\text{expected}}$$
$$z_{\text{unexplained}} = \frac{|\Delta y_{\text{unexplained}}|}{\sigma_{\text{jump}}(p, \Delta t)}$$

Adjudicated as clean diurnal movement if:
$$\text{sign}(y_t - y_{t-\Delta t}) == \text{sign}(\Delta y_{\text{expected}}) \quad \text{AND} \quad \left( |y_t - y_{t-\Delta t}| \le |\Delta y_{\text{expected}}| + 2.5 \sigma_0 \quad \text{OR} \quad z_{\text{unexplained}} < 3.0 \right)$$

---

## 6. Authoritative Benchmark Results across 7 Locked Seeds

| Configuration | Macro Precision | Macro Recall | Macro F1 | Mean TP | Mean FP | Mean FN | TP Delta vs Step19 | FP Delta vs Step19 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Step 19 Baseline Reference** | **73.33% $\pm$ 1.37%** | **95.42% $\pm$ 0.36%** | **82.92% $\pm$ 0.89%** | **12,467.6** | 4,534.7 | **599.0** | 0.0 | 0.0 |
| **Step 21 Diurnal ROC Adjudicator** | 73.24% $\pm$ 1.48% | 91.33% $\pm$ 0.42% | 81.28% $\pm$ 0.89% | 11,934.1 | 4,361.0 | 1,132.4 | **$-533.4$** | **$-173.7$** |
| **Step 21 Negative Control (12h Shift)** | 72.79% $\pm$ 1.43% | 86.45% $\pm$ 0.64% | 79.03% $\pm$ 0.88% | 11,295.9 | **4,221.4** | 1,770.7 | $-1,171.7$ | $-313.3$ |

---

## 7. Per-Seed Benchmark Breakdown

### Config B: Step 21 Diurnal ROC Adjudicator
| Seed | Precision | Recall | F1 | TP | FP | FN |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 42 | 72.30% | 90.70% | 80.46% | 11,708 | 4,486 | 1,201 |
| 101 | 73.15% | 91.94% | 81.48% | 11,971 | 4,393 | 1,049 |
| 202 | 75.36% | 91.48% | 82.64% | 12,301 | 4,023 | 1,145 |
| 2024 | 74.36% | 91.76% | 82.15% | 12,165 | 4,195 | 1,093 |
| 8888 | 74.11% | 91.11% | 81.74% | 12,010 | 4,195 | 1,172 |
| 20260924 | 73.39% | 91.23% | 81.35% | 11,977 | 4,342 | 1,151 |
| 45456231412727229999 | 69.98% | 91.09% | 79.15% | 11,407 | 4,893 | 1,116 |
| **Mean** | **73.24%** | **91.33%** | **81.28%** | **11,934.1** | **4,361.0** | **1,132.4** |

---

## 8. Transition & TP-Safety Audit

Auditing all 14,416 decision changes across the 7 seeds (`scratch/precision_forensics/step21_transition_audit.csv`):

| Transition Outcome | Total Count | Mean per Seed | Proportion (%) | Interpretation |
| :--- | :---: | :---: | :---: | :--- |
| **TP_REMOVED (Destruction)** | **6,381** | **911.6** | **44.26%** | Genuine anomalies suppressed by adjudicator |
| **FP_REMOVED (Cure)** | **3,302** | **471.7** | **22.91%** | Clean diurnal transitions correctly filtered |
| **TP_ADDED (Recovery)** | 2,647 | 378.1 | 18.36% | Secondary detections via altered downstream state |
| **FP_ADDED (New False Alarms)** | 2,086 | 298.0 | 14.47% | State-contamination induced false alarms |
| **Net TP Delta** | **$-3,734$** | **$-533.4$** | — | **Severe Net True Positive Loss** |
| **Net FP Delta** | **$-1,216$** | **$-173.7$** | — | **Modest False Positive Reduction** |

---

## 9. Per-Fault Recall Audit (Step 19 vs Step 21)

| Fault Type | Baseline TP (Step 19) | Step 21 TP | TP Lost / Seed | Baseline Recall | Step 21 Recall | Recall Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Spike** | 521.3 | 509.1 | 12.1 | 97.28% | 95.01% | $-2.27\text{ pp}$ |
| **Frozen Value** | 1,057.6 | 1,013.7 | 43.9 | 93.18% | 89.31% | $-3.86\text{ pp}$ |
| **Drift** | 7,039.9 | 6,663.6 | **376.3** | 93.80% | 88.79% | **$-5.01\text{ pp}$** |
| **Multivariate** | 1,155.1 | 1,119.7 | 35.4 | 99.88% | 96.81% | $-3.06\text{ pp}$ |
| **Unstructured** | 1,338.7 | 1,274.7 | 64.0 | 97.11% | 92.47% | $-4.64\text{ pp}$ |
| **Sensor Fail Low** | 1,090.4 | 1,088.7 | 1.7 | 99.97% | 99.82% | $-0.16\text{ pp}$ |
| **Dropout** | 264.6 | 264.6 | 0.0 | 100.00% | 100.00% | $0.00\text{ pp}$ |

---

## 10. Root-Cause Autopsy: Why Did Spike Adjudication Destroy Drift Recall?

The transition audit uncovered a critical architectural coupling mechanism:
1. **Tier 1 Multi-Fault Catchment**: When a sensor is drifting upward during the morning ($+0.10^\circ\text{C}/\text{h}$ fault ramp on top of $+0.80^\circ\text{C}/\text{h}$ natural warming), the single-step change is $+0.90^\circ\text{C}/\text{h}$. Under Step 19, this triggered Tier 1 Spike jump ($z = 5.2 > 3.0$).
2. **The Adjudicator Mask**: The Diurnal ROC adjudicator observes $+0.90^\circ\text{C}$ moving in the same positive direction as the $+0.80^\circ\text{C}$ diurnal expectation. The unexplained difference is only $+0.10^\circ\text{C} < 2.5\sigma_0$, so the adjudicator **vetoed the Tier 1 spike**.
3. **State Contamination Feedback**: Because Tier 1 did not fire, `StationBuffer.record_raw_reading` recorded the anomalous $+0.90^\circ\text{C}$ reading into `hist_df` as a CLEAN observation.
4. **CUSUM Crippling**: Incorporating the unflagged drifting reading into `hist_df` shifted the local dynamic expectation $\mathbb{E}[y_t]$ upward towards the fault, collapsing subsequent Tier 2 SPRT residuals and causing Tier 2 to miss the entire remainder of the drift episode.

---

## 11. Negative Control Analysis (Config C)
In Config C, solar time was shifted by +12 hours (inverting the expected diurnal warming/cooling phase):
- Recall dropped catastrophically to **86.45%** (losing 1,171.7 TPs/seed).
- Precision degraded to **72.79%**.
This confirmed that the adjudicator's behavior is causally coupled to the astronomical diurnal cycle, but also demonstrated that when an environmental model is misaligned with anomalous observations, it creates severe destructive interference.

---

## 12. Fixed-Variable Ledger
| Parameter | Value | Origin | Classification | Arbitrary? |
| :--- | :---: | :--- | :--- | :---: |
| Wald Boundary $\eta$ | 5.86 | $\ln((1-\beta)/\alpha)$ | Mathematical Derivation | NO |
| Sensor Floor $\sigma_0$ | Hardware Specs | Sensor Quantization Table | Physical Instrument Floor | NO |
| Diurnal ROC $\mathbb{E}[\Delta y \mid h]$ | Cache Array | 70% Clean Historical Partition | Data-Derived Baseline | NO |
| **New Arbitrary Variables** | **0** | **Strict Constraint** | **N/A** | **NO** |

---

## 13. Case Studies

### Case 1: Clean Morning Warming (AWS-CHN-024, Hour 08)
- $y_{t-1} = 26.0^\circ\text{C}, y_t = 26.8^\circ\text{C} \implies \Delta y = +0.80^\circ\text{C}$.
- Raw Jump: $z = 4.62 > 3.0 \rightarrow$ Raw Spike Triggered.
- Adjudicator: $\mathbb{E}[\Delta y \mid h=8] = +0.75^\circ\text{C} \implies \Delta y_{\text{unexplained}} = +0.05^\circ\text{C} < 0.25^\circ\text{C}$.
- **Result**: Correctly adjudicated clean (FP cured).

### Case 2: Injected Drift during Morning Warming (AWS-DEL-011, Hour 09)
- Natural warming $= +0.70^\circ\text{C}$, Injected drift $= +0.20^\circ\text{C} \implies \Delta y = +0.90^\circ\text{C}$.
- Raw Jump: $z = 5.20 > 3.0 \rightarrow$ Raw Spike Triggered.
- Adjudicator: $\mathbb{E}[\Delta y \mid h=9] = +0.70^\circ\text{C} \implies \Delta y_{\text{unexplained}} = +0.20^\circ\text{C} < 0.25^\circ\text{C}$.
- **Result**: Inadvertently adjudicated clean $\rightarrow$ TP suppressed $\rightarrow$ `hist_df` contaminated $\rightarrow$ Drift episode missed.

---

## 14. Decision & Classification
- **Classification**: **REJECT (DO NOT PROMOTE)**.
- **Rationale**: The mechanism does not satisfy the primary Pareto criterion: Precision did not improve meaningfully (73.24% vs 73.33%), while Recall suffered unacceptable degradation ($-4.09\text{ pp}$, losing 533.4 TPs/seed) due to state contamination.

---

## 15. Recommendation for Next Step
**Step 22 — Decoupled Dual-Buffer Temporal Architecture**:
Before applying any Tier-1 innovation adjudication, the detector must separate the **Detection State Buffer** from the **Physical Baseline History Store**. Spikes that are adjudicated as environmental transitions must NOT be immediately admitted into the clean baseline history without multi-step verification, eliminating the state-contamination feedback loop.
