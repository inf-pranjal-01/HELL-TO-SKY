import re
with open('config.py', 'r', encoding='utf-8') as f:
    content = f.read()
new_constants = 
if "SPIKE_DIURNAL_MIN_PEERS" not in content:
    content += new_constants
with open('config.py', 'w', encoding='utf-8') as f:
    f.write(content)
