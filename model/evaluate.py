"""Offline evaluation for production replay and oracle-clean diagnostics.

Production mode uses the live StateManager/DecisionEngine path and never sends
ground-truth labels to detection. Oracle mode uses an offline-only vectorized
feature pass whose rolling baselines mask labeled fault rows, then scores every
row through the same score_reading detector. Oracle scores are diagnostic; they
are not the production acceptance benchmark.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.benchmark_contract import episodic_metrics, pooled_row_metrics
from model.detect import PARAM_PREFIXES, _cusum_evidence_series, score_reading
from model.features import build_feature_matrix
from model.state import RAW_HISTORY_MAXLEN_HOURS, StateManager

DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_PATH = PROJECT_ROOT / "model_artifacts" / "isolation_forest.pkl"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
LABEL_COLUMNS = {
    "is_anomaly", "fault_type", "episode_id", "fault_parameter",
    "fault_parameters", "fault_events", "__source_file",
}
EPISODIC_TYPES = {"frozen_value", "drift"}


def _label_bool(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False)
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _load_inputs(labeled_files: list[Path]) -> pd.DataFrame:
    frames = []
    for path in sorted(map(Path, labeled_files)):
        frame = pd.read_csv(path, parse_dates=["timestamp"])
        if "is_anomaly" not in frame.columns:
            raise ValueError(f"{path} has no is_anomaly ground-truth column")
        if "station_id" not in frame.columns:
            raise ValueError(f"{path} has no station_id column")
        frame["__source_file"] = path.name
        frame["is_anomaly"] = _label_bool(frame["is_anomaly"])
        if "fault_type" not in frame.columns:
            frame["fault_type"] = "none"
        frame["fault_type"] = frame["fault_type"].fillna("none").astype(str)
        frames.append(frame)
    if not frames:
        raise ValueError("No labeled replay files were supplied")
    full = pd.concat(frames, ignore_index=True)
    full["timestamp"] = pd.to_datetime(full["timestamp"], utc=True, errors="raise")
    if full.duplicated(["station_id", "timestamp"]).any():
        duplicate = full.loc[full.duplicated(["station_id", "timestamp"], keep=False), ["station_id", "timestamp"]].head(1)
        raise ValueError(f"Duplicate station/timestamp row in labeled inputs: {duplicate.to_dict('records')}")
    return full.sort_values(["timestamp", "station_id"], kind="mergesort").reset_index(drop=True)


def _raw_reading(row: dict) -> dict:
    """Strip all labels and evaluation-only columns before detector ingress."""
    return {key: value for key, value in row.items() if key not in LABEL_COLUMNS}


def _timestamp_ns(values) -> np.ndarray:
    """Return UTC timestamps as nanoseconds, independent of pandas' input resolution."""
    timestamps = pd.to_datetime(values, utc=True, errors="raise")
    return timestamps.to_numpy(dtype="datetime64[ns]").view("int64")


def _latest_position_at_or_before(timestamp_ns: np.ndarray, timestamp) -> int:
    """Find the latest causal history row without mixing datetime resolutions."""
    target_ns = int(_timestamp_ns([timestamp])[0])
    return int(np.searchsorted(timestamp_ns, target_ns, side="right") - 1)


def _event_parameters(verdict: dict, fault_type: str) -> list[str]:
    parameters = set()
    for rule in verdict.get("rules_fired", []) or []:
        if isinstance(rule, dict) and rule.get("type") == fault_type and rule.get("parameter"):
            parameters.add(str(rule["parameter"]))
    if not parameters:
        parameters.update(str(param) for param in verdict.get("likely_faulty_sensors", []) or [] if param)
    return sorted(parameters)


def _predicted_events(predictions: pd.DataFrame) -> list[dict]:
    """Make predicted frozen/drift episodes; adjacent readings form one event."""
    if predictions.empty:
        return []
    events = []
    active_by_key = {}
    rows = predictions.sort_values(["station_id", "station_sequence"], kind="mergesort")
    for row in rows.itertuples(index=False):
        if not row.is_anomaly_pred or row.fault_type_pred not in EPISODIC_TYPES:
            continue
        params = json.loads(row.fault_parameters_pred_json)
        if not params:
            params = ["__unknown_parameter__"]  # remains unmatched, counts as a predicted FP episode
        for parameter in params:
            key = (row.station_id, row.fault_type_pred, parameter)
            current = active_by_key.get(key)
            if current is not None and current["last_sequence"] + 1 == row.station_sequence:
                current["end_timestamp"] = row.timestamp
                current["last_sequence"] = row.station_sequence
                continue
            event = {
                "episode_id": f"pred:{row.station_id}:{row.station_sequence}:{row.fault_type_pred}:{parameter}",
                "station_id": row.station_id,
                "fault_type": row.fault_type_pred,
                "parameters": [parameter],
                "start_timestamp": row.timestamp,
                "end_timestamp": row.timestamp,
                "last_sequence": row.station_sequence,
            }
            events.append(event)
            active_by_key[key] = event
    for event in events:
        event.pop("last_sequence", None)
    return events


def _load_event_ledger(labeled_files: list[Path], explicit_path: Path | None = None) -> list[dict] | None:
    candidates = [Path(explicit_path)] if explicit_path else sorted({Path(p).parent / "fault_events.csv" for p in labeled_files})
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    if len(existing) != 1:
        raise ValueError("All labeled inputs in one evaluation must use exactly one fault_events.csv ledger")
    return pd.read_csv(existing[0]).to_dict("records")


def _metrics(predictions: pd.DataFrame, truth_events: list[dict] | None) -> dict:
    row = pooled_row_metrics(
        predictions["is_anomaly_gt"].tolist(), predictions["is_anomaly_pred"].tolist(),
    )
    by_type = {}
    reported_types = (set(predictions["fault_type_gt"]) | set(predictions["fault_type_pred"])) - {"none"}
    for fault_type in sorted(reported_types):
        true_mask = predictions["fault_type_gt"].eq(fault_type)
        pred_mask = predictions["is_anomaly_pred"] & predictions["fault_type_pred"].eq(fault_type)
        tp = int((true_mask & pred_mask).sum())
        fp = int((~true_mask & pred_mask).sum())
        fn = int((true_mask & ~pred_mask).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        by_type[fault_type] = {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall}

    episodic = None
    if truth_events is not None:
        predicted_events = _predicted_events(predictions)
        episodic = {
            fault_type: episodic_metrics(truth_events, predicted_events, fault_type)
            for fault_type in sorted(EPISODIC_TYPES)
        }
    return {"rows": int(len(predictions)), "row_level": row, "by_fault_type": by_type,
            "episodic": episodic,
            "episodic_note": None if episodic is not None else "unavailable: no event ledger was supplied"}


class _NullHistoryStore:
    def append(self, *args, **kwargs):
        pass

    def mark_spike(self, *args, **kwargs):
        pass

    def get_all(self, *args, **kwargs):
        return pd.DataFrame()


def _remove_ground_truth_row(state_manager: StateManager, station_id: str, timestamp) -> bool:
    """Oracle-only: discard a just-ingested labeled-fault row from future baselines."""
    buffer = state_manager.buffers[station_id]
    if not buffer._raw_rows:
        return False
    expected = pd.to_datetime(timestamp, utc=True)
    actual = pd.to_datetime(buffer._raw_rows[-1].get("timestamp"), utc=True, errors="coerce")
    if pd.isna(actual) or actual != expected:
        return False
    buffer._raw_rows.pop()
    buffer._cache_dirty = True
    return True


def _make_oracle_feature_cache(frame: pd.DataFrame, artifact: dict) -> tuple[dict, dict, dict, dict]:
    """Vectorize causal features, model scores, and CUSUM evidence once."""
    featured = build_feature_matrix(frame.copy())
    groups = {}
    positions = {}
    model_results = {}
    cusum_results = {}
    for station_id, group in featured.groupby("station_id", sort=False):
        group = group.reset_index(drop=True)
        group["timestamp"] = pd.to_datetime(group["timestamp"], utc=True)
        station_id = str(station_id)
        groups[station_id] = group.drop(columns=list(LABEL_COLUMNS), errors="ignore")
        for position, timestamp in enumerate(group["timestamp"]):
            positions[(station_id, timestamp)] = position

        model_features = groups[station_id][artifact["feature_columns"]].to_numpy(dtype=float)
        complete = ~pd.isna(model_features).any(axis=1)
        raw_scores = {}
        if complete.any():
            try:
                scored = artifact["model"].decision_function(model_features[complete])
                raw_scores = dict(zip(np.flatnonzero(complete), scored))
            except Exception:
                raw_scores = {}
        station_model_results = []
        for position in range(len(group)):
            if position in raw_scores:
                z = (0.0 - float(raw_scores[position])) / (artifact["training_score_std"] + 1e-9)
                pct = float(np.clip(100 / (1 + np.exp(-1.5 * z)), 0, 100))
                station_model_results.append((pct, "AVAILABLE"))
            elif complete[position]:
                station_model_results.append((None, "FAILED_INFERENCE"))
            elif min(position + 1, RAW_HISTORY_MAXLEN_HOURS) < 48:
                station_model_results.append((None, "UNAVAILABLE_WARMUP"))
            else:
                station_model_results.append((None, "UNAVAILABLE_MISSING_FEATURES"))
        model_results[station_id] = station_model_results

        station_cusum = {}
        for parameter, prefix in PARAM_PREFIXES.items():
            station_cusum[parameter] = _cusum_evidence_series(
                groups[station_id], prefix, parameter, station_id,
                max_window=RAW_HISTORY_MAXLEN_HOURS,
            )
        cusum_results[station_id] = station_cusum
    return groups, positions, model_results, cusum_results


def _evaluate_oracle_fast_serial(frame: pd.DataFrame, artifact: dict, ledger: list[dict] | None,
                                 progress_every: int = 5000,
                                 metadata: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """Fast offline diagnostic: label-masked baselines, every row scored."""
    metadata = metadata if metadata is not None else pd.read_csv(DATA_DIR / "stations_metadata.csv")
    manager = StateManager(metadata, artifact, history_store=_NullHistoryStore())
    manager.explainer = None
    feature_groups, feature_positions, model_results, cusum_results = _make_oracle_feature_cache(frame, artifact)
    # Keep raw histories as prebuilt per-station frames. The former loop
    # rebuilt a DataFrame from a deque for every target and every peer at
    # every timestamp, dominating replay time with pandas object creation.
    raw_groups = {}
    raw_timestamp_ns = {}
    for station_id, group in frame.groupby("station_id", sort=False):
        station_id = str(station_id)
        raw_group = group.sort_values("timestamp", kind="mergesort").drop(
            columns=list(LABEL_COLUMNS), errors="ignore"
        ).reset_index(drop=True)
        raw_groups[station_id] = raw_group
        raw_timestamp_ns[station_id] = _timestamp_ns(raw_group["timestamp"])
    station_sequences = {str(s): 0 for s in metadata["station_id"]}
    results = []
    started = time.perf_counter()
    processed = 0

    for timestamp, timestamp_group in frame.groupby("timestamp", sort=True):
        row_records = []
        current_time = pd.to_datetime(timestamp, utc=True)
        for row in timestamp_group.to_dict("records"):
            station_id = str(row["station_id"])
            raw = _raw_reading(row)
            reading_time = pd.to_datetime(row["timestamp"], utc=True)
            row_records.append((row, station_id, raw, reading_time))

        for row, station_id, raw, reading_time in row_records:
            group = feature_groups.get(station_id)
            position = feature_positions.get((station_id, reading_time))
            if group is None or position is None:
                raise ValueError(f"Missing oracle features for {station_id} at {reading_time}")
            history_df = raw_groups[station_id].iloc[
                max(0, position + 1 - RAW_HISTORY_MAXLEN_HOURS):position + 1
            ]
            neighbor_buffers = {}
            neighbor_features = {}
            for neighbor_id in manager.neighbor_map.get(station_id, []):
                neighbor_id = str(neighbor_id)
                peer_group = raw_groups.get(neighbor_id)
                peer_times = raw_timestamp_ns.get(neighbor_id)
                if peer_group is None or peer_times is None:
                    continue
                peer_position = _latest_position_at_or_before(peer_times, reading_time)
                if peer_position >= 0:
                    peer_start = max(0, peer_position + 1 - RAW_HISTORY_MAXLEN_HOURS)
                    neighbor_buffers[neighbor_id] = peer_group.iloc[peer_start:peer_position + 1]
                    peer_feature_group = feature_groups.get(neighbor_id)
                    if peer_feature_group is not None:
                        neighbor_features[neighbor_id] = peer_feature_group.iloc[peer_position]

            feature_row = group.iloc[position]
            history_start = max(0, position + 1 - RAW_HISTORY_MAXLEN_HOURS)
            history_features = group.iloc[history_start:position + 1]
            try:
                verdict = score_reading(
                    raw, history_df, artifact, neighbor_buffers=neighbor_buffers,
                    state=None, precomputed_features=feature_row,
                    precomputed_neighbors=neighbor_features,
                    precomputed_history_featured=history_features,
                    precomputed_model_result=model_results[station_id][position],
                    precomputed_cusum={
                        parameter: evidence[position]
                        for parameter, evidence in cusum_results[station_id].items()
                    },
                    include_suggestions=False,
                )
            except Exception as exc:
                raise RuntimeError(f"oracle evaluation failed at {station_id} {reading_time}: {exc!r}") from exc

            fault_type_pred = verdict.get("fault_type") or "none"
            results.append({
                "station_id": station_id,
                "timestamp": reading_time,
                "station_sequence": station_sequences.get(station_id, 0),
                "is_anomaly_gt": bool(row["is_anomaly"]),
                "fault_type_gt": row.get("fault_type", "none") or "none",
                "is_anomaly_pred": bool(verdict.get("is_anomaly", False)),
                "fault_type_pred": fault_type_pred,
                "fault_parameters_pred_json": json.dumps(_event_parameters(verdict, fault_type_pred)),
                "anomaly_score_pct": verdict.get("anomaly_score_pct", 0),
                "decision_basis": verdict.get("decision_basis"),
                "network_state": verdict.get("network_corroboration"),
                "eligible_peer_count": verdict.get("eligible_peer_count"),
                "corroborating_peer_count": verdict.get("corroborating_peer_count"),
                "diverged_peer_count": verdict.get("diverged_peer_count"),
            })
            station_sequences[station_id] = station_sequences.get(station_id, 0) + 1
            processed += 1

        if progress_every and processed and processed % progress_every < len(row_records):
            elapsed = time.perf_counter() - started
            print(f"  oracle: processed {processed:,}/{len(frame):,} rows in {elapsed:.1f}s")

    predictions = pd.DataFrame(results)
    elapsed = time.perf_counter() - started
    report = _metrics(predictions, ledger)
    report["elapsed_seconds"] = round(elapsed, 3)
    report["rows_per_second"] = round(len(predictions) / elapsed, 2) if elapsed else None
    report["evaluation_path"] = "vectorized_label_masked_diagnostic"
    return predictions, report


def _oracle_cluster_worker(payload):
    frame, artifact, metadata, progress_every = payload
    return _evaluate_oracle_fast_serial(frame, artifact, None, progress_every, metadata)


def _evaluate_oracle_fast(frame: pd.DataFrame, artifact: dict, ledger: list[dict] | None,
                          progress_every: int = 5000, workers: int = 1) -> tuple[pd.DataFrame, dict]:
    """Run independent station clusters in parallel, then score the merged predictions."""
    metadata = pd.read_csv(DATA_DIR / "stations_metadata.csv")
    cluster_groups = list(metadata.groupby("cluster_id", sort=True))
    workers = max(1, min(int(workers), len(cluster_groups)))
    if workers == 1:
        predictions, report = _evaluate_oracle_fast_serial(frame, artifact, ledger, progress_every, metadata)
        report["cluster_workers"] = 1
        return predictions, report

    started = time.perf_counter()
    tasks = []
    for _, cluster_metadata in cluster_groups:
        stations = set(cluster_metadata["station_id"].astype(str))
        cluster_frame = frame[frame["station_id"].astype(str).isin(stations)].copy()
        if not cluster_frame.empty:
            tasks.append((cluster_frame, artifact, cluster_metadata.copy(), progress_every))
    model = artifact.get("model")
    original_n_jobs = getattr(model, "n_jobs", None)
    if original_n_jobs is not None:
        model.n_jobs = 1
    try:
        pool = ThreadPoolExecutor(max_workers=min(workers, len(tasks)))
        with pool:
            results = list(pool.map(_oracle_cluster_worker, tasks))
    finally:
        if original_n_jobs is not None:
            model.n_jobs = original_n_jobs
    predictions = pd.concat([result[0] for result in results], ignore_index=True)
    predictions = predictions.sort_values(["timestamp", "station_id"], kind="mergesort").reset_index(drop=True)
    elapsed = time.perf_counter() - started
    report = _metrics(predictions, ledger)
    report["elapsed_seconds"] = round(elapsed, 3)
    report["rows_per_second"] = round(len(predictions) / elapsed, 2) if elapsed else None
    report["evaluation_path"] = "vectorized_label_masked_diagnostic"
    report["cluster_workers"] = min(workers, len(tasks))
    return predictions, report


def _evaluate_stream(frame: pd.DataFrame, artifact: dict, mode: str, ledger: list[dict] | None,
                     progress_every: int = 5000, workers: int = 1) -> tuple[pd.DataFrame, dict]:
    if mode == "oracle":
        return _evaluate_oracle_fast(frame, artifact, ledger, progress_every, workers)
    metadata = pd.read_csv(DATA_DIR / "stations_metadata.csv")
    manager = StateManager(metadata, artifact, history_store=_NullHistoryStore())
    manager.explainer = None
    station_sequences = {station: 0 for station in metadata["station_id"]}
    results = []
    started = time.perf_counter()
    processed = 0

    for timestamp, timestamp_group in frame.groupby("timestamp", sort=True):
        network_snapshot = {}
        row_records = []
        for row in timestamp_group.to_dict("records"):
            station_id = str(row["station_id"])
            raw = _raw_reading(row)
            reading_time = pd.to_datetime(row["timestamp"], utc=True)
            network_snapshot[station_id] = (raw, reading_time)
            row_records.append((row, station_id, raw, reading_time))

        for row, station_id, raw, reading_time in row_records:
            try:
                verdict = manager.ingest_reading(
                    station_id, raw, reading_time, network_snapshot,
                )
            except Exception as exc:
                raise RuntimeError(f"{mode} evaluation failed at {station_id} {reading_time}: {exc!r}") from exc

            ground_truth = bool(row["is_anomaly"])
            if mode == "oracle" and ground_truth:
                _remove_ground_truth_row(manager, station_id, reading_time)

            fault_type_pred = verdict.get("fault_type") or "none"
            parameters = _event_parameters(verdict, fault_type_pred)
            results.append({
                "station_id": station_id,
                "timestamp": reading_time,
                "station_sequence": station_sequences.get(station_id, 0),
                "is_anomaly_gt": ground_truth,
                "fault_type_gt": row.get("fault_type", "none") or "none",
                "is_anomaly_pred": bool(verdict.get("is_anomaly", False)),
                "fault_type_pred": fault_type_pred,
                "fault_parameters_pred_json": json.dumps(parameters),
                "anomaly_score_pct": verdict.get("anomaly_score_pct", 0),
                "decision_basis": verdict.get("decision_basis"),
                "network_state": verdict.get("network_corroboration"),
                "eligible_peer_count": verdict.get("eligible_peer_count"),
                "corroborating_peer_count": verdict.get("corroborating_peer_count"),
                "diverged_peer_count": verdict.get("diverged_peer_count"),
            })
            station_sequences[station_id] = station_sequences.get(station_id, 0) + 1
            processed += 1

        if progress_every and processed and processed % progress_every < len(row_records):
            elapsed = time.perf_counter() - started
            print(f"  {mode}: processed {processed:,}/{len(frame):,} rows in {elapsed:.1f}s")

    predictions = pd.DataFrame(results)
    elapsed = time.perf_counter() - started
    report = _metrics(predictions, ledger)
    report["elapsed_seconds"] = round(elapsed, 3)
    report["rows_per_second"] = round(len(predictions) / elapsed, 2) if elapsed else None
    report["evaluation_path"] = "sequential_state_manager"
    return predictions, report


def _new_output_dir(output_dir: Path | None) -> Path:
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        output_dir = RESULTS_DIR / f"evaluation_{stamp}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def _detector_config_snapshot() -> dict:
    import config
    names = (
        "MODEL_WEIGHT", "RULE_WEIGHT", "FUSION_ANOMALY_THRESHOLD",
        "MODEL_ALONE_OVERRIDE_THRESHOLD", "RULE_CONFIDENCE_BYPASS",
        "FROZEN_CONSECUTIVE_REQUIRED", "FROZEN_CONSECUTIVE_REQUIRED_PRESSURE",
        "FROZEN_MIN_MODEL_CORROBORATION", "FROZEN_PEER_ACTIVITY_RANGE_4H_THRESHOLD",
        "CUSUM_THRESHOLD", "CUSUM_DIRECTION_STREAK_REQUIRED", "CUSUM_DRIFT_ALLOWANCE",
        "DRIFT_MIN_MODEL_CORROBORATION",
    )
    return {name: getattr(config, name) for name in names}


def evaluate_all(
    labeled_files: list[Path],
    artifact: dict,
    *,
    mode: str = "both",
    output_dir: Path | None = None,
    event_ledger_path: Path | None = None,
    progress_every: int = 5000,
    workers: int = 1,
) -> dict:
    if mode not in {"production", "oracle", "both"}:
        raise ValueError("mode must be 'production', 'oracle', or 'both'")
    labeled_files = sorted(map(Path, labeled_files))
    frame = _load_inputs(labeled_files)
    ledger = _load_event_ledger(labeled_files, event_ledger_path)
    output_dir = _new_output_dir(output_dir)
    print(f"Rows: {len(frame):,}; stations: {frame['station_id'].nunique()}; output: {output_dir}")
    print("Production: ground-truth columns are stripped before StateManager ingress.")
    print("Oracle: ground-truth faults mask offline causal baselines; every row is scored by the shared detector (diagnostic only).")

    modes = ("production", "oracle") if mode == "both" else (mode,)
    results = {}
    for run_mode in modes:
        print(f"\nRunning {run_mode} evaluation...")
        predictions, summary = _evaluate_stream(frame, artifact, run_mode, ledger, progress_every, workers)
        path = output_dir / f"{run_mode}_predictions.csv"
        predictions.to_csv(path, index=False)
        summary["predictions_path"] = str(path)
        results[run_mode] = summary
        row = summary["row_level"]
        print(f"{run_mode}: row precision={row['precision']:.1%}, recall={row['recall']:.1%}, "
              f"TP={row['tp']} FP={row['fp']} FN={row['fn']} | "
              f"{summary['elapsed_seconds']:.1f}s ({summary['rows_per_second']:.1f} rows/s)")
        if summary["episodic"] is None:
            print(f"  Frozen/drift episode metrics {summary['episodic_note']}")
        else:
            for fault_type, metrics in summary["episodic"].items():
                print(f"  {fault_type}: P={metrics['precision']:.1%} R={metrics['recall']:.1%} "
                      f"TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']}")

    manifest = {
        "mode": mode,
        "input_files": [str(path) for path in labeled_files],
        "row_count": int(len(frame)),
        "station_count": int(frame["station_id"].nunique()),
        "event_ledger": str(event_ledger_path) if event_ledger_path else (
            str(labeled_files[0].parent / "fault_events.csv") if (labeled_files[0].parent / "fault_events.csv").exists() else None
        ),
        "artifact_path": str(ARTIFACTS_PATH),
        "detector_config": _detector_config_snapshot(),
        "oracle_cluster_workers": workers,
        "outputs": results,
    }
    (output_dir / "summary.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"\nSummary saved to {output_dir / 'summary.json'}")
    return {"output_dir": str(output_dir), **results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Skyguard without overwriting existing evaluation outputs.")
    parser.add_argument("--input-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--event-ledger", type=Path, default=None)
    parser.add_argument("--mode", choices=("production", "oracle", "both"), default="both")
    parser.add_argument("--progress-every", type=int, default=5000)
    parser.add_argument("--workers", type=int, default=7,
                        help="Independent cluster workers for oracle diagnostics (1 disables parallelism).")
    args = parser.parse_args()
    if not ARTIFACTS_PATH.exists():
        raise FileNotFoundError(f"Trained model artifact not found: {ARTIFACTS_PATH}")
    labeled = sorted(args.input_dir.glob("*_labeled.csv"))
    if not labeled:
        raise FileNotFoundError(f"No *_labeled.csv files found in {args.input_dir}")
    evaluate_all(
        labeled, joblib.load(ARTIFACTS_PATH), mode=args.mode,
        output_dir=args.output_dir, event_ledger_path=args.event_ledger,
        progress_every=args.progress_every,
        workers=args.workers,
    )
