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

# Load sibling peer buffers for CHN-024
siblings = PeerSpatialEngine.get_sibling_peers("AWS-CHN-024")
sibling_dfs = {}
for sib in siblings:
    p = Path(f"data/{sib}_labeled.csv")
    if p.exists():
        sdf = pd.read_csv(p, parse_dates=["timestamp"])
        sdf["timestamp"] = pd.to_datetime(sdf["timestamp"], utc=True)
        sibling_dfs[sib] = sdf

sibling_bufs = {sib: StationBuffer(sib) for sib in siblings}

for idx, row in df.iterrows():
    ts = row["timestamp"]
    raw = {
        "station_id": "AWS-CHN-024",
        "timestamp": ts,
        "temperature_c": row["temperature_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"]
    }
    
    # Advance sibling buffers to current timestamp
    for sib, sbuf in sibling_bufs.items():
        if sib in sibling_dfs:
            srows = sibling_dfs[sib][sibling_dfs[sib]["timestamp"] == ts]
            if not srows.empty:
                srow = srows.iloc[0]
                sraw = {
                    "station_id": sib,
                    "timestamp": ts,
                    "temperature_c": srow["temperature_c"],
                    "pressure_hpa": srow["pressure_hpa"],
                    "humidity_pct": srow["humidity_pct"]
                }
                sbuf.record_raw_reading(sraw, timestamp=ts, verdict={"is_anomaly": False})
                
    v = score_reading(
        raw_reading=raw,
        history_df=buf.raw_history_df(),
        artifact=artifact,
        neighbor_buffers=sibling_bufs,
        sprt_state=buf.sprt_state,
        include_evaluation_diagnostics=True
    )
    buf.record_raw_reading(raw, timestamp=ts, verdict=v)
    
    if row["fault_type"] == "drift":
        sprt_info = buf.sprt_state.get(row.get("fault_parameter") or "temperature_c", {})
        print(f"Row {idx:4d} | GT: drift ({row.get('fault_parameter')}) | IsAnom: {v.get('is_anomaly')} | Fault: {v.get('fault_type')} | Basis: {v.get('decision_basis')}")
