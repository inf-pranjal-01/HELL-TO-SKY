import re
with open('model/detect.py', 'r', encoding='utf-8') as f:
    content = f.read()
import_pattern = r'from config import \(\n'
new_imports = r'from config import (\n    NETWORK_MIN_ELIGIBLE_PEERS,\n    NETWORK_CORROBORATION_RATIO,\n'
content = re.sub(import_pattern, new_imports, content)
frozen_logic_old = 
frozen_logic_new = 
content = content.replace(frozen_logic_old, frozen_logic_new)
general_logic_old = 
general_logic_new = 
content = content.replace(general_logic_old, general_logic_new)
with open('model/detect.py', 'w', encoding='utf-8') as f:
    f.write(content)
