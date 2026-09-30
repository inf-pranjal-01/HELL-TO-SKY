
import numpy as np
import pandas as pd
from pathlib import Path
DATA_DIR = Path(__file__).parent.parent / "data"
ROLLING_WINDOW_HOURS = "48h"
ROLLING_MIN_PERIODS = 6
VOLATILITY_BASELINE_WINDOW_HOURS = 24 * 30
ROC_SHORT_HOURS = 1
ROC_LONG_HOURS = 3
RAW_COLUMNS = ["temperature_c", "pressure_hpa", "humidity_pct"]
FEATURE_COLUMNS = [
    "temperature_c", "pressure_hpa", "humidity_pct",
    "temp_deviation", "pressure_deviation", "humidity_deviation",
    "temp_roc_1h", "pressure_roc_1h", "humidity_roc_1h",
    "temp_roc_3h", "pressure_roc_3h", "humidity_roc_3h",
    "temp_volatility_z", "pressure_volatility_z", "humidity_volatility_z",
    "dewpoint_depression_c", "vapor_pressure_deficit_kpa",
    "hour_sin", "hour_cos", "doy_sin", "doy_cos",
    "dt_hours",
    "temp_robust_scale", "pressure_robust_scale", "humidity_robust_scale",
    "temp_hours_since_valid", "pressure_hours_since_valid", "humidity_hours_since_valid",
    "temp_range_1h", "pressure_range_1h", "humidity_range_1h",
    "temp_range_3h", "pressure_range_3h", "humidity_range_3h",
    "temp_range_6h", "pressure_range_6h", "humidity_range_6h",
    "temp_range_24h", "pressure_range_24h", "humidity_range_24h",
    "temp_slope_6h", "pressure_slope_6h", "humidity_slope_6h",
    "temp_slope_24h", "pressure_slope_24h", "humidity_slope_24h",
    "temp_same_hour_res", "pressure_same_hour_res", "humidity_same_hour_res",
]
RULE_ONLY_PREFIXES = [
    ("temperature_c", "temp"),
    ("pressure_hpa", "pressure"),
    ("humidity_pct", "humidity"),
]
DRIFT_LOOKBACK_HOURS = 720
def _compute_time_offset_slope(df_station: pd.DataFrame, col: str, target_offset_hours: float):
    ts = pd.to_datetime(df_station["timestamp"], utc=True)
    vals = pd.to_numeric(df_station[col], errors="coerce")
    df_lookup = pd.DataFrame({"target_time": ts - pd.to_timedelta(target_offset_hours, unit="h"), "orig_ts": ts, "orig_val": vals})
    df_source = pd.DataFrame({"target_time": ts, "past_val": vals, "past_ts": ts}).sort_values("target_time")
    merged = pd.merge_asof(
        df_lookup.sort_values("target_time"),
        df_source,
        on="target_time",
        direction="backward",
        tolerance=pd.to_timedelta(max(1.5, target_offset_hours * 0.75), unit="h")
    ).sort_values("orig_ts")
    actual_dt_hours = (merged["orig_ts"] - merged["past_ts"]).dt.total_seconds() / 3600.0
    val_diff = merged["orig_val"] - merged["past_val"]
    slope = val_diff / actual_dt_hours.replace(0, np.nan)
    return slope.values, val_diff.values
def _rolling_baseline(series: pd.Series, exclude_mask: pd.Series = None):
    clean_series = series.mask(exclude_mask) if exclude_mask is not None else series
    prior = clean_series.shift(1)
    roll = prior.rolling(ROLLING_WINDOW_HOURS, min_periods=ROLLING_MIN_PERIODS)
    import numpy as np
    mad = prior.rolling(ROLLING_WINDOW_HOURS, min_periods=ROLLING_MIN_PERIODS).apply(
        lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))), raw=True
    )
    return roll.mean(), roll.std(), mad
def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").set_index("timestamp", drop=False)
    exclude_mask = df["is_anomaly"].fillna(False).astype(bool) if "is_anomaly" in df.columns else None
    for col, prefix in [("temperature_c", "temp"), ("pressure_hpa", "pressure"), ("humidity_pct", "humidity")]:
        values = pd.to_numeric(df[col], errors="coerce")
        df[col] = values
        mean, std, mad = _rolling_baseline(values, exclude_mask)
        robust_scale = 1.4826 * mad
        safe_scale = robust_scale.replace(0, np.nan)
        df[f"{prefix}_deviation"] = (values - mean) / safe_scale
        clean_values = values.mask(exclude_mask) if exclude_mask is not None else values
        df[f"{prefix}_rolling_std"] = std
        df[f"{prefix}_rolling_mad"] = mad
        df[f"{prefix}_robust_scale"] = robust_scale
        df[f"{prefix}_rolling_mean"] = mean
        df[f"{prefix}_rolling_mean_3h"] = values.shift(1).rolling("3h", min_periods=1).mean()
        df[f"{prefix}_rolling_mean_24h"] = clean_values.shift(1).rolling("24h", min_periods=6).mean()
        df["dt_hours"] = df.index.to_series().diff().dt.total_seconds() / 3600.0
        valid_times = df.index.to_series()[values.notna()]
        last_valid = valid_times.reindex(df.index, method='ffill')
        df[f"{prefix}_hours_since_valid"] = (df.index.to_series() - last_valid).dt.total_seconds() / 3600.0
        for w in ["1h", "3h", "6h", "24h"]:
            df[f"{prefix}_range_{w}"] = values.rolling(w, min_periods=1).max() - values.rolling(w, min_periods=1).min()
        long_baseline = std.rolling("720h", min_periods=ROLLING_MIN_PERIODS).median()
        long_spread = std.rolling("720h", min_periods=ROLLING_MIN_PERIODS).std()
        df[f"{prefix}_volatility_z"] = (std - long_baseline) / long_spread.replace(0, np.nan)
        safe_dt = df["dt_hours"].replace(0, np.nan)
        roc_per_hour = values.diff() / safe_dt
        df[f"{prefix}_roc_1h"] = roc_per_hour
        slope_3h, _ = _compute_time_offset_slope(df, col, ROC_LONG_HOURS)
        df[f"{prefix}_roc_3h"] = slope_3h
        slope_6h, _ = _compute_time_offset_slope(df, col, 6.0)
        df[f"{prefix}_slope_6h"] = slope_6h
        slope_24h, diff_24h = _compute_time_offset_slope(df, col, 24.0)
        df[f"{prefix}_slope_24h"] = slope_24h
        df[f"{prefix}_same_hour_res"] = diff_24h
        df[f"{prefix}_normalized_roc_1h"] = df[f"{prefix}_roc_1h"] / safe_scale
    df["warm_up_complete"] = df["temp_rolling_std"].notna()
    return df.reset_index(drop=True)
def saturation_vapor_pressure_kpa(temp_c):
    exponent = (17.67 * temp_c) / (temp_c + 243.5)
    return 0.6112 * np.exp(np.clip(exponent, -100, 100))
def add_cross_parameter_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("timestamp").reset_index(drop=True)
    temp_c = pd.to_numeric(df["temperature_c"], errors="coerce")
    humidity_pct = pd.to_numeric(df["humidity_pct"], errors="coerce").clip(lower=0.01, upper=100.0)
    gamma = (17.67 * temp_c) / (243.5 + temp_c) + np.log(humidity_pct / 100.0)
    dew_point_c = (243.5 * gamma) / (17.67 - gamma)
    df["dewpoint_depression_c"] = temp_c - dew_point_c
    es_now = saturation_vapor_pressure_kpa(temp_c)
    df["vapor_pressure_deficit_kpa"] = es_now * (1 - humidity_pct / 100.0)
    return df
def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    hour = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    doy = df["timestamp"].dt.dayofyear
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return df
def add_rule_only_signals(df: pd.DataFrame) -> pd.DataFrame:
    from config import FROZEN_CONSECUTIVE_REQUIRED, FROZEN_CONSECUTIVE_REQUIRED_PRESSURE
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col, prefix in RULE_ONLY_PREFIXES:
        df[f"{prefix}_consec_diff"] = df[col].diff(1).abs()
        df[f"{prefix}_{DRIFT_LOOKBACK_HOURS}h_delta"] = df[col] - df[col].shift(DRIFT_LOOKBACK_HOURS)
        req = 4
        std_window = df[col].rolling(req, min_periods=req).std()
        threshold = 0.055 if prefix != "humidity" else 0.05
        is_frozen = (std_window <= threshold).fillna(False)
        run_id = is_frozen.ne(is_frozen.shift()).cumsum()
        streak = is_frozen.groupby(run_id).cumcount() + 1
        streak = streak + (req - 1)
        streak = streak.where(is_frozen, 0)
        df[f"{prefix}_frozen_streak"] = streak
        df[f"{prefix}_floor_frozen_match"] = is_frozen
    return df
def get_threshold(thresholds: dict, rule_type: str, prefix: str, station_id: str) -> float:
    per_station = thresholds[rule_type][prefix]
    return per_station.get(station_id, per_station["__global__"])
def calibrate_rule_thresholds(featured_clean: pd.DataFrame) -> dict:
    MIN_ROWS_FOR_PER_STATION = 200
    thresholds = {"roc_small": {}, "spike": {}}
    def _calibrate(
        rule_key: str,
        value_fn,
        quantile: float,
        per_station: bool = True,
    ):
        per_station_vals = {}
        if per_station:
            for station_id, group in featured_clean.groupby("station_id"):
                vals = value_fn(group)
                if len(vals) >= MIN_ROWS_FOR_PER_STATION:
                    per_station_vals[station_id] = float(
                        vals.quantile(quantile)
                    )
        global_val = float(
            value_fn(featured_clean).quantile(quantile)
        )
        thresholds[rule_key][prefix] = {
            "__global__": global_val,
            **per_station_vals,
        }
    for _, prefix in RULE_ONLY_PREFIXES:
        roc_col = f"{prefix}_roc_1h"
        dev_col = f"{prefix}_deviation"
        _calibrate(
            "roc_small",
            lambda g: g[roc_col].abs(),
            0.20,
        )
        _calibrate(
            "spike",
            lambda g: g[dev_col].abs(),
            0.99999,
            per_station=False,
        )
    return thresholds
def build_features_for_history(history_df: pd.DataFrame) -> pd.DataFrame:
    df = add_temporal_features(history_df)
    df = add_cross_parameter_features(df)
    df = add_time_features(df)
    df = add_rule_only_signals(df)
    return df
def build_features_for_latest(history_df: pd.DataFrame) -> pd.Series:
    return build_features_for_history(history_df).iloc[-1]
def build_rule_signals_recent(history_df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    df = history_df.sort_values("timestamp").reset_index(drop=True)
    df = add_rule_only_signals(df)
    return df.tail(n)
def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in df.columns:
        raise ValueError("Expected a 'timestamp' column -- did you pass the raw fetched/validated CSV?")
    missing_raw = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing_raw:
        raise ValueError(f"Missing expected raw columns: {missing_raw}")
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    per_station_frames = []
    for station_id, group in df.groupby("station_id", sort=False):
        group = add_temporal_features(group)
        group = add_cross_parameter_features(group)
        group = add_time_features(group)
        group = add_rule_only_signals(group)
        per_station_frames.append(group)
    df = pd.concat(per_station_frames, ignore_index=True)
    return df
def main():
    stations_path = DATA_DIR / "all_stations.csv"
    if not stations_path.exists():
        print(f"Expected {stations_path.name} in {DATA_DIR} "
              f"(output of data_fetch.py -> validate_data.py). Run that first.")
        return
    df = pd.read_csv(stations_path, parse_dates=["timestamp"])
    if "is_anomaly" in df.columns:
        print("NOTE: input already has is_anomaly/fault_type columns (looks like a "
              "_labeled.csv). That's fine for testing detect.py against known faults, "
              "but train.py must fit only on a RAW un-injected file.\n")
    featured = build_feature_matrix(df)
    n_total = len(featured)
    n_ready = featured[FEATURE_COLUMNS].notna().all(axis=1).sum()
    print(f"Built {len(FEATURE_COLUMNS)} model features for {n_total} rows across "
          f"{df['station_id'].nunique()} stations.")
    print(f"{n_ready}/{n_total} rows have a complete feature vector (no NaNs from "
          f"rolling-window warm-up); the rest are the first ~{ROLLING_WINDOW_HOURS}h "
          f"of each station's history and should be dropped before training.\n")
    sample_cols = ["station_id", "timestamp", "temperature_c", "temp_deviation",
                   "temp_floor_frozen_match",
                   "temp_normalized_roc_1h", "temp_consec_diff",
                   "vapor_pressure_consistency_dev", "dewpoint_depression_c"]
    print("Sample rows:")
    print(featured[sample_cols].dropna().head(5).to_string(index=False))
    output_path = DATA_DIR / "all_stations_features.csv"
    featured.to_csv(output_path, index=False)
    print(f"\nSaved full feature matrix -> {output_path}")
if __name__ == "__main__":
    main()
