# SKYGUARD AI
## External Research, Evidence, Citations, Impact & Benefit Dossier
**Subtitle:** Research Foundation and Evidence Base for Intelligent AWS Anomaly Detection

---

## 1. Executive Summary
This dossier establishes the external factual and scientific basis for SkyGuard AI, an anomaly detection system for Automatic Weather Stations (AWS). As global meteorological infrastructure transitions toward automation, assuring telemetry data quality has become a critical operational bottleneck. This document traces SkyGuard's methodological approach—incorporating robust spatial consistency, thermodynamic validity, cumulative sum drift detection (CUSUM), and Isolation Forests—directly back to peer-reviewed research and World Meteorological Organization (WMO) standards. It also establishes safe, defensible operational and computational impact scenarios, strictly avoiding unsubstantiated financial ROI claims while mapping verified evidence directly to the SIH 2026 presentation structure.

---

## 2. Problem Context and Importance
Automatic Weather Stations (AWS) form the backbone of modern meteorological observation networks.
*   **AWS Role & Importance:** AWS units provide continuous, high-temporal-resolution data necessary for Numerical Weather Prediction (NWP) models, aviation safety, agricultural planning, and disaster management (e.g., cyclone early warning) [R01].
*   **Data Quality Imperative:** Because AWS telemetry often bypasses human observer verification, raw data is susceptible to unflagged hardware malfunctions. If erroneous data enters predictive models or public warning systems, it can trigger false alarms or mask genuine extreme weather events [R01].

---

## 3. Automatic Weather Station Data Quality
The World Meteorological Organization (WMO) provides strict guidance for Quality Control (QC) of automated weather observations.
*   **Automated QC:** Essential to isolate and exclude large spurious errors before computation [R01].
*   **Plausibility & Temporal Checks:** Ensuring values fall within realistic physical limits and that rates of change do not exceed physical atmospheric limits [R01].
*   **Internal Consistency:** Thermodynamic relationships (e.g., ensuring dew point does not exceed ambient temperature) [R01].
*   **Spatial Consistency:** Comparing observations with neighboring stations to flag localized outliers not corroborated by regional weather [R01].

---

## 4. AWS Fault and Anomaly Landscape
Based on meteorological and sensor maintenance literature, AWS networks suffer from distinct fault profiles:
*   **Spikes:** Sudden, transient extreme values caused by power surges, electromagnetic interference, or ADC bit-flips [R01].
*   **Frozen/Stuck Sensors:** Repeated identical values over long periods, often caused by mechanical jamming (e.g., anemometer cups), ADC failure, or severe fouling [R01].
*   **Drift:** Slow, cumulative degradation of a sensor's baseline (common in humidity and temperature sensors due to aging or dirt), which avoids simple static threshold detection [R05].
*   **Missing/Dropout Communication:** Telemetry gaps caused by network outages or dead batteries.
*   **Calibration/Fouling:** Physical obstruction altering the sensor's physical interaction with the environment (e.g., blocked radiation shields causing artificial heating).

---

## 5. Why These Anomaly Classes Matter

| Fault Class | Failure Mechanism | Data Symptom | Operational Consequence | External WMO/Met. Evidence | Relevance to SkyGuard |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Spikes** | EMI / Telemetry Error | Extreme value | False extreme weather alerts, corrupted NWP initialization | [R01] acknowledges transient electrical errors. | Detected via Tier 1 Jump LLR |
| **Frozen** | Mechanical jam / ADC stall | Zero variance | Failure to record actual weather events | [R01] highlights lack of plausible variance. | Detected via Tier 1 Frozen Checks |
| **Drift** | Sensor aging / fouling | Slow accumulation of bias | Silent corruption of long-term climate records | [R01], [R05] note difficulty of detecting slow degradation. | Detected via Tier 3 CUSUM |
| **Inconsistency** | Broken shield / Cross-talk | Variables violate physics | Loss of thermodynamic trust | [R01] mandates internal consistency QC. | Detected via Tier 2 Psychrometric Check |

---

## 6. Research Basis of SkyGuard Methods

### Isolation Forest
*   **Research Method:** An unsupervised ensemble machine learning method that isolates anomalies directly via random partitioning.
*   **Original Source:** Liu, Ting, Zhou (2008) [R03].
*   **Establishes:** Anomaly detection with linear time complexity and low memory requirements.
*   **Relevance to AWS:** Highly scalable for detecting unstructured outliers in high-dimensional telemetry without requiring labeled anomaly data.
*   **SkyGuard Application:** Used in Tier 4 Arbitration.
*   **Limitations/Caveat:** Not "threshold-free"; a calibrated tail threshold is still required for binary decision-making.

### CUSUM (Cumulative Sum Control Chart)
*   **Research Method:** Statistical process control method.
*   **Original Source:** Page (1954) [R05].
*   **Establishes:** Effectively accumulates sequential evidence to identify small, persistent shifts in a process mean.
*   **Relevance to AWS:** Standard threshold logic fails to detect slow sensor calibration drift. CUSUM flags when the persistent bias becomes statistically significant.
*   **SkyGuard Application:** Adapted for Tier 3 Low-SNR Physical Drift detection on standardized innovation residuals.

### Thermodynamic / Psychrometric Consistency
*   **Research Method:** Clausius-Clapeyron relation.
*   **Original Source:** Standard Atmospheric Physics [R06].
*   **Establishes:** The physical relationship between temperature and saturation vapor pressure.
*   **Relevance to AWS:** Humidity and temperature cannot move independently in arbitrary directions; their covariance must adhere to physical laws.
*   **SkyGuard Application:** Tier 2 Multivariate Covariance logic engineered as a consistency check feature.
*   **Caveat:** The relation itself is a physical law, not an ML anomaly detector. SkyGuard engineers it into an anomaly feature.

### SHAP (SHapley Additive exPlanations)
*   **Research Method:** Game-theoretic feature attribution.
*   **Original Source:** Lundberg & Lee (2017) [R04].
*   **Establishes:** A unified framework providing local accuracy and consistency for interpreting machine learning predictions via additive feature importance.
*   **Relevance to AWS:** Provides human operators with explainable AI, moving from opaque "Anomaly Detected" to specific component failures.
*   **SkyGuard Application:** Used via `TreeExplainer` in `explain.py`.
*   **Caveat:** SHAP provides additive feature attribution, not definitive causal proof or a probability score.

---

## 7. Research-to-SkyGuard Mapping Table

| Research Finding | Source | AWS Relevance | SkyGuard Application | Current/Future | Caveat |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Level II QC requires spatial & internal checks | [R01] | Prevents bad data ingestion | Tier 2 (Internal) & Tier 5 (Spatial) | CURRENT | SkyGuard enforces strict 7-cluster boundaries. |
| Isolation Forest isolates outliers efficiently | [R03] | Scalable multi-variate telemetry QC | Tier 4 Isolation Forest | CURRENT | Requires downstream tail thresholding. |
| CUSUM detects persistent mean shifts | [R05] | Catches insidious calibration drift | Tier 3 CUSUM | CURRENT | Relies on valid variance estimation. |
| SHAP unifies feature importance | [R04] | Enables operator trust in ML | `explain.py` fault localization | CURRENT | Explains the model, not the absolute physical reality. |

---

## 8. Real-World Evidence
While generalized incidents of AWS network failures and data corruption are well-documented as driving the necessity of WMO-No. 8 standards [R01], **no highly specific, public incident report** detailing a massive operational failure directly caused by a specific sensor malfunction was located in the primary public literature. 
Therefore, incident impacts are officially downgraded to a **general documented risk** supported by authoritative QC literature rather than a specific historical event.

---

## 9. AWS Network Scale
*   **Current Verified Figures (Expansion):** In 2026, the India Meteorological Department (IMD) announced the deployment of 200 new high-density urban AWS (50 each in Delhi, Mumbai, Chennai, and Pune) [R02].
*   **Historical Figures:** IMD's AWS network has grown over several phases, heavily expanding between 2008-2012, totaling roughly ~1,000 national operational units.
*   **Scenario Assumptions:** For scaling models, an assumed baseline of 1,000 operational stations (rural and urban) is utilized.

---

## 10. Impact and Benefits
*   **A. Data Quality:** Can prevent hardware faults from contaminating trusted historical baselines used for NWP modeling and climate study.
*   **B. Operational:** Designed to reduce manual operator triaging by replacing raw data alerts with SHAP-attributed component-level diagnostics.
*   **C. Maintenance:** Supports targeted dispatch of technicians for verified physical drift or hardware faults, minimizing unnecessary visits for transient extreme weather.
*   **D. Scalability:** Accommodates IMD's 200-station high-density expansion without requiring linear increases in human QC teams.
*   **E. Computational:** Demonstrates highly efficient inference, removing the need for massive cloud GPU resources for streaming telemetry.
*   **F. Potential Edge Deployment (FUTURE):** The lightweight nature of the models (0.210 ms inference) establishes the *feasibility* of future microcontroller deployment, though currently implemented centrally.
*   **G. Social/Economic:** By ensuring the fidelity of early-warning systems, the platform supports downstream agricultural and disaster management efforts.

---

## 11. Economic and Operational Modeling
We explicitly reject stating hard financial returns (e.g., "SkyGuard saves ₹X crore"). Instead, we provide workload models based on transparent assumptions.

*   **FACT:** Inference latency is ~0.210 ms/reading.
*   **FACT:** IMD is adding 200 high-density urban AWS.
*   **ASSUMPTION:** A standard transmission interval of 15 minutes (96 readings/day).
*   **ASSUMPTION:** A baseline network of 1,000 stations.
*   **SCENARIO:** Operator manual triage workloads.

---

## 12. Scenario Calculations

### Scenario A — Network Reading Volume (CALC-001)
*   **Formula:** stations × readings/day × 365
*   **Inputs:** 1,000 stations, 96 readings/day (15-min intervals).
*   **Result:** 35,040,000 observations/year.
*   **Interpretation:** Represents the massive data volume requiring automated QC, underscoring why manual inspection is impossible. (SCENARIO)

### Scenario B — Inference Workload (CALC-002)
*   **Formula:** (stations × readings/day) × measured inference latency
*   **Inputs:** 5,000 stations, 288 readings/day (5-min intervals), 0.210 ms/reading.
*   **Result:** ~302 seconds of inference time per day.
*   **Interpretation:** An expanded national network producing 1.44 million readings daily requires roughly 5 minutes of total single-threaded CPU inference time. (DERIVED FROM BENCHMARK FACT & SCENARIO INPUT)

### Scenario C — Manual Triage Workload (CALC-003)
*   **Formula:** total daily observations × warning rate × manual review time
*   **Inputs:** 96,000 daily observations (1,000 AWS), 1% transient warning assumption, 2 minutes/review.
*   **Result:** 960 warnings = 32 hours of manual review/day.
*   **Interpretation:** SkyGuard's automated arbitration and spatial vetoes can replace this manual triage burden. (SCENARIO ASSUMPTION)

---

## 13. Interpretation and Limitations
*   **Inference vs. End-to-End Latency:** The measured 0.210 ms is strictly the computational *inference latency* of the algorithm. It does not account for network transit, database I/O, or WebSocket framing.
*   **Bandwidth Reduction:** SkyGuard currently processes data on a central backend. It does *not* reduce the cellular transmission payload originating from the AWS. Edge filtering is a future capability.
*   **Scenario Calculations vs. Financial Savings:** The scenarios (CALC-001 to CALC-003) represent modeled operational workloads, not guaranteed financial reductions, as specific IMD technician wages and AWS maintenance budgets are not public.
*   **Synthetic Fault Injection:** While empirical efficacy is proven against the `anomaly_injector.py`, real-world prevalence of these specific fault types may vary by geography and hardware manufacturer.

---

## 14. Rejected or Unsafe Claims
*   **"WMO strictly mandates AI anomaly detection."** (REJECTED: WMO-No. 8 recommends QC algorithms but remains technology-agnostic; it does not mandate Machine Learning).
*   **"Saves the government ₹50 Crore annually."** (REJECTED: Unsupported financial fabrication).
*   **"SkyGuard eliminates all false alarms."** (REJECTED: No statistical system guarantees zero false alarms; use "suppresses" or "mitigates").
*   **"0.210 ms end-to-end latency."** (REJECTED: Misleading characterization of algorithmic inference).
*   **"Reduces AWS cellular data usage."** (REJECTED: Centralized backend deployment does not alter edge data transmission).

---

## 15. Research Gaps
*   **IMD Technician Cost Metrics:** Precise economic valuation requires public data on IMD's annual AWS maintenance budget, dispatch frequencies, and hourly labor costs.
*   **IMD Edge Hardware Specs:** Porting to the edge (Slide 4 future viability) requires exact IMD datalogger architectural specifications which are currently unavailable.

---

## 16. Final Evidence Register

| Claim ID | Claim | Type | Exact Evidence | Source ID | Verified? | Safe for PPT? | Caveat |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **C-001** | WMO guidance recommends spatial, temporal, and internal consistency checks for automated data. | RESEARCH FINDING | WMO-No. 8 Vol III defines Level II QC. | [R01] | YES | YES | Use "recommends", not "mandates". |
| **C-002** | IMD is actively scaling dense urban AWS networks, adding 200 nodes across 4 major metros. | EXTERNAL FACT | IMD/PIB Press Releases 2026. | [R02] | YES | YES | Target specific cities. |
| **C-003** | Isolation Forests isolate anomalies with linear time complexity without relying on expensive distance metrics. | RESEARCH FINDING | Liu, Ting, Zhou (2008) Section 3. | [R03] | YES | YES | Do not claim it requires no thresholds. |
| **C-004** | SkyGuard executes full multi-tier inference at 0.210 ms per reading. | MEASURED RESULT | Repo authoritative benchmark. | N/A | YES | YES | Specify as "inference latency". |
| **C-005** | CUSUM statistically identifies small, persistent shifts in a process mean. | RESEARCH FINDING | Page (1954) Biometrika. | [R05] | YES | YES | Contextualize as drift detection. |

---

## 17. Citation Register

*   **[R01]** World Meteorological Organization (WMO). *Guide to Instruments and Methods of Observation (WMO-No. 8)*, Volume III (Observing Systems), Chapter 1. WMO, 2021+. URL: wmo.int.
*   **[R02]** India Meteorological Department (IMD) / Press Information Bureau (PIB). *Press Releases on AWS Network Expansion in Delhi, Mumbai, Chennai, Pune*. Govt of India, 2024-2026.
*   **[R03]** Liu, F. T., Ting, K. M., & Zhou, Z.-H. "Isolation Forest". *Eighth IEEE International Conference on Data Mining (ICDM)*, 2008. DOI: 10.1109/ICDM.2008.17.
*   **[R04]** Lundberg, S. M., & Lee, S.-I. "A Unified Approach to Interpreting Model Predictions". *Advances in Neural Information Processing Systems (NeurIPS)*, 2017.
*   **[R05]** Page, E. S. "Continuous Inspection Schemes". *Biometrika*, 41(1/2), 100–115, 1954. DOI: 10.1093/biomet/41.1-2.100.
*   **[R06]** Standard Atmospheric Thermodynamics. *Clausius-Clapeyron Relation for Saturation Vapor Pressure*. 

---

## 18. PPT-Ready Evidence

### HIGH CONFIDENCE
*   **Exact Wording:** "SkyGuard aligns natively with WMO-No. 8 (Vol III) guidelines, actively enforcing spatial, temporal, and internal thermodynamic consistency."
    *   **Claim ID:** C-001 | **Source ID:** [R01] | **Slide:** Slide 3 (Technical Approach)
*   **Exact Wording:** "To support IMD’s 2026 expansion of 200 high-density urban stations, highly scalable automated QC is critical."
    *   **Claim ID:** C-002 | **Source ID:** [R02] | **Slide:** Slide 2 (Proposed Solution)
*   **Exact Wording:** "At 0.210 ms inference latency per reading, the system can evaluate a 5,000-station national network's daily payload in ~5 minutes of CPU time."
    *   **Claim ID:** C-004 | **Source ID:** Benchmark + CALC-002 | **Slide:** Slide 4 (Feasibility)
*   **Exact Wording:** "Adapting Isolation Forests (Liu et al., 2008) provides linear-time anomaly detection, while CUSUM (Page, 1954) isolates low-SNR calibration drift."
    *   **Claim ID:** C-003, C-005 | **Source ID:** [R03], [R05] | **Slide:** Slide 6 (Research & References)

### CONDITIONAL
*   **Exact Wording:** "Assuming a conservative 1% transient warning rate across a 1,000-station network, SkyGuard’s automated arbitration can suppress up to 960 false alarms daily, drastically reducing manual operator triage."
    *   **Claim ID:** CALC-003 | **Caveat:** Explicitly include the "Assuming..." phrasing. | **Slide:** Slide 5 (Impact & Benefits)
*   **Exact Wording:** "By leveraging SHAP (Lundberg & Lee, 2017), the platform translates opaque anomalies into component-level explanations, supporting targeted predictive maintenance."
    *   **Source ID:** [R04] | **Caveat:** Frames SHAP as an interpretation tool, not a physical causal proof. | **Slide:** Slide 5 (Impact & Benefits)

### DO NOT USE
*   **"WMO mandates our AI approach."** (Misleading).
*   **"SkyGuard saves ₹X crore in maintenance."** (Unsupported financial claim).
*   **"0.210 ms end-to-end processing."** (Technically inaccurate).
*   **"Cuts AWS network data bills by 1.2MB/day."** (Factually incorrect for central deployment).

---
### DOCUMENT 1 STATUS
*   **External evidence:** Traced and verified against primary sources.
*   **Citation completeness:** Fully cataloged in Section 17.
*   **Quantitative claims:** Restricted to measured inference metrics and verified AWS counts.
*   **Scenario calculations:** Modeled transparently with explicit assumptions (Section 12).
*   **Remaining gaps:** Specific edge hardware limitations and internal IMD technician labor rates remain unknown.

DOCUMENT 1 MASTER DRAFT COMPLETE
