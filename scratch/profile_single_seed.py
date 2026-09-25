"""
scratch/profile_single_seed.py
Quick profile on 200 readings to check exact per-reading breakdown
"""
import time
import joblib
import pandas as pd
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from model.detect import score_reading, PARAMS
from model.state import StationBuffer
from model.peer_spatial_engine import PeerSpatialEngine
import data.anomaly_injector as injector

DATA_DIR = Path(__file__).parent.parent / "data"
ARTIFACTS_DIR = Path(__file__).parent.parent / "model_artifacts"

artifact = joblib.load(ARTIFACTS_DIR / "isolation_forest.pkl")
stations_path = DATA_DIR / "all_stations.csv"
df = pd.read_csv(stations_path, parse_dates=["timestamp"])
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp").reset_index(drop=True)
cutoff_idx = int(len(df) * 0.7)
test_df = df.iloc[cutoff_idx:].copy().reset_index(drop=True)

# Inject for 4 stations in Delhi cluster
delhi_stations = ["AWS-DEL-011", "AWS-DEL-101", "AWS-DEL-102", "AWS-DEL-103"]
delhi_df = test_df[test_df["station_id"].isin(delhi_stations)].copy()
buffers = {st: StationBuffer(st) for st in delhi_stations}

times = []
for i, row in enumerate(delhi_df.head(400).to_dict("records")):
    st_id = row["station_id"]
    ts = row["timestamp"]
    raw_reading = {
        "station_id": st_id,
        "timestamp": ts,
        "temperature_c": row["temperature_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"],
    }
    sibling_ids = PeerSpatialEngine.get_sibling_peers(st_id)
    neighbor_bufs = {nid: buffers[nid] for nid in sibling_ids if nid in buffers}
    
    t0 = time.perf_counter()
    hist_df = buffers[st_id].raw_history_df()
    verdict = score_reading(raw_reading, hist_df, artifact, neighbor_bufs)
    buffers[st_id].record_raw_reading(raw_reading, timestamp=ts, verdict=verdict)
    t1 = time.perf_counter()
    times.append(t1 - t0)

print(f"Mean time per reading (with 3 peers): {sum(times)/len(times)*1000:.3f} ms")
print(f"p95 time per reading: {pd.Series(times).quantile(0.95)*1000:.3f} ms")
print(f"Total time for 400 readings: {sum(times):.3f} s")
