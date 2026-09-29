import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import joblib
from model.detect import score_reading, PARAMS
from model.state import StationBuffer
from model.peer_spatial_engine import PeerSpatialEngine

df = pd.read_csv("data/AWS-CHN-024_labeled.csv", parse_dates=["timestamp"])
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
buf = StationBuffer("AWS-CHN-024")
artifact = joblib.load("model_artifacts/isolation_forest.pkl")

siblings = PeerSpatialEngine.get_sibling_peers("AWS-CHN-024")
sibling_bufs = {sib: StationBuffer(sib) for sib in siblings}

for idx, row in df.iloc[:1880].iterrows():
    ts = row["timestamp"]
    raw = {
        "station_id": "AWS-CHN-024",
        "timestamp": ts,
        "temperature_c": row["temperature_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"]
    }
    v = score_reading(
        raw_reading=raw,
        history_df=buf.raw_history_df(),
        artifact=artifact,
        neighbor_buffers=sibling_bufs,
        sprt_state=buf.sprt_state,
        include_evaluation_diagnostics=True
    )
    buf.record_raw_reading(raw, timestamp=ts, verdict=v)
    if idx >= 1865:
        print(f"Row {idx} | GT: {row['fault_type']} | T: {row['temperature_c']} | P: {row['pressure_hpa']} | RH: {row['humidity_pct']} | SPRT: {buf.sprt_state.get('pressure_hpa')} | Basis: {v.get('decision_basis')}")
