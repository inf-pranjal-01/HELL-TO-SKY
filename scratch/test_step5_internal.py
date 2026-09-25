"""
scratch/test_step5_internal.py

Comprehensive internal verification test suite for Path 2 architecture modules:
1. Dynamic Expectation & Solar Hour calculation
2. Uncertainty Budget (heteroskedastic decomposition)
3. Sequential SPRT (pre-whitened CUSUM with gap handling)
4. Peer Spatial Engine (robust median & distance weighting)
5. Cross-Channel Covariance & Mahalanobis Distance
6. Detector 6-Tier Fault Priority Hierarchy & Conflict Arbitration
7. Causal Event Tracking & 3-Time Distinction
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from model.dynamic_expectation import calculate_solar_hour, compute_dynamic_expectation, compute_continuous_trend_state
from model.uncertainty_budget import UncertaintyBudget, SENSOR_QUANTIZATION_FLOORS
from model.sequential_sprt import SequentialSPRT
from model.peer_spatial_engine import PeerSpatialEngine, haversine_distance_km
from model.cross_channel_covariance import CrossChannelEngine, compute_dewpoint_c
from model.detect import score_reading, SensorHealthTracker, PARAMS


def test_1_dynamic_expectation():
    print("--- Running Test 1: Dynamic Expectation & Solar Hour ---")
    ts = pd.Timestamp("2025-06-21 06:00:00", tz="UTC")
    solar_h_delhi = calculate_solar_hour(ts, "AWS-DEL-011")
    solar_h_kolkata = calculate_solar_hour(ts, "AWS-KOL-015")
    
    # Kolkata (lon ~88.4) is east of Delhi (lon ~77.2), so solar hour in Kolkata must be ahead of Delhi
    assert solar_h_kolkata > solar_h_delhi, f"Kolkata ({solar_h_kolkata:.2f}) should be ahead of Delhi ({solar_h_delhi:.2f})"
    
    # Trend decay test across 3h vs 25h gap
    trend_short = compute_continuous_trend_state(
        current_time=pd.Timestamp("2025-06-21 13:00:00", tz="UTC"),
        prior_time=pd.Timestamp("2025-06-21 10:00:00", tz="UTC"),
        prior_trend=0.0,
        prior_residual=2.0,
        tau_hours=6.0
    )
    assert trend_short > 0.5, f"Trend after 3h should be positive: {trend_short}"
    
    trend_long = compute_continuous_trend_state(
        current_time=pd.Timestamp("2025-06-22 13:00:00", tz="UTC"),
        prior_time=pd.Timestamp("2025-06-21 10:00:00", tz="UTC"),
        prior_trend=1.5,
        prior_residual=2.0,
        tau_hours=6.0
    )
    assert trend_long == 0.0, f"Trend after 27h gap must reset to 0.0: {trend_long}"
    print("[PASS] Test 1: Dynamic Expectation & Solar Hour verified.")


def test_2_uncertainty_budget():
    print("--- Running Test 2: Uncertainty Budget Decomposition ---")
    history_df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01 00:00:00", periods=48, freq="1h", tz="UTC"),
        "temperature_c": np.random.normal(25.0, 1.2, 48),
        "pressure_hpa": np.random.normal(1010.0, 0.6, 48),
        "humidity_pct": np.random.normal(60.0, 3.0, 48)
    })
    
    sigma_1h, b1 = UncertaintyBudget.compute_composite_predictive_uncertainty(
        "temperature_c", solar_hour=12.0, dt_hours=1.0, history_df=history_df, peer_dispersion=0.2
    )
    sigma_12h, b12 = UncertaintyBudget.compute_composite_predictive_uncertainty(
        "temperature_c", solar_hour=12.0, dt_hours=12.0, history_df=history_df, peer_dispersion=0.2
    )
    
    # Variance must strictly grow with gap length \Delta t
    assert sigma_12h > sigma_1h, f"12h gap uncertainty ({sigma_12h:.2f}) must exceed 1h ({sigma_1h:.2f})"
    assert b1["sigma_sensor"] == 0.10, "Sensor floor must equal 0.10C"
    
    # Reconstruction uncertainty inflation
    sigma_rec_0 = UncertaintyBudget.compute_reconstruction_uncertainty("temperature_c", 1.0, 0)
    sigma_rec_3 = UncertaintyBudget.compute_reconstruction_uncertainty("temperature_c", 1.0, 3)
    assert sigma_rec_3 > sigma_rec_0, "Reconstruction uncertainty must inflate with gap step count"
    print("[PASS] Test 2: Uncertainty Budget verified.")


def test_3_sequential_sprt():
    print("--- Running Test 3: Pre-Whitened SPRT / CUSUM ---")
    # Test pre-whitening on autocorrelated innovations
    res_t0 = 2.0
    res_t1 = 2.1
    whitened_eps = SequentialSPRT.pre_whiten_residual("temperature_c", res_t1, res_t0, dt_hours=1.0, current_sigma=1.0)
    # Autocorrelated persistence should reduce effective surprise compared to raw residual
    assert whitened_eps < res_t1, f"Pre-whitening must reduce correlated step magnitude: {whitened_eps:.2f} < {res_t1:.2f}"
    
    # CUSUM accumulation test
    s_pos, s_neg = 0.0, 0.0
    for step in range(10):
        s_pos, s_neg, llr = SequentialSPRT.update_cusum("temperature_c", s_pos, s_neg, 1.5, dt_hours=1.0, current_sigma=1.0)
    
    upper, lower = SequentialSPRT.get_wald_boundaries()
    assert s_pos > 5.0, "S+ accumulator must grow under sustained positive bias"
    assert llr > upper, f"LLR ({llr:.2f}) should cross Wald upper threshold ({upper:.2f})"
    print("[PASS] Test 3: Sequential SPRT verified.")


def test_4_peer_spatial_engine():
    print("--- Running Test 4: Peer Spatial Engine & Robust Median ---")
    dist = haversine_distance_km(28.6139, 77.2090, 28.5355, 77.3910)
    assert 15.0 < dist < 25.0, f"Delhi to Noida distance should be ~20km, got {dist:.2f}km"
    
    now = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    # Simulate 3 peers where 1 peer is corrupted/outlier
    neighbor_buffers = {
        "AWS-DEL-101": pd.DataFrame({"timestamp": [now], "temperature_c": [22.0]}),
        "AWS-DEL-102": pd.DataFrame({"timestamp": [now], "temperature_c": [22.5]}),
        "AWS-DEL-103": pd.DataFrame({"timestamp": [now], "temperature_c": [-40.0]}),  # Corrupted peer
    }
    peer_med, peer_disp, n_p = PeerSpatialEngine.compute_robust_peer_consensus(
        "AWS-DEL-011", "temperature_c", now, neighbor_buffers
    )
    assert n_p == 3, "All 3 peers should be eligible"
    # Weighted median should resist single corrupted peer (-40C) and stay near 22-22.5C
    assert 21.0 <= peer_med <= 23.0, f"Robust median corrupted by outlier peer: {peer_med}"
    print("[PASS] Test 4: Peer Spatial Engine verified.")


def test_5_cross_channel_mahalanobis():
    print("--- Running Test 5: Cross-Channel Thermodynamic Bounds & 3D Mahalanobis ---")
    # Invariant checks
    is_imp, r = CrossChannelEngine.check_physical_invariants(temp_c=25.0, pressure_hpa=1010.0, humidity_pct=105.0)
    assert is_imp, "Humidity > 100% must be flagged as physically impossible"
    
    is_imp, r = CrossChannelEngine.check_physical_invariants(temp_c=20.0, pressure_hpa=1010.0, humidity_pct=95.0)
    assert not is_imp, "Valid T/RH must pass physical invariant check"
    
    # 3D Mahalanobis distance test:
    # Correlated weather (T down, RH up): [ -2.0, 0.0, +2.0 ]
    d_sq_normal, p_norm, _ = CrossChannelEngine.compute_mahalanobis_distance(-2.0, 0.0, 2.0)
    # Physically inconsistent electronic fault (T up, RH up): [ +3.0, 0.0, +3.0 ]
    d_sq_fault, p_fault, _ = CrossChannelEngine.compute_mahalanobis_distance(3.0, 0.0, 3.0)
    
    assert d_sq_fault > d_sq_normal * 1.8, f"Inconsistent T/RH fault ({d_sq_fault:.2f}) must have much higher D^2 than normal ({d_sq_normal:.2f})"
    assert p_fault < 0.001, f"Inconsistent fault p-value ({p_fault:.4e}) must be highly significant"
    print("[PASS] Test 5: Cross-Channel Covariance verified.")


def test_6_detection_priority_hierarchy():
    print("--- Running Test 6: 6-Tier Fault Priority Hierarchy ---")
    now = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    # Realistic baseline with natural variations
    history_df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01 00:00:00", periods=12, freq="1h", tz="UTC"),
        "temperature_c": [22.0, 22.2, 22.5, 23.0, 23.8, 24.5, 25.0, 25.4, 25.6, 25.5, 25.2, 25.0],
        "pressure_hpa": [1012.0, 1011.8, 1011.5, 1011.2, 1010.9, 1010.6, 1010.4, 1010.2, 1010.1, 1010.0, 1010.0, 1010.1],
        "humidity_pct": [68.0, 67.5, 66.0, 64.0, 62.0, 60.5, 59.0, 58.5, 59.0, 60.0, 60.5, 60.0]
    })
    
    # Conflict 1: Tier 0 Hardware Rail vs Normal
    rail_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": -40.0, "pressure_hpa": 1010.1, "humidity_pct": 60.0}
    v_rail = score_reading(rail_reading, history_df, artifact={})
    assert v_rail["is_anomaly"], "Rail reading must be anomalous"
    assert v_rail["decision_basis"] == "TIER_0_HARD_INVARIANT", f"Expected Tier 0, got {v_rail['decision_basis']}"
    assert v_rail["fault_type"] == "sensor_fail_low"
    
    # Conflict 2: Tier 1 Spike vs Tier 3
    spike_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": 35.0, "pressure_hpa": 1010.0, "humidity_pct": 60.0}
    v_spike = score_reading(spike_reading, history_df, artifact={})
    assert v_spike["is_anomaly"], "Spike reading must be anomalous"
    assert "TIER_1" in v_spike["decision_basis"], f"Expected Tier 1, got {v_spike['decision_basis']}"
    assert v_spike["fault_type"] == "spike"
    
    # Conflict 3: Tier 1 Frozen Value
    frozen_hist = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01 00:00:00", periods=8, freq="1h", tz="UTC"),
        "temperature_c": np.full(8, 25.10),
        "pressure_hpa": np.full(8, 1010.0),
        "humidity_pct": np.full(8, 60.0)
    })
    frozen_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": 25.10, "pressure_hpa": 1010.0, "humidity_pct": 60.0}
    v_frozen = score_reading(frozen_reading, frozen_hist, artifact={})
    assert v_frozen["is_anomaly"], "Frozen reading must be anomalous"
    assert v_frozen["fault_type"] == "frozen_value"
    
    # Clean Reading
    clean_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": 25.1, "pressure_hpa": 1010.0, "humidity_pct": 60.0}
    v_clean = score_reading(clean_reading, history_df, artifact={})
    assert not v_clean["is_anomaly"], "Clean reading must not be anomalous"
    assert v_clean["decision_basis"] == "NORMAL"
    print("[PASS] Test 6: 6-Tier Fault Priority Hierarchy verified.")


if __name__ == "__main__":
    test_1_dynamic_expectation()
    test_2_uncertainty_budget()
    test_3_sequential_sprt()
    test_4_peer_spatial_engine()
    test_5_cross_channel_mahalanobis()
    test_6_detection_priority_hierarchy()
    print("\n=======================================================")
    print("ALL PATH 2 STEP 5 INTERNAL VERIFICATION TESTS PASSED!")
    print("=======================================================")
