"""
SkyGuard AI — Phase 2b: Model training.

Trains the Isolation Forest offline on raw, real historical observations
only -- never on injected/labeled data. Feeding corrupted data into training
would contaminate the baseline representation of nominal atmospheric states.

Isolation Forest builds an ensemble of randomized trees that isolate observations
via random feature/threshold splits. Anomalous observations reside far from the
nominal distribution and require few splits to isolate, while nominal points
require many splits. Using n_estimators=100 provides score stability across trees.
"""

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
    """
    Loads the RAW combined dataset. Hard-fails if the input looks like a
    labeled/injected file -- this is the training/serving separation
    rule enforced in code, not just a comment.

    Operates strictly on uncorrupted baseline measurements to prevent
    leakage between training and serving evaluation regimes.
    """
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

    # True Temporal Split (P0/Phase 3): Ensure we don't mix future and past data randomly.
    # Train only on the first 70% of the dataset chronologically.
    df = df.sort_values("timestamp")
    cutoff_idx = int(len(df) * 0.7)
    cutoff_date = df.iloc[cutoff_idx]["timestamp"]
    print(f"Temporal Split: Training on data before {cutoff_date}")
    df = df[df["timestamp"] < cutoff_date]

    print(f"Loaded {len(df)} raw rows across {df['station_id'].nunique()} stations.\n")

    # SIGNATURE CHANGE (§9, features.py): single-arg now -- metadata was
    # only ever used for spatial-feature cluster lookups, removed with
    # the rest of that machinery.
    featured = build_feature_matrix(df)

    # Drop warm-up rows (first ~48h per station) that don't have a
    # complete rolling baseline yet -- an incomplete feature vector
    # isn't a real training example, it's a startup artifact.
    before = len(featured)
    featured = featured.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)
    after = len(featured)
    print(f"Dropped {before - after} warm-up rows with incomplete features "
          f"(expected: roughly ROLLING_MIN_PERIODS=6h x {df['station_id'].nunique()} "
          f"stations -- NOT the full 48h window, since min_periods lets rolling "
          f"features start producing values after just 6h of history).")
    print(f"{after} rows remain for training.\n")

    X = featured[FEATURE_COLUMNS].values

    # contamination=0.01 (NOT 'auto'). 'auto' uses the original paper's
    # offset_=-0.5 heuristic which flags ~11% of training data as anomalous
    # even on a fully clean training set. Empirically: 4.4% of training rows
    # score model_pct > 72, meaning ~93 clean readings per station will
    # cross the fusion threshold when ANY rule (drift/spike) also fires.
    # That directly drives the 85-226 clean-station FPs we measured.
    # Setting contamination=0.01 makes the model's internal boundary
    # conservative: only the most extreme 1% of training rows are flagged,
    # substantially lowering model_pct on normal readings. Injected fault
    # events (extreme rail values, sustained drifts, T/RH violations) will
    # still score very high relative to the rescaled distribution.
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=0.01,
        random_state=RANDOM_STATE,
        # Single-process fitting keeps training reliable in restricted
        # Windows environments where joblib cannot create worker IPC
        # handles. It changes throughput only, not the model contract.
        n_jobs=1,
    )
    model.fit(X)

    # decision_function: higher = more normal, lower/negative = more
    # anomalous. Saving this training distribution alongside the model
    # gives detect.py/evaluate.py a reference point for "what did
    # normal actually look like," instead of calibrating blind.
    scores = model.decision_function(X)
    print("Training score distribution (decision_function; LOWER = more anomalous):")
    print(pd.Series(scores).describe())

    # Rule-layer thresholds (roc_small, spike -- frozen/drift are no
    # longer calibrated, see features.py's calibrate_rule_thresholds
    # docstring), calibrated empirically from this SAME real clean
    # `featured` data. Using the already-dropna'd `featured` (same rows
    # as X) is fine even though a handful of rows within the first
    # DRIFT_LOOKBACK_HOURS=24h per station may still be NaN in the
    # diagnostic-only Nh_delta column specifically (FEATURE_COLUMNS only
    # requires ROLLING_MIN_PERIODS=6h, shorter than the 24h delta needs)
    # -- pandas' .quantile() skips NaN by default, and it's a small
    # fraction of ~2000+ rows/station either way.
    rule_thresholds = calibrate_rule_thresholds(featured)

    # Empirical rule thresholds for single-station temporal jumps and spikes
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
