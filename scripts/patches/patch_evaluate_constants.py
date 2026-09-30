import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r'# Hard physical sanity bounds.*?PHYSICAL_BOUNDS = \{.*?\}\n', '', content, flags=re.DOTALL)
import_block = "from config import (\n    ARTIFACTS_PATH,\n    CLUSTERS,\n    FUSION_ANOMALY_THRESHOLD,\n"
new_import_block = "from config import (\n    ARTIFACTS_PATH,\n    CLUSTERS,\n    FUSION_ANOMALY_THRESHOLD,\n    PHYSICAL_BOUNDS,\n    HELPER_ALERT_THRESHOLD,\n    FROZEN_HELPER_ALERT_THRESHOLD,\n"
content = content.replace(import_block, new_import_block)
content = re.sub(r'HELPER_ALERT_THRESHOLD = 0\.92\n', '', content)
content = re.sub(r'# This stricter specialist path.*?FROZEN_HELPER_ALERT_THRESHOLD = 0\.90\n', '', content, flags=re.DOTALL)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
