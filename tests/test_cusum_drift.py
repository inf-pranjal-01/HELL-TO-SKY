import unittest
from collections import deque
import sys
import os

# Ensure we can import from model
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.detect import _cusum_evidence
from config import CUSUM_DRIFT_THRESHOLD

class TestCusumDrift(unittest.TestCase):
    def test_positive_drift(self):
        # Simulated continuous positive residual
        s_pos, s_neg, drift_streak = 0.0, 0.0, 0
        
        # Add positive residuals for 10 periods
        for _ in range(10):
            s_pos, s_neg, drift_streak, fired, score, reason = _cusum_evidence(
                residual=1.5,
                s_pos=s_pos,
                s_neg=s_neg,
                drift_streak=drift_streak,
                allowance=0.5,
                threshold=CUSUM_DRIFT_THRESHOLD
            )
            
        self.assertTrue(s_pos > CUSUM_DRIFT_THRESHOLD, "CUSUM should accumulate past threshold")
        self.assertTrue(fired, "Drift rule should fire")
        self.assertTrue(drift_streak > 0, "Streak should be positive")

    def test_instant_reset_fix(self):
        # Build up drift
        s_pos = CUSUM_DRIFT_THRESHOLD - 1.0
        s_neg = 0.0
        drift_streak = 5
        
        # One noisy opposite sign residual
        s_pos, s_neg, drift_streak, fired, score, reason = _cusum_evidence(
            residual=-1.5,
            s_pos=s_pos,
            s_neg=s_neg,
            drift_streak=drift_streak,
            allowance=0.5,
            threshold=CUSUM_DRIFT_THRESHOLD
        )
        
        # Instant reset bug would make s_pos = 0.0. The fix clamps the deduction.
        self.assertTrue(s_pos > 0.0, "CUSUM should not instantly reset on single noisy reading")

if __name__ == '__main__':
    unittest.main()
