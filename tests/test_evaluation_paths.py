"""Focused checks for evaluation label isolation and oracle baseline masking."""

from collections import deque
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

from model.evaluate import (
    _latest_position_at_or_before, _metrics, _prediction_diagnostics, _raw_reading,
    _remove_ground_truth_row, _timestamp_ns,
)
from model.detect import (
    PARAM_PREFIXES, _cusum_evidence, _cusum_evidence_series,
    _multiclass_fault_label,
)
from model.features import FEATURE_COLUMNS, build_feature_matrix, build_features_for_latest
from model.state import StationBuffer
from model.state import RAW_HISTORY_MAXLEN_HOURS


class EvaluationPathTests(unittest.TestCase):
    def test_binary_fault_helper_cannot_supply_a_fault_type(self):
        class BinaryHelper:
            classes_ = np.array([False, True])

            def predict_proba(self, _frame):
                raise AssertionError("binary helper must not be used as a type classifier")

        label, confidence = _multiclass_fault_label(
            BinaryHelper(), ["signal"], pd.DataFrame({"signal": [1.0]}),
        )
        self.assertIsNone(label)
        self.assertIsNone(confidence)

    def test_multiclass_fault_helper_only_returns_a_type_and_confidence(self):
        class MulticlassHelper:
            classes_ = np.array(["drift", "frozen_value", "spike"])

            def predict_proba(self, frame):
                self.assert_columns = list(frame.columns)
                return np.array([[0.1, 0.8, 0.1]])

        helper = MulticlassHelper()
        label, confidence = _multiclass_fault_label(
            helper, ["signal"], pd.DataFrame({"signal": [1.0]}),
        )
        self.assertEqual(label, "frozen_value")
        self.assertEqual(confidence, 0.8)
        self.assertEqual(helper.assert_columns, ["signal"])

    def test_oracle_peer_history_lookup_normalizes_pandas_timestamp_resolution(self):
        peer_timestamps = pd.Series(pd.date_range(
            "2025-01-01T00:00:00Z", periods=3, freq="h",
        ))
        peer_ns = _timestamp_ns(peer_timestamps)

        self.assertEqual(
            _latest_position_at_or_before(peer_ns, pd.Timestamp("2025-01-01T01:00:00Z")),
            1,
        )
        self.assertEqual(
            _latest_position_at_or_before(peer_ns, pd.Timestamp("2024-12-31T23:00:00Z")),
            -1,
        )

    def test_detector_ingress_strips_ground_truth_and_evaluation_columns(self):
        reading = _raw_reading({
            "station_id": "AWS-TEST-001",
            "timestamp": "2025-01-01T00:00:00Z",
            "temperature_c": 24.0,
            "is_anomaly": True,
            "fault_type": "drift",
            "episode_id": "event-1",
            "__source_file": "sample_labeled.csv",
        })
        self.assertEqual(reading["temperature_c"], 24.0)
        self.assertFalse({"is_anomaly", "fault_type", "episode_id", "__source_file"} & reading.keys())

    def test_fault_breakdown_counts_wrong_type_alert_as_fp_and_fn(self):
        predictions = pd.DataFrame({
            "is_anomaly_gt": [True, True, False],
            "fault_type_gt": ["drift", "frozen_value", "none"],
            "is_anomaly_pred": [True, True, True],
            "fault_type_pred": ["frozen_value", "drift", "spike"],
        })
        metrics = _metrics(predictions, None)
        self.assertEqual((metrics["row_level"]["tp"], metrics["row_level"]["fp"], metrics["row_level"]["fn"]), (2, 1, 0))
        self.assertEqual((metrics["by_fault_type"]["drift"]["tp"],
                          metrics["by_fault_type"]["drift"]["fp"],
                          metrics["by_fault_type"]["drift"]["fn"]), (0, 1, 1))
        self.assertEqual((metrics["by_fault_type"]["frozen_value"]["tp"],
                          metrics["by_fault_type"]["frozen_value"]["fp"],
                          metrics["by_fault_type"]["frozen_value"]["fn"]), (0, 1, 1))
        self.assertEqual(metrics["by_fault_type"]["spike"]["fp"], 1)

    def test_prediction_diagnostics_break_down_false_alarms_and_missed_rows(self):
        predictions = pd.DataFrame({
            "station_id": ["AWS-TEST-001", "AWS-TEST-001", "AWS-TEST-002"],
            "timestamp": pd.to_datetime(["2025-01-01T00:00Z"] * 3, utc=True),
            "is_anomaly_gt": [False, True, True],
            "fault_type_gt": ["none", "drift", "frozen_value"],
            "is_anomaly_pred": [True, False, True],
            "fault_type_pred": ["unstructured_anomaly", "none", "frozen_value"],
            "decision_basis": ["ML_MODEL_ISOLATION", "NORMAL", "FUSED_CONSENSUS"],
            "network_state": ["REGIONAL_STABILITY", None, "CONFIRMED_DIVERGENCE"],
            "fault_parameters_pred_json": ["[]", "[]", '["temperature_c"]'],
        })
        diagnostics = _prediction_diagnostics(predictions, None)
        self.assertEqual(diagnostics["false_alarms"]["count"], 1)
        self.assertEqual(diagnostics["false_alarms"]["by_network_state"]["REGIONAL_STABILITY"], 1)
        self.assertEqual(diagnostics["missed_rows"]["by_true_type"]["drift"], 1)

    def test_episode_diagnostics_identify_delayed_confirmation_and_miss_reason(self):
        predictions = pd.DataFrame({
            "station_id": ["AWS-TEST-001"] * 4,
            "timestamp": pd.date_range("2025-01-01T00:00Z", periods=4, freq="h"),
            "is_anomaly_gt": [True, True, True, False],
            "fault_type_gt": ["drift", "drift", "drift", "none"],
            "is_anomaly_pred": [False, True, False, True],
            "fault_type_pred": ["none", "drift", "none", "drift"],
            "fault_parameters_pred_json": ["[]", '["temperature_c"]', "[]", '["temperature_c"]'],
            "decision_basis": ["NORMAL", "FUSED_CONSENSUS", "NORMAL", "FUSED_CONSENSUS"],
            "network_state": [None, "CONFIRMED_DIVERGENCE", None, "CONFIRMED_DIVERGENCE"],
            "station_sequence": [0, 1, 2, 3],
        })
        ledger = [
            {"episode_id": "drift-1", "station_id": "AWS-TEST-001", "fault_type": "drift",
             "parameters": '["temperature_c"]', "start_timestamp": "2025-01-01T00:00Z",
             "end_timestamp": "2025-01-01T02:00Z"},
        ]
        diagnostics = _prediction_diagnostics(predictions, ledger)["episodic_confirmation"]["drift"]
        self.assertEqual(diagnostics["matched_episode_count"], 1)
        self.assertEqual(diagnostics["matched_episodes"][0]["confirmation_delay_hours"], 1.0)
        self.assertEqual(diagnostics["missed_episode_count"], 0)

    def test_oracle_removes_only_the_matching_current_fault_reading(self):
        timestamp = pd.Timestamp("2025-01-01T00:00:00Z")
        previous = {"timestamp": timestamp - pd.Timedelta(hours=1), "temperature_c": 22.0}
        current = {"timestamp": timestamp, "temperature_c": 40.0}
        buffer = SimpleNamespace(_raw_rows=deque([previous, current]), _cache_dirty=False)
        manager = SimpleNamespace(buffers={"AWS-TEST-001": buffer})

        self.assertTrue(_remove_ground_truth_row(manager, "AWS-TEST-001", timestamp))
        self.assertEqual(list(buffer._raw_rows), [previous])
        self.assertTrue(buffer._cache_dirty)
        self.assertFalse(_remove_ground_truth_row(manager, "AWS-TEST-001", timestamp))

    def test_station_history_cache_refreshes_after_clean_reading_append(self):
        buffer = StationBuffer("AWS-TEST-001")
        self.assertTrue(buffer.raw_history_df().empty)
        buffer.record_raw_reading(
            {"temperature_c": 24.0},
            pd.Timestamp("2025-01-01T00:00:00Z"),
            {"is_anomaly": False},
        )
        refreshed = buffer.raw_history_df()
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(float(refreshed.iloc[0]["temperature_c"]), 24.0)

    def test_vectorized_oracle_features_match_sequential_clean_features(self):
        source = pd.read_csv("data/AWS-BHO-101_labeled.csv").head(48)
        source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
        source["is_anomaly"] = False
        matrix = build_feature_matrix(source)
        for position in (31, 34, 40, 47):
            prefix = source.iloc[:position + 1].drop(columns=["is_anomaly", "fault_type"], errors="ignore")
            sequential = build_features_for_latest(prefix)
            cached = matrix.iloc[position]
            for column in FEATURE_COLUMNS:
                if pd.isna(sequential[column]) and pd.isna(cached[column]):
                    continue
                if pd.isna(sequential[column]) or pd.isna(cached[column]):
                    self.fail(f"feature {column} differs at row {position}")
                self.assertAlmostEqual(float(sequential[column]), float(cached[column]), places=8,
                                       msg=f"feature {column} differs at row {position}")

    def test_labeled_fault_is_excluded_from_future_oracle_baseline(self):
        source = pd.read_csv("data/AWS-BHO-101_labeled.csv").head(55)
        source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
        source["is_anomaly"] = False
        source.loc[30, "temperature_c"] = 100.0
        source.loc[30, "is_anomaly"] = True
        masked = build_feature_matrix(source.copy())
        unmasked_source = source.drop(columns=["is_anomaly", "fault_type"], errors="ignore")
        unmasked = build_feature_matrix(unmasked_source)
        self.assertNotAlmostEqual(float(masked.loc[40, "temp_rolling_mean"]),
                                  float(unmasked.loc[40, "temp_rolling_mean"]), places=8)
        self.assertNotAlmostEqual(float(masked.loc[40, "temp_rolling_mean"]),
                                  100.0, places=2)

    def test_vectorized_cusum_matches_each_sequential_prefix(self):
        source = pd.read_csv("data/AWS-BHO-101_labeled.csv").head(64)
        source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
        source["is_anomaly"] = False
        featured = build_feature_matrix(source).drop(columns=["is_anomaly", "fault_type"], errors="ignore")
        station_id = str(source.iloc[0]["station_id"])
        for parameter, prefix in PARAM_PREFIXES.items():
            cached = _cusum_evidence_series(
                featured, prefix, parameter, station_id, RAW_HISTORY_MAXLEN_HOURS,
            )
            for position in range(len(featured)):
                start = max(0, position + 1 - RAW_HISTORY_MAXLEN_HOURS)
                sequential = _cusum_evidence(
                    featured.iloc[start:position + 1], prefix, parameter, station_id,
                )
                self.assertEqual(cached[position], sequential, f"CUSUM mismatch for {parameter} at {position}")

    def test_vectorized_cusum_resets_to_the_live_history_window(self):
        size = 800
        featured = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=size, freq="h", tz="UTC"),
            "humidity_roc_1h": [(-1.0 if i % 7 == 0 else 0.8) for i in range(size)],
            "humidity_robust_scale": [1.0] * size,
            "humidity_pct": [60.0 + (i % 3) for i in range(size)],
        })
        cached = _cusum_evidence_series(featured, "humidity", "humidity_pct", "AWS-TEST-001", 128)
        for position in (127, 128, 129, 300, 799):
            start = max(0, position + 1 - 128)
            sequential = _cusum_evidence(
                featured.iloc[start:position + 1], "humidity", "humidity_pct", "AWS-TEST-001",
            )
            self.assertEqual(cached[position], sequential, f"windowed CUSUM mismatch at {position}")


if __name__ == "__main__":
    unittest.main()
