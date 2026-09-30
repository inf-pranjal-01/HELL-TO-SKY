import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    'episodic_faults = ["frozen_value", "drift", "spike", "multivariate_inconsistency"]',
    'episodic_faults = ["frozen_value", "drift", "multivariate_inconsistency"]'
)
helper_block_regex = re.compile(
    r'(# Network-aware supervised helper -------------------------------------------------.*?)(?=has_rule_ft = )',
    re.DOTALL
)
match = helper_block_regex.search(content)
if not match:
    print("Could not find helper block!")
    exit(1)
helper_block = match.group(1)
content = content.replace(helper_block, '')
new_helper_logic = 
content = content.replace(
    'model_pct = vectorized_model_scores(featured, artifact)',
    new_helper_logic + '\n    model_pct = vectorized_model_scores(featured, artifact)'
)
old_pred_ft = "
content = content.replace(old_pred_ft, "")
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
