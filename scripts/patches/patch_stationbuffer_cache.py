import re
with open('model/state.py', 'r', encoding='utf-8') as f:
    content = f.read()
init_target = 
init_replace = 
content = content.replace(init_target, init_replace)
raw_target = 
raw_replace = 
content = content.replace(raw_target, raw_replace)
record_target = 
record_replace = 
content = content.replace(record_target, record_replace)
reset_target = 
reset_replace = 
content = content.replace(reset_target, reset_replace)
spike_target = 
spike_replace = 
content = content.replace(spike_target, spike_replace)
with open('model/state.py', 'w', encoding='utf-8') as f:
    f.write(content)
