"""Ground-truth, split, and metric contract for Skyguard replay benchmarks.

Overall detection is scored with pooled row-level micro metrics. Frozen and
drift are additionally scored as fault episodes, matched one-to-one by station,
fault type, affected parameter, and time overlap. This contract is independent
of the detector and is safe to import in offline evaluation/tests only.
"""

from __future__ import annotations

import json
from typing import Iterable


CALIBRATION_SEEDS = (71001, 71002, 71003)
HELD_OUT_SEEDS = (82001, 82002, 82003)

# One deterministic leave-one-faulted-station-out fold per injection center.
# Clean neighboring stations remain available to measure false alarms and
# regional context; the held-out center is never part of that fold's tuning set.
FAULTED_STATIONS = (
    "AWS-BHO-030", "AWS-CHN-024", "AWS-DEL-011", "AWS-KOL-015",
    "AWS-MUM-007", "AWS-RAN-067", "AWS-VAR-052",
)
STATION_HOLDOUT_FOLDS = tuple((station,) for station in FAULTED_STATIONS)


def pooled_row_metrics(truth: Iterable[bool], predicted: Iterable[bool]) -> dict:
    truth = [bool(value) for value in truth]
    predicted = [bool(value) for value in predicted]
    if len(truth) != len(predicted):
        raise ValueError("truth and predicted must have the same number of rows")
    tp = sum(t and p for t, p in zip(truth, predicted))
    fp = sum((not t) and p for t, p in zip(truth, predicted))
    fn = sum(t and (not p) for t, p in zip(truth, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _parameters(event: dict) -> set[str]:
    value = event.get("parameters", event.get("affected_parameters", []))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    return {str(item) for item in (value or [])}


def _as_utc(value):
    import pandas as pd
    result = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(result):
        raise ValueError(f"event timestamp is missing or invalid: {value!r}")
    return result


def _overlaps(truth_event: dict, predicted_event: dict, fault_type: str) -> bool:
    if truth_event.get("station_id") != predicted_event.get("station_id"):
        return False
    if truth_event.get("fault_type") != fault_type or predicted_event.get("fault_type") != fault_type:
        return False
    if not (_parameters(truth_event) & _parameters(predicted_event)):
        return False
    true_start = _as_utc(truth_event.get("start_timestamp", truth_event.get("start")))
    true_end = _as_utc(truth_event.get("end_timestamp", truth_event.get("end")))
    pred_start = _as_utc(predicted_event.get("start_timestamp", predicted_event.get("start")))
    pred_end = _as_utc(predicted_event.get("end_timestamp", predicted_event.get("end")))
    return max(true_start, pred_start) <= min(true_end, pred_end)


def episodic_metrics(
    truth_events: Iterable[dict], predicted_events: Iterable[dict], fault_type: str,
) -> dict:
    """One-to-one maximum-cardinality overlap matching for one fault type."""
    truth = [event for event in truth_events if event.get("fault_type") == fault_type]
    predicted = [event for event in predicted_events if event.get("fault_type") == fault_type]
    candidates = [
        [i for i, true_event in enumerate(truth) if _overlaps(true_event, pred_event, fault_type)]
        for pred_event in predicted
    ]
    true_to_pred = {}

    def assign(pred_index: int, seen: set[int]) -> bool:
        for true_index in candidates[pred_index]:
            if true_index in seen:
                continue
            seen.add(true_index)
            if true_index not in true_to_pred or assign(true_to_pred[true_index], seen):
                true_to_pred[true_index] = pred_index
                return True
        return False

    for pred_index in range(len(predicted)):
        assign(pred_index, set())

    tp = len(true_to_pred)
    fp, fn = len(predicted) - tp, len(truth) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    matches = sorted((pred_index, true_index) for true_index, pred_index in true_to_pred.items())
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "truth_episodes": len(truth), "predicted_episodes": len(predicted),
        "precision": precision, "recall": recall, "f1": f1,
        "matches": matches,
    }
