import sys
with open('model/evaluate.py', 'r') as f:
    content = f.read()
old_block = 
new_block = 
if old_block not in content:
    print("Could not find the target block in evaluate.py")
    sys.exit(1)
content = content.replace(old_block, new_block)
with open('model/evaluate.py', 'w') as f:
    f.write(content)
print("Successfully patched model/evaluate.py")
