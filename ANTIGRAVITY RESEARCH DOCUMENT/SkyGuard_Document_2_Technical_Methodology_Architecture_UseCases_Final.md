# SKYGUARD AI — DOCUMENT 2
## Technical Methodology, Architecture & Use-Case Document
**Comprehensive Engineering Specification of the 6-Tier Anomaly Detection Architecture**

---

### 1. Executive Summary
This document provides the definitive architectural specification of **SkyGuard AI**, an intelligent real-time anomaly detection and quality assurance platform for Automatic Weather Station (AWS) networks. SkyGuard implements a deterministic **Tier 0–5 Priority Arbitration Hierarchy**, a continuous 49-feature physical-time engineering matrix, an atomic same-timestamp temporal buffer, and cluster-isolated spatial peer consensus. 

By prioritizing hard physical laws, log-likelihood ratios (LLR), sequential drift analysis (SPRT), and 3D Mahalanobis covariance before evaluating unsupervised machine learning (Isolation Forest), SkyGuard achieves transparent, explainable (SHAP), and computationally lightweight ($0.210\text{ ms}$ p95) data validation.

---

### 2. Problem Formulation & System Objectives
Surface meteorological telemetry is characterized by multivariate coupling ($T, P, RH$), non-stationary diurnal cycles, and spatial correlation across proximal stations. Traditional threshold-based QC systems fail to detect low-amplitude calibration drift and frequently trigger false alarms during severe atmospheric fronts.

#### Core Technical Objectives:
1. **Zero Contamination of Trusted State:** Prevent corrupted sensor observations from entering rolling historical baselines.
2. **Sub-2-Second Total Processing:** Maintain ultra-fast single-reading algorithmic inference ($< 2.0\text{ ms}$).
3. **Severe Weather Preservation:** Suppress false alarms when extreme readings are corroborated by regional sibling stations.
4. **Interpretable Diagnostics:** Deliver additive feature attributions (SHAP) to inform field maintenance dispatches.

---

### 3. Station, Cluster & Peer Topology
SkyGuard organizes the meteorological network into strict, non-overlapping geographic clusters to enforce localized spatial reasoning without cross-regional contamination:

```
+-------------------------------------------------------------------------+
|                        7 GEOGRAPHIC CLUSTERS                            |
|  [DEL] Delhi   [MUM] Mumbai   [CHN] Chennai   [KOL] Kolkata             |
|  [BHO] Bhopal  [RAN] Ranchi   [VAR] Varanasi                            |
+-------------------------------------------------------------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
  +--------------------+                                 +--------------------+
  |  CLUSTER [MUM]     |                                 |  CLUSTER [DEL]     |
  |  - AWS-MUM-007 (C) |                                 |  - AWS-DEL-011 (C) |
  |  - AWS-MUM-101 (S) |                                 |  - AWS-DEL-101 (S) |
  |  - AWS-MUM-102 (S) |                                 |  - AWS-DEL-102 (S) |
  |  - AWS-MUM-103 (S) |                                 |  - AWS-DEL-103 (S) |
  +--------------------+                                 +--------------------+
```

* **Network Scope:** 28 total operational stations partitioned into 7 distinct clusters ($N_{\text{cluster}} = 7$).
* **Cluster Structure:** Exactly 4 stations per cluster (1 primary center station $C$, 3 regional sibling peers $S_1, S_2, S_3$).
* **Spatial Isolation:** Peer consensus queries operate strictly within the target station's assigned cluster. There is zero cross-cluster influence, preventing microclimatic differences (e.g., coastal Mumbai vs. inland Delhi) from distorting local spatial baselines.

---

### 4. End-to-End Ingestion & Processing Pipeline

```
Raw Ingestion (REST / WebSocket)
             |
             v
[Step 1] Atomic Temporal Alignment (merge_asof continuous physical time)
             |
             v
[Step 2] 49-Feature Physical Vector Construction
             |
             v
[Step 3] Deterministic Priority Arbitration (TIER 0 -> TIER 5)
             |
             +---> TIER 0: Hard Invariants & Electrical Rails
             +---> TIER 1: Specialist LLR (Spike >5-sigma, Frozen F-ratio)
             +---> TIER 2: Pre-Whitened SPRT Sequential Drift
             +---> TIER 3: 3D Mahalanobis Covariance & Spatial Contrast
             +---> TIER 4: Isolation Forest Empirical Tail Score
             +---> TIER 5: Spatial Consensus Veto (NORMAL vs AMBIGUOUS)
             |
             v
[Step 4] Explainability Extraction (TreeExplainer SHAP attribution)
             |
             v
[Step 5] Causal State Management (Quarantine vs Assimilation into StationBuffer)
             |
             v
Downstream Dispatch (FastAPI WebSocket Streaming / CSV History Store)
```

---

### 5. 49-Feature Continuous Physical-Time Matrix
The feature extraction engine (`model/features.py`) strictly avoids positional row shifts (`.shift(n)`), utilizing exact physical timestamps and `pd.merge_asof` to compute continuous dynamics regardless of irregular sampling intervals or packet drops:

| Feature Index Range | Canonical Category | Mathematical Formulation / Implementation | Physical & Diagnostic Role |
| :--- | :--- | :--- | :--- |
| **01 – 03** | Raw Measured Values | $x_t = [T_t, P_t, RH_t]$ | Base telemetry input channels. |
| **04 – 06** | Innovation Residuals | $z_t = (x_t - \mu_{\text{diurnal}})/\sigma_{\text{diurnal}}$ | Z-score deviation from local diurnal expectation. |
| **07 – 12** | Rates of Change ($1\text{h}, 3\text{h}$) | $\Delta x / \Delta t = (x_t - x_{t-\Delta t}) / \Delta t_{\text{hours}}$ | Physical atmospheric rate-of-change velocities. |
| **13 – 15** | Short-Term Volatility | $\sigma_{3\text{h}}(x) = \sqrt{\frac{1}{N}\sum(x_i - \bar{x})^2}$ | Identifies turbulence vs. abnormal stillness. |
| **16 – 17** | Thermodynamic Couplings | $T_{\text{dew}} = T - \frac{100 - RH}{5}; \;\; \text{VPD} = e_s(T)(1 - \frac{RH}{100})$ | Cross-channel psychrometric consistency bounds. |
| **18 – 21** | Cyclical Time Encodings | $\sin/\cos(2\pi \cdot \text{Hour}/24), \;\; \sin/\cos(2\pi \cdot \text{DOY}/365)$ | Diurnal and seasonal cyclical phase alignment. |
| **22** | Elapsed Physical Time | $\Delta t_{\text{hours}} = (t_k - t_{k-1}) / 3600.0$ | Continuous temporal interval tracking. |
| **23 – 25** | Robust Statistical Scales | $\text{Scale}_{\text{robust}} = (x_t - \text{median}) / \text{IQR}$ | Outlier-resistant localized baseline tracking. |
| **26 – 28** | Sensor Gap History | $\Delta t_{\text{valid}} = \text{Hours since last trusted reading}$ | Quarantined sensor downtime duration. |
| **29 – 40** | Rolling Ranges ($1\text{h}, 3\text{h}, 6\text{h}, 24\text{h}$) | $\text{Range}_{W} = \max_{W}(x) - \min_{W}(x)$ | Multi-scale dispersion and variance collapse checking. |
| **41 – 46** | Rolling Slopes ($6\text{h}, 24\text{h}$) | $\beta_W = \text{Cov}(t, x)_W / \text{Var}(t)_W$ | Long-term synoptic trend gradient analysis. |
| **47 – 49** | Diurnal Residual Baselines | $r_{\text{diurnal}} = x_t - \text{Baseline}(h_{\text{diurnal}})$ | Hour-of-day baseline residual tracking. |

---

### 6. The Deterministic Tier 0–5 Priority Hierarchy
`DecisionEngine.decide` in `model/detect.py` implements a strict top-down priority hierarchy where deterministic physical laws always take precedence over statistical models:

#### TIER 0: Hard Invariants & Hardware Rails
* **Logic:** Evaluates fixed hardware limits and absolute thermodynamic invariants:
$$T_t \notin [-40^\circ\text{C}, +60^\circ\text{C}], \quad P_t \notin [800\text{ hPa}, 1100\text{ hPa}], \quad RH_t \notin [0\%, 100\%]$$
* **Transducer Rail Detection:** Identifies exact electrical sentinels (e.g., $0.00\text{ V}$ ground faults or ADC saturation).
* **Verdict:** Immediate `FAULT (CRITICAL)`; bypasses downstream statistical layers.

#### TIER 1: High-Specificity Specialist Faults (Spike & Frozen)
* **Spike Detection (Jump LLR):** Evaluates instantaneous dynamic acceleration:
$$\text{LLR}_{\text{spike}} = \frac{|x_t - x_{t-1}| - \mu_{\text{jump}}}{\sigma_{\text{jump}}}$$
Flagged if $\text{LLR} > 5.0\sigma$ without corresponding rate-of-change across sibling peers.
* **Frozen Value Detection (Variance Collapse):** Evaluates local F-ratio variance collapse over contiguous readings:
$$F_{\text{variance}} = \frac{\text{Var}_{\text{target}}(x)_{4\text{h}}}{\text{Mean}(\text{Var}_{\text{peers}}(x)_{4\text{h}})}$$
Flagged if $F_{\text{variance}} \approx 0$ while peer stations exhibit active diurnal fluctuation.

#### TIER 2: Persistent Temporal Faults (Pre-Whitened SPRT Drift)
* **Logic:** Evaluates standardized innovation residuals using the Sequential Probability Ratio Test (SPRT) to accumulate low-SNR calibration drift evidence:
$$S_t = \max\left(0, \; S_{t-1} + \frac{\delta}{\sigma^2}\left(z_t - \mu_0 - \frac{\delta}{2}\right)\right)$$
* **Verdict:** Flagged as `FAULT (DRIFT)` when cumulative sum $S_t > h_{\text{threshold}}$, catching slow sensor bias shifts before they breach static thresholds.

#### TIER 3: Cross-Channel 3D Mahalanobis Covariance & Spatial Contrast
* **Logic:** Evaluates the joint covariance vector across Temperature, Pressure, and Relative Humidity:
$$D^2 = \begin{bmatrix} z_T & z_P & z_{RH} \end{bmatrix} \mathbf{\Sigma}^{-1} \begin{bmatrix} z_T \\ z_P \\ z_{RH} \end{bmatrix}$$
* **Thermodynamic Violation:** If $D^2 > \chi^2_{3, 0.999} = 16.27$ ($p < 10^{-3}$), the system isolates a cross-channel physical breakdown (e.g., temperature rising sharply while relative humidity remains locked).

#### TIER 4: Model-Dominant Supported Faults (Isolation Forest)
* **Logic:** Evaluates the continuous 49-feature matrix through an ensemble of 100 Isolation Trees.
* **Scoring:** The continuous anomaly score is mapped to an empirical z-score $z_{\text{IF}}$.
* **Arbitration:** If $z_{\text{IF}}$ falls in the extreme statistical tail ($z > 3.0$) and is corroborated by cross-channel divergence, it is classified as `FAULT (MULTIVARIATE_INCONSISTENCY)`.

#### TIER 5: Fallback Arbiter & Spatial Consensus Veto
* **Logic:** If an anomaly flag is raised by Tiers 1-4, the Spatial Consensus Engine inspects the 3 sibling stations in the cluster.
* **Veto Rule:** If $\ge 2$ sibling peers exhibit matching directional movements exceeding their local rate-of-change thresholds, the anomaly is classified as a **Genuine Regional Weather Event**. The alert is VETOED, and the state resolves to `NORMAL` or `AMBIGUOUS`.

---

### 7. StateManager & Trusted State Isolation
To prevent data contamination from corrupting future baseline estimates, `StateManager` (`model/state.py`) implements strict ground-truth isolation:
* **Causal Exclusion:** When an incoming observation is classified as `FAULT` (or when a sensor is in `OFFLINE` status), the observation is strictly **quarantined**. It is recorded in the raw historical audit log but **excluded** from the internal sliding `StationBuffer` deque.
* **Unpolluted Rolling Baselines:** Rolling means, variances, and diurnal profiles are computed exclusively over certified `NORMAL` observations.

```
Incoming Reading (T, P, RH)
             |
             v
   [Decision Engine]
             |
      +------+------+
      |             |
 [is_anomaly]  [is_normal]
      |             |
      v             v
 Quarantined   Assimilated into
 (Audit Log)   StationBuffer deque
 (No baseline  (Used for future
  pollution)    rolling baselines)
```

---

### 8. Explainability Architecture (SHAP Feature Attribution)
* **Engine:** `ExplainerCache` in `model/explain.py` wraps `shap.TreeExplainer` around the trained `IsolationForest` model.
* **Attribution Output:** For every flagged reading, the system computes the local additive contribution $\phi_i$ of each feature in the 49-dimensional space.
* **Human-Readable Diagnostics:** The top contributing features are mapped to natural language summaries (e.g., *"Temperature deviation (+3.8 sigma) and VPD deficit contributed 84% of the anomaly score"*).
* **Defensible Scope:** SHAP provides *model-feature attribution*, explaining why the algorithm flagged the reading. It is presented as diagnostic evidence, not definitive physical causal proof.

---

### 9. Current vs. Future Architectural Matrix

| Architectural Subsystem | Current Implemented Architecture | Demonstrated Status | Future Architectural Roadmap |
| :--- | :--- | :--- | :--- |
| **Inference Engine** | Vectorized NumPy / Scikit-Learn on CPU | **CURRENTLY DEMONSTRATED** | C-optimized edge firmware (ESP32/ARM Cortex) |
| **Temporal State Buffer** | In-memory circular deques (`collections.deque`) | **CURRENTLY DEMONSTRATED** | Distributed Redis state cache |
| **Historical Storage** | Flat-file CSV streaming (`HistoryStore`) | **CURRENTLY DEMONSTRATED** | Production TimescaleDB / PostgreSQL cluster |
| **API & Streaming** | FastAPI REST endpoints + Live WebSockets | **CURRENTLY DEMONSTRATED** | gRPC streaming ingestion gateway |
| **Spatial Discovery** | Static 7-cluster topology (4 stations/cluster) | **CURRENTLY DEMONSTRATED** | Dynamic PostGIS geospatial radius clustering |
| **Sensor Maintenance** | Health status tracking + fault type attribution | **CURRENTLY SUPPORTED** | Predictive Remaining Useful Life (RUL) modeling |

---

### 10. Operational Use Cases

#### Use Case 1: Real-Time Automatic Weather Station Quality Control
* **Operational Scope:** Automated real-time screening of raw surface meteorological streams before ingestion into national archives.
* **Status:** **CURRENTLY DEMONSTRATED** (Validated across 60,480 evaluation rows in 7-seed benchmark; achieves 95.42% ± 0.36% mean recall and 73.33% ± 1.37% mean precision).

#### Use Case 2: Numerical Weather Prediction (NWP) Data Ingestion Protection
* **Operational Scope:** Quarantining corrupted sensor streams to prevent spurious gradient initialization in 4D-Var data assimilation grids.
* **Status:** **CURRENTLY DEMONSTRATED** (Guaranteed via `StationBuffer` causal exclusion).

#### Use Case 3: Targeted Field Maintenance & Sensor Health Diagnostics
* **Operational Scope:** Utilizing SHAP feature attributions and fault classification to guide physical technician dispatches to specific degraded sensor modules.
* **Status:** **CURRENTLY SUPPORTED** (Provides component-level failure identification; does not predict future failures before physical onset).

#### Use Case 4: Microcontroller-Based Edge Datalogger Validation
* **Operational Scope:** Executing lightweight algorithmic inference ($0.210\text{ ms}$) directly on embedded station dataloggers to quarantine bad readings before cellular transmission.
* **Status:** **FUTURE APPLICATION** (Computationally feasible; requires C/C++ firmware porting).

---

### 11. Technical Claim Register

| Claim ID | Technical Claim | Source Code Verification | Audit Status |
| :--- | :--- | :--- | :--- |
| **TC-01** | Continuous 49-feature extraction without positional `.shift()` operations. | Verified in `model/features.py` via `merge_asof` | **VALID** |
| **TC-02** | Strict Tier 0-5 Priority Arbitration Hierarchy. | Verified in `model/detect.py` (`_evaluate_hierarchy`) | **VALID** |
| **TC-03** | Algorithmic inference latency executes in p95 $0.210\text{ ms}$ on CPU. | Verified in `README.md` and benchmark profiler | **VALID** |
| **TC-04** | Ground-truth labels are causally excluded from state buffers. | Verified in `model/state.py` (`record_raw_reading`) | **VALID** |
| **TC-05** | Production deployment uses TimescaleDB and PostGIS. | Codebase uses CSV `HistoryStore` and static clusters | **FUTURE SCOPE** |

---

### 12. References
* **[M01]** Liu, F. T., Ting, K. M., and Zhou, Z.-H. "Isolation Forest." *IEEE ICDM*, 2008.
* **[M02]** Page, E. S. "Continuous Inspection Schemes." *Biometrika*, vol. 41, 1954, pp. 100–115.
* **[M03]** Lundberg, S. M., and Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." *NeurIPS*, 2017.
* **[M05]** Mahalanobis, P. C. "On the generalised distance in statistics." *Proc. Natl. Inst. Sci. India*, 1936.
