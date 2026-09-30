with open("model/features.py", "r", encoding="utf-8") as f:
    code = f.read()
code = code.replace('    "dewpoint_depression_c", "vapor_pressure_deficit_kpa",\n    "vapor_pressure_consistency_dev",', '    "dewpoint_depression_c", "vapor_pressure_deficit_kpa",')
old_calc = 
if old_calc in code:
    code = code.replace(old_calc, '
with open("model/features.py", "w", encoding="utf-8") as f:
    f.write(code)
print("vapor_pressure_consistency_dev removed from features.py successfully.")
