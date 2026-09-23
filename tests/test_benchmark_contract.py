import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from data.anomaly_injector import (
    _affected_parameters,
    inject_anomalies,
    inject_multivariate,
    inject_unstructured_anomaly,
)
from evaluation.benchmark_contract import (
    CALIBRATION_SEEDS,
    HELD_OUT_SEEDS,
    FAULTED_STATIONS,
    STATION_HOLDOUT_FOLDS,
    episodic_metrics,
    pooled_row_metrics,
)


class BenchmarkContractTests(unittest.TestCase):
    def event(self, event_id, fault_type, parameter, start, end, station="AWS-TEST-001"):
        return {
            "episode_id": event_id,
            "station_id": station,
            "fault_type": fault_type,
            "parameters": [parameter],
            "start_timestamp": start,
            "end_timestamp": end,
        }

    def test_row_metrics_are_pooled_micro_counts(self):
        metrics = pooled_row_metrics([True, True, False, False], [True, False, True, False])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (1, 1, 1))
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)

    def test_delayed_detection_matches_when_it_overlaps_same_parameter_episode(self):
        truth = [self.event("g1", "drift", "temperature_c", "2025-01-01 00:00", "2025-01-01 06:00")]
        predicted = [self.event("p1", "drift", "temperature_c", "2025-01-01 04:00", "2025-01-01 05:00")]
        result = episodic_metrics(truth, predicted, "drift")
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))

    def test_mismatched_station_parameter_or_fault_type_does_not_match(self):
        truth = [self.event("g1", "frozen_value", "pressure_hpa", "2025-01-01", "2025-01-01 04:00")]
        predicted = [
            self.event("p1", "frozen_value", "temperature_c", "2025-01-01 01:00", "2025-01-01 02:00"),
            self.event("p2", "drift", "pressure_hpa", "2025-01-01 01:00", "2025-01-01 02:00"),
        ]
        result = episodic_metrics(truth, predicted, "frozen_value")
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))

    def test_one_predicted_episode_cannot_cover_two_truth_episodes(self):
        truth = [
            self.event("g1", "drift", "temperature_c", "2025-01-01 00:00", "2025-01-01 01:00"),
            self.event("g2", "drift", "temperature_c", "2025-01-01 04:00", "2025-01-01 05:00"),
        ]
        predicted = [self.event("p1", "drift", "temperature_c", "2025-01-01 00:00", "2025-01-01 05:00")]
        result = episodic_metrics(truth, predicted, "drift")
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 1))

    def test_injector_returns_lossless_event_ledger_without_changing_default_api(self):
        count = 1200
        hours = np.arange(count)
        frame = pd.DataFrame({
            "station_id": ["AWS-TEST-001"] * count,
            "timestamp": pd.date_range("2025-01-01", periods=count, freq="h"),
            "temperature_c": 22 + 6 * np.sin(2 * np.pi * hours / 24),
            "pressure_hpa": 1012 + np.sin(hours / 8),
            "humidity_pct": 55 + 15 * np.sin(2 * np.pi * (hours - 6) / 24),
        })
        with patch("data.anomaly_injector.ANOMALY_DENSITY_MULTIPLIER", 0.25), \
             patch("data.anomaly_injector.MIN_EVENTS_PER_TYPE", 1):
            labeled, ledger = inject_anomalies(frame, seed=42, return_events=True)
            legacy_result = inject_anomalies(frame, seed=42)

        self.assertIn("is_anomaly", labeled)
        self.assertIn("fault_type", labeled)
        self.assertIsInstance(legacy_result, pd.DataFrame)
        self.assertGreater(len(ledger), 0)
        self.assertTrue(ledger["episode_id"].is_unique)
        self.assertTrue((ledger["start_index"] <= ledger["end_index"]).all())
        self.assertTrue(ledger["parameters"].map(lambda value: bool(value)).all())
        for event in ledger.to_dict("records"):
            self.assertEqual(event["start_timestamp"], labeled.loc[event["start_index"], "timestamp"])
            self.assertEqual(event["end_timestamp"], labeled.loc[event["end_index"], "timestamp"])

    def test_benchmark_seed_and_station_folds_are_disjoint_and_complete(self):
        self.assertFalse(set(CALIBRATION_SEEDS) & set(HELD_OUT_SEEDS))
        held_out = [station for fold in STATION_HOLDOUT_FOLDS for station in fold]
        self.assertEqual(set(held_out), set(FAULTED_STATIONS))
        self.assertEqual(len(held_out), len(set(held_out)))

    def test_multichannel_fault_ledger_keeps_all_affected_parameters(self):
        all_parameters = {"temperature_c", "pressure_hpa", "humidity_pct"}
        self.assertEqual(set(_affected_parameters(inject_multivariate, "temperature_c")), all_parameters)
        self.assertEqual(set(_affected_parameters(inject_unstructured_anomaly, "pressure_hpa")), all_parameters)
        self.assertEqual(_affected_parameters(lambda *_: None, "humidity_pct"), ["humidity_pct"])


if __name__ == "__main__":
    unittest.main()
