with open('FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx', 'r') as f:
    text = f.read()
import re
old_body = 
new_body = 
if old_body in text:
    text = text.replace(old_body, new_body)
    print("Patched ExplainabilityCommandCenter block 1")
else:
    print("ExplainabilityCommandCenter block 1 not found")
with open('FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx', 'w') as f:
    f.write(text)
