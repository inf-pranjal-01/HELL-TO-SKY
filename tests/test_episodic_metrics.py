"""Evaluator-facing event metric checks."""

import unittest

from evaluation.benchmark_contract import episodic_metrics


class EpisodicMetricTests(unittest.TestCase):
    def event(self, event_id, parameter, start, end):
        return {
            "episode_id": event_id,
            "station_id": "AWS-TEST-001",
            "fault_type": "drift",
            "parameters": [parameter],
            "start_timestamp": start,
            "end_timestamp": end,
        }

    def test_delayed_detection_matches_overlapping_parameter_episode(self):
        truth = [self.event("true-1", "temperature_c", "2025-01-01", "2025-01-01 06:00")]
        predicted = [self.event("pred-1", "temperature_c", "2025-01-01 04:00", "2025-01-01 05:00")]
        result = episodic_metrics(truth, predicted, "drift")
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))

    def test_nonoverlap_or_wrong_parameter_are_unmatched(self):
        truth = [self.event("true-1", "temperature_c", "2025-01-01", "2025-01-01 02:00")]
        predicted = [
            self.event("pred-1", "temperature_c", "2025-01-01 03:00", "2025-01-01 04:00"),
            self.event("pred-2", "pressure_hpa", "2025-01-01 01:00", "2025-01-01 02:00"),
        ]
        result = episodic_metrics(truth, predicted, "drift")
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 2, 1))

    def test_one_prediction_matches_at_most_one_truth_episode(self):
        truth = [
            self.event("true-1", "temperature_c", "2025-01-01", "2025-01-01 01:00"),
            self.event("true-2", "temperature_c", "2025-01-01 04:00", "2025-01-01 05:00"),
        ]
        predicted = [self.event("pred-1", "temperature_c", "2025-01-01", "2025-01-01 05:00")]
        result = episodic_metrics(truth, predicted, "drift")
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
