import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
metric_split = 
content = content.replace(
    'res_df = pd.DataFrame(results)',
    'res_df = pd.DataFrame(results)\n' + metric_split
)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
