import os
import sys
import pandas as pd
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.detect import score_reading
from model.features import add_temporal_features
import joblib

def reproduce_ranchi():
    print("Reproducing Ranchi False Positive for 2025-01-02 08:00 to 12:00")
    
    csv_path = os.path.join("data", "AWS-RAN-067_labeled.csv")
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return
        
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Filter for the relevant period (we need some history for rolling windows)
    # Let's get data up to 2025-01-02 12:00, starting from a few days before
    end_time = pd.to_datetime("2025-01-02 12:00:00")
    start_time = end_time - pd.Timedelta(days=5) # 5 days of history
    
    mask = (df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)
    test_df = df[mask].copy().sort_values("timestamp").reset_index(drop=True)
    
    # Load model artifact
    artifact_path = os.path.join("model_artifacts", "isolation_forest.pkl")
    if not os.path.exists(artifact_path):
        print(f"Error: Model artifact {artifact_path} not found.")
        return
        
    artifact = joblib.load(artifact_path)
    
    # Test timestamps
    target_times = [
        "2025-01-02 08:00:00",
        "2025-01-02 09:00:00",
        "2025-01-02 10:00:00",
        "2025-01-02 11:00:00",
        "2025-01-02 12:00:00",
    ]
    
    for target in target_times:
        target_dt = pd.to_datetime(target)
        # History up to this point
        hist = test_df[test_df["timestamp"] <= target_dt].copy()
        
        if len(hist) == 0:
            print(f"Not enough history for {target}, len={len(hist)}")
            continue
            
        raw_reading = hist.iloc[-1].to_dict()
        raw_reading["timestamp"] = str(raw_reading["timestamp"])
        
        # We pass history_df EXCLUDING the current reading, so the model predicts on it.
        # Wait, score_reading expects history_df to INCLUDE the reading? No, let's look at simulator.py
        # Actually in simulator.py: history_df includes the current reading at the end.
        
        feature_row = add_temporal_features(hist).iloc[-1]
        verdict = score_reading(raw_reading, hist, artifact)
        
        print(f"\n--- Timestamp: {target} ---")
        print(f"Raw Reading: T={raw_reading['temperature_c']}°C, P={raw_reading['pressure_hpa']}hPa, H={raw_reading['humidity_pct']}%")
        
        # Manually reconstruct the drift calculation steps for temp
        raw_roc = feature_row.get("temp_roc_1h")
        from model.seasonal_baseline import get_expected_roc
        expected = get_expected_roc(raw_reading["station_id"], "temp", target_dt.hour)
        scale_val = feature_row.get("temp_robust_scale")
        residual = (raw_roc - expected) / float(scale_val) if pd.notna(scale_val) and scale_val > 0 else 0
        
        print(f"[Trace] temp_roc_1h: {raw_roc:.3f}, expected_roc: {expected:.3f}, robust_scale: {scale_val:.3f}, normalized_res: {residual:.3f}")
        
        print(f"Verdict Is Anomaly: {verdict['is_anomaly']}")
        print(f"Fault Type: {verdict.get('fault_type')}")
        print(f"Model Score: {verdict.get('model_confidence_pct')}%")
        print(f"Rule Score: {verdict.get('rule_confidence_pct')}%")
        
        rules_fired = verdict.get('rules_fired', [])
        if rules_fired:
            print("Rules Fired:")
            for r in rules_fired:
                print(f"  - {r['type']} ({r['parameter']}): {r.get('confidence')}% - {r.get('reason')}")
        else:
            print("Rules Fired: None")

if __name__ == "__main__":
    reproduce_ranchi()
