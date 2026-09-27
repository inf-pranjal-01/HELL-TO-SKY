# Formal Likelihood Ratio (LLR) & Statistical Hypothesis Validation
**Path 2 — Precision Step 6**

---

## 1. Physical Hypothesis Formulation

For a weather sensor observing channel $y(t)$ at discrete timestamps $t_k = t_{k-1} + \Delta t_k$, we define the causal incremental observation:
$$\Delta y(t_k) = y(t_k) - y(t_{k-1})$$

Conditioned on all strictly causal contextual information available prior to observing $y(t_k)$:
$$\mathcal{C}(t_k) = \left\{ y(t_{k-1}),\, y(t_{k-2}),\, \dots,\, h_{\text{solar}}(t_k),\, \Delta \tilde{\mathbf{y}}_{\text{peers}}(t_k) \right\}$$

### Null Hypothesis $\mathcal{H}_0$ (Clean Physical Atmospheric Dynamics)
Under $\mathcal{H}_0$, the observation is driven by genuine atmospheric physical processes plus sensor measurement quantization error:
$$\Delta y(t_k) \mid \mathcal{H}_0, \mathcal{C}(t_k) \sim \mathcal{N}\left( \mu_0(t_k),\, \sigma_0^2(t_k) \right)$$
where:
$$\mu_0(t_k) = \mathbb{E}[\Delta y(t_k) \mid \mathcal{C}(t_k)] = w_{\text{diurnal}} \cdot \dot{\mu}(h) \Delta t_k + w_{\text{peer}} \cdot \Delta \tilde{y}_{\text{peer}}(t_k)$$
$$\sigma_0^2(t_k) = 2\sigma_{\text{sensor}}^2 + \sigma_{\text{process}}^2(\Delta t_k) + \sigma_{\text{pred}}^2(t_k)$$

- $2\sigma_{\text{sensor}}^2$: Independent sensor quantization errors at $t_k$ and $t_{k-1}$.
- $\sigma_{\text{process}}^2(\Delta t_k)$: Empirical atmospheric dispersion over elapsed physical time $\Delta t_k$.
- $\sigma_{\text{pred}}^2(t_k)$: Epistemic residual uncertainty of the causal contextual expectation model.

### Alternative Hypothesis $\mathcal{H}_1$ (Isolated Transducer Spike Anomaly)
Under $\mathcal{H}_1$, the observation is corrupted by an instantaneous electrical spike, bit-flip, or hardware discontinuity:
$$\Delta y(t_k) \mid \mathcal{H}_1, \mathcal{C}(t_k) \sim \mathcal{N}\left( \mu_0(t_k),\, \sigma_1^2(t_k) \right) \quad \text{with } \sigma_1 \gg \sigma_0$$
or under a generalized maximum-likelihood / uninformative spike distribution over dynamic range $[-M, M]$:
$$p(\Delta y(t_k) \mid \mathcal{H}_1, \mathcal{C}(t_k)) = \frac{1}{\sqrt{2\pi}\sigma_1} \exp\left(-\frac{(\Delta y(t_k) - \mu_0(t_k))^2}{2\sigma_1^2}\right)$$

---

## 2. Derivation of the Exact Causal LLR

The exact log-likelihood ratio for single-step jump evidence is:
$$\Lambda(t_k) = \ln \left[ \frac{p(\Delta y(t_k) \mid \mathcal{H}_1, \mathcal{C}(t_k))}{p(\Delta y(t_k) \mid \mathcal{H}_0, \mathcal{C}(t_k))} \right]$$

Substituting the respective Gaussian densities:
$$p(\Delta y \mid \mathcal{H}_0) = \frac{1}{\sqrt{2\pi}\sigma_0} \exp\left(-\frac{1}{2}\left(\frac{\Delta y - \mu_0}{\sigma_0}\right)^2\right)$$
$$p(\Delta y \mid \mathcal{H}_1) = \frac{1}{\sqrt{2\pi}\sigma_1} \exp\left(-\frac{1}{2}\left(\frac{\Delta y - \mu_0}{\sigma_1}\right)^2\right)$$

Taking the natural logarithm:
$$\Lambda(t_k) = \ln\left(\frac{\sigma_0(t_k)}{\sigma_1}\right) + \frac{1}{2}\left(\frac{\Delta y(t_k) - \mu_0(t_k)}{\sigma_0(t_k)}\right)^2 - \frac{1}{2}\left(\frac{\Delta y(t_k) - \mu_0(t_k)}{\sigma_1}\right)^2$$

When $\sigma_1 \gg \sigma_0$ (e.g. $\sigma_1 \approx \text{Sensor Dynamic Scale}$):
$$\frac{1}{2}\left(\frac{\Delta y - \mu_0}{\sigma_1}\right)^2 \approx 0$$

Defining the normalized contextual surprise $z(t_k) = \frac{\Delta y(t_k) - \mu_0(t_k)}{\sigma_0(t_k)}$ and setting reference $\sigma_1 \propto \sigma_{\text{sensor}}$:
$$\Lambda(t_k) = \frac{1}{2} z(t_k)^2 - \ln\left(\frac{\sigma_0(t_k)}{\sigma_{\text{sensor}}}\right)$$

---

## 3. Mathematical Validation & Terminology Designation

### Is this a legitimate Log-Likelihood Ratio (LLR)?
**YES.** Under the stated Gaussian shift / scale mixture formulation, $\Lambda(t_k)$ is mathematically identical to the Wald Sequential Probability Ratio Test (SPRT) log-likelihood ratio.

### Wald Decision Boundaries
- **Alert Boundary (Spike Detection)**:
  $$\Lambda(t_k) \ge \ln\left(\frac{1 - \beta}{\alpha}\right) \approx \ln\left(\frac{1 - 0.001}{0.002}\right) = 6.1633 \quad (\text{WALD\_UPPER\_ALERT})$$
- **Reset Boundary (Clean Confirmation)**:
  $$\Lambda(t_k) \le \ln\left(\frac{\beta}{1 - \alpha}\right) \approx -6.1633 \quad (\text{WALD\_LOWER\_RESET})$$

### Boundary Condition Check:
1. When innovation is small ($|z| \to 0$): $\Lambda(t_k) = -\ln(\sigma_0 / \sigma_{\text{sensor}}) < 0$, providing continuous evidence in favor of $\mathcal{H}_0$.
2. When innovation is large ($|z| \ge 3.6$): $\frac{1}{2}(3.6)^2 = 6.48 \ge 6.16$, crossing the Wald alert threshold and declaring a spike.
3. During volatile weather ($\sigma_0$ expands): The penalty term $-\ln(\sigma_0 / \sigma_{\text{sensor}})$ decreases the score, naturally requiring larger deviations to declare a fault during storms.
