# PATH 2 — STEP 23: BENCHMARK INTEGRITY AND REPRODUCIBILITY AUDIT

**Author**: Antigravity Machine Learning & Atmospheric Forensics Team  
**Date**: 2026-09-26  
**Status**: COMPLETED — EXPERIMENTAL REPRODUCIBILITY RESTORED  
**Decision**: **ONE AUTHORITATIVE BENCHMARK LOCKED**  
**Git Integrity**: 0 Commits, 0 Pushes, 0 Production Detector Modifications  

---

## 1. Problem Statement
During the evaluation of Step 22 (Decoupled Dual-Buffer State Architecture), an unexpected discrepancy occurred in the reference control configurations:
- **Historical Step 19**: Established and locked at **Precision = 73.33%**, **Recall = 95.42%**, **F1 = 82.92%** (Mean TP = 12,467.6, Mean FP = 4,534.7, Mean FN = 599.0).
- **Step 22 Driver Output for "Step 19 Reference"**: Reported **Precision = 72.41%**, **Recall = 89.34%**, **F1 = 79.98%** (Mean TP = 11,672.7, Mean FP = 4,447.3, Mean FN = 1,393.9).
- **Step 22 Driver Output for "Step 21 Reference"**: Reported **Precision = 72.96%**, **Recall = 81.39%**, **F1 = 76.94%** (compared to historical Step 21 at 73.24% Precision / 91.33% Recall).

This represents a ~6.08 percentage point collapse in recall for the exact same named configuration on the exact same dataset, indicating configuration drift within experimental tooling.

---

## 2. Why Reproducibility is Critical
In iterative ML/statistical systems engineering, evaluating architectural modifications against a non-stationary reference baseline creates false signals:
1. Improvements may appear artificially magnified or diminished.
2. Root-cause forensics become confounded between detector mechanics and evaluation driver bugs.
3. Chasing metrics against a shifting baseline inevitably traps the research in non-converging precision/recall loops.

Therefore, all architectural and detector experiments were halted until the reference configuration discrepancy was conclusively identified, isolated, and resolved.

---

## 3. Historical Authoritative Results Across 7 Locked Seeds

| Configuration | Macro Precision | Macro Recall | Macro F1 | Mean TP | Mean FP | Mean FN |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Step 16 Baseline** | 72.60% $\pm$ 1.53% | **97.81% $\pm$ 0.23%** | **83.33% $\pm$ 1.05%** | **12,781.0** | 4,822.7 | **285.6** |
| **Step 18 Untouched** | **73.41% $\pm$ 1.37%** | 94.44% $\pm$ 0.33% | 82.60% $\pm$ 0.91% | 12,340.6 | **4,469.3** | 726.0 |
| **Step 19 Reference** | 73.33% $\pm$ 1.37% | 95.42% $\pm$ 0.36% | 82.92% $\pm$ 0.89% | 12,467.6 | 4,534.7 | 599.0 |
| **Step 21 Reference** | 73.24% $\pm$ 1.60% | 91.33% $\pm$ 0.40% | 81.28% $\pm$ 1.07% | 11,934.1 | 4,361.0 | 1,132.4 |

---

## 4. Step-22 Reported Results

| Step 22 Driver Configuration | Macro Precision | Macro Recall | Macro F1 | Mean TP | Mean FP | Mean FN |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Config A (Step 19 Ref in Step 22)** | 72.41% $\pm$ 1.34% | 89.34% $\pm$ 1.37% | 79.98% $\pm$ 0.99% | 11,672.7 | 4,447.3 | 1,393.9 |
| **Config B (Step 21 Ref in Step 22)** | 72.96% $\pm$ 1.35% | 81.39% $\pm$ 1.48% | 76.94% $\pm$ 1.13% | 10,634.6 | 3,939.4 | 2,432.0 |
| **Config C (Step 22 Dual Buffer)** | 72.84% $\pm$ 1.33% | 80.85% $\pm$ 1.44% | 76.63% $\pm$ 1.09% | 10,563.4 | 3,937.9 | 2,503.1 |

---

## 5. Observed Discrepancy
- **Delta in Step 19 Reference**: $-6.08\text{ pp}$ Recall ($-794.9\text{ TPs/seed}$), $-0.92\text{ pp}$ Precision, $-2.94\text{ pp}$ F1.
- **Delta in Step 21 Reference**: $-9.94\text{ pp}$ Recall ($-1,299.5\text{ TPs/seed}$), $-0.28\text{ pp}$ Precision, $-4.34\text{ pp}$ F1.

---

## 6. Experimental Audit Protocol
To pinpoint the divergence without altering production code:
1. Compute cryptographic SHA256 hashes of all datasets, injectors, and model files.
2. Execute historical Step 19 driver (`build_step19_population_and_audit.py`) directly on all 7 seeds.
3. Execute Step 21 driver (`run_step21_benchmark.py`) directly on all 7 seeds.
4. Execute Step 22 driver (`run_step22_benchmark.py`) directly on all 7 seeds.
5. Trace Seed 42 observation-by-observation to identify the exact timestamp of first prediction divergence.

---

## 7. Configuration Diff Matrix (`scratch/precision_forensics/step23_configuration_diff.csv`)

| Component | Historical Step 19 Driver | Step 22 Benchmark Driver | Identical? |
| :--- | :--- | :--- | :---: |
| **Dataset file** | `data/all_stations.csv` | `data/all_stations.csv` | **YES** |
| **Dataset SHA256** | `1c113f12...` | `1c113f12...` | **YES** |
| **Injector code** | `data/anomaly_injector.py` | `data/anomaly_injector.py` | **YES** |
| **Injector SHA256** | `12f72ee2...` | `12f72ee2...` | **YES** |
| **Test split** | 70% temporal index cutoff | 70% temporal index cutoff | **YES** |
| **Seed list** | 7 locked seeds | 7 locked seeds | **YES** |
| **Station ordering** | `eval_df.sort_values('timestamp')` | `eval_df.sort_values('timestamp')` | **YES** |
| **Timestamp sorting** | UTC ascending | UTC ascending | **YES** |
| **State initialization** | Fresh per seed | Fresh per seed | **YES** |
| **Buffer anomaly exclusion** | **YES (`StationBuffer` excludes anomalies)** | **NO (`DualStationBuffer` appended all rows to raw)** | **NO (ROOT CAUSE)** |
| **Prior value reference $y_{t-1}$** | **Last clean baseline observation** | **Immediate $t-1$ observation (including faults)** | **NO (ROOT CAUSE)** |
| **Tier 0 Hard Rails** | `_check_hardware_rail` + bounds | `_check_hardware_rail` + bounds | **YES** |
| **Tier 1 Specialist** | Jump LLR $\ge 5.86$, Frozen check | Jump LLR $\ge 5.86$, Frozen check | **YES** |
| **Tier 2 ROC CUSUM** | $k=0.50, \eta=5.86, \text{decay}=e^{-\Delta t / 24}$ | $k=0.50, \eta=5.86, \text{decay}=e^{-\Delta t / 24}$ | **YES** |
| **Tier 3 Instant Cov** | $\mathbf{\Sigma}_{\Delta} \cdot \Delta t, D^2 > 16.27$ | $\mathbf{\Sigma}_{\Delta} \cdot \Delta t, D^2 > 16.27$ | **YES** |
| **Dynamic expectation** | `compute_dynamic_expectation` | `compute_dynamic_expectation` | **YES** |
| **Scoring** | `bool(is_anomaly) == gt` | `bool(is_anomaly) == gt` | **YES** |
| **Ground truth** | Injected `is_anomaly` column | Injected `is_anomaly` column | **YES** |

---

## 8. Dataset Integrity
- File: `data/all_stations.csv`
- SHA256: `1c113f12ee663d40e6e3c1bb04110c993489b45c9d03afc3b89952b08f675188` (4,138,620 bytes).
- Total observations: 60,480 across 28 stations.
- Split cutoff: Index 42,336 (70% clean training, 30% evaluation stream = 18,144 observations).

---

## 9. Injector Integrity
- File: `data/anomaly_injector.py`
- SHA256: `12f72ee2d5a041f8f8d9c641f42f87e69c067872af5c242eeeec911a04f1e8cc` (40,573 bytes).
- Deterministic behavior: Verified invariant across all 7 seeds. Ground truth labels (`is_anomaly`, `fault_type`) match 100% bit-for-bit.

---

## 10. State Integrity
- Historical Step 19 and Step 21 drivers use `model.state.StationBuffer`.
- In `model.state.StationBuffer.record_raw_reading`:
  ```python
  if verdict.get("is_anomaly"):
      return
  ```
  Anomalous readings are excluded from the history buffer, ensuring that the prior value $y_{t-1}$ represents the pre-fault baseline.

---

## 11. Evaluation-Order Integrity
- Observation streams are sorted strictly by `timestamp` in UTC ascending order across all stations.
- Station grouping, peer buffer lookups, and chronological replay match across all drivers.

---

## 12. Ground-Truth Integrity
- Scoring evaluates strictly `bool(verdict["is_anomaly"]) == bool(row["is_anomaly"])`.
- No reliance on diagnostic fault labels or post-hoc heuristics.

---

## 13. First-Divergence Forensic Trace (Seed 42)
Tracing chronologically on Seed 42 (`scratch/precision_forensics/step23_first_divergence_seed42.csv`):
- **First Divergent Row**: Row 60, Station `AWS-CHN-103`, `2025-03-05 02:00:00+00:00`.
- **Historical Step 19 Driver**: Evaluated against clean prior $y_{t-1} = 23.6^\circ\text{C}$ ($\Delta t = 1.0\text{h}$). Cumulative ROC CUSUM reached $S^+ = 6.12 \ge 5.86 \rightarrow$ **Fired Tier 2**. Row 60 was excluded from history.
- **Step 22 Config A Driver**: Evaluated against un-excluded raw predecessor $y_{t-1} = 23.5^\circ\text{C}$. CUSUM residual evaluated lower ($S^+ = 4.89 < 5.86 \rightarrow$ **Normal**). Row 60 was appended to raw history.
- **Downstream Fault Blinding**: In multi-step continuous faults (e.g. ramp drift, frozen value), appending anomalous rows causes step-deltas $\Delta y_t = y_t - y_{t-1}$ to equal the incremental step noise ($\approx 0.05^\circ\text{C}/\text{h}$) rather than the total anomalous displacement. The Step 22 driver became blind to multi-step anomalies, destroying ~795 TPs/seed.

---

## 14. Root Cause
The root cause was **inadvertent state-semantic modification in `run_step22_benchmark.py`**:
- When creating `DualStationBuffer` to test raw vs trusted history, `_raw_rows.append(row)` was called unconditionally.
- In Config A and Config B (the control configurations), the detector was configured to read prior values and history from `_raw_rows`.
- This violated the core contract of `StationBuffer` (which excludes flagged anomalies), causing the reference controls in Step 22 to degrade.

---

## 15. Correction
The driver state semantics have been unified in `scratch/precision_forensics/run_step23_benchmark_integrity_audit_optimized.py`, adhering strictly to `model.state.StationBuffer` exclusion principles.

---

## 16. Reproduction Results Across 7 Locked Seeds

### Macro Metrics
| Benchmark / Driver | Configuration Name | Precision | Recall | F1 | Mean TP | Mean FP | Mean FN |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Historical Step 19 Driver** | **Step 19 Reference** | **73.33% $\pm$ 1.37%** | **95.42% $\pm$ 0.36%** | **82.92% $\pm$ 0.89%** | **12,467.6** | **4,534.7** | **599.0** |
| **Step 21 Driver** | **Config A (Step 19 Ref)** | **73.33% $\pm$ 1.48%** | **95.42% $\pm$ 0.38%** | **82.92% $\pm$ 0.96%** | **12,467.6** | **4,534.7** | **599.0** |
| **Step 21 Driver** | **Config B (Step 21 Ref)** | **73.24% $\pm$ 1.60%** | **91.33% $\pm$ 0.40%** | **81.28% $\pm$ 1.07%** | **11,934.1** | **4,361.0** | **1,132.4** |

### Per-Seed Exact Reproduction Table
| Seed | Step 19 Hist TP | Step 19 Hist FP | Step 19 Hist FN | Step 19 Precision | Step 19 Recall | Step 19 F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 42 | 12,351 | 4,651 | 558 | 72.64% | 95.68% | 82.59% |
| 101 | 12,428 | 4,581 | 592 | 73.07% | 95.45% | 82.77% |
| 202 | 12,736 | 4,236 | 710 | 75.04% | 94.72% | 83.74% |
| 2024 | 12,709 | 4,338 | 549 | 74.55% | 95.86% | 83.87% |
| 8888 | 12,612 | 4,478 | 570 | 73.80% | 95.68% | 83.32% |
| 20260924 | 12,520 | 4,480 | 608 | 73.65% | 95.37% | 83.11% |
| 45456231412727229999 | 11,917 | 4,979 | 606 | 70.53% | 95.16% | 81.02% |
| **Macro Mean** | **12,467.6** | **4,534.7** | **599.0** | **73.33%** | **95.42%** | **82.92%** |

---

## 17. Limitations
- Single-step jump detectors depend intrinsically on the clean history buffer remaining uncontaminated. When faults are long-duration and unflagged, buffer contamination remains a potential failure mode, reinforcing the necessity of multi-horizon temporal accumulation in Tier 2.

---

## 18. Threats to Validity
- Any experimental script that introduces ad-hoc buffer state structures risks silently altering baseline expectations.

---

## 19. Decision
- **DECISION**: **ONE AUTHORITATIVE BENCHMARK LOCKED**.
- **Historical Step 19 is 100% verified and reproducible** (73.33% P / 95.42% R / 82.92% F1).
- **Step 21 is 100% verified and reproducible** (73.24% P / 91.33% R / 81.28% F1).
- **Step 22 script is declared INVALID due to driver state contamination**.

---

## 20. Rules for Future Benchmark Locking
1. **Mandatory Hash Check**: Every runner script must verify the SHA256 hashes of `all_stations.csv`, `anomaly_injector.py`, and detector modules before execution.
2. **Canonical State Import**: All runners must import `StationBuffer` from `model.state`. No local ad-hoc buffer classes.
3. **Automated Seed 42 Control Gate**: All benchmark scripts must evaluate Seed 42 against the locked standard (`TP=12,351, FP=4,651, FN=558`) before executing experimental candidates.
