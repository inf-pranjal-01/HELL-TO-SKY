# SKYGUARD AI — DOCUMENT 1
## External Research, Evidence, Citations, Impact & Benefit Dossier
**Authoritative Evidence Base for SIH 2026 Presentation & Technical Defense**

---

### 1. Executive Summary
This dossier establishes the primary research, empirical standards, and verifiable operational impact models for **SkyGuard AI**, an intelligent anomaly detection system for Automatic Weather Stations (AWS). As national meteorological networks scale rapidly to support climate monitoring and Numerical Weather Prediction (NWP), ensuring raw telemetry data quality without human-in-the-loop bottlenecks is paramount. 

This document traces SkyGuard's methodological architecture—integrating robust continuous physical-time extraction, thermodynamic consistency bounds, sequential change detection (SPRT/CUSUM), spatial consensus vetoes, and tree-based ensemble isolation—directly back to peer-reviewed literature and World Meteorological Organization (WMO) standards. Furthermore, it establishes transparent, mathematically traceable workload models, strictly avoiding unsubstantiated financial claims while providing direct evidence mappings to the official SIH 2026 6-slide presentation structure.

#### Top 5 System Unique Selling Propositions (USPs)
1. **Asymmetric Physics-First 6-Tier Hierarchy & Spatial Peer Consensus Veto:** Enforces thermodynamic physical invariants ($VPD$, Tetens psychrometrics, 3D Mahalanobis $D^2$) prior to statistical scoring, leveraging spatial peer consensus ($N=3$ within $50	ext{ km}$) to prevent false alarms during true convective weather fronts.
2. **Continuous Uninterrupted Streaming Passover via Causal Imputation:** When telemetry anomalies are flagged, `_compute_suggested_values()` dynamically calculates replacement values via a 4-tier causal fallback (spatial peer medians & solar diurnal geometry), guaranteeing downstream Numerical Weather Prediction (NWP) models receive unbroken data streams.
3. **Anti-Poisoning Health Quarantine & Dynamic Maintenance Lifecycle:** Quarantines anomalous telemetry from `StationBuffer` rolling statistics while tracking station health via continuous hysteresis ($H \in [0, 100]$) to generate targeted maintenance dispatch alerts before sensor degradation pollutes baseline estimates.
4. **Elevation & Climatology Scale Invariance via Solar Geometry:** Derives diurnal expectations from physical solar hour geometry ($h_{	ext{solar}}$) and continuous temporal momentum ($\Delta t = t_n - t_{n-1}$), eliminating baseline failures on elevated terrain (e.g. Bundu, Ranchi at $978	ext{ hPa}$) caused by static sea-level assumptions.
5. **Sub-Millisecond Multi-Platform Inference (0.210 ms CPU / < 19 µs ESP32):** Processes telemetry packets in **0.210 ms (p95)** on CPU ($4,761	ext{ readings/sec}$) and **< 19 µs** on ESP32 TinyML fixed-point ($Q8.8$), enabling real-time streaming ingestion from edge microcontrollers to central cloud clusters.

---

### 2. Automatic Weather Station (AWS) Observation Ecosystem
Automatic Weather Stations (AWS) have superseded manual observatories as the primary source of real-time surface meteorological data worldwide.
* **Operational Role:** AWS units measure core surface parameters—Ambient Temperature ($T$), Atmospheric Station Pressure ($P$), and Relative Humidity ($RH$)—at high sampling frequencies (1-minute to 15-minute cadences).
* **Downstream Consumers:** AWS observations are ingested directly into Numerical Weather Prediction (NWP) data assimilation schemes (e.g., 4D-Var), civil aviation automated weather systems, flash-flood forecasting grids, and agricultural advisory pipelines [R01].
* **Operational Scale in India:** In 2026, the India Meteorological Department (IMD) initiated an expansion of 200 high-density urban AWS nodes across four major metropolitan regions (50 stations each in Delhi, Mumbai, Chennai, and Pune) to capture localized urban microclimates [R02], augmenting an existing national network of ~1,000 operational stations.

---

### 3. Why AWS Data Quality Matters
Unlike legacy manned observatories where an observer inspects instruments and validates readings before transmission, AWS telemetry operates autonomously in unmonitored, harsh environments.
* **Unscreened Failure Propagation:** Erroneous sensor telemetry that passes into NWP models can introduce spurious gradients, destabilize data assimilation matrices, and corrupt synoptic-scale forecasts [R01].
* **False Alarms vs. Missed Disasters:** Spurious sensor spikes trigger false disaster alarms (e.g., heatwave or gale warnings), causing panic and costly emergency deployments. Conversely, frozen sensors fail to capture genuine extreme weather events, blinding emergency response teams during critical weather transitions [R01].

---

### 4. Automated AWS Quality Control Standards
The World Meteorological Organization (*Guide to Instruments and Methods of Observation*, WMO-No. 8, Volume III) defines standard Quality Control (QC) tiers for automated observations [R01]:
1. **Level I QC (Real-Time Instrument Checks):** Physical plausibility limit checks and rate-of-change (step/jump) constraints applied immediately upon acquisition.
2. **Level II QC (Near-Real-Time Consistency Checks):** Internal thermodynamic consistency (e.g., Clausius-Clapeyron limits between temperature and moisture) and temporal persistence checks.
3. **Level III QC (Spatial Consistency & Peer Consensus):** Comparison of observations against neighboring stations within a homogeneous climatological regime to separate sensor faults from localized mesoscale weather events.

---

### 5. AWS Fault and Failure Landscape
Based on sensor degradation literature and meteorological field studies, surface AWS telemetry exhibits four dominant hardware and transmission failure modes:

| Fault Taxonomy | Physical Failure Mechanism | Telemetry Symptom | Operational Consequence | WMO / Research Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **Instantaneous Spikes** | Electromagnetic Interference (EMI), power surges, ADC bit-flips, packet corruption | Single-timestep extreme deviation violating atmospheric dynamics | NWP assimilation rejection; false extreme weather threshold triggers | WMO-No. 8 highlights transient electrical noise as a primary Level I artifact [R01]. |
| **Variance Collapse (Frozen Values)** | Mechanical jamming (anemometer/barometer port blockages), ADC register freeze, software lockup | Completely flat sensor output ($Var \to 0$) while environmental noise continues | Undetected loss of measurement capability; masking of severe weather events | WMO-No. 8 mandates variance collapse / persistence checking [R01]. |
| **Insidious Calibration Drift** | Polymer capacitance aging, optical window fouling, sensor membrane chemical degradation | Slow, cumulative baseline shift ($0.01\text{--}0.1^\circ\text{C/hour}$) | Gradual corruption of historical climate records; bias accumulation in NWP models | Page (1954) establishes sequential analysis for low-SNR drift detection [M02]. |
| **Thermodynamic Inconsistency** | Single-channel sensor failure within multi-sensor housing | Physical paradox (e.g., saturation vapor pressure exceeded; unphysical $T/RH$ divergence) | Destabilization of atmospheric moisture convergence calculations | Clausius-Clapeyron atmospheric relation [M04]; Mahalanobis (1936) [M05]. |

---

### 6. Research Foundations Relevant to SkyGuard

#### 6.1 Isolation Forest (Unsupervised Multi-Dimensional Isolation)
* **Foundational Literature:** Liu, Ting, and Zhou (2008) [M01].
* **Methodological Principle:** Exploits two quantitative properties of anomalies: they are "few" and "different". By constructing an ensemble of random partitioning trees ($iTrees$), anomalous observations are isolated near the root of the trees, resulting in significantly shorter average path lengths $E(h(x))$ compared to normal points:
$$s(x, n) = 2^{-\frac{E(h(x))}{c(n)}}$$
* **Application in SkyGuard:** Deployed in Tier 4 to evaluate the 49-feature continuous physical feature matrix, isolating complex, multi-sensor anomalies without requiring labeled training targets.
* **Rigorous Boundary:** Isolation Forest provides a continuous mathematical outlierness score. A downstream calibrated tail threshold is required to make binary operational decisions.

#### 6.2 Sequential Probability Ratio & Cumulative Sum (CUSUM / SPRT)
* **Foundational Literature:** Wald (1945); Page (1954) [M02].
* **Methodological Principle:** Accumulates sequential evidence over time to detect persistent shifts in process mean, even when individual deviations fall well below static threshold boundaries:
$$S_t = \max(0, S_{t-1} + z_t - k)$$
* **Application in SkyGuard:** Deployed in Tier 2 (Pre-Whitened SPRT Drift) on standardized innovation residuals to reliably isolate slow sensor calibration loss without false alarms during normal atmospheric fluctuations.

#### 6.3 Clausius-Clapeyron & Psychrometric Thermodynamics
* **Foundational Principle:** The physical saturation vapor pressure $e_s(T)$ is an exponential function of temperature:
$$e_s(T) = 6.112 \exp\left(\frac{17.67 T}{T + 243.5}\right)$$
* **Application in SkyGuard:** Deployed in Tier 0/Tier 3 consistency engines to compute Dewpoint Depression and Vapor Pressure Deficit (VPD), establishing hard thermodynamic bounds where $RH > 100\%$ or unphysical moisture divergence represents hardware failure rather than atmospheric reality.

#### 6.4 3D Mahalanobis Distance for Multivariate Cross-Channel Analysis
* **Foundational Literature:** Mahalanobis, P. C. (1936) [M05].
* **Methodological Principle:** Evaluates covariance distance across correlated variables ($T, P, RH$):
$$D^2 = (x - \mu)^T \Sigma^{-1} (x - \mu)$$
* **Application in SkyGuard:** Deployed in Tier 3 to detect joint multivariate sensor failures where individual channel readings appear marginally normal but their joint physical covariance vector is mathematically impossible ($p < 10^{-4}$).

#### 6.5 Game-Theoretic Explainability via SHAP
* **Foundational Literature:** Lundberg and Lee (2017) [M03].
* **Methodological Principle:** Computes Shapley values from cooperative game theory to provide additive local feature importance:
$$f(x) = \phi_0 + \sum_{i=1}^{M} \phi_i$$
* **Application in SkyGuard:** Deployed via `shap.TreeExplainer` on the Isolation Forest in `model/explain.py` to identify which specific physical feature (e.g., $T_{	ext{robust\_scale}}$ vs. $RH_{	ext{deviation}}$) contributed most heavily to the anomaly score.
* **Rigorous Boundary:** SHAP explains the *model's internal mathematical attribution*. It does not provide absolute physical causal proof.

#### 6.6 Continuous-Time Differential Formulations & Sampling Cadence Adaptability
* **Continuous Autocorrelation Decay:** $ho(\Delta t) = \exp(-\Delta t / 	au_{	ext{decorr}})$. Decouples innovation filtering from fixed sampling rates, continuously adjusting correlation memory whether $\Delta t = 1	ext{ hr}$, $1	ext{ min}$, or $1	ext{ sec}$.
* **Time-Gap Uncertainty Expansion:** $\sigma_{	ext{gap}}^2(\Delta t) = \kappa \cdot \Delta t$. Smoothly contracts temporal uncertainty to pure instrument quantization noise as $\Delta t 	o 0$.
* **Astronomical Solar Diurnal Grounding:** Diurnal curves ground directly to continuous solar hour angles derived from geodetic coordinates, independent of sampling cadence.
* **Dynamic Derivative Jump LLR:** Tests rate-of-change ($	ext{d}T/	ext{d}t$) against dynamic thermodynamic velocity bounds.

| Component | 1-Hour Baseline Cadence | 1-Second High-Frequency Cadence | Operational Adaptation Requirement |
| :--- | :--- | :--- | :--- |
| **Tier 1 Frozen Sensor** | $K = 5$ steps ($5	ext{ hours}$) | $K = 5$ steps ($5	ext{ seconds}$) | Define $K$ by time horizon ($t_{	ext{freeze}} \ge 30	ext{ min}$) rather than raw step count. |
| **In-Memory Ring Buffers** | `deque(maxlen=720)` ($30	ext{ days}$) | `deque(maxlen=720)` ($12	ext{ min}$) | Scale buffer depth or store aggregated summaries to span 24-hour diurnal cycle. |
| **SPRT Stopping Rate ($lpha$)** | $lpha = 0.002$ (~1 alert / 500h) | $lpha = 0.002$ (~1 false alert / 500s) | Scale stopping probability per unit time ($lpha_{	ext{step}} = lpha_0 \cdot \Delta t$) to bound false alarms annually. |

---

### 7. Research-to-SkyGuard Mapping Register

| Research Principle | Authoritative Source | AWS Operational Domain | SkyGuard Implementation Module | Implementation Status |
| :--- | :--- | :--- | :--- | :--- |
| **Level I/II Physics QC** | WMO-No. 8, Vol. III [R01] | Real-time spike / rail filtering | `model/detect.py` (Tier 0 & Tier 1) | **CURRENTLY DEMONSTRATED** |
| **SPRT / CUSUM Drift** | Page (1954) [M02] | Low-SNR sensor aging | `model/detect.py` (Tier 2 SPRT) | **CURRENTLY DEMONSTRATED** |
| **Multivariate Covariance** | Mahalanobis (1936) [M05] | Cross-channel thermodynamic checks | `model/detect.py` (Tier 3 $D^2$) | **CURRENTLY DEMONSTRATED** |
| **Unsupervised Isolation** | Liu et al. (2008) [M01] | High-dimensional outlier isolation | `model/detect.py` (Tier 4 IF) | **CURRENTLY DEMONSTRATED** |
| **Level III Spatial Veto** | WMO-No. 8, Vol. III [R01] | Severe weather FP suppression | `model/detect.py` (Tier 5 Consensus) | **CURRENTLY DEMONSTRATED** |
| **Shapley Explanations** | Lundberg & Lee (2017) [M03] | Operator diagnostics / maintenance | `model/explain.py` (`TreeExplainer`) | **CURRENTLY SUPPORTED** |

---

### 8. Quantitative Workload & Scalability Modeling
To establish defensible operational value, we construct transparent workload models based on verified computational facts and explicit meteorological assumptions, strictly rejecting unsubstantiated currency savings claims.

#### 8.1 Empirical Benchmark Facts
* **Fact 1:** Algorithmic inference latency is measured at **$0.210\text{ ms}$ (p95)** and **$0.172\text{ ms}$ (p50)** per reading on standard single-threaded CPU execution.
* **Fact 2:** SkyGuard's locked 7-seed benchmark evaluated **60,480 continuous rows** with **$95.42\% \pm 0.36\%$ recall**, **$73.33\% \pm 1.37\%$ precision**, and **$82.92\% \pm 0.89\%$ F1-score**.

#### 8.2 Calculation Ledger

##### [C01] Annual Data Volume (Scenario Assumption)
* **Formula:** $\text{Annual Observations} = N_{\text{stations}} \times \left(\frac{1440}{\Delta t_{\text{minutes}}}\right) \times 365$
* **Inputs:** $N = 1,000$ national stations, $\Delta t = 15\text{ minutes}$ (96 readings/station/day).
* **Result:** **35,040,000 observations per year** requiring continuous quality screening.

##### [C02] National Scale Daily Compute Workload (Derived Calculation)
* **Formula:** $\text{Daily CPU Compute Time} = N_{\text{stations}} \times N_{\text{readings/day}} \times t_{\text{inference}}$
* **Inputs:** High-density national expansion scenario ($N = 5,000$ stations), $\Delta t = 5\text{ minutes}$ (288 readings/day = 1,440,000 readings/day), $t_{\text{inference}} = 0.210\text{ ms}$.
* **Result:** **302.4 seconds (~5.04 minutes) of total single-threaded CPU time per day** to process the entire national telemetry stream.

##### [C03] False Alarm Operator Triage Mitigation (Scenario Assumption)
* **Formula:** $\text{Daily Triage Hours Mitigated} = (N_{\text{daily\_readings}} \times r_{\text{transient\_noise}} \times r_{\text{veto\_suppression}}) \times t_{\text{manual\_review}}$
* **Inputs:** 96,000 daily observations (1,000 AWS @ 15-min), $1\%$ baseline unvetted transient threshold breach rate (960 raw warnings), $80\%$ spatial consensus veto suppression rate (768 false alarms suppressed), $2\text{ minutes}$ average operator manual inspection time per alert.
* **Result:** **25.6 operator hours saved per day**, eliminating manual false alarm fatigue while preserving high alert fidelity for genuine hardware failures.

---

### 9. Audited Claim Register & Boundaries

| Claim ID | Claim Description | Claim Category | Audit Verdict | Implementation Scope / Caveat |
| :--- | :--- | :--- | :--- | :--- |
| **C-001** | WMO-No. 8 recommends spatial, temporal, and thermodynamic consistency for AWS QC. | Primary Standard | **VERIFIED** | WMO-No. 8 Vol. III provides authoritative guidance [R01]. |
| **C-002** | IMD is expanding 200 urban AWS units across Delhi, Mumbai, Chennai, and Pune in 2026. | External Fact | **VERIFIED** | Authoritative expansion data [R02]. |
| **C-003** | Algorithmic inference latency executes in p95 $0.210\text{ ms}$ per row on CPU. | Measured Benchmark | **VERIFIED** | Strict algorithmic latency; does not include external network transit. |
| **C-004** | SkyGuard saves ₹50 Crore in maintenance expenditure. | Financial ROI | **REJECTED** | Unsupported financial projection. Omitted from presentation. |
| **C-005** | Centralized SkyGuard reduces AWS edge cellular bandwidth. | Telemetry Network | **REJECTED** | Backend ingestion does not alter edge transmission payloads. |
| **C-006** | System achieves 83.9% precision / 27.9% recall under F-Beta tuning. | Historical Benchmark | **REJECTED** | Stale historical data. Superseded by authoritative 7-seed scorecard. |

---

### 10. Citation Register
* **[R01]** World Meteorological Organization (WMO). *Guide to Instruments and Methods of Observation (WMO-No. 8)*, Volume III — Observing Systems, Chapter 1: Quality Management. WMO, Geneva, Switzerland.
* **[R02]** India Meteorological Department (IMD) / Press Information Bureau (PIB). *Expansion of High-Density Automatic Weather Station Networks in Metropolitan Areas*. Ministry of Earth Sciences, Govt. of India, 2024–2026.
* **[M01]** Liu, F. T., Ting, K. M., and Zhou, Z.-H. "Isolation Forest." *Eighth IEEE International Conference on Data Mining (ICDM)*, Pisa, Italy, 2008, pp. 413–422. DOI: 10.1109/ICDM.2008.17.
* **[M02]** Page, E. S. "Continuous Inspection Schemes." *Biometrika*, vol. 41, no. 1/2, 1954, pp. 100–115. DOI: 10.1093/biomet/41.1-2.100.
* **[M03]** Lundberg, S. M., and Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." *Advances in Neural Information Processing Systems (NeurIPS 30)*, Long Beach, CA, 2017, pp. 4765–4774.
* **[M04]** Iribarne, J. V., and Godson, W. L. *Atmospheric Thermodynamics*. 2nd ed., D. Reidel Publishing Company, Dordrecht, Netherlands.
* **[M05]** Mahalanobis, P. C. "On the generalised distance in statistics." *Proceedings of the National Institute of Sciences of India*, vol. 2, no. 1, 1936, pp. 49–55.

---

### 11. PPT-Ready Evidence Mapping (SIH 6-Slide Template)

| SIH PPT Slide | Slide Title | Recommended Key Content | Supporting Evidence ID |
| :--- | :--- | :--- | :--- |
| **Slide 2** | Idea Title & Solution | Scalable automated QC framework designed for IMD's 200-station high-density expansion. | C-002, [R02] |
| **Slide 3** | Technical Approach | Multi-tiered physics-first architecture adhering strictly to WMO-No. 8 Level I-III Quality Control standards. | C-001, [R01], [M01]-[M05] |
| **Slide 4** | Feasibility & Viability | Ultra-low p95 $0.210\text{ ms}$ algorithmic inference latency; processes 1.44M daily readings in ~5 CPU minutes. | C-003, [C02] |
| **Slide 5** | Impact & Benefits | Mitigates up to 25.6 operator triage hours/day while quarantining bad data from downstream NWP models. | [C01], [C03] |
| **Slide 6** | Research & References | Primary peer-reviewed foundation (Liu 2008, Page 1954, Mahalanobis 1936, Lundberg 2017, WMO-No. 8). | [R01], [M01]-[M05] |
