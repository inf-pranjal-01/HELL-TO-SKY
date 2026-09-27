# ANTIGRAVITY — SKYGUARD AI
# PATH 2 — PRECISION STEP 11: FIXED-THRESHOLD LINEAGE & TRUE ADAPTIVITY AUDIT

**Status**: FINAL PRE-IMPROVEMENT AUDIT  
**Working Tree**: Uncommitted & Preserved | Baseline Detector Intact | Zero Production Changes  
**Investigative Scope**: Exhaustive code-archaeology inventory of all fixed constants, decision boundaries, placeholders, and data flows across the baseline detector codebase and its historical evolution.

---

## 1. Executive Summary

Path 2 was designed as a "dynamic, data-adaptive, evidential" anomaly detection architecture to replace the static heuristic thresholds of the legacy detector. However, a rigorous code audit reveals that the current baseline operates as a **hybrid system**:
1. **Dynamic Inputs & Normalization**: The feature generation, dynamic expectation $\mathbb{E}[y \mid \mathcal{C}]$, composite uncertainty budget $\sigma_t$, pre-whitening filters $\epsilon_t = r_t - \phi r_{t-1}$, and spatial peer consensus $\mu_{\text{peer}}$ are fully data-adaptive and dynamic.
2. **Fixed Statistical Decision Boundaries**: The terminal decision gates ($z \ge 3.0$, Wald SPRT boundary $A_{\text{Wald}} = 6.16$, $\chi^2_3$ critical $p < 0.001$, Isolation Forest $z_{\text{IF}} > 3.0 \land D^2 > 8.0$) are fixed mathematical constants derived from false-alarm constraints ($\alpha, \beta$).
3. **Surviving Placeholders**: A small number of domain-estimated placeholders (such as the fixed additive jump variance $0.25 \cdot \Delta t$ and pressure calmness guard $0.4\text{ hPa}$) survived into the active baseline.

This audit establishes that a **fixed decision boundary on a properly standardized evidential quantity** ($z = \frac{\Delta y}{\sigma_t} \ge 3.0$ or $S_t \ge \ln \frac{1-\beta}{\alpha}$) is mathematically sound and statistically principled. The failure in Step 7 was not the existence of fixed decision boundaries, but the **improper distortion of the standardized evidence numerator ($r = \Delta y - \mathbb{E}[\Delta y]$) and denominator ($\sigma_{\text{jump}}$ inflation)**.

---

## 2. Exact Threshold Chronology & Lineage

```
+----------------------------------------------------------------------------------------------------+
| 1. LEGACY DETECTOR (Draft 1 & 2)                                                                   |
|    - Purely static hard thresholds everywhere:                                                     |
|      * Spike: |z| > 3.5 on uncalibrated z-score                                                    |
|      * Frozen: std < 0.055 across rolling window                                                   |
|      * Drift: CUSUM > 6.0 with fixed slack allowance                                               |
|      * Fusion: MODEL_WEIGHT=0.6, RULE_WEIGHT=0.4, FUSION_THRESHOLD=50, MODEL_OVERRIDE=70           |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
| 2. PATH 2 STEP 1 & 2 (Evidential Architecture & 6-Tier Hierarchy)                                  |
|    - Eliminated legacy weighted fusion and arbitrary score additions.                              |
|    - Introduced formal Wald SPRT boundaries: ln((1-beta)/alpha) = 6.16 (alpha=0.002, beta=0.05).   |
|    - Introduced instrument quantization floors (T=0.10C, P=0.50hPa, RH=1.00%).                     |
|    - Introduced Chi-Square 3-DOF Mahalanobis test (p < 0.001, D^2 > 16.27).                        |
|    - Replaced |z| > 3.5 with standard normal tail z >= 3.0.                                       |
|    - Retained temporary placeholder: sigma_jump = sqrt(2*floor^2 + 0.25*dt).                       |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
| 3. PATH 2 STEP 3 & 4 (Peer Integration & Adversarial Audit)                                        |
|    - Added continuous spatial peer consensus.                                                      |
|    - Added pressure calmness guard: peer_dispersion < 0.4 hPa -> penalize frozen LLR.              |
|    - Adversarial audit rejected fixed peer delta thresholds (0.8 hPa) and reverted to baseline.    |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
| 4. PATH 2 STEP 5 & 6 (Contextual Innovation & Offline Study)                                       |
|    - Formulated expected movement E[dy|C] and residual process noise rates.                        |
|    - Offline validation showed high static separation under clean history.                         |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
| 5. PATH 2 STEP 7 (Contextual Innovation Production Failure)                                        |
|    - Replaced raw jump with contextual innovation r = dy - E[dy|C].                                |
|    - Hard-coded channel weights (P=0.85, T=0.20, RH=0.20) and process noise denominators.          |
|    - Result: Recall collapsed from 97.27% -> 82.01% (-15.26 pp).                                  |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
| 6. PATH 2 STEP 8, 9 & 10 (Forensic Autopsies & Factorial Audit)                                    |
|    - Restored pristine baseline (Precision 72.35%, Recall 97.27%, F1 82.97%).                     |
|    - Proved 81.31% of loss was Drift and 10.84% Frozen due to contextual suppression & contam.     |
|    - Reconciled 8,118 within-episode vs 320 inter-episode contamination points.                    |
|    - 2x2 Factorial proved Contextual Removal is primary (+12.51 pp) and Clean State is secondary.  |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
| 7. CURRENT BASELINE (Step 11 Verified State)                                                       |
|    - Pristine dynamic features + Wald SPRT architecture.                                          |
|    - Retains legitimate physical/instrument floors and derived Wald/Chi2 boundaries.               |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Master Inventory of Active Constants in Current Baseline

Every active numerical constant across [`model/detect.py`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/model/detect.py), [`model/uncertainty_budget.py`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/model/uncertainty_budget.py), [`model/sequential_sprt.py`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/model/sequential_sprt.py), and [`model/cross_channel_covariance.py`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/model/cross_channel_covariance.py):

| Constant / Rule Name | Value | File & Line | Category | Nature | Epistemic Justification | Step 12 Action |
| :--- | :---: | :---: | :--- | :---: | :--- | :--- |
| `TEMP_FAIL_LOW_RAIL` | $-40.0^\circ\text{C}$ ($\pm 0.05$) | `detect.py:90` | Physical / Hardware Rail | Fixed | Pt100 / thermistor ADC disconnect floor | **Keep Fixed** |
| `PRES_FAIL_LOW_RAIL` | $0.0\text{ hPa}$ ($\pm 0.05$) | `detect.py:92` | Physical / Hardware Rail | Fixed | Pressure transducer 0V ground short rail | **Keep Fixed** |
| `HUM_FAIL_LOW_RAIL` | $0.0\%$ ($\pm 0.05$) | `detect.py:94` | Physical / Hardware Rail | Fixed | Capacitive sensor 0V ground short rail | **Keep Fixed** |
| `SENSOR_QUANT_FLOORS` | $T=0.10, P=0.50, RH=1.00$ | `uncertainty_budget.py:17` | Instrument Characteristic | Fixed | AWS ADC quantization resolution floor | **Keep Fixed** |
| `THERMO_BOUNDS` | $T \in [-40, 60], P \in [300, 1100]$ | `cross_channel_covariance.py:15` | Physical Invariant | Fixed | Earth thermodynamic limits & Clausius-Clapeyron | **Keep Fixed** |
| `SPIKE_NOISE_GATE` | $|\Delta y| < 2.5 \cdot \sigma_{\text{floor}}$ | `detect.py:120` | Noise Gate | Dynamic ($2.5 \sigma_f$) | Prevents floating-point division on ADC noise | **Keep Fixed** |
| `SPIKE_ADDITIVE_VAR` | $0.25 \cdot \max(0.5, \Delta t)$ | `detect.py:123` | Temporary Placeholder | Fixed Constant | Arbitrary 0.25 variance added across all params | **Scale to Channel** |
| `WALD_UPPER_ALERT` | $\ln \frac{1-\beta}{\alpha} \approx 6.16$ | `detect.py:38` | Statistical Decision Boundary | Derived Constant | Formal Wald boundary for $\alpha=0.002, \beta=0.05$ | **Keep Derived** |
| `SPIKE_Z_THRESHOLD` | $z_{\text{jump}} \ge 3.0$ | `detect.py:129` | Statistical Decision Boundary | Fixed Constant | Standard Normal 3-sigma tail ($p < 0.00135$) | **Keep Standard** |
| `FROZEN_EXACT_HOLD` | $\text{range} < 10^{-4}, K \ge 5$ | `detect.py:167` | Instrument Characteristic | Fixed | Identical floats over 5+ hrs is impossible | **Keep Fixed** |
| `FROZEN_WINDOW_K` | $K = 5$ | `detect.py:159` | Operational Window | Fixed | Minimum sample size for variance estimation | **Keep Fixed** |
| `PRES_CALM_GUARD` | $\sigma_{\text{peer}} < 0.4\text{ hPa}$ | `detect.py:181` | Domain Heuristic | Fixed Constant | Regional barometric calm suppression | **Scale to Peer IQR** |
| `FROZEN_VAR_BOUND` | $s^2 \le (1.2 \sigma_{\text{floor}})^2$ | `detect.py:185` | Statistical Decision Boundary | Dynamic ($1.44 \sigma_f^2$) | Confirms variance collapse to ADC noise | **Keep Fixed** |
| `CUSUM_PHI` | $\phi = [0.70, 0.85, 0.65]$ | `sequential_sprt.py:22` | Data-Derived Parameter | Calibrated | AR(1) autocorrelation on clean training data | **Keep Calibrated** |
| `CUSUM_ALLOWANCE_K` | $k = 0.5 \cdot \sigma_t$ | `sequential_sprt.py:54` | Statistical Decision Parameter | Dynamic | Page's CUSUM optimal allowance $k = \delta/2$ | **Keep Dynamic** |
| `DRIFT_PEER_BOOST` | $\text{LLR} \times 1.4$ | `detect.py:383` | Domain Heuristic | Fixed Multiplier | Accelerates divergence against peer consensus | **Keep Heuristic** |
| `MAHALANOBIS_CHI2_P` | $p < 0.001$ ($D^2 > 16.27$) | `cross_channel_covariance.py:48` | Statistical Decision Boundary | Derived Constant | Chi-square 3-DOF distribution at $\alpha=0.001$ | **Keep Derived** |
| `IF_TAIL_Z` | $z_{\text{IF}} > 3.0 \land D^2 > 8.0$ | `detect.py:447` | Statistical Decision Boundary | Fixed Constant | Extreme statistical tail of Isolation Forest | **Keep Standard** |
| `AMBIGUOUS_MAX_Z` | $\max |z| > 2.2 \land N_{\text{peer}} = 0$ | `detect.py:467` | Statistical Decision Boundary | Fixed Constant | Flags uncorroborated tension for review | **Keep Standard** |
| `HEALTH_DEBOUNCE` | $\text{clean\_streak} \ge 3$ | `detect.py:66` | Operational Policy | Fixed | Prevents flapping between Healthy and Warning | **Keep Fixed** |

---

## 4. Actual Baseline Decision Path Trace

To verify exactly where dynamic data adaptation occurs and where fixed boundaries decide verdicts, we traced real observations through the baseline detector:

### Decision Path for Reading $y_t$ at Station $S$

```
Raw Reading: y_t = (T, P, RH) at Timestamp t
                    │
                    ▼
[TIER 0: HARDWARE RAIL CHECK] ───────────────────────────► (Fixed Rails: -40°C, 0 hPa, 0%)
  │ No rail violation                                      If matched -> ALERT (Tier 0)
  ▼
[TIER 0: THERMODYNAMIC BOUND CHECK] ─────────────────────► (Fixed Bounds: [-40, 60], T_dew <= T)
  │ Within thermodynamic envelope                          If violated -> ALERT (Tier 0)
  ▼
[DYNAMIC FEATURE GENERATION] (Fully Dynamic)
  ├─ Elapsed Physical Time: Δt = (t - t_prev) [Dynamic]
  ├─ Solar Hour & Diurnal Curve: calculate_solar_hour(t, S) [Dynamic]
  ├─ Dynamic Expectation: E[y_t | history_df] [Dynamic]
  ├─ Spatial Peer Consensus: μ_peer, σ_peer from neighbor_buffers [Dynamic]
  ├─ Composite Uncertainty: σ_total(param, solar_hr, Δt, history, σ_peer) [Dynamic]
  └─ Standardized Residual: z_t = (y_t - E[y_t]) / σ_total [Dynamic]
                    │
                    ▼
[TIER 1: HIGH-SPECIFICITY SPECIALIST CHECK]
  ├─ Spike Check:
  │    * Jump: Δy = y_t - y_prev [Dynamic]
  │    * Sub-quantization gate: |Δy| < 2.5 * σ_floor [Dynamic Floor]
  │    * Sigma: σ_jump = sqrt(2*σ_floor^2 + 0.25*Δt) [Fixed 0.25 Placeholder]
  │    * Z-Score: z_jump = |Δy| / σ_jump [Dynamic Evidence]
  │    * Wald LLR: S_jump = 0.5 * z_jump^2 - ln(σ_jump/σ_floor) [Dynamic Evidence]
  │    * DECISION: S_jump >= 6.16 AND z_jump >= 3.0 ───────► FIXED STATISTICAL BOUNDARY
  │                                                          If True -> ALERT (Tier 1 Spike)
  │
  └─ Frozen Check:
       * History Window: last K=5 readings [Fixed K]
       * Target Variance: s^2_target = var(recent_5) [Dynamic]
       * Peer Variance: s^2_peer = (σ_peer)^2 [Dynamic]
       * F-Ratio: F = (s^2_target + σ_floor^2) / (s^2_peer + σ_floor^2) [Dynamic Evidence]
       * Frozen LLR: S_frozen = 0.5 * K * (-ln(F) + F - 1) [Dynamic Evidence]
       * DECISION: S_frozen >= 6.16 AND s^2_target <= (1.2*σ_floor)^2 ──► FIXED STATISTICAL BOUNDARY
                                                             If True -> ALERT (Tier 1 Frozen)
  │ Neither Tier 1 fired
  ▼
[TIER 2: PERSISTENT TEMPORAL SPRT DRIFT]
  ├─ AR(1) Pre-Whitening: ε_t = r_t - φ * r_prev [Dynamic Residual, Calibrated φ]
  ├─ Page's CUSUM: S_pos, S_neg with allowance k = 0.5 * σ_total [Dynamic Allowance & Accumulator]
  ├─ Peer Directional Contrast: Boost 1.4x if (r_t * r_peer) < 0 [Dynamic Context]
  └─ DECISION: drift_LLR >= 6.16 ────────────────────────► FIXED STATISTICAL BOUNDARY
                                                           If True -> ALERT (Tier 2 Drift)
  │ Tier 2 did not fire
  ▼
[TIER 3: 3D MAHALANOBIS CROSS-CHANNEL CHECK]
  ├─ Covariance: D^2 = z^T Σ^-1 z across (T, P, RH) [Dynamic z-vector, Calibrated Σ]
  └─ DECISION: p_value(Chi2_3, D^2) < 0.001 (D^2 > 16.27) ─► DERIVED STATISTICAL BOUNDARY
                                                           If True -> ALERT (Tier 3 Mahalanobis)
  │ Tier 3 did not fire
  ▼
[TIER 4: MODEL-DOMINANT MULTIVARIATE CHECK]
  ├─ Isolation Forest: score = decision_function(X) [Dynamic Feature Vector]
  ├─ Tail Score: z_IF = -score / σ_train [Dynamic Feature]
  └─ DECISION: z_IF > 3.0 AND D^2 > 8.0 ─────────────────► FIXED STATISTICAL BOUNDARY
                                                           If True -> ALERT (Tier 4 Model)
  │ Tier 4 did not fire
  ▼
[TIER 5: AMBIGUITY VS NORMAL STATE]
  ├─ Ambiguity Check: max |z| > 2.2 AND len(neighbors) == 0 ──► FIXED BOUNDARY (Mark AMBIGUOUS)
  └─ Final Default: NORMAL (is_anomaly = False) ──────────► Clean Reading
```

---

## 5. Dynamic Evidence + Fixed Decision Boundary Architecture

A critical question of this audit was:
> *"Does using a dynamic uncertainty estimate $\sigma_t$ with a fixed decision boundary $z \ge 3.0$ create an architectural contradiction?"*

### Statistical Proof of Principled Equivalence
1. **The Role of Dynamic Uncertainty**:
   The predictive uncertainty $\sigma_t(\mathcal{C}_t)$ represents the conditional standard deviation of the measurement under the null hypothesis $H_0$ (normal atmospheric variation):
   $$\text{Var}(y_t \mid \mathcal{C}_t) = \sigma_t^2$$
2. **Standardization into Scale-Free Evidence**:
   When we divide the raw residual by $\sigma_t$, the standardized innovation $z_t$ has unit variance under $H_0$:
   $$z_t = \frac{y_t - \mathbb{E}[y_t \mid \mathcal{C}_t]}{\sigma_t} \sim \mathcal{N}(0, 1) \quad \text{under } H_0$$
3. **Why the Terminal Boundary MUST Be Fixed**:
   Because $z_t$ is strictly standardized to $\mathcal{N}(0, 1)$, a fixed decision threshold $z_{\text{crit}} = 3.0$ guarantees a constant, mathematically controlled false-positive rate:
   $$\alpha = P(|z_t| \ge 3.0 \mid H_0) = 2 \cdot (1 - \Phi(3.0)) = 0.0027$$
   If the decision boundary were dynamically modified in tandem with $\sigma_t$, the false-alarm rate $\alpha$ would fluctuate arbitrarily across solar hours and stations.
4. **Conclusion**:
   **Dynamic Evidence + Fixed Statistical Decision Boundary is the mathematically correct Neyman-Pearson formulation**. The failure in Step 7 was that $\sigma_{\text{jump}}$ was artificially inflated with macro process noise, which broke the fundamental property that $z_t \sim \mathcal{N}(0, 1)$ under $H_0$.

---

## 6. Isolation Forest Audit

| Property | Value / Implementation | Forensic Audit Finding |
| :--- | :--- | :--- |
| **Model Type** | `sklearn.ensemble.IsolationForest` | 100 trees, standard random partition trees |
| **Training Data** | 70% clean historical split of `all_stations.csv` | Strictly clean, uncorrupted baseline data |
| **Contamination Parameter** | `contamination="auto"` (offset = -0.5) | Standard scikit-learn non-parametric offset |
| **Feature Set** | 18 engineered features (rolling means, diffs, diurnal) | Causal window-based engineered features |
| **Live Updatability** | Offline trained artifact (`isolation_forest.pkl`) | Fixed model weights, strictly causal evaluation |
| **Role in Baseline Hierarchy** | **Tier 4 Supported Specialist Only** | Never acts as an autonomous uncorroborated trigger |
| **Corroboration Requirement** | $z_{\text{IF}} > 3.0 \land D^2_{\text{Mahalanobis}} > 8.0$ | Requires cross-channel physical divergence before firing |

**Verdict**: The Isolation Forest in the baseline detector is strictly constrained to Tier 4 as a corroborated specialist for multivariate inconsistencies. It does NOT suffer from rogue override behavior.

---

## 7. Surviving Placeholders That Became Production Logic

The audit identified three specific constants that were introduced as domain placeholders and should be addressed in future experiments:

1. **`0.25 * max(0.5, dt_hours)` in `sigma_jump` (`detect.py:123`)**:
   - *Origin*: Introduced in Step 2 as a provisional estimate of temporal jump variance.
   - *Flaw*: It adds a fixed variance of $0.25$ equally across Temperature ($^\circ\text{C}$), Pressure ($\text{hPa}$), and Humidity ($\%$), ignoring that $0.25$ represents $(0.5^\circ\text{C})^2$ for temperature, $(0.5\text{ hPa})^2$ for pressure, and $(0.5\%)^2$ for humidity.
   - *Requirement for Step 12*: Scale additive jump variance strictly by channel quantization floors: $\sigma_{\text{jump}}^2 = 2 \sigma_{\text{floor}, k}^2 + \lambda_k \Delta t$.

2. **`peer_dispersion < 0.4 hPa` in Frozen Pressure Guard (`detect.py:181`)**:
   - *Origin*: Introduced in Step 3 to prevent false frozen alerts during calm barometric weather.
   - *Flaw*: Hardcoded at $0.4\text{ hPa}$.
   - *Requirement for Step 12*: Scale calmness detection to the station's historical peer dispersion distribution.

3. **`clean_streak >= 3` in `SensorHealthTracker` (`detect.py:66`)**:
   - *Origin*: Introduced in Step 1 as a recovery debounce count.
   - *Flaw*: A fixed 3-hour observation count.
   - *Justification*: Legitimate operational debounce policy to prevent state oscillation.

---

## 8. Final Synthesis: True Dynamic vs Legitimate Fixed Components

```
+---------------------------------------------------------------------------------------------------+
| A. TRUE DYNAMIC COMPONENTS (Genuinely Adapt to Live Data)                                          |
|    1. Dynamic Solar Hour & Diurnal Expectation E[y_t | C_t]                                       |
|    2. Composite Conditional Uncertainty Budget sigma_total(t)                                      |
|    3. Spatial Peer Median Consensus & Robust Peer Dispersion IQR                                  |
|    4. AR(1) Pre-Whitening Residual Filter epsilon_t = r_t - phi * r_{t-1}                         |
|    5. Sequential Page's CUSUM Accumulators S_pos(t), S_neg(t) with dynamic allowance k = 0.5*sigma |
|    6. 3D Cross-Channel Mahalanobis Distance D^2(t) = z^T Sigma^{-1} z                             |
|    7. Transient Sub-Quantization Gating |Delta y| < 2.5 * sigma_floor                             |
|    8. Causal Station Buffer State Management & Anomaly History Filtering                          |
+---------------------------------------------------------------------------------------------------+
| B. LEGITIMATELY FIXED COMPONENTS (Physical Invariants & Calibrated Standards)                      |
|    1. Electrical Hardware Fail-Low Rails (-40.0°C, 0.0 hPa, 0.0%)                                 |
|    2. Earth Thermodynamic Invariant Envelope ([-40, 60], [300, 1100], [0, 100], T_dew <= T)       |
|    3. Instrument ADC Quantization Floors (T=0.10°C, P=0.50 hPa, RH=1.00%)                         |
|    4. Derived Wald SPRT Alert Boundary ln((1-beta)/alpha) = 6.16 (alpha=0.002, beta=0.05)         |
|    5. Standard Normal Statistical Significance Threshold z >= 3.0                                 |
|    6. Theoretical Chi-Square 3-DOF Critical Value p < 0.001 (D^2 > 16.27)                         |
|    7. AR(1) Autocorrelation Parameters phi = [0.70, 0.85, 0.65] (Calibrated from clean data)     |
+---------------------------------------------------------------------------------------------------+
| C. PLACEHOLDERS TO BE CLEANED IN STEP 12                                                          |
|    1. Fixed 0.25 additive jump variance -> Replace with channel-quantization scaling              |
|    2. Hardcoded 0.4 hPa pressure calmness guard -> Replace with peer dispersion distribution       |
+---------------------------------------------------------------------------------------------------+
```

---

## 9. Final Summary

### CONFIRMED FINDINGS
1. **Hybrid Architecture Identified**: Path 2 successfully implemented dynamic feature generation, dynamic expectation, and dynamic uncertainty, but correctly retained fixed statistical decision boundaries derived from formal false-alarm rate constraints ($\alpha=0.002, \beta=0.05$).
2. **Dynamic Evidence + Fixed Boundary Is Mathematically Sound**: When evidence is properly standardized ($z = \frac{\Delta y}{\sigma_t} \sim \mathcal{N}(0, 1)$), a fixed decision boundary $z \ge 3.0$ is the exact Neyman-Pearson optimal test for a constant false-alarm rate.
3. **Root Cause of Step 7 Failure Re-Confirmed**: The failure in Step 7 was NOT having a fixed $z \ge 3.0$ boundary; it was corrupting the evidence numerator ($r = \Delta y - \mathbb{E}[\Delta y]$) and inflating the denominator ($\sigma_{\text{jump}}$ with atmospheric process noise).

### FIXED VALUES THAT ARE LEGITIMATELY FIXED
1. **Hardware Rails**: $-40.0^\circ\text{C}, 0.0\text{ hPa}, 0.0\%$.
2. **Physical Bounds**: Temperature $[-40, 60]^\circ\text{C}$, Pressure $[300, 1100]\text{ hPa}$, Humidity $[0, 100]\%$, $T_{\text{dew}} \le T_{\text{amb}}$.
3. **Instrument Quantization Floors**: $T=0.10^\circ\text{C}, P=0.50\text{ hPa}, RH=1.00\%$.
4. **Wald SPRT Decision Boundary**: $\ln \frac{1-0.05}{0.002} = 6.16$.
5. **Statistical Tail Critical Values**: $z \ge 3.0$ ($p < 0.00135$), $\chi^2_3$ ($p < 0.001$).

### FIXED STATISTICAL BOUNDARIES THAT REQUIRE RECONSIDERATION
1. None of the core statistical boundaries ($\alpha, \beta, \chi^2$) require arbitrary modification; they are mathematically grounded.

### PLACEHOLDERS THAT BECAME ACTIVE LOGIC
1. `0.25 * max(0.5, dt_hours)` in `sigma_jump` (`detect.py:123`) — Must be replaced with channel-specific quantization variance $\lambda_k \sigma_{\text{floor}, k}^2 \Delta t$.
2. `peer_dispersion < 0.4 hPa` in `detect.py:181` — Must be scaled to regional peer dispersion statistics.

### WHAT MUST NOT BE CHANGED
1. **The 97.27% Baseline Recall Floor**: Raw physical continuity checks must remain unsuppressed.
2. **Hardware & Physical Invariant Rails**: Must never be made dynamic.
3. **Causal Benchmark Contract & Slicing**: Slicing ($70\%$ cutoff), seeds, and injector must remain locked.

### PRECISE REQUIREMENTS FOR STEP 12
1. **Primary Detection Floor**: Maintain unsuppressed raw physical jump evidence ($|\Delta y_t| / \sigma_{\text{floor}} \ge 3.0$) as the non-negotiable primary detection tier.
2. **Additive Contextual Corroboration**: Use contextual innovation strictly as an additive corroborator for ambiguous ranges ($2.0 \le z < 3.0$) and false-alarm pruning, never as a subtractive replacement filter.
3. **Contamination-Immune History Buffering**: Implement a quarantined reference state update policy that prevents unconfirmed candidate anomalies from entering `raw_history_df()`.
4. **Channel-Scaled Jump Variances**: Replace the fixed $0.25$ placeholder in $\sigma_{\text{jump}}$ with channel-specific physical quantization scaling.

---

## 10. Critical End Condition

Step 11 code archaeology and threshold lineage audit is complete. All constants, boundaries, and placeholders are classified and justified.

**Step 12 is now ready to perform the first production improvement experiment.**
