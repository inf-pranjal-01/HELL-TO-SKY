import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import joblib
from evaluation.fast_benchmark import load_dataset, _evaluate_cluster
from model.features import build_feature_matrix
from model.peer_spatial_engine import STATION_CLUSTERS

full_df, metadata = load_dataset()
artifact = joblib.load("model_artifacts/isolation_forest.pkl")

clean_inputs = full_df.drop(columns=["is_anomaly", "fault_type", "episode_id", "fault_parameter", "fault_parameters", "fault_events", "__source_file"], errors="ignore").copy()
featured_df = build_feature_matrix(clean_inputs)
feature_dict = {(str(r["station_id"]), r["timestamp"]): r for _, r in featured_df.iterrows()}

records = full_df.to_dict("records")

# Evaluate first cluster (e.g. Cluster DEL: AWS-DEL-011 and peers)
c_id = "DEL"
c_stations = STATION_CLUSTERS[c_id]
results, ep_results = _evaluate_cluster(c_id, c_stations, records, feature_dict, artifact)

df_res = pd.DataFrame(results)
drift_res = df_res[df_res["fault_gt"] == "drift"]

print(f"Total drift rows in {c_id}: {len(drift_res)}")
print(f"Drift detected in {c_id}: {drift_res['is_pred'].sum()} / {len(drift_res)}")
print("\nMissed drift rows sample:")
missed = drift_res[~drift_res["is_pred"]].head(15)
print(missed[["station_id", "timestamp", "is_gt", "is_pred", "decision_basis"]])
