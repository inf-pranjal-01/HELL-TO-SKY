with open('main.py', 'r') as f:
    text = f.read()
import re
old_block1 = 
new_block1 = 
if old_block1 in text:
    text = text.replace(old_block1, new_block1)
    print("Patched main.py block 1")
else:
    print("main.py block 1 not found")
old_block2 = 
new_block2 = 
if old_block2 in text:
    text = text.replace(old_block2, new_block2)
    print("Patched main.py block 2")
else:
    print("main.py block 2 not found")
old_block3 = 
new_block3 = 
if old_block3 in text:
    text = text.replace(old_block3, new_block3)
    print("Patched main.py block 3")
else:
    print("main.py block 3 not found")
with open('main.py', 'w') as f:
    f.write(text)
