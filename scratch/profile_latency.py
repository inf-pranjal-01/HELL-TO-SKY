"""
scratch/profile_latency.py

Profiles the live detection latency per component.
"""

import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

sys.path.append(str(Path(__file__).parent.parent))

from model.detect import score_reading, PARAMS
from model.state import StationBuffer
from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.uncertainty_budget import UncertaintyBudget
from model.sequential_sprt import SequentialSPRT
from model.peer_spatial_engine import PeerSpatialEngine
from model.cross_channel_covariance import CrossChannelEngine

artifact_path = Path(__file__).parent.parent / "model_artifacts" / "isolation_forest.pkl"
artifact = joblib.load(artifact_path)

now = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
history_df = pd.DataFrame({
    "timestamp": pd.date_range("2025-01-01 00:00:00", periods=24, freq="1h", tz="UTC"),
    "temperature_c": 25.0 + np.random.randn(24) * 0.5,
    "pressure_hpa": 1013.0 + np.random.randn(24) * 0.2,
    "humidity_pct": 60.0 + np.random.randn(24) * 2.0
})

raw_reading = {
    "station_id": "AWS-DEL-011",
    "timestamp": now,
    "temperature_c": 25.2,
    "pressure_hpa": 1013.1,
    "humidity_pct": 61.0,
}

# Measure 100 runs of score_reading
times = []
for _ in range(100):
    t0 = time.perf_counter()
    v = score_reading(raw_reading, history_df, artifact=artifact)
    t1 = time.perf_counter()
    times.append((t1 - t0) * 1000.0)  # ms

print(f"Mean Latency per reading: {np.mean(times):.3f} ms (median: {np.median(times):.3f} ms, p95: {np.percentile(times, 95):.3f} ms, max: {np.max(times):.3f} ms)")
