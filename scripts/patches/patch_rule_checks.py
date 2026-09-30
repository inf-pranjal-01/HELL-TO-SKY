import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    'def _rule_checks(raw_reading: dict, feature_row: pd.Series, history_df: pd.DataFrame, artifact: dict) -> dict:',
    'def _rule_checks(raw_reading: dict, feature_row: pd.Series, history_df: pd.DataFrame, featured_buffer: pd.DataFrame, artifact: dict) -> dict:'
)
old_featurize_call = 
content = content.replace(old_featurize_call, "
old_score_reading_rules = 'rules = _rule_checks(raw_reading, feature_row, history_df, artifact)'
new_score_reading_rules = 
content = content.replace(old_score_reading_rules, new_score_reading_rules)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
