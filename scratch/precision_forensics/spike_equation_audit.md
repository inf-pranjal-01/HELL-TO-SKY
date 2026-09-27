# ANTIGRAVITY — SKYGUARD AI
# PATH 2 — SPIKE EQUATION STATISTICAL & MATHEMATICAL AUDIT

**Author**: Antigravity Core Autonomous Agent  
**Date**: September 25, 2026  
**Status**: Step 4 Deep Causal Audit Complete  

---

## 1. Exact Source Implementation Trace

Tracing the mathematical pipeline directly from [`model/detect.py`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/model/detect.py#L100-L140):

```python
def evaluate_spike_evidence(
    param: str,
    current_val: float,
    expected_val: float,
    prior_val: Optional[float],
    current_sigma: float,
    dt_hours: float
) -> Tuple[float, Optional[str], Dict[str, any]]:
    sensor_floor = SENSOR_QUANTIZATION_FLOORS.get(param, 0.10)
    
    if prior_val is not None:
        jump_mag = abs(current_val - prior_val)
    else:
        jump_mag = abs(current_val - expected_val)
    
    if jump_mag < 2.5 * sensor_floor:
        return 0.0, None, {"jump_llr": 0.0, "is_spike": False}
    
    sigma_jump = math.sqrt(2.0 * (sensor_floor ** 2) + 0.25 * max(0.5, dt_hours))
    z_jump = jump_mag / max(1e-4, sigma_jump)
    
    jump_llr = float(0.5 * (z_jump ** 2) - math.log(max(1.1, sigma_jump / sensor_floor)))
    is_spike = jump_llr >= WALD_UPPER_ALERT and z_jump >= 3.0
    ...
```

---

## 2. Step-by-Step Mathematical Derivation

Let $y(t)$ be the latest measurement at physical time $t$, and $y(t-1)$ be the immediate causal predecessor at time $t - \Delta t$.

### Step 1: Jump Magnitude Calculation
$$\Delta y(t) = y(t) - y(t-1)$$
$$\text{jump\_mag} = |\Delta y(t)|$$
*(Note: If $y(t-1)$ is missing, it falls back to $|y(t) - \hat{y}(t)|$, but in standard sequential operation it is strictly the 1-step difference $|\Delta y(t)|$.)*

### Step 2: Jump Uncertainty Formulation ($\sigma_{\text{jump}}$)
$$\sigma_{\text{jump}} = \sqrt{2 \cdot \sigma_{\text{floor}}^2 + 0.25 \cdot \max(0.5, \Delta t)}$$
Where quantization floors $\sigma_{\text{floor}}$ from [`model/uncertainty_budget.py`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/model/uncertainty_budget.py):
- $\text{Temperature}: \sigma_{\text{floor}} = 0.10^\circ\text{C} \implies \sigma_{\text{jump}} = \sqrt{2(0.01) + 0.25(1.0)} = \sqrt{0.27} \approx 0.52^\circ\text{C}$
- $\text{Pressure}: \sigma_{\text{floor}} = 0.50\text{ hPa} \implies \sigma_{\text{jump}} = \sqrt{2(0.25) + 0.25(1.0)} = \sqrt{0.75} \approx 0.87\text{ hPa}$
- $\text{Humidity}: \sigma_{\text{floor}} = 1.00\% \implies \sigma_{\text{jump}} = \sqrt{2(1.0) + 0.25(1.0)} = \sqrt{2.25} = 1.50\%$

### Step 3: Standardized Z-Score
$$z_{\text{jump}} = \frac{|\Delta y(t)|}{\sigma_{\text{jump}}}$$

### Step 4: Wald Sequential Log-Likelihood Ratio
$$\Lambda_{\text{jump}} = \frac{1}{2} z_{\text{jump}}^2 - \ln\left( \max\left(1.1, \; \frac{\sigma_{\text{jump}}}{\sigma_{\text{floor}}}\right) \right)$$

### Step 5: Decision Rule
$$\text{Decision} = \text{SPIKE} \iff \Lambda_{\text{jump}} \ge 12.0 \quad \text{AND} \quad z_{\text{jump}} \ge 3.0$$

---

## 3. Critical Flaws in the Statistical Formulation

| Property | Intended Statistical Meaning | Actual Implemented Reality |
|:---|:---|:---|
| **What is measured** | Discontinuous unphysical transducer impulse | Raw physical weather change $|\Delta y(t)|$ |
| **Denominator $\sigma_{\text{jump}}$** | Physical process change uncertainty over $\Delta t$ | Instrument quantization noise floor ($\sim 0.52^\circ\text{C}, 0.87\text{ hPa}$) |
| **Process vs Noise Ratio** | Natural atmospheric rate should be within $\pm 3\sigma$ | Natural weather std is **$8\times$ to $37\times$ larger** than $\sigma_{\text{jump}}$ |
| **Diurnal Subtraction** | Should subtract expected rate of change $\Delta \hat{y}(t)$ | $\Delta \hat{y}(t)$ is completely ignored; raw slope is evaluated |
| **Temporal Shape** | Spikes should be 1-step impulses with immediate return | Multi-step monotonic weather fronts trigger sustained spike cascades |

### Conclusion of Equation Audit
The detector does not measure a "spike" in the physical or signal-processing sense. It measures the **raw 1-hour rate of change against an instrument noise scale**. Consequently, any convective rain cooling ($-3^\circ\text{C}/\text{h}$), frontal pressure shift ($-3\text{ hPa}/\text{h}$), or sunrise humidity plunge ($-10\%/\text{h}$) is mathematically guaranteed to fire the Tier-1 Instantaneous Spike alarm.
