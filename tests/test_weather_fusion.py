"""Checks that persistent evidence needs model or regional context."""

import unittest

import pandas as pd

from config import RULE_CONFIDENCE_BYPASS, graduated_confidence_drift, graduated_confidence_frozen
from model.detect import _corroborate_network, _fuse_and_score


class WeatherFusionTests(unittest.TestCase):
    def _network(self, peer_rocs):
        timestamp = pd.Timestamp("2025-01-01T12:00:00Z")
        target = {
            "station_id": "AWS-BHO-030", "timestamp": timestamp,
            "temperature_c": 20.0, "pressure_hpa": 1010.0, "humidity_pct": 50.0,
        }
        target_history = pd.DataFrame([
            {**target, "timestamp": timestamp - pd.Timedelta(hours=1)}, target,
        ])
        peers, peer_features = {}, {}
        for station_id, roc in zip(("AWS-BHO-101", "AWS-BHO-102", "AWS-BHO-103"), peer_rocs):
            peers[station_id] = pd.DataFrame([
                {
                    "station_id": station_id,
                    "timestamp": timestamp - pd.Timedelta(hours=offset),
                    "temperature_c": 20.0 - (3 - offset) * roc,
                    "pressure_hpa": 1010.0, "humidity_pct": 50.0,
                }
                for offset in (3, 2, 1, 0)
            ])
            peer_features[station_id] = pd.Series({"temp_roc_1h": roc, "temp_deviation": 0.1})
        decision = _corroborate_network(
            target, target_history, peers, "frozen_value", ["temperature_c"],
            artifact=None,
            precomputed_features=pd.Series({"temp_roc_1h": 0.0, "temp_deviation": 0.1}),
            precomputed_neighbors=peer_features,
        )
        return decision

    def test_local_frozen_and_drift_confidence_stay_below_bypass(self):
        self.assertEqual(graduated_confidence_frozen(5, 5), 80.0)
        self.assertLess(graduated_confidence_frozen(10, 5), RULE_CONFIDENCE_BYPASS)
        self.assertEqual(graduated_confidence_drift(6.0, 6.0), 85.0)
        self.assertLess(graduated_confidence_drift(100.0, 6.0), RULE_CONFIDENCE_BYPASS)

    def test_peer_agreement_vetoes_frozen_but_peer_divergence_confirms_it(self):
        frozen = {"type": "frozen_value", "parameter": "temperature_c", "confidence": 80.0}
        regional = self._network((0.05, 0.08, 0.0))
        self.assertTrue(regional["veto"])
        self.assertFalse(_fuse_and_score(10.0, [frozen])[1])
        self.assertFalse(_fuse_and_score(10.0, [])[1])

        divergent = self._network((0.8, 0.8, 0.05))
        self.assertFalse(divergent["veto"])
        confirmed = {**frozen, "confidence": frozen["confidence"] + divergent["confidence_bonus"]}
        self.assertTrue(_fuse_and_score(10.0, [confirmed])[1])


if __name__ == "__main__":
    unittest.main()
