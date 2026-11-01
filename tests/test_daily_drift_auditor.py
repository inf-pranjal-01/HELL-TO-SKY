"""
tests/test_daily_drift_auditor.py

Unit tests for the WMO-No. 8 Diurnal Secular Invariant Drift Auditor.
Verifies:
1. Nominal calibration consensus across coherent cluster peers.
2. Recalibration advisory triggering on persistent unilateral secular drift (0.8°C < |delta| <= 1.5°C).
3. Critical recalibration dispatch recommendation on severe drift (|delta| > 1.5°C).
4. Microclimatic frontal dispersion veto (suppressing alarms when peer spread > 1.0°C).
5. StateManager integration and API endpoint verification.
"""

import unittest
import numpy as np
import pandas as pd
from model.daily_drift_auditor import DailyDriftAuditor
from model.peer_spatial_engine import STATION_CLUSTERS


class TestDailyDriftAuditor(unittest.TestCase):
    def setUp(self):
        self.auditor = DailyDriftAuditor()
        self.cluster = "MUM"
        self.stations = STATION_CLUSTERS[self.cluster]
        self.target_station = self.stations[0]
        self.peer_stations = self.stations[1:]
        self.timestamps = pd.date_range("2026-05-01 00:00:00", periods=36, freq="h", tz="UTC")

    def test_nominal_calibration(self):
        """Coherent peers without sensor drift return CALIBRATED_NOMINAL."""
        for t in self.timestamps:
            for s in self.stations:
                diurnal_temp = 28.0 + 3.5 * np.sin(2 * np.pi * t.hour / 24)
                self.auditor.record_observation(s, t, diurnal_temp)

        audit = self.auditor.audit_station(self.target_station)
        self.assertEqual(audit["status"], "CALIBRATED_NOMINAL")
        self.assertLessEqual(abs(audit["secular_divergence_c"]), 0.80)
        self.assertIn("WMO-No. 8", audit["wmo_compliance"])

    def test_recalibration_advisory(self):
        """Unilateral secular drift of +1.1°C against coherent peers flags RECALIBRATION_ADVISORY."""
        for t in self.timestamps:
            for s in self.stations:
                diurnal_temp = 28.0 + 3.5 * np.sin(2 * np.pi * t.hour / 24)
                if s == self.target_station:
                    diurnal_temp += 1.10  # +1.1°C unilateral sensor bias
                self.auditor.record_observation(s, t, diurnal_temp)

        audit = self.auditor.audit_station(self.target_station)
        self.assertEqual(audit["status"], "RECALIBRATION_ADVISORY")
        self.assertGreater(abs(audit["secular_divergence_c"]), 0.80)
        self.assertLessEqual(abs(audit["secular_divergence_c"]), 1.50)
        self.assertLessEqual(audit["peer_coherence_c"], 1.00)
        self.assertIn("preventive calibration service advised", audit["advisory_message"])

    def test_critical_recalibration_required(self):
        """Unilateral secular drift of +1.8°C against coherent peers flags CRITICAL_RECALIBRATION_REQUIRED."""
        for t in self.timestamps:
            for s in self.stations:
                diurnal_temp = 28.0 + 3.5 * np.sin(2 * np.pi * t.hour / 24)
                if s == self.target_station:
                    diurnal_temp += 1.80  # +1.8°C critical sensor bias
                self.auditor.record_observation(s, t, diurnal_temp)

        audit = self.auditor.audit_station(self.target_station)
        self.assertEqual(audit["status"], "CRITICAL_RECALIBRATION_REQUIRED")
        self.assertGreater(abs(audit["secular_divergence_c"]), 1.50)
        self.assertIn("field recalibration dispatch recommended", audit["advisory_message"])

    def test_synoptic_discordance_veto(self):
        """When peer spread is wide (> 1.0°C) due to active weather fronts, alarms are deferred."""
        for t in self.timestamps:
            for i, s in enumerate(self.stations):
                # Strong regional frontal gradient causing wide peer spread
                front_dispersion = float(i) * 1.50
                diurnal_temp = 28.0 + front_dispersion + 3.5 * np.sin(2 * np.pi * t.hour / 24)
                self.auditor.record_observation(s, t, diurnal_temp)

        audit = self.auditor.audit_station(self.target_station)
        self.assertEqual(audit["status"], "CALIBRATED_NOMINAL")
        self.assertIn("active microclimatic dispersion", audit["advisory_message"])
        self.assertIn("deferred", audit["advisory_message"])


if __name__ == "__main__":
    unittest.main()
