import pandas as pd
import json
from pathlib import Path
import joblib
from model.detect import score_reading
from model.state import StateManager

DATA_DIR = Path("data")
ARTIFACTS_PATH = Path("model_artifacts/isolation_forest.pkl")

metadata = pd.read_csv(DATA_DIR / "stations_metadata.csv")
artifact = joblib.load(ARTIFACTS_PATH)

# Filter for RAN cluster (Ranchi)
ran_stations = ["AWS-RAN-067", "AWS-RAN-101", "AWS-RAN-102", "AWS-RAN-103"]
metadata_ran = metadata[metadata["station_id"].isin(ran_stations)].copy()

files = [DATA_DIR / f"{s}_labeled.csv" for s in ran_stations]
frames = [pd.read_csv(f, parse_dates=["timestamp"]) for f in files]
frame = pd.concat(frames, ignore_index=True)
frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
frame = frame.sort_values(["timestamp", "station_id"]).reset_index(drop=True)

class _NullHistoryStore:
    def append(self, *args, **kwargs): pass
    def append_batch(self, *args, **kwargs): pass
    def get_recent(self, *args, **kwargs): return pd.DataFrame()
    def get_all(self, *args, **kwargs): return pd.DataFrame()

manager = StateManager(metadata_ran, artifact, history_store=_NullHistoryStore())
manager.explainer = None

results = []
for timestamp, group in frame.groupby("timestamp", sort=True):
    network_snapshot = {}
    row_records = []
    for row in group.to_dict("records"):
        station_id = str(row["station_id"])
        raw = {k: v for k, v in row.items() if k not in ["is_anomaly", "fault_type", "episode_id", "fault_parameter", "fault_parameters", "fault_events"]}
        reading_time = pd.to_datetime(row["timestamp"], utc=True)
        network_snapshot[station_id] = (raw, reading_time)
        row_records.append((row, station_id, raw, reading_time))
        
    for row, station_id, raw, reading_time in row_records:
        verdict = manager.ingest_reading(station_id, raw, reading_time, network_snapshot, include_evaluation_diagnostics=True)
        if station_id == "AWS-RAN-103" and reading_time.month == 1 and reading_time.day in [1, 2]:
            results.append({
                "timestamp": reading_time,
                "temperature": raw.get("temperature_c"),
                "is_anomaly_gt": bool(row["is_anomaly"]),
                "is_anomaly_pred": bool(verdict.get("is_anomaly", False)),
                "fault_type_pred": verdict.get("fault_type"),
                "decision_basis": verdict.get("decision_basis"),
                "rules_fired": verdict.get("rules_fired"),
                "anomaly_score_pct": verdict.get("anomaly_score_pct"),
                "model_confidence_pct": verdict.get("model_confidence_pct"),
                "rule_confidence_pct": verdict.get("rule_confidence_pct"),
                "evaluation_diagnostics": verdict.get("evaluation_diagnostics")
            })

df_res = pd.DataFrame(results)
print("=== RAN-103 Results for Jan 1-2 ===")
false_alarms = df_res[df_res["is_anomaly_pred"] & ~df_res["is_anomaly_gt"]]
print(f"Total rows: {len(df_res)}, False Alarms: {len(false_alarms)}")
for idx, r in false_alarms.head(15).iterrows():
    print(f"{r['timestamp']} | T={r['temperature']} | Basis={r['decision_basis']} | Fault={r['fault_type_pred']} | Score={r['anomaly_score_pct']:.1f} | ModelConf={r['model_confidence_pct']} | Rules={r['rules_fired']}")
