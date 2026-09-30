with open('main.py', 'r') as f:
    text = f.read()
import re
old_recent_block = 
new_recent_block = 
if old_recent_block in text:
    text = text.replace(old_recent_block, new_recent_block)
    print("Patched recent anomalies return in main.py")
else:
    print("Block not found!")
with open('main.py', 'w') as f:
    f.write(text)
