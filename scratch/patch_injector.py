
with open("data/anomaly_injector.py", "r", encoding="utf-8") as f:
    code = f.read()
code = code.replace(, )
code = code.replace("MULTI_COLUMN_FAULTS = {inject_multivariate, inject_unstructured_anomaly}", "MULTI_COLUMN_FAULTS = {inject_multivariate}")
with open("data/anomaly_injector.py", "w", encoding="utf-8") as f:
    f.write(code)
print("Anomaly injector weights updated successfully.")
