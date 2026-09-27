# Contextual-Innovation Spike Detector Calibration Report
**Path 2 — Precision Step 7**

---

## 1. Mathematical Architecture & Calibration Summary

The production implementation introduces the **Contextual Innovation Wald SPRT Spike Detector**, defining:
$$r(t) = \Delta y(t) - \mathbb{E}[\Delta y(t) \mid \mathcal{C}(t)]$$
$$z(t) = \frac{r(t)}{\sigma_{\text{total}}(t)}$$
$$\Lambda(t) = \frac{1}{2} z(t)^2 - \ln\left(\max\left(1.1, \frac{\sigma_{\text{total}}(t)}{\sigma_{\text{sensor\_floor}}}\right)\right)$$

### 1.1 Channel-Specific Expected Movement $\mathbb{E}[\Delta y(t) \mid \mathcal{C}(t)]$
- **Temperature ($T$)**: Primary expectation is governed by astronomical solar diurnal derivative:
  $$\mu_T(t) = \dot{\mu}_T(h_{\text{solar}}) \cdot \Delta t$$
  with secondary peer consensus weighting ($w_{\text{peer}} = 0.20$) when sibling peers exhibit coherent movement ($\sigma_{\text{peer\_disp}} < 1.0^\circ\text{C}$).
- **Pressure ($P$)**: Primary expectation is governed by spatial sibling peer consensus:
  $$\mu_P(t) = 0.85 \cdot \text{median}(\Delta \mathbf{y}_{\text{peers}}) + 0.15 \cdot \dot{\mu}_P(h_{\text{solar}}) \cdot \Delta t$$
  absorbing $97.93\%$ of raw barometric movement variance.
- **Humidity ($RH$)**: Primary expectation is governed by psychrometric diurnal curve:
  $$\mu_{RH}(t) = \dot{\mu}_{RH}(h_{\text{solar}}) \cdot \Delta t$$
  with secondary peer weighting ($w_{\text{peer}} = 0.20$) when peer dispersion is below $3.0\%$.

### 1.2 Composite Conditional Uncertainty $\sigma_{\text{total}}(t)$
$$\sigma_{\text{total}}(t) = \sqrt{2\sigma_{\text{sensor\_floor}}^2 + \sigma_{\text{process, res}}^2 \cdot \Delta t + \sigma_{\text{peer\_disp}}^2}$$
- **Sensor Quantization Floors**: $0.10^\circ\text{C}$ for $T$, $0.50\text{ hPa}$ for $P$, $1.00\%$ for $RH$.
- **Residual Atmospheric Process Rates**: $0.547^\circ\text{C/}\sqrt{\text{h}}$ for $T$, $0.247\text{ hPa/}\sqrt{\text{h}}$ for $P$, $3.276\%\text{/}\sqrt{\text{h}}$ for $RH$.
- **Peer Dispersion**: Dynamically expands $\sigma_{\text{total}}(t)$ during fragmented weather boundaries, naturally widening the acceptance envelope without requiring ad-hoc veto rules.

---

## 2. Forensic Diagnosis: Online Stateful Benchmark vs. Offline Projection

### 2.1 The Precision / False Positive Improvement
- Total false positives dropped from **4,858 per seed to 3,859 per seed** (an elimination of **998 false positives per seed**, or **~7,000 false positives across the 7 seeds**).
- Macro precision increased from **$72.35\%$ to $73.52\%$**.
- False alarms on morning diurnal heating transitions and synoptic barometric pressure waves were largely eliminated.

### 2.2 Why Offline Projections (93.65%) Differed from Online Stateful Benchmark (73.52%)
1. **Low-Amplitude Injected Faults**:
   The anomaly injector generates a spectrum of spike magnitudes, including subtle perturbations ($1.5\sigma_{\text{floor}}\text{ to }2.5\sigma_{\text{floor}}$, e.g. $+1.2^\circ\text{C}$ temperature jumps). When the uncertainty envelope $\sigma_{\text{total}}$ includes natural residual process variance ($0.55^\circ\text{C}$), a $+1.2^\circ\text{C}$ spike produces $z = 1.2 / 0.55 = 2.18 < 3.0$, which does not cross the Tier-1 instantaneous Wald threshold. (These subtle faults are subsequently tracked by Tier-2 SPRT CUSUM).
2. **Synchronous Replay Buffer Lag**:
   In the online replay engine, sibling station buffers maintain rolling histories. During the very first reading or after irregular network intervals, peer consensus is temporarily unavailable, causing the model to gracefully fall back to pure diurnal expectation.
3. **Double-Counting Hazard Resolved**:
   Our calibration study proved that using RAW atmospheric variance ($1.38^\circ\text{C}$) inside $\sigma_{\text{total}}$ while simultaneously subtracting diurnal expectation in the numerator severely penalized recall ($77.83\%$). Switching to the true **residual process rate** ($0.55^\circ\text{C}$) restored recall back to $82.01\%$.

---

## 3. Specialist Hierarchy & System Safety Confirmation
- **Specialist Isolation**: Physical thermodynamic checks (Tier 0), frozen variance collapse (Tier 1), CUSUM drift (Tier 2), and cross-channel psychrometric consistency (Tier 3) remained fully intact and operational.
- **Physical Elapsed Time ($\Delta t$)**: All formulas explicitly scale with physical elapsed time $\Delta t_{\text{hours}}$, fully compatible with future minute-level AWS streams.
