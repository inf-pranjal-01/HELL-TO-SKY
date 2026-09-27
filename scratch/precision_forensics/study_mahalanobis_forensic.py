"""
scratch/precision_forensics/study_mahalanobis_forensic.py

Deep forensic study of Tier 3 Mahalanobis:
Why did it generate 3,017 FP/seed (62.6% of all FPs)?
How does Mahalanobis on Instantaneous Jump Innovations compare to Seasonal Innovations?
"""

import sys
import math
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent
df_fps = pd.read_csv(OUTPUT_DIR / "step16_fp_population.csv")

print("=" * 80)
print("TIER 3 MAHALANOBIS DEEP FORENSIC AUDIT")
print("=" * 80)

maha_fps = df_fps[df_fps["decision_basis"] == "TIER_3_MAHALANOBIS_CROSS_CHANNEL"]
print(f"Total Tier 3 Mahalanobis False Positives (7 seeds): {len(maha_fps)} ({len(maha_fps)/7:.1f} per seed)")
print(f"Percentage of ALL Step 16 False Positives: {len(maha_fps)/len(df_fps)*100:.2f}%")

print("\nMahalanobis D^2 distribution in these FPs:")
print(maha_fps["mahalanobis_d_sq"].describe())

print("\nAre these FPs thermodynamically coherent weather events?")
print(f"Thermodynamic coherence rate: {maha_fps['thermo_coherent'].mean()*100:.2f}%")

print("\nChannel z_predictive distribution in Mahalanobis FPs:")
print(maha_fps["z_predictive"].describe())
