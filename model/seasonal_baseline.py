
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Optional
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)
BASELINE_DATA_DIR = Path(__file__).parent.parent / "data"
FALLBACK_EXPECTED_ROC = 0.0
_cache: Dict[str, Dict[str, np.ndarray]] = {}
_PARAMS = {
    "temp":     "temperature_c",
    "pressure": "pressure_hpa",
    "humidity": "humidity_pct",
}
def _load_csv(station_id: str) -> Optional[pd.DataFrame]:
    path = BASELINE_DATA_DIR / f"{station_id}.csv"
    if not path.exists():
        logger.debug("[seasonal_baseline] No historical CSV for %s at %s", station_id, path)
        return None
    try:
        df = pd.read_csv(path, parse_dates=["timestamp"])
        return df
    except Exception as exc:
        logger.warning("[seasonal_baseline] Could not load %s: %s", path, exc)
        return None
def _build_expected_roc(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    df = df.sort_values("timestamp").copy()
    df["_hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    result: Dict[str, np.ndarray] = {}
    for prefix, col in _PARAMS.items():
        if col not in df.columns:
            result[prefix] = np.zeros(24)
            continue
        df["_roc"] = df[col].diff()
        by_hour = (
            df.dropna(subset=["_roc"])
            .groupby("_hour")["_roc"]
            .mean()
            .reindex(range(24), fill_value=0.0)
        )
        result[prefix] = by_hour.to_numpy(dtype=float)
    return result
def _ensure_loaded(station_id: str) -> None:
    if station_id in _cache:
        return
    df = _load_csv(station_id)
    if df is None:
        _cache[station_id] = {p: np.zeros(24) for p in _PARAMS}
    else:
        _cache[station_id] = _build_expected_roc(df)
        logger.info(
            "[seasonal_baseline] Loaded baseline for %s (%d rows, %d months)",
            station_id, len(df),
            max(1, round((df["timestamp"].max() - df["timestamp"].min()).days / 30))
        )
def get_expected_roc(station_id: str, param: str, hour: int) -> float:
    _ensure_loaded(station_id)
    try:
        return float(_cache[station_id][param][hour % 24])
    except (KeyError, IndexError):
        return FALLBACK_EXPECTED_ROC
def preload_all(data_dir: Optional[Path] = None) -> None:
    target = data_dir or BASELINE_DATA_DIR
    for csv_path in sorted(target.glob("AWS-*.csv")):
        if "_labeled" in csv_path.name:
            continue
        sid = csv_path.stem
        _ensure_loaded(sid)
    logger.info("[seasonal_baseline] Preloaded baselines for %d stations", len(_cache))
