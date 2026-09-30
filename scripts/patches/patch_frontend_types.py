with open('FRONTEND/src/types/index.ts', 'r') as f:
    text = f.read()
import re
new_type = 
text = text.replace(, new_type)
old_la = 
new_la = 
text = re.sub(
    r'(export interface LatestAnomaly \{[^}]+observed_values\?: Record<string, number \| null>;\n)\}',
    r'\g<1>  regime?: string;\n  network_corroboration?: NetworkCorroborationState;\n}',
    text
)
text = re.sub(
    r'(export interface RecentAnomalyItem \{[^}]+observed_values\?: Record<string, number \| null>;\n)\}',
    r'\g<1>  regime?: string;\n  network_corroboration?: NetworkCorroborationState;\n}',
    text
)
text = re.sub(
    r'(export interface AnomalyExplanation \{[^}]+fault_type\?: AnomalyType;\n)\}',
    r'\g<1>  regime?: string;\n  network_corroboration?: NetworkCorroborationState;\n}',
    text
)
with open('FRONTEND/src/types/index.ts', 'w') as f:
    f.write(text)
print("Patched types")
