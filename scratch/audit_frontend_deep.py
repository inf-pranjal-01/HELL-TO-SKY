"""
scratch/audit_frontend_deep.py
Deep inspection of all frontend files for:
- Fault types
- Feature lists
- Probability vs confidence
- Peer references
- Suggested values
- Mock data
"""

import os
import re
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
FE_DIR = ROOT_DIR / "FRONTEND" / "src"

files = list(FE_DIR.rglob("*.*"))
print(f"Total frontend files: {len(files)}")

# Check for 'unstructured_anomaly' in frontend
unstructured_matches = []
prob_matches = []
peer_matches = []
feature_matches = []

for f in files:
    if f.suffix in {".ts", ".tsx", ".css", ".json"}:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            rel = f.relative_to(FE_DIR)
            
            # Check for unstructured_anomaly
            if "unstructured_anomaly" in content.lower():
                unstructured_matches.append((str(rel), [line.strip() for line in content.splitlines() if "unstructured_anomaly" in line.lower()]))
                
            # Check for probability
            for line_no, line in enumerate(content.splitlines(), 1):
                if re.search(r"\bprobabilit(?:y|ies)\b", line, re.I) and not "math." in line:
                    prob_matches.append((str(rel), line_no, line.strip()))
                    
            # Check for 27 or 28 stations / neighbors
            for line_no, line in enumerate(content.splitlines(), 1):
                if re.search(r"\b27\b|\b28\b", line):
                    peer_matches.append((str(rel), line_no, line.strip()))
                    
        except Exception as e:
            print(f"Error reading {f}: {e}")

print(f"\n--- unstructured_anomaly occurrences ({len(unstructured_matches)}) ---")
for fpath, lines in unstructured_matches:
    print(f"{fpath}:")
    for l in lines:
        print(f"  {l}")

print(f"\n--- Probability occurrences ({len(prob_matches)}) ---")
for fpath, line_no, l in prob_matches:
    print(f"{fpath}:{line_no}: {l}")

print(f"\n--- 27/28 station/peer occurrences ({len(peer_matches)}) ---")
for fpath, line_no, l in peer_matches:
    print(f"{fpath}:{line_no}: {l}")
