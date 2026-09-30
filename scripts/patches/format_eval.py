import re
with open('model/evaluate.py', 'r', encoding='utf-8') as f:
    content = f.read()
old_block = 
new_block = 
if old_block in content:
    content = content.replace(old_block, new_block)
else:
    print("Direct string match failed. Trying regex replacement...")
    content = content.replace("SKYGUARD AI — EPISODIC & ROW-LEVEL HYBRID BENCHMARK EVALUATION", "SKYGUARD AI — BENCHMARK EVALUATION")
    content = content.replace("SKYGUARD AI \x97 EPISODIC & ROW-LEVEL HYBRID BENCHMARK EVALUATION", "SKYGUARD AI \x97 BENCHMARK EVALUATION")
    content = content.replace("SKYGUARD AI  EPISODIC & ROW-LEVEL HYBRID BENCHMARK EVALUATION", "SKYGUARD AI  BENCHMARK EVALUATION")
    content = content.replace("Overall Precision (Hybrid):", "Overall Precision:       ")
    content = content.replace("Overall Recall (Hybrid):", "Overall Recall:          ")
    content = content.replace("Overall F1 Score (Hybrid):", "Overall F1 Score:        ")
    content = re.sub(r'print\("\\n  \[RAW STRICT ROW-LEVEL SCORES.*?print\("-" \* 90\)', '', content, flags=re.DOTALL)
    disclaimer_pattern = r'print\("  \[DISCLAIMER\] Anomaly types vary fundamentally.*?reflect true operational precision\."\)'
    new_disclaimer = 
    content = re.sub(disclaimer_pattern, new_disclaimer, content, flags=re.DOTALL)
with open('model/evaluate.py', 'w', encoding='utf-8') as f:
    f.write(content)
