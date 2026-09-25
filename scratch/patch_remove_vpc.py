with open("model/features.py", "r", encoding="utf-8") as f:
    code = f.read()

# Remove vapor_pressure_consistency_dev from FEATURE_COLUMNS
code = code.replace('    "dewpoint_depression_c", "vapor_pressure_deficit_kpa",\n    "vapor_pressure_consistency_dev",', '    "dewpoint_depression_c", "vapor_pressure_deficit_kpa",')

# Remove calculation in add_cross_parameter_features
old_calc = """    temp_prev = temp_c.shift(1)
    humidity_prev = pd.to_numeric(df["humidity_pct"], errors="coerce").shift(1)
    es_prev = saturation_vapor_pressure_kpa(temp_prev)
    rh_expected = (humidity_prev * (es_prev / es_now)).clip(0.0, 100.0)
    df["vapor_pressure_consistency_dev"] = humidity_pct - rh_expected"""

if old_calc in code:
    code = code.replace(old_calc, '    # Replaced rigid Clausius-Clapeyron equality with 3D thermodynamic covariance in CrossChannelEngine')

with open("model/features.py", "w", encoding="utf-8") as f:
    f.write(code)

print("vapor_pressure_consistency_dev removed from features.py successfully.")
