with open('model/simulator.py', 'r') as f:
    text = f.read()
import re
old_block1 = 
new_block1 = 
if old_block1 in text:
    text = text.replace(old_block1, new_block1)
    print("Patched simulator block 1")
else:
    print("Simulator block 1 not found")
old_block2 = 
new_block2 = 
if old_block2 in text:
    text = text.replace(old_block2, new_block2)
    print("Patched simulator block 2")
else:
    print("Simulator block 2 not found")
with open('model/simulator.py', 'w') as f:
    f.write(text)
