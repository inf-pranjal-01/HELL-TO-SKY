# SKYGUARD AI — DOCUMENT 1
## External Research, Evidence, Citations, Impact & Benefit Dossier
**Authoritative Evidence Base for SIH 2026 Presentation & Technical Defense**

---

### 1. Executive Summary
**SkyGuard AI** is an intelligent real-time data quality control and anomaly detection system for Automatic Weather Stations (AWS). Modern meteorological agencies continuously collect surface weather readings—such as Ambient Temperature, Atmospheric Station Pressure, and Relative Humidity—at high temporal frequencies (every 1 to 15 minutes). Because these sensors operate unattended in harsh outdoor environments, they frequently suffer from hardware glitches, power surges, sensor degradation, and communication drops.

When bad data passes unflagged into Numerical Weather Prediction (NWP) forecast models, it corrupts weather forecasts and triggers costly false disaster alarms. SkyGuard AI solves this problem by providing an automated, sub-millisecond screening pipeline grounded in thermodynamic physics, statistical change detection, spatial peer verification, and machine learning. All performance metrics and operational workload models presented in this document are derived directly from verified empirical code benchmarks, strictly excluding unverified financial claims.

#### Top 5 System Unique Selling Propositions (USPs)
1. **Smart 6-Tier Physics Screening & Spatial Peer Cross-Check:** Evaluates physical weather laws (such as temperature, pressure, and humidity relationships) before applying statistical models, and checks neighboring stations within 50 km to stop false alarms during real storm fronts.
2. **Continuous Uninterrupted Streaming Passover (Suggested Replacement Readings):** When a sensor sends bad or missing data, the system instantly estimates and suggests a physically accurate replacement value so weather forecasting models keep running smoothly without crashing.
3. **Anti-Poisoning Data Quarantine & Health Score Lifecycle:** Automatically isolates bad data so it cannot corrupt long-term baseline statistics, and tracks station health scores (0 to 100) to notify operators when maintenance is needed.
4. **Elevation & Climate Scale Adaptability:** Automatically adjusts baseline expectations for high-altitude stations (such as mountain or plateau weather stations) so altitude differences do not trigger fake alarms.
5. **Sub-Millisecond Multi-Platform Speed:** Processes each weather reading in just **0.210 milliseconds (p95)** on central computers (handling over 4,700 readings per second) and under **19 microseconds** on low-cost ESP32 microcontrollers.

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

### 6. Prototype Status & Future Scope
SkyGuard AI is an **~80% complete, fully functional working prototype**. It has been tested and validated across a 28-station network topology under blind chronological evaluation datasets.

#### 6.1 Currently Built & Operational Features (~80% Complete Prototype)
* **6-Tier Physics & ML Detection Engine:** Complete multi-tier priority arbitration combining physical invariants, SPRT drift, 3D Mahalanobis, and spatial peer consensus.
* **Continuous Streaming Imputation (Suggested Replacement Readings):** Real-time 4-tier fallback generator providing clean substitute readings when data is missing or corrupted.
* **Dynamic Sensor Health & Quarantine:** Station health tracking with continuous score hysteresis (0 to 100) to isolate faulty sensors and prevent baseline corruption.
* **Ultra-Low Latency Inference:** Optimized code running in 0.210 ms (p95) on CPU and under 19 microseconds on ESP32 microcontrollers.
* **Real-Time Operator Web Dashboard:** Live dashboard with interactive maps, live streaming endpoints, and SHAP diagnostic explanations.

#### 6.2 Future Scope & Institutional Deployment Roadmap
* **Native WMO Data Format Adapters:** Adding direct binary decoders for WMO BUFR and NetCDF4 meteorological file formats.
* **Institutional Security & Access Control:** Integrating CERT-In cybersecurity compliance, OAuth2/SAML single sign-on, and role-based access control.
* **Automated Technician Dispatch ERP:** Direct integration with GIS maintenance ticketing systems to auto-dispatch field technicians when health scores drop.
* **Multi-Year Field Deployment:** Extended operational field trials across diverse weather regions (monsoon, coastal, desert, and high-altitude alpine stations).

---

### 7. Evidence & Source Traceability Register
This register maps key technical claims directly to their underlying standards and peer-reviewed citations:

| Claim ID | Claim Description | Primary Source / Standard |
| :--- | :--- | :--- |
| **C-001** | WMO mandates Level I-III physical, temporal, and spatial Quality Control for AWS. | WMO-No. 8 (Vol. III, Ch. 1) [R01] |
| **C-002** | High-density AWS networks capture localized urban and regional microclimates. | IMD / PIB Technical Reports [R02] |
| **C-003** | Single-reading algorithmic inference executes in p95 $0.210\text{ ms}$ on standard CPU. | Benchmark Profiler Artifact [E01] |
| **C-004** | Sequential SPRT / CUSUM accumulates low-SNR calibration drift evidence. | Page (1954); Wald (1945) [M02] |
| **C-005** | Isolation Forests isolate high-dimensional anomalies with linear time complexity. | Liu, Ting, Zhou (2008) [M01] |
| **C-006** | SHAP additive feature attributions provide component-level failure diagnostics. | Lundberg & Lee (2017) [M03] |

---

### 8. Citation Register
* **[R01]** World Meteorological Organization (WMO). *Guide to Instruments and Methods of Observation (WMO-No. 8)*, Volume III — Observing Systems, Chapter 1: Quality Management. WMO, Geneva, Switzerland.
* **[R02]** India Meteorological Department (IMD) / Press Information Bureau (PIB). *Expansion of High-Density Automatic Weather Station Networks in Metropolitan Areas*. Ministry of Earth Sciences, Govt. of India, 2024–2026.
* **[M01]** Liu, F. T., Ting, K. M., and Zhou, Z.-H. "Isolation Forest." *Eighth IEEE International Conference on Data Mining (ICDM)*, Pisa, Italy, 2008.
* **[M02]** Page, E. S. "Continuous Inspection Schemes." *Biometrika*, 1954.
* **[M03]** Lundberg, S. M., & Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." *NeurIPS*, 2017.
* **[M04]** Iribarne, J. V., & Godson, W. L. *Atmospheric Thermodynamics*, 1981.
* **[M05]** Mahalanobis, P. C. "On the generalised distance in statistics." *Proc. Nat. Inst. Sci. India*, 1936.
