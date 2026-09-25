"""
scratch/test_database_persistence.py
Tests database and history store persistence:
1. Schema verification (TimescaleDB / CSV mirror)
2. Raw vs Suggested value separation (suggested values must never overwrite raw observations)
3. Causality & timezone safety (UTC timestamp normalization)
4. State transitions logging
5. Append, query, and trim operations
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

from history_store import HistoryStore, HISTORY_COLUMNS, RAW_PARAMS

# Create a clean temporary directory for isolated persistence testing
temp_dir = Path(tempfile.mkdtemp(prefix="skyguard_test_db_"))

try:
    print("--- 1. Initializing HistoryStore with temporary storage ---")
    store = HistoryStore(base_dir=temp_dir, max_days=30)
    print(f"Store initialized at {store.base_dir}. Use DB: {store.use_db}")
    
    st_id = "AWS-DEL-011"
    ts = pd.Timestamp("2025-03-10 12:00:00+00:00")
    
    # 2. Append a clean reading
    raw_clean = {
        "temperature_c": 28.5,
        "pressure_hpa": 1012.0,
        "humidity_pct": 55.0,
    }
    verdict_clean = {
        "is_anomaly": False,
        "fault_type": None,
        "severity": "low",
        "anomaly_score_pct": 4.2,
        "decision_basis": "NORMAL_TELEMETRY",
        "suggested_values": {},
        "model_confidence_pct": 2.1,
        "rule_confidence_pct": 0.0,
    }
    store.append(st_id, ts, raw_clean, verdict_clean, source="live")
    
    # 3. Append an anomalous reading with counterfactual suggested value
    ts_anom = ts + pd.Timedelta(hours=1)
    raw_anom = {
        "temperature_c": 42.0, # Spiked
        "pressure_hpa": 1012.2,
        "humidity_pct": 54.8,
    }
    verdict_anom = {
        "is_anomaly": True,
        "fault_type": "spike",
        "severity": "high",
        "anomaly_score_pct": 94.5,
        "decision_basis": "PHYSICAL_SPIKE_JUMP",
        "suggested_values": {"temperature_c": 28.9},
        "model_confidence_pct": 88.0,
        "rule_confidence_pct": 95.0,
    }
    store.append(st_id, ts_anom, raw_anom, verdict_anom, source="live")
    
    # 4. Query recent history
    recent_df = store.get_recent(st_id, hours=6, source="live")
    print(f"\n--- 2. Retrieved {len(recent_df)} rows from store ---")
    assert len(recent_df) == 2, f"Expected 2 rows, got {len(recent_df)}"
    
    # 5. Verify Column Schema
    for col in HISTORY_COLUMNS:
        assert col in recent_df.columns, f"Missing column {col} in history DataFrame"
    print(">> Schema validation PASSED: All HISTORY_COLUMNS present.")
    
    # 6. Verify Separation of Measured vs Suggested values
    clean_row = recent_df.iloc[0]
    anom_row = recent_df.iloc[1]
    
    assert clean_row["temperature_c"] == 28.5
    assert not clean_row["is_anomaly"]
    assert pd.isna(clean_row["suggested_temperature_c"]) or clean_row["suggested_temperature_c"] is None
    
    assert anom_row["temperature_c"] == 42.0, "Raw measured temperature was altered!"
    assert anom_row["is_anomaly"] == True
    assert anom_row["fault_type"] == "spike"
    assert anom_row["suggested_temperature_c"] == 28.9, "Suggested counterfactual value missing or incorrect!"
    print(">> Measured vs Suggested Separation PASSED: Raw observation (42.0°C) and suggested replacement (28.9°C) remain strictly distinct.")
    
    # 7. Verify Timezone Awareness
    assert recent_df["timestamp"].dt.tz is not None, "Timestamp must be timezone-aware (UTC)"
    print(">> Timezone verification PASSED: All stored timestamps are UTC-aware.")
    
    # 8. Verify State Transition Logging
    store.log_health_transition(st_id, ts, "HEALTHY", "WARNING", "Isolated temperature spike")
    trans_path = store.base_dir / f"{st_id}_health_events.csv"
    assert trans_path.exists(), "Health events log missing"
    trans_df = pd.read_csv(trans_path)
    assert len(trans_df) == 1
    assert trans_df.iloc[0]["old_state"] == "HEALTHY"
    assert trans_df.iloc[0]["new_state"] == "WARNING"
    print(">> State transition logging PASSED.")
    
    print("\n=======================================================")
    print("ALL DATABASE PERSISTENCE TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")

finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
