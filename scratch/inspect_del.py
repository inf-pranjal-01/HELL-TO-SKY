import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import joblib
from model.detect import score_reading, PARAMS
from model.state import StationBuffer
from model.peer_spatial_engine import PeerSpatialEngine

df = pd.read_csv("data/AWS-DEL-011_labeled.csv", parse_dates=["timestamp"])
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
buf = StationBuffer("AWS-DEL-011")
artifact = joblib.load("model_artifacts/isolation_forest.pkl")

siblings = PeerSpatialEngine.get_sibling_peers("AWS-DEL-011")
sibling_bufs = {sib: StationBuffer(sib) for sib in siblings}
sibling_dfs = {sib: pd.read_csv(f"data/{sib}_labeled.csv", parse_dates=["timestamp"]) for sib in siblings}

for idx, row in df.iloc[:260].iterrows():
    ts = row["timestamp"]
    raw = {
        "station_id": "AWS-DEL-011",
        "timestamp": ts,
        "temperature_c": row["temperature_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"]
    }
    for sib, sbuf in sibling_bufs.items():
        srows = sibling_dfs[sib][sibling_dfs[sib]["timestamp"] == ts]
        if not srows.empty:
            sr = srows.iloc[0]
            sbuf.record_raw_reading({
                "station_id": sib,
                "timestamp": ts,
                "temperature_c": sr["temperature_c"],
                "pressure_hpa": sr["pressure_hpa"],
                "humidity_pct": sr["humidity_pct"]
            }, timestamp=ts, verdict={"is_anomaly": False})
            
    v = score_reading(
        raw_reading=raw,
        history_df=buf.raw_history_df(),
        artifact=artifact,
        neighbor_buffers=sibling_bufs,
        sprt_state=buf.sprt_state,
        include_evaluation_diagnostics=True
    )
    buf.record_raw_reading(raw, timestamp=ts, verdict=v)
    if 58 <= idx <= 92:
        p_sprt = buf.sprt_state.get("pressure_hpa")
        t_sprt = buf.sprt_state.get("temperature_c")
        h_sprt = buf.sprt_state.get("humidity_pct")
        print(f"Row {idx:2d} | GT: {row['fault_type']} | T: {row['temperature_c']:.1f} | P: {row['pressure_hpa']:.1f} | RH: {row['humidity_pct']:.1f} | T_sprt: {t_sprt} | P_sprt: {p_sprt} | Basis: {v.get('decision_basis')}")
