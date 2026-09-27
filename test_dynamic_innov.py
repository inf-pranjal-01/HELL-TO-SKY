import pandas as pd
import io
import math
import numpy as np
from model.seasonal_baseline import get_expected_roc
from model.uncertainty_budget import SENSOR_QUANTIZATION_FLOORS, GAP_GROWTH_RATES
from model.cross_channel_covariance import CrossChannelEngine

data = '''2025-01-01 05:00:00,10.0,979.9,93,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 06:00:00,9.9,981.1,94,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 07:00:00,12.3,981.7,85,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 08:00:00,14.3,982.5,74,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 09:00:00,16.4,982.9,64,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 10:00:00,18.8,982.4,53,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 11:00:00,21.2,981.6,42,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 12:00:00,23.0,980.3,34,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 13:00:00,24.0,979.0,30,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 14:00:00,24.2,978.1,28,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 15:00:00,24.0,977.8,27,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 16:00:00,22.3,977.9,33,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 17:00:00,18.3,977.9,43,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 18:00:00,17.2,979.3,55,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 19:00:00,16.0,980.0,63,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 20:00:00,14.7,980.4,69,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 21:00:00,13.2,980.6,75,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 22:00:00,11.9,980.8,78,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 23:00:00,10.9,980.7,80,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 00:00:00,10.2,980.3,81,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 01:00:00,9.7,979.7,84,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 02:00:00,9.2,978.8,87,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 03:00:00,9.0,978.5,88,AWS-RAN-103,Bundu,RAN,neighbor,False,'''

cols = ['timestamp', 'temperature_c', 'pressure_hpa', 'humidity_pct', 'station_id', 'station_name', 'cluster', 'role', 'is_anomaly_gt', 'extra']
df = pd.read_csv(io.StringIO(data.strip()), header=None, names=cols)

params = ['temperature_c', 'pressure_hpa', 'humidity_pct']
prefixes = {'temperature_c': 'temp', 'pressure_hpa': 'pressure', 'humidity_pct': 'humidity'}

prior_row = None
for idx, row in df.iterrows():
    ts = pd.to_datetime(row['timestamp'], utc=True)
    hour = ts.hour
    
    z_scores = {}
    if prior_row is not None:
        dt = (ts - prior_row['ts']).total_seconds() / 3600.0
        for p in params:
            val = float(row[p])
            p_val = float(prior_row[p])
            prefix = prefixes[p]
            exp_roc = get_expected_roc('AWS-RAN-103', prefix, hour)
            actual_delta = val - p_val
            innov = actual_delta - (exp_roc * dt)
            
            floor = SENSOR_QUANTIZATION_FLOORS[p]
            kappa = GAP_GROWTH_RATES[p]
            sigma_innov = math.sqrt(2.0 * (floor ** 2) + kappa * dt)
            z_scores[p] = innov / sigma_innov
            
        d_sq, p_val_m, _ = CrossChannelEngine.compute_mahalanobis_distance(z_scores['temperature_c'], z_scores['pressure_hpa'], z_scores['humidity_pct'])
        print(f"{ts.strftime('%H:%M')} | T={row['temperature_c']} | z_T={z_scores['temperature_c']:.2f}, z_P={z_scores['pressure_hpa']:.2f}, z_H={z_scores['humidity_pct']:.2f} | D^2={d_sq:.2f}")
    else:
        print(f"{ts.strftime('%H:%M')} | T={row['temperature_c']} | Cold Start Baseline")
        
    prior_row = {'ts': ts, **{p: row[p] for p in params}}
