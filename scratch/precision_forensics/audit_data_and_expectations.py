"""
Step 5 Deep Offline Mathematical and Statistical Study.
Conducts:
1. Data Unit and Quality Audit (Station pressure distribution, intra-station clean delta P, cross-station differences)
2. Expected Movement Model Evaluations (Persistence, Local Trend, Diurnal/Solar, Peer Common-Mode, Fused Context, Adaptive Trend-Damped)
3. Process Variance Decomposition (Sensor floor, Process variance, Prediction uncertainty, Gap uncertainty, Peer dispersion)
4. Peer Lag Structure Analysis
5. Temporal Shape Characterization
6. Spike Representation Comparison
7. Architecture Ablation & Detection Simulation
"""

import os
import sys
import json
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional

def run_data_unit_audit():
    print("=== PART 1: DATA UNIT & QUALITY AUDIT ===")
    df = pd.read_csv("data/all_stations.csv")
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values(['station_id', 'timestamp']).reset_index(drop=True)
    
    stations = df['station_id'].unique()
    print(f"Total records: {len(df)}, Stations: {len(stations)}")
    
    st_stats = []
    for st in stations:
        sub = df[df['station_id'] == st].copy()
        sub['dt_hours'] = sub['timestamp'].diff().dt.total_seconds() / 3600.0
        
        # Intra-station delta
        p_vals = sub['pressure_hpa'].dropna()
        dp = sub['pressure_hpa'].diff()
        dp_clean = dp[sub['dt_hours'] <= 1.5].dropna()
        
        t_vals = sub['temperature_c'].dropna()
        dt_clean = sub['temperature_c'].diff()[sub['dt_hours'] <= 1.5].dropna()
        
        rh_vals = sub['humidity_percent'].dropna()
        drh_clean = sub['humidity_percent'].diff()[sub['dt_hours'] <= 1.5].dropna()
        
        st_stats.append({
            'station_id': st,
            'count': len(sub),
            'p_mean': p_vals.mean(),
            'p_std': p_vals.std(),
            'p_min': p_vals.min(),
            'p_max': p_vals.max(),
            'dp_1h_mean': dp_clean.mean(),
            'dp_1h_std': dp_clean.std(),
            'dp_1h_p99': dp_clean.abs().quantile(0.99),
            'dp_1h_max': dp_clean.abs().max(),
            'dt_1h_std': dt_clean.std(),
            'dt_1h_p99': dt_clean.abs().quantile(0.99),
            'drh_1h_std': drh_clean.std(),
            'drh_1h_p99': drh_clean.abs().quantile(0.99)
        })
        
    st_df = pd.DataFrame(st_stats)
    print("\nStation summary:")
    print(st_df[['station_id', 'p_mean', 'p_std', 'p_min', 'p_max', 'dp_1h_std', 'dp_1h_p99', 'dp_1h_max']].to_string())
    
    # Global cross-station differences
    all_p_diff = df['pressure_hpa'].diff() # Un-partitioned (includes station jump boundaries)
    unpartitioned_std = all_p_diff.std()
    
    # Intra-station differences
    intra_diffs = []
    for st in stations:
        sub = df[df['station_id'] == st]
        intra_diffs.append(sub['pressure_hpa'].diff().dropna())
    intra_diff_all = pd.concat(intra_diffs)
    intra_std = intra_diff_all.std()
    
    print(f"\nDiagnostic Discovery:")
    print(f"Unpartitioned raw diff std across full DataFrame (with boundary jumps between stations): {unpartitioned_std:.2f} hPa")
    print(f"Intra-station diff std (clean natural 1h movement): {intra_std:.2f} hPa")
    print(f"Station mean pressure ranges from {st_df['p_mean'].min():.2f} hPa to {st_df['p_mean'].max():.2f} hPa (Elevation offset = {st_df['p_mean'].max() - st_df['p_mean'].min():.2f} hPa)")
    
    return st_df, df

if __name__ == "__main__":
    st_df, df = run_data_unit_audit()
