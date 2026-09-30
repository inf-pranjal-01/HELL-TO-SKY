import re
with open('data/anomaly_injector.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r'\s*inject_spike_decay:\s*\d+,\s*#.*?\n', '\n', content)
content = re.sub(r'\s*inject_spike_decay:\s*[\d\.]+,\n', '\n', content)
content = content.replace('inject_spike, inject_spike_decay, inject_frozen', 'inject_spike, inject_frozen')
with open('data/anomaly_injector.py', 'w', encoding='utf-8') as f:
    f.write(content)
