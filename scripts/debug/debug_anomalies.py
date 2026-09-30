import pandas as pd
from model.detect import load_model, score_reading
from model.state import StateManager
def test():
    artifact = load_model()
    df = pd.read_csv("data/AWS-MUM-007.csv", parse_dates=["timestamp"])
    df = df.head(100)
    metadata = pd.read_csv("data/stations_metadata.csv")
    state = StateManager(metadata, artifact)
    for i, row in df.iterrows():
        reading = row.to_dict()
        reading["timestamp"] = reading["timestamp"].isoformat()
        verdict = state.ingest_reading(reading)
        if verdict["is_anomaly"]:
            print(f"Anomaly at {reading['timestamp']}: "
                  f"Score={verdict['anomaly_score_pct']}% "
                  f"Model={verdict['model_confidence_pct']}% "
                  f"Rules={verdict['rules_fired']} "
                  f"Fault={verdict['fault_type']}")
if __name__ == "__main__":
    test()
