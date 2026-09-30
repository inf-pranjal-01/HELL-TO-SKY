import re
with open('model/state.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    'from model.detect import score_reading, SensorHealthTracker, PARAMS',
    'from model.engine import DecisionEngine\nfrom model.detect import SensorHealthTracker, PARAMS'
)
content = content.replace(
    ,
)
with open('model/state.py', 'w', encoding='utf-8') as f:
    f.write(content)
