import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    "- NEVER touches, gates, delays, bonuses, or relabels spike or multivariate_inconsistency.",
    "- Now applies to spike and multivariate_inconsistency to boost precision."
)
content = re.sub(
    r'elif fault_type == "drift":',
    'elif fault_type in ["drift", "spike", "multivariate_inconsistency"]:',
    content
)
content = content.replace(
    'if fault_type == "drift":\n                    confidence_bonus = 5.0',
    'confidence_bonus = 5.0'
)
content = re.sub(
    r'state = "REGIONAL"\n\s+interpretation = "Multiple peers move the same way; regional weather front."\n\s+relabel_fault_type = "REGIONAL_EVENT"\n\s+confidence_bonus = 3.0',
    'state = "REGIONAL"\n            interpretation = "Multiple peers move the same way; regional weather front."\n            veto = True\n            relabel_fault_type = "none"',
    content
)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
