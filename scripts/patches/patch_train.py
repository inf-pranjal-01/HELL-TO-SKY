import re
with open('model/train.py', 'r', encoding='utf-8') as f:
    content = f.read()
split_logic = 
content = content.replace(
    'df = load_clean_training_data()',
    'df = load_clean_training_data()\n' + split_logic
)
with open('model/train.py', 'w', encoding='utf-8') as f:
    f.write(content)
