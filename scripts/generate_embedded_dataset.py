import pandas as pd
import numpy as np

df = pd.read_csv('data/AWS-CHN-024_labeled.csv')

# Find representative slices for each fault type and clean rows
clean_rows = df[df['is_anomaly'] == False].head(50)

fault_samples = []
for ftype in ['drift', 'spike', 'frozen_value', 'sensor_fail_low', 'multivariate_inconsistency', 'dropout', 'unstructured_anomaly']:
    sub = df[df['fault_type'] == ftype]
    if not sub.empty:
        fault_samples.append(sub.head(20))

combined = pd.concat([clean_rows] + fault_samples).sort_index()

print(f"Generated embedded dataset slice with {len(combined)} rows.")

cpp_lines = [
    "#pragma once",
    "#include <pgmspace.h>",
    "#include <stdint.h>",
    "#include <math.h>",
    "",
    "struct EmbeddedSample {",
    "    float temp_c;",
    "    float pressure_hpa;",
    "    float humidity_pct;",
    "    const char* timestamp;",
    "    bool is_anomaly_gt;",
    "    const char* fault_type_gt;",
    "};",
    "",
    "static const EmbeddedSample EMBEDDED_TEST_DATASET[] PROGMEM = {"
]

for idx, row in combined.iterrows():
    t_val = "NAN" if pd.isna(row['temperature_c']) else f"{float(row['temperature_c']):.2f}f"
    p_val = "NAN" if pd.isna(row['pressure_hpa']) else f"{float(row['pressure_hpa']):.2f}f"
    h_val = "NAN" if pd.isna(row['humidity_pct']) else f"{float(row['humidity_pct']):.2f}f"
    
    ts_val = f'"{str(row["timestamp"])}"'
    anom_gt = "true" if bool(row['is_anomaly']) else "false"
    ft_gt = f'"{str(row["fault_type"])}"' if pd.notna(row['fault_type']) else "nullptr"
    
    cpp_lines.append(f"    {{{t_val}, {p_val}, {h_val}, {ts_val}, {anom_gt}, {ft_gt}}},")

cpp_lines.append("};")
cpp_lines.append("")
cpp_lines.append(f"#define EMBEDDED_DATASET_COUNT {len(combined)}")

with open('EDGE/esp32_arduino/embedded_test_dataset.h', 'w') as f:
    f.write("\n".join(cpp_lines))

print("Successfully generated EDGE/esp32_arduino/embedded_test_dataset.h!")
