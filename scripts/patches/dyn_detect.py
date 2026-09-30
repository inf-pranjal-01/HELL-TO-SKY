import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
dynamic_logic = 
content = content.replace(
    ,
    dynamic_logic
)
peer_logic_old = 
peer_logic_new = 
content = content.replace(peer_logic_old, peer_logic_new)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
