import unittest
import sys
import os

# Ensure we can import from model
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.detect import _rule_checks
from config import (
    PHYSICAL_LIMITS, SPIKE_THRESHOLDS_STD, FROZEN_THRESHOLDS_MIN_PERIODS, FROZEN_THRESHOLDS_STD_MAX
)

class TestRuleBoundaries(unittest.TestCase):
    def test_physical_limits(self):
        history_df = None # Doesn't matter for physical bounds if not used
        
        # Test just below threshold
        raw_reading = {"temperature_c": PHYSICAL_LIMITS["temperature_c"][1] - 0.1}
        rules = _rule_checks(raw_reading, {}, {}, history_df=None)
        self.assertFalse(any(r["type"] == "physical_bounds" for r in rules["fired"]))
        
        # Test just above threshold
        raw_reading = {"temperature_c": PHYSICAL_LIMITS["temperature_c"][1] + 0.1}
        rules = _rule_checks(raw_reading, {}, {}, history_df=None)
        self.assertTrue(any(r["type"] == "physical_bounds" for r in rules["fired"]))

if __name__ == '__main__':
    unittest.main()
