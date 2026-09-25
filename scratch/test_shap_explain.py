"""
scratch/test_shap_explain.py
Tests SHAP explainer cache and feature attribution across the 49 canonical features.
"""
import sys
from pathlib import Path
import joblib
import pandas as pd
import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

from model.explain import ExplainerCache, FEATURE_DISPLAY_NAMES, likely_faulty_params
from model.features import FEATURE_COLUMNS

ARTIFACTS_DIR = Path(__file__).parent.parent / "model_artifacts"
artifact = joblib.load(ARTIFACTS_DIR / "isolation_forest.pkl")

print(f"Artifact features count: {len(artifact['feature_columns'])}")
assert len(artifact["feature_columns"]) == 49, "Expected 49 features in artifact"

explainer_cache = ExplainerCache(artifact)

# Create a sample feature row with 49 features
feature_data = {col: 0.0 for col in FEATURE_COLUMNS}
feature_data["temperature_c"] = 38.5
feature_data["temp_deviation"] = 12.0
feature_data["temp_roc_1h"] = 8.5
feature_data["pressure_hpa"] = 1012.0
feature_data["humidity_pct"] = 55.0

sample_row = pd.Series(feature_data)

res = explainer_cache.explain(sample_row)

print("\nExplanation Result:")
print(f"  Method: {res['method']}")
print(f"  Features count: {len(res['features'])}")

print("\nTop 5 contributing features:")
for feat in res["features"][:5]:
    print(f"  - {feat['name']} ({feat['column']}): {feat['impact']}")

likely = likely_faulty_params(res["features"], top_n=3)
print(f"\nLikely faulty sensors: {likely}")
assert "temperature_c" in likely, f"Expected temperature_c in likely faulty sensors, got {likely}"

print("\n>> SHAP Explainer Verification PASSED!")
