import sys
import pandas as pd
from pathlib import Path
def patch_evaluate():
    path = Path("model/evaluate.py")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
