import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "relabel_fault_type = \"none\"" in line and lines[i+1].strip() == "else:":
        pass
content = "".join(lines)
broken_block = "
fixed_block = "
content = content.replace(broken_block, fixed_block)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
