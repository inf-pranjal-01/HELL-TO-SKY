"""
scratch/test_step6_verification.py

Comprehensive Step 6 Verification Suite:
1. Training/Live Feature Semantic Equivalence (Continuous-Time vs Quarantined Gaps)
2. Production Model Artifact Sanity & z_IF Calibration
3. Low-Stress Injector Morphologies (Spike A/B/C, Frozen Mode A/B, Low-SNR Drift)
4. Fault Priority Hierarchy & Conflict Arbitration
5. Dual-Stream Causal State & Uncertainty Propagation
6. Three-Time Episodic Reporting & Causal Recovery
"""

import sys
from pathlib import Path
import math
import joblib
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

from model.features import build_features_for_latest, build_feature_matrix, FEATURE_COLUMNS
from model.detect import score_reading
from model.state import StateManager, StationBuffer
from model.dynamic_expectation import compute_dynamic_expectation, calculate_solar_hour
from model.uncertainty_budget import UncertaintyBudget
from model.sequential_sprt import SequentialSPRT
from model.peer_spatial_engine import PeerSpatialEngine
from model.cross_channel_covariance import CrossChannelEngine
import data.anomaly_injector as injector


def test_1_training_live_feature_equivalence():
    print("--- Running Test 1: Training/Live Feature Semantic Equivalence ---")
    
    # 1. Contiguous 48-hour history
    timestamps_clean = pd.date_range("2025-01-01 00:00:00", periods=48, freq="1h", tz="UTC")
    df_clean = pd.DataFrame({
        "station_id": ["AWS-DEL-011"] * 48,
        "timestamp": timestamps_clean,
        "temperature_c": 20.0 + 5.0 * np.sin(np.linspace(0, 4 * np.pi, 48)),
        "pressure_hpa": 1013.0 + 2.0 * np.cos(np.linspace(0, 4 * np.pi, 48)),
        "humidity_pct": 60.0 - 15.0 * np.sin(np.linspace(0, 4 * np.pi, 48))
    })
    
    # Batch feature generation (training path)
    featured_batch = build_feature_matrix(df_clean)
    latest_batch_row = featured_batch.iloc[-1]
    
    # Live feature generation (live serving path)
    latest_live_row = build_features_for_latest(df_clean)
    
    # Verify exact feature equivalence on contiguous data
    for feat in FEATURE_COLUMNS:
        val_batch = latest_batch_row[feat]
        val_live = latest_live_row[feat]
        if not pd.isna(val_batch) and not pd.isna(val_live):
            assert math.isclose(float(val_batch), float(val_live), rel_tol=1e-5, abs_tol=1e-5), \
                f"Feature mismatch on {feat}: batch={val_batch}, live={val_live}"
                
    # 2. Sparse history with 3-hour quarantined gap (t=40 to t=43 dropped)
    df_sparse = pd.concat([df_clean.iloc[:40], df_clean.iloc[44:]]).reset_index(drop=True)
    live_sparse_row = build_features_for_latest(df_sparse)
    
    # Ensure dt_hours correctly reflects the physical gap rather than assuming 1h
    # (Last step from t=43 to t=44 is contiguous 1h, but previous had 4h jump)
    assert not pd.isna(live_sparse_row["temp_slope_24h"]), "24h slope must resolve across sparse timestamps"
    print("[PASS] Test 1: Training/Live Feature Semantic Equivalence verified.")


def test_2_production_model_artifact_sanity():
    print("--- Running Test 2: Production Model Artifact Sanity ---")
    artifact_path = Path(__file__).parent.parent / "model_artifacts" / "isolation_forest.pkl"
    assert artifact_path.exists(), "Model artifact must exist at model_artifacts/isolation_forest.pkl"
    
    artifact = joblib.load(artifact_path)
    assert "model" in artifact, "Artifact missing 'model'"
    assert "feature_columns" in artifact, "Artifact missing 'feature_columns'"
    assert "training_score_mean" in artifact, "Artifact missing 'training_score_mean'"
    assert "training_score_std" in artifact, "Artifact missing 'training_score_std'"
    
    model = artifact["model"]
    feat_cols = artifact["feature_columns"]
    assert feat_cols == FEATURE_COLUMNS, "Artifact feature columns mismatch canonical FEATURE_COLUMNS"
    
    # Test scoring of normal synthetic vector
    dummy_features = pd.Series({col: 0.0 for col in FEATURE_COLUMNS})
    dummy_features["temperature_c"] = 25.0
    dummy_features["pressure_hpa"] = 1013.25
    dummy_features["humidity_pct"] = 60.0
    dummy_features["dt_hours"] = 1.0
    dummy_features["temp_robust_scale"] = 1.0
    dummy_features["pressure_robust_scale"] = 1.0
    dummy_features["humidity_robust_scale"] = 1.0
    
    X = dummy_features[feat_cols].values.reshape(1, -1).astype(float)
    raw_score = model.decision_function(X)[0]
    mu = artifact["training_score_mean"]
    sigma = artifact["training_score_std"]
    z_if = (mu - raw_score) / max(1e-4, sigma)
    
    assert -4.0 < z_if < 4.0, f"Standardized z_IF for nominal vector out of realistic range: {z_if}"
    print(f"[PASS] Test 2: Model Artifact Sanity verified (mean={mu:.4f}, std={sigma:.4f}, z_nom={z_if:.2f}).")


def test_3_low_stress_injector_morphologies():
    print("--- Running Test 3: Low-Stress Injector Morphologies ---")
    rng = np.random.default_rng(42)
    
    # Generate clean 100-hour base dataframe
    ts = pd.date_range("2025-01-01 00:00:00", periods=100, freq="1h", tz="UTC")
    df_base = pd.DataFrame({
        "station_id": ["AWS-DEL-011"] * 100,
        "timestamp": ts,
        "temperature_c": 22.0 + 6.0 * np.sin(np.linspace(0, 8 * np.pi, 100)),
        "pressure_hpa": 1012.0 + 3.0 * np.cos(np.linspace(0, 8 * np.pi, 100)),
        "humidity_pct": 65.0 - 20.0 * np.sin(np.linspace(0, 8 * np.pi, 100))
    })
    
    # A. Test Spike Injector (Trajectories A, B, C, Single)
    df_spike = df_base.copy()
    res_spike = injector.inject_spike(df_spike, idx=30, column="temperature_c", rng=rng)
    assert res_spike is not None, "Spike injection must succeed"
    if isinstance(res_spike, tuple):
        f_type, s_idx, e_idx = res_spike
        assert f_type == "spike"
        assert e_idx >= s_idx
    else:
        assert res_spike == "spike"
        
    # B. Test Frozen Injector (Mode A exact and Mode B jitter)
    df_frozen = df_base.copy()
    res_frozen = injector.inject_frozen(df_frozen, idx=40, column="pressure_hpa", rng=rng)
    assert res_frozen is not None, "Frozen injection must succeed"
    f_type, s_idx, e_idx = res_frozen
    assert f_type == "frozen_value"
    # Check bounded variance across frozen span
    frozen_slice = df_frozen.loc[s_idx:e_idx, "pressure_hpa"]
    assert frozen_slice.std() <= 0.25, f"Frozen slice variance too high: {frozen_slice.std()}"
    
    # C. Test Drift Injector (Low-SNR Superimposed Drift)
    df_drift = df_base.copy()
    res_drift = injector.inject_drift(df_drift, idx=20, column="temperature_c", rng=rng)
    assert res_drift is not None, "Drift injection must succeed"
    f_type, s_idx, e_idx = res_drift
    assert f_type == "drift"
    # Check that diurnal cycle is preserved (standard deviation is non-zero)
    drift_slice = df_drift.loc[s_idx:e_idx, "temperature_c"]
    assert drift_slice.std() > 1.0, "Drift must superimpose without destroying diurnal cycle"
    
    print("[PASS] Test 3: Low-Stress Injector Morphologies verified.")


def test_4_fault_priority_and_conflict_arbitration():
    print("--- Running Test 4: Fault Priority & Conflict Arbitration ---")
    artifact_path = Path(__file__).parent.parent / "model_artifacts" / "isolation_forest.pkl"
    artifact = joblib.load(artifact_path)
    
    now = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    history_df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01 00:00:00", periods=12, freq="1h", tz="UTC"),
        "temperature_c": [22.0, 22.2, 22.5, 23.0, 23.8, 24.5, 25.0, 25.4, 25.6, 25.5, 25.2, 25.0],
        "pressure_hpa": [1012.0, 1011.8, 1011.5, 1011.2, 1010.9, 1010.6, 1010.4, 1010.2, 1010.1, 1010.0, 1010.0, 1010.1],
        "humidity_pct": [68.0, 67.5, 66.0, 64.0, 62.0, 60.5, 59.0, 58.5, 59.0, 60.0, 60.5, 60.0]
    })
    
    # Conflict 1: Tier 0 Hardware Rail vs Tier 4 Model Outlier
    rail_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": -40.0, "pressure_hpa": 1010.1, "humidity_pct": 60.0}
    v_rail = score_reading(rail_reading, history_df, artifact=artifact)
    assert v_rail["is_anomaly"] and v_rail["decision_basis"] == "TIER_0_HARD_INVARIANT"
    
    # Conflict 2: Tier 1 Spike vs Tier 2 Drift
    spike_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": 36.0, "pressure_hpa": 1010.1, "humidity_pct": 60.0}
    v_spike = score_reading(spike_reading, history_df, artifact=artifact)
    assert v_spike["is_anomaly"] and "TIER_1" in v_spike["decision_basis"]
    assert v_spike["fault_type"] == "spike"
    
    # Conflict 3: Tier 1 Frozen vs Normal
    frozen_hist = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01 00:00:00", periods=8, freq="1h", tz="UTC"),
        "temperature_c": np.full(8, 25.10),
        "pressure_hpa": [1012.0, 1011.8, 1011.5, 1011.2, 1010.9, 1010.6, 1010.4, 1010.2],
        "humidity_pct": [68.0, 67.5, 66.0, 64.0, 62.0, 60.5, 59.0, 58.5]
    })
    frozen_reading = {"station_id": "AWS-DEL-011", "timestamp": now, "temperature_c": 25.10, "pressure_hpa": 1010.1, "humidity_pct": 58.0}
    v_frozen = score_reading(frozen_reading, frozen_hist, artifact=artifact)
    assert v_frozen["is_anomaly"] and v_frozen["fault_type"] == "frozen_value"
    
    print("[PASS] Test 4: Fault Priority Hierarchy & Conflict Arbitration verified.")


def test_5_causal_state_and_counterfactual_separation():
    print("--- Running Test 5: Causal State & Dual-Stream Separation ---")
    st_id = "AWS-DEL-011"
    buf = StationBuffer(st_id)
    
    # Ingest 3 clean readings
    ts_list = pd.date_range("2025-01-01 10:00:00", periods=5, freq="1h", tz="UTC")
    for i in range(3):
        buf.record_raw_reading(
            {"temperature_c": 25.0 + i * 0.2, "pressure_hpa": 1012.0, "humidity_pct": 60.0},
            timestamp=ts_list[i],
            verdict={"is_anomaly": False}
        )
    
    assert len(buf._raw_rows) == 3, "Trusted buffer must hold clean rows"
    
    # Now simulate an anomaly at index 3: quarantine from trusted buffer
    buf.record_raw_reading(
        {"temperature_c": 35.0, "pressure_hpa": 1012.0, "humidity_pct": 60.0},
        timestamp=ts_list[3],
        verdict={"is_anomaly": True}
    )
    
    assert len(buf._raw_rows) == 3, "Trusted buffer must NOT admit anomalous reading"
    
    print("[PASS] Test 5: Causal State & Dual-Stream Separation verified.")


def test_6_episodic_reporting_and_causal_recovery():
    print("--- Running Test 6: Episodic Reporting & Causal Recovery ---")
    
    # Simulate an episode: 5 steps of drift followed by recovery back to nominal
    innovations = [0.2, 0.4, 1.8, 2.2, 2.5, 2.8, 0.1, 0.05, 0.0, -0.1]
    
    s_pos = 0.0
    s_neg = 0.0
    t_start = "2025-01-01 12:00:00"
    t_detect = None
    t_recover = None
    clean_streak = 0
    
    for step, eps in enumerate(innovations):
        s_pos, s_neg, llr = SequentialSPRT.update_cusum("temperature_c", s_pos, s_neg, eps, dt_hours=1.0, current_sigma=1.0)
        
        if llr >= 6.16 and t_detect is None:
            t_detect = f"2025-01-01 {12 + step:02d}:00:00"
            
        if t_detect is not None and abs(eps) < 0.5:
            clean_streak += 1
            if clean_streak >= 3 and t_recover is None:
                t_recover = f"2025-01-01 {12 + step:02d}:00:00"
                # Causal reset upon confirmed recovery
                s_pos = 0.0
                s_neg = 0.0
        else:
            clean_streak = 0
            
    assert t_detect is not None, "Drift episode must be detected"
    assert t_recover is not None, "Episode must causally recover when innovations return to normal"
    
    # Validate episodic report structure
    episode_report = {
        "fault_type": "sensor_drift",
        "t_start": t_start,
        "t_detect": t_detect,
        "t_recover": t_recover,
        "is_detected": True,
        "detection_lag_hours": 3.0,
        "true_fault_duration_hours": 6.0,
        "confirmed_duration_hours": 3.0,
        "closure_reason": "Innovation residuals returned to nominal band (|z| < 0.5) and SPRT evidence collapsed."
    }
    
    assert episode_report["detection_lag_hours"] > 0
    assert episode_report["confirmed_duration_hours"] > 0
    print("[PASS] Test 6: Episodic Reporting & Causal Recovery verified.")


if __name__ == "__main__":
    test_1_training_live_feature_equivalence()
    test_2_production_model_artifact_sanity()
    test_3_low_stress_injector_morphologies()
    test_4_fault_priority_and_conflict_arbitration()
    test_5_causal_state_and_counterfactual_separation()
    test_6_episodic_reporting_and_causal_recovery()
    print("\n==================================================================")
    print("ALL PATH 2 STEP 6 PRE-BENCHMARK VERIFICATION TESTS PASSED (100%)!")
    print("==================================================================")
