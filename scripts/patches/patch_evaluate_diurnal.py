import sys
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
target_start = 
replacement_start = 
if target_start not in content:
    print("Could not find target_start in evaluate.py")
    sys.exit(1)
content = content.replace(target_start, replacement_start)
target_spike = 
replacement_spike = 
if target_spike not in content:
    print("Could not find target_spike in evaluate.py")
    sys.exit(1)
content = content.replace(target_spike, replacement_spike)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully patched model/evaluate.py to include Diurnal Consensus Filter.")
