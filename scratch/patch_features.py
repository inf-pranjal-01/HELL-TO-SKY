import re

with open("model/features.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if "For longer lookbacks (3h, 6h, 24h)" in line:
        skip = True
        new_lines.append("        # Continuous-time causal slopes and residuals via exact timestamp lookup\n")
        new_lines.append("        slope_3h, _ = _compute_time_offset_slope(df, col, ROC_LONG_HOURS)\n")
        new_lines.append('        df[f"{prefix}_roc_3h"] = slope_3h\n')
        new_lines.append("        slope_6h, _ = _compute_time_offset_slope(df, col, 6.0)\n")
        new_lines.append('        df[f"{prefix}_slope_6h"] = slope_6h\n')
        new_lines.append("        slope_24h, diff_24h = _compute_time_offset_slope(df, col, 24.0)\n")
        new_lines.append('        df[f"{prefix}_slope_24h"] = slope_24h\n')
        new_lines.append('        df[f"{prefix}_same_hour_res"] = diff_24h\n')
        continue
    if skip:
        if 'df[f"{prefix}_same_hour_res"]' in line:
            skip = False
        continue
    new_lines.append(line)

with open("model/features.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Features patch applied successfully.")
