
import sys
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
sys.path.append(str(Path(__file__).parent.parent))
from model.features import build_feature_matrix, FEATURE_COLUMNS, calibrate_rule_thresholds
DATA_DIR = Path(__file__).parent.parent / "data"
ARTIFACTS_DIR = Path(__file__).parent.parent / "model_artifacts"
N_ESTIMATORS = 100
RANDOM_STATE = 42
def load_clean_training_data():
    stations_path = DATA_DIR / "all_stations.csv"
    if not stations_path.exists():
        raise FileNotFoundError(
            f"Expected {stations_path.name} in {DATA_DIR} "
            f"(output of data_fetch.py -> validate_data.py). Run that first."
        )
    df = pd.read_csv(stations_path, parse_dates=["timestamp"])
    if "is_anomaly" in df.columns or "fault_type" in df.columns:
        raise ValueError(
            "all_stations.csv contains is_anomaly/fault_type columns -- this looks "
            "like a labeled/injected file, not the raw combined dataset. train.py "
            "must only ever see raw data. Re-run data_fetch.py's combined output, "
            "or check you haven't accidentally pointed this at a *_labeled.csv."
        )
    return df
def train():
    df = load_clean_training_data()
    df = df.sort_values("timestamp")
    cutoff_idx = int(len(df) * 0.7)
    cutoff_date = df.iloc[cutoff_idx]["timestamp"]
    print(f"Temporal Split: Training on data before {cutoff_date}")
    df = df[df["timestamp"] < cutoff_date]
    print(f"Loaded {len(df)} raw rows across {df['station_id'].nunique()} stations.\n")
    featured = build_feature_matrix(df)
    before = len(featured)
    featured = featured.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)
    after = len(featured)
    print(f"Dropped {before - after} warm-up rows with incomplete features "
          f"(expected: roughly ROLLING_MIN_PERIODS=6h x {df['station_id'].nunique()} "
          f"stations -- NOT the full 48h window, since min_periods lets rolling "
          f"features start producing values after just 6h of history).")
    print(f"{after} rows remain for training.\n")
    X = featured[FEATURE_COLUMNS].values
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=0.01,
        random_state=RANDOM_STATE,
        n_jobs=1,
    )
    model.fit(X)
    scores = model.decision_function(X)
    print("Training score distribution (decision_function; LOWER = more anomalous):")
    print(pd.Series(scores).describe())
    rule_thresholds = calibrate_rule_thresholds(featured)
    print("\n--- PER-STATION THRESHOLD DIAGNOSTIC ---")
    for rule_key in ("roc_small", "spike"):
        for prefix in ["temp", "pressure", "humidity"]:
            entries = rule_thresholds[rule_key][prefix]
            n_stations = len([k for k in entries if k != "__global__"])
            print(f"{rule_key}[{prefix}]: {n_stations} stations calibrated individually, "
                  f"__global__={entries['__global__']:.4f}")
            print(f"  sample values: {dict(list(entries.items())[:5])}")
    print("--- END DIAGNOSTIC ---")
    print("\nCalibrated rule thresholds (from real clean data, see features.py's "
          "calibrate_rule_thresholds docstring for the percentiles used):")
    print(rule_thresholds)
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    artifact = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "training_score_mean": float(scores.mean()),
        "training_score_std": float(scores.std()),
        "training_score_min": float(scores.min()),
        "training_score_max": float(scores.max()),
        "rule_thresholds": rule_thresholds,
        "n_estimators": N_ESTIMATORS,
        "random_state": RANDOM_STATE,
        "n_training_rows": after,
    }
    output_path = ARTIFACTS_DIR / "isolation_forest.pkl"
    joblib.dump(artifact, output_path)
    print(f"\nSaved trained model + metadata -> {output_path}")
    print("\nThis .pkl is what detect.py loads ONCE at API startup -- see "
          "BACKEND_BLUEPRINT.md section 4 for why it must never retrain per-request.")
if __name__ == "__main__":
    train()
