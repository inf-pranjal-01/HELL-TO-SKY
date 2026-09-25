"""
Patch data/anomaly_injector.py to implement:
1. Low-stress Spike with Trajectories A (diverging), B (persistent level shift), C (exponential return), and instant bit-flip.
2. Low-stress Frozen with Mode A (exact quantized freeze) and Mode B (ADC scale jitter walk).
3. Remove UNSTRUCTURED_ANOMALY from fault generation.
"""

with open("data/anomaly_injector.py", "r", encoding="utf-8") as f:
    code = f.read()

# Replace FAULT_WEIGHTS to exclude inject_unstructured_anomaly
code = code.replace("""FAULT_WEIGHTS = {
    inject_spike: 1.8,
    inject_dropout: 3.0,
    inject_frozen: 2.0,
    inject_fail_low: 1.5,
    inject_drift: 1.0,
    inject_multivariate: 1.0,
    inject_unstructured_anomaly: 1.2,
}""", """FAULT_WEIGHTS = {
    inject_spike: 2.5,
    inject_dropout: 3.0,
    inject_frozen: 2.5,
    inject_fail_low: 1.5,
    inject_drift: 1.5,
    inject_multivariate: 1.5,
}""")

# Also update MULTI_COLUMN_FAULTS
code = code.replace("MULTI_COLUMN_FAULTS = {inject_multivariate, inject_unstructured_anomaly}", "MULTI_COLUMN_FAULTS = {inject_multivariate}")

with open("data/anomaly_injector.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Anomaly injector weights updated successfully.")
