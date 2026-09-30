
FROZEN_VARIANCE_FLOOR = None
FROZEN_RANGE_FLOOR = None
IS_ANOMALY_THRESHOLD = None
SOFT_RULE_FLOOR = None
HARD_RULE_FLOOR = None
MODEL_ONLY_THRESHOLD = None
RECOVERY_CLEAN_STREAK_REQUIRED = 3
MODEL_WEIGHT = 0.6
RULE_WEIGHT = 0.4
FUSION_ANOMALY_THRESHOLD = 50.0
MODEL_ALONE_OVERRIDE_THRESHOLD = 95.0
RULE_CONFIDENCE_BYPASS = 90.0
SPIKE_REVERSION_RATIO = 0.50
SPIKE_DEVIATION_MULTIPLIER = 1.5
RULE_BASE_CONFIDENCE = {
    "physical_bounds": 100.0,
    "dropout": 100.0,
    "frozen_value": 80.0,
    "sensor_fail_low": 95.0,
    "drift": 85.0,
    "spike": 85.0,
    "multivariate_single": 45.0,
    "multivariate_confirmed": 88.0,
}
def graduated_confidence_frozen(streak: int, req: int) -> float:
    base = RULE_BASE_CONFIDENCE["frozen_value"]
    if req <= 0: return base
    ratio = max(0.0, min(1.0, (streak - req) / req))
    return round(base + (89.5 - base) * ratio, 1)
def graduated_confidence_drift(accumulator_val: float, threshold: float, is_ewma: bool = False) -> float:
    base = RULE_BASE_CONFIDENCE["drift"]
    if threshold <= 0: return base
    ratio = max(0.0, min(1.0, (abs(accumulator_val) - threshold) / threshold))
    return round(base + (89.5 - base) * ratio, 1)
def graduated_confidence_spike(abs_dev: float, spike_threshold: float, reversion_cleanliness: float = 1.0) -> float:
    if spike_threshold <= 0: return 92.0
    dev_ratio = max(0.0, min(1.0, (abs_dev - spike_threshold) / spike_threshold))
    rev_factor = max(0.5, min(1.0, reversion_cleanliness))
    ratio = dev_ratio * rev_factor
    return round(85.0 + (95.0 - 85.0) * ratio, 1)
def graduated_confidence_fail_low(val: float, floor: float, streak: int, req: int) -> float:
    depth_ratio = 1.0 if floor == 0.0 and val <= 0.0 else (
        max(0.0, min(1.0, (floor - val) / abs(floor))) if floor != 0.0 else 0.0
    )
    streak_ratio = max(0.0, min(1.0, (streak - req) / req)) if req > 0 else 0.0
    ratio = 0.6 * depth_ratio + 0.4 * streak_ratio
    return round(92.0 + (98.0 - 92.0) * ratio, 1)
def graduated_confidence_multivariate(joint_z: float, threshold: float, confirmed: bool) -> float:
    if threshold <= 0:
        return 88.0 if confirmed else 45.0
    ratio = max(0.0, min(1.0, (joint_z - threshold) / threshold))
    if confirmed:
        return round(88.0 + (95.0 - 88.0) * ratio, 1)
    else:
        return round(45.0 + (60.0 - 45.0) * ratio, 1)
SPATIAL_CORROBORATION_MIN_PEERS = 2
SPATIAL_CORROBORATION_THRESHOLD_SIGMA = 1.5
CUSUM_DRIFT_ALLOWANCE = {
    "temperature_c": 0.05,
    "pressure_hpa": 0.02,
    "humidity_pct": 0.05
}
EWMA_DRIFT_ALPHA = 0.05
EWMA_DRIFT_THRESHOLD = 2.5
CUSUM_THRESHOLD = 6.0
CUSUM_DIRECTION_STREAK_REQUIRED = 2
DRIFT_MIN_MODEL_CORROBORATION = 0.0
FROZEN_CONSECUTIVE_REQUIRED = 5
FROZEN_CONSECUTIVE_REQUIRED_PRESSURE = 4
FROZEN_MIN_MODEL_CORROBORATION = 0.0
FROZEN_PEER_ACTIVITY_RANGE_4H_THRESHOLD = {
    "temperature_c": 1.0,
    "pressure_hpa": 1.0,
    "humidity_pct": 8.0,
}
MULTIVARIATE_TEMP_DEVIATION_THRESHOLD = 3.0
MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD = 1.5
MULTIVARIATE_PRESSURE_FLAT_THRESHOLD = 1.5
MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD = 20.0
MULTIVARIATE_PERSISTENCE_REQUIRED = 3
MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT = 1.5
MULTIVARIATE_ATTRIBUTION_DOMINANCE = 0.7
FAIL_LOW_FLOOR = {
    "temp": -8.0,
    "pressure": 150.0,
    "humidity": 3.0,
}
FAIL_LOW_CONSECUTIVE_REQUIRED = 2
WINDOW_10H_SIZE = 10
WINDOW_10H_TRIGGER = 4
WINDOW_24H_SIZE = 24
WINDOW_24H_TRIGGER = 4
SEVERITY_CRITICAL_FLOOR = 90.0
SEVERITY_HIGH_FLOOR = 70.0
SEVERITY_MEDIUM_FLOOR = 55.0
HELPER_ALERT_THRESHOLD = 0.85
FROZEN_HELPER_ALERT_THRESHOLD = 0.85
def score_to_severity(score_pct: float) -> str:
    if score_pct is None:
        return "none"
    if score_pct >= SEVERITY_CRITICAL_FLOOR:
        return "critical"
    if score_pct >= SEVERITY_HIGH_FLOOR:
        return "high"
    if score_pct >= SEVERITY_MEDIUM_FLOOR:
        return "medium"
    return "low"
from data_fetch import CLUSTERS
SPIKE_DIURNAL_MIN_PEERS = 2
SPIKE_DIURNAL_CONSENSUS_FRACTION = 0.5
SPIKE_DIURNAL_SUPPRESSION_FACTOR = 0.38
SPIKE_DIURNAL_PEER_MIN_ROC = {
    "temperature_c": 0.5,
    "pressure_hpa": 0.2,
    "humidity_pct": 1.0
}
NETWORK_MIN_ELIGIBLE_PEERS = 2
NETWORK_CORROBORATION_RATIO = 0.5
PHYSICAL_BOUNDS = {
    "temperature_c": (-50.0, 60.0),
    "pressure_hpa": (850.0, 1085.0),
    "humidity_pct": (0.0, 100.0)
}
HELPER_ALERT_THRESHOLD = 0.85
FROZEN_HELPER_ALERT_THRESHOLD = 0.85
def get_station_normal_ranges(station_id: str) -> dict:
    return {
        "temperature_c": {"normal_min": 5.0, "normal_max": 45.0},
        "pressure_hpa": {"normal_min": 950.0, "normal_max": 1050.0},
        "humidity_pct": {"normal_min": 10.0, "normal_max": 95.0}
    }
