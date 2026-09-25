"""
scratch/scan_lexicon.py
Scans repository files for obsolete lexicon terms and categorizes them.
"""
import os
import re
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
TARGET_EXTS = {".py", ".ts", ".tsx", ".md", ".json"}

PATTERNS = {
    "27 neighbors / 27 stations": re.compile(r"27\s*(?:neighbors|nearby|stations|peers)", re.I),
    "vapor_pressure_consistency_dev": re.compile(r"vapor_pressure_consistency_dev", re.I),
    "50 features / 42 features / 34 features": re.compile(r"\b(?:50|42|34)\s*(?:features|engineered\s*features)\b", re.I),
    "unstructured_anomaly": re.compile(r"unstructured_anomaly", re.I),
    "positional shift duration": re.compile(r"shift\((?:3|6|24)\)", re.I),
    "isolation forest probability": re.compile(r"isolation\s*forest\s*probability", re.I),
}

results = {k: [] for k in PATTERNS}

for p in ROOT_DIR.rglob("*"):
    if p.is_file() and p.suffix in TARGET_EXTS:
        if any(skip in str(p) for skip in [".git", "node_modules", ".venv", "dist", "build", "scratch"]):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for name, pat in PATTERNS.items():
                matches = pat.findall(content)
                if matches:
                    results[name].append((str(p.relative_to(ROOT_DIR)), len(matches)))
        except Exception:
            pass

print("=== LEXICON SCAN RESULTS ===")
for name, file_list in results.items():
    print(f"\n--- {name} ---")
    if not file_list:
        print("  None found.")
    else:
        for fpath, count in file_list:
            print(f"  {fpath}: {count} occurrences")
