"""
scratch/precision_forensics/audit_gap_and_disambiguation.py

Investigates the gap duration (dt) and environmental disambiguation of Step 12 New FPs.
"""

import math
import pandas as pd
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent
df_fps = pd.read_csv(OUTPUT_DIR / "step12_new_fp_dataset.csv")

print("=" * 80)
print("NEW FALSE POSITIVES GAP (dt) AUDIT")
print("=" * 80)

print(f"Total New FPs across 7 seeds: {len(df_fps)}")
print(f"dt summary:")
print(df_fps["dt"].describe())

print("\ndt distribution buckets:")
print(pd.cut(df_fps["dt"], bins=[-1, 0.5, 1.5, 2.5, 6.0, 24.0, 1000.0]).value_counts(sort=False))

# What happens if instantaneous spike rule is restricted to consecutive/short gaps (dt <= 2.5 hr)?
fps_gap_gt_2_5 = df_fps[df_fps["dt"] > 2.5]
fps_gap_le_2_5 = df_fps[df_fps["dt"] <= 2.5]

print(f"\nNew FPs with dt > 2.5 hr (Data gap artifacts): {len(fps_gap_gt_2_5)} ({len(fps_gap_gt_2_5)/len(df_fps)*100:.1f}%) | Mean per seed: {len(fps_gap_gt_2_5)/7:.1f}")
print(f"New FPs with dt <= 2.5 hr (Consecutive operation): {len(fps_gap_le_2_5)} ({len(fps_gap_le_2_5)/len(df_fps)*100:.1f}%) | Mean per seed: {len(fps_gap_le_2_5)/7:.1f}")

print("\nFor consecutive operation (dt <= 2.5 hr), channel breakdown:")
print(fps_gap_le_2_5["channel"].value_counts())
print("\nFor consecutive operation (dt <= 2.5 hr), delta statistics:")
print(fps_gap_le_2_5.groupby("channel")["raw_delta"].describe())

print("\nFor consecutive operation (dt <= 2.5 hr), solar hour distribution for temperature:")
temp_consec = fps_gap_le_2_5[fps_gap_le_2_5["channel"] == "temperature_c"]
print(temp_consec["solar_hour"].describe())
