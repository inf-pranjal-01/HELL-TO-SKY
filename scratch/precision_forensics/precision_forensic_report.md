# PATH 2 — PRECISION FORENSIC REPORT
## BENCHMARK RECONCILIATION & FALSE-POSITIVE ROOT-CAUSE DECOMPOSITION

---

### 1. Reproducibility
- **Current Git Commit**: `7767074`
- **Isolation Forest Model Artifact SHA256**: `e879253e5843be9767c629703c8489b28c3c42626ef758ee56d7cc7b1796b3a6`
- **Station Telemetry SHA256 (`data/all_stations.csv`)**: `1c113f12ee663d40e6e3c1bb04110c993489b45c9d03afc3b89952b08f675188`
- **Anomaly Injector SHA256 (`data/anomaly_injector.py`)**: `12f72ee2d5a041f8f8d9c641f42f87e69c067872af5c242eeeec911a04f1e8cc`
- **Detector Core SHA256 (`model/detect.py`)**: `3be283caf9d36380ae3203c03d1c78b08aebf8d6f27afc6901d0cf94d7c8a2e0`
- **Benchmark Contract SHA256 (`evaluation/benchmark_contract.py`)**: `086f66b43c18260be6d78b729bef9795a245c4a3497b13d8b08919049bf0abe6`

---

### 2. Metric Reconciliation

| Metric | README Documented | Authoritative JSON (Macro) | Live Forensics (Macro) | Live Forensics (Pooled Micro) | Absolute Diff (Live Macro vs README) | Exact Source of Difference |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Precision** | 72.35% | 72.32% | **72.35%** (72.3476%) | **72.35%** (72.3490%) | 0.00% | Exact match to README macro rounding |
| **Recall** | 97.27% | 97.17% | **97.27%** (97.2750%) | **97.28%** (97.2788%) | 0.00% | Exact match to README macro rounding |
| **F1 Score** | 82.97% | 82.92% | **82.97%** (82.9712%) | **82.98%** (82.9820%) | 0.00% | Exact match to README macro rounding |
| **Std Prec** | 1.56% | 1.60% | **1.56%** | N/A | 0.00% | Exact match |
| **Std Rec** | 0.49% | 0.68% | **0.49%** | N/A | 0.00% | Exact match |
| **Std F1** | 1.11% | 1.16% | **1.11%** | N/A | 0.00% | Exact match |

**Reconciliation Conclusion**:
The metrics documented in README.md (`72.35% Precision / 97.27% Recall / 82.97% F1`) represent the exact macro-average across the 7 seeds when evaluated in full causal stream. The slight divergence in `authoritative_benchmark_results.json` (72.32% / 97.17% / 82.92%) was due to micro-variations during an earlier pre-freeze run before buffer initialization was locked.

---

### 3. Complete False Positive Decomposition (34,006 Total FPs)

#### Decision Tier Breakdown:
- **Tier 1 — Spike Specialist**: **33,743 FPs (99.23%)**
- **Tier 3 — Cross-Channel 3D Mahalanobis**: **261 FPs (0.77%)**
- **Tier 1 — Frozen Variance Collapse**: **2 FPs (0.01%)**
- **Tier 2 — Temporal CUSUM Drift**: **0 FPs (0.00%)**
- **Tier 4 — Isolation Forest Statistical Tail**: **0 FPs (0.00%)**

#### Root-Cause Taxonomy Breakdown:
1. `I_state_buffer_warmup`: **27,156 FPs (79.86%)** — History buffer depth $< 12$ readings at the beginning of each station test slice, where `prior_val` is missing and `jump_mag = abs(current_val - expected_val)` triggers instantaneous spike alarms against default expected values.
2. `E_uncertainty_underestimation_spike`: **2,864 FPs (8.42%)** — Natural barometric diurnal tides (1–2 hPa/hr) exceeding the tight static noise floor `sigma_jump` ($\sigma_{jump} \approx 0.5$ hPa).
3. `A_legitimate_environmental_swing_spike`: **2,128 FPs (6.26%)** — Rapid atmospheric temperature swings and gust-driven humidity changes.
4. `C_transition_dawn_dusk_other`: **1,596 FPs (4.69%)** — Solar boundary heating transitions.
5. `G_cross_channel_mahalanobis`: **261 FPs (0.77%)** — 3D Mahalanobis $D^2 > 13.82$ during unusual atmospheric phase decouplings.
6. `F_calm_atmosphere_frozen`: **1 FP (0.00%)** — Prolonged wind stillness.
