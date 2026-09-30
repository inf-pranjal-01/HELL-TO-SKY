
import numpy as np
import pandas as pd
from pathlib import Path
import argparse
import json
DATA_DIR = Path(__file__).parent
INJECTION_RATE = 0.05
ANOMALY_DENSITY_MULTIPLIER = 2.5
RANDOM_SEED = 45456231412727229999
FAIL_LOW_LENGTH = 3
def compute_bounds(series: pd.Series, z_thresh: float = 3.0):
    mean = series.mean()
    std = series.std()
    return mean, std, mean + z_thresh * std, mean - z_thresh * std
HARD_PHYSICAL_LIMITS = {
    "temperature_c": (-50.0, 60.0),
    "humidity_pct": (0.0, 100.0),
    "pressure_hpa": (850.0, 1085.0),
}
ADC_NOISE_FLOOR_STD = {
    "temperature_c": 0.05,
    "pressure_hpa": 0.03,
    "humidity_pct": 0.05,
}
FROZEN_MAX_DEVIATION = {
    "temperature_c": 0.3,
    "pressure_hpa": 0.2,
    "humidity_pct": 0.4,
}
FAIL_LOW_RAIL_VALUE = {
    "temperature_c": -40.0,
    "pressure_hpa": 0.0,
    "humidity_pct": 0.0,
}
FAIL_LOW_NOISE_STD = 0.05
def saturation_vapor_pressure_kpa(temp_c):
    return 0.6112 * np.exp((17.67 * temp_c) / (temp_c + 243.5))
def clip_to_physical_limits(df: pd.DataFrame, column: str, start_idx: int, end_idx: int):
    if column in HARD_PHYSICAL_LIMITS:
        low, high = HARD_PHYSICAL_LIMITS[column]
        df.loc[start_idx:end_idx, column] = df.loc[start_idx:end_idx, column].clip(low, high)
def spans_overlap(a_start, a_end, b_start, b_end):
    return not (a_end < b_start or a_start > b_end)
def has_overlap(claimed_spans, cols, start, end):
    return any(
        spans_overlap(start, end, claimed_start, claimed_end)
        for col in cols
        for claimed_start, claimed_end in claimed_spans.get(col, [])
    )
def inject_spike(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    mean, std, upper, lower = compute_bounds(df[column])
    low, high = HARD_PHYSICAL_LIMITS.get(column, (-np.inf, np.inf))
    obs_floor = {"temperature_c": 0.10, "pressure_hpa": 1.00, "humidity_pct": 1.00}.get(column, 0.50)
    magnitude = rng.uniform(3.0, 4.5)
    sign = float(rng.choice([-1.0, 1.0]))
    delta0 = sign * magnitude * max(std, 2.5 * obs_floor)
    subtype = rng.choice(["single", "trajectory_a", "trajectory_b", "trajectory_c"], p=[0.25, 0.25, 0.25, 0.25])
    if subtype == "single":
        cand = float(df.loc[idx, column]) + delta0
        if not (low <= cand <= high):
            return None
        df.loc[idx, column] = cand
        return "spike"
    elif subtype == "trajectory_a":
        tail_len = int(rng.integers(2, 5))
        end_idx = min(idx + tail_len, len(df) - 1)
        n_steps = end_idx - idx + 1
        baseline = df.loc[idx:end_idx, column].to_numpy(dtype=float)
        t = np.arange(n_steps)
        offset = delta0 * (1.0 + 0.3 * t)
        vals = baseline + offset
        if not (low <= vals[0] <= high):
            return None
        df.loc[idx:end_idx, column] = np.clip(vals, low, high)
        return "spike", idx, end_idx
    elif subtype == "trajectory_b":
        tail_len = int(rng.integers(3, 6))
        end_idx = min(idx + tail_len, len(df) - 1)
        n_steps = end_idx - idx + 1
        baseline = df.loc[idx:end_idx, column].to_numpy(dtype=float)
        vals = baseline + delta0
        if not (low <= vals[0] <= high):
            return None
        df.loc[idx:end_idx, column] = np.clip(vals, low, high)
        return "spike", idx, end_idx
    else:
        tail_len = int(rng.integers(2, 5))
        end_idx = min(idx + tail_len, len(df) - 1)
        n_steps = end_idx - idx + 1
        tau = rng.uniform(0.7, 1.8)
        baseline = df.loc[idx:end_idx, column].to_numpy(dtype=float)
        t = np.arange(n_steps)
        decayed = baseline + delta0 * np.exp(-t / tau)
        if not (low <= decayed[0] <= high):
            return None
        df.loc[idx:end_idx, column] = np.clip(decayed, low, high)
        return "spike", idx, end_idx
def inject_frozen(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    freeze_length = rng.integers(5, 9)
    end_idx = min(idx + freeze_length, len(df) - 1)
    n_steps = end_idx - idx + 1
    anchor = float(df.loc[idx, column])
    mode = rng.choice(["mode_a_exact", "mode_b_jitter"], p=[0.4, 0.6])
    if mode == "mode_a_exact":
        df.loc[idx:end_idx, column] = anchor
    else:
        noise_std = ADC_NOISE_FLOOR_STD[column]
        max_dev = FROZEN_MAX_DEVIATION[column]
        walk = np.cumsum(rng.normal(0, noise_std, n_steps))
        walk = np.clip(walk, -max_dev, max_dev)
        walk[0] = 0.0
        df.loc[idx:end_idx, column] = anchor + walk
    clip_to_physical_limits(df, column, idx, end_idx)
    return "frozen_value", idx, end_idx
def inject_drift(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    drift_length = rng.integers(20, 50)
    end_idx = min(idx + drift_length, len(df) - 1)
    direction = rng.choice([-1.0, 1.0])
    param_std = min(float(df[column].std()), 3.0 if column == "temperature_c" else 5.0)
    max_offset = param_std * rng.uniform(2.5, 4.5)
    steps = end_idx - idx + 1
    if rng.choice([True, False]):
        ramp = np.linspace(0, max_offset, steps)
    else:
        ramp = max_offset * (np.linspace(0, 1, steps) ** rng.uniform(1.3, 2.0))
    min_step = max(df[column].std() * 1e-4, 1e-6)
    ramp = np.maximum.accumulate(ramp + np.arange(steps) * min_step)
    natural_values = df.loc[idx:end_idx, column].to_numpy(dtype=float)
    df.loc[idx:end_idx, column] = natural_values + direction * ramp
    clip_to_physical_limits(df, column, idx, end_idx)
    return "drift", idx, end_idx
def inject_dropout(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    df.loc[idx, column] = np.nan
    return "dropout"
def inject_fail_low(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    end_idx = min(idx + FAIL_LOW_LENGTH, len(df) - 1)
    n_steps = end_idx - idx + 1
    rail_value = FAIL_LOW_RAIL_VALUE[column]
    noise = rng.normal(0, FAIL_LOW_NOISE_STD, n_steps)
    df.loc[idx:end_idx, column] = rail_value + noise
    return "sensor_fail_low", idx, end_idx
def inject_multivariate(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    window = rng.integers(2, 5)
    end_idx = min(idx + window, len(df) - 1)
    n_steps = end_idx - idx + 1
    temp_std = min(float(df["temperature_c"].std()), 3.0)
    pressure_std = min(float(df["pressure_hpa"].std()), 4.0)
    temp_before = df.loc[idx:end_idx, "temperature_c"].to_numpy(dtype=float)
    rh_before = df.loc[idx:end_idx, "humidity_pct"].to_numpy(dtype=float)
    temp_delta = rng.uniform(2.2, 3.5) * temp_std
    temp_after = np.clip(temp_before + temp_delta, -5.0, 48.0)
    es_before = saturation_vapor_pressure_kpa(temp_before)
    es_after = saturation_vapor_pressure_kpa(temp_after)
    rh_physically_consistent = np.clip(rh_before * (es_before / es_after), 0.0, 100.0)
    physically_expected_drop = rh_before - rh_physically_consistent
    fault_rh_rise = np.maximum(physically_expected_drop, 0.5) * rng.uniform(1.5, 2.5)
    rh_after = rh_before + fault_rh_rise
    df.loc[idx:end_idx, "temperature_c"] = temp_after
    df.loc[idx:end_idx, "humidity_pct"] = rh_after
    df.loc[idx:end_idx, "pressure_hpa"] += rng.normal(0, pressure_std * 0.1, n_steps)
    clip_to_physical_limits(df, "temperature_c", idx, end_idx)
    clip_to_physical_limits(df, "humidity_pct", idx, end_idx)
    clip_to_physical_limits(df, "pressure_hpa", idx, end_idx)
    return "multivariate_inconsistency", idx, end_idx
def inject_unstructured_anomaly(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    window = rng.integers(3, 8)
    end_idx = min(idx + window, len(df) - 1)
    n_steps = end_idx - idx + 1
    t_std = min(float(df["temperature_c"].std()), 3.0)
    p_std = min(float(df["pressure_hpa"].std()), 4.0)
    h_std = min(float(df["humidity_pct"].std()), 8.0)
    sign_t = rng.choice([-1.0, 1.0], size=n_steps)
    sign_p = -sign_t
    sign_h = rng.choice([-1.0, 1.0], size=n_steps)
    t_pert = sign_t * rng.uniform(1.8, 2.4, size=n_steps) * t_std
    p_pert = sign_p * rng.uniform(1.6, 2.2, size=n_steps) * p_std
    h_pert = sign_h * rng.uniform(1.8, 2.4, size=n_steps) * h_std
    df.loc[idx:end_idx, "temperature_c"] += t_pert
    df.loc[idx:end_idx, "pressure_hpa"] += p_pert
    df.loc[idx:end_idx, "humidity_pct"] += h_pert
    df.loc[idx:end_idx, "temperature_c"] = df.loc[idx:end_idx, "temperature_c"].clip(5.0, 45.0)
    df.loc[idx:end_idx, "pressure_hpa"] = df.loc[idx:end_idx, "pressure_hpa"].clip(920.0, 1040.0)
    df.loc[idx:end_idx, "humidity_pct"] = df.loc[idx:end_idx, "humidity_pct"].clip(15.0, 95.0)
    return "unstructured_anomaly", idx, end_idx
FAULT_MAX_LEN = {
    inject_spike: 1,
    inject_frozen: 8,
    inject_drift: 49,
    inject_dropout: 1,
    inject_multivariate: 4,
    inject_fail_low: FAIL_LOW_LENGTH,
    inject_unstructured_anomaly: 8,
}
MULTI_COLUMN_FAULTS = {inject_multivariate}
FAULT_WEIGHTS = {
    inject_spike: 2.5,
    inject_dropout: 3.0,
    inject_frozen: 2.5,
    inject_fail_low: 1.5,
    inject_drift: 1.5,
    inject_multivariate: 1.5,
}
MIN_EVENTS_PER_TYPE = 4
def _affected_parameters(fault_fn, sampled_column: str) -> list[str]:
    if fault_fn is inject_multivariate:
        return ["temperature_c", "humidity_pct", "pressure_hpa"]
    if fault_fn is inject_unstructured_anomaly:
        return ["temperature_c", "pressure_hpa", "humidity_pct"]
    return [sampled_column]
def inject_anomalies(
    df: pd.DataFrame,
    seed: int = RANDOM_SEED,
    *,
    return_events: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    if ANOMALY_DENSITY_MULTIPLIER < 0:
        raise ValueError("ANOMALY_DENSITY_MULTIPLIER must be zero or positive")
    df = df.copy().reset_index(drop=True)
    df["is_anomaly"] = False
    df["fault_type"] = None
    columns = ["temperature_c", "pressure_hpa", "humidity_pct"]
    df[columns] = df[columns].astype(float)
    n_rows = len(df)
    target_anomalous_rows = int(n_rows * INJECTION_RATE * ANOMALY_DENSITY_MULTIPLIER)
    fault_functions = [
        inject_spike, inject_frozen, inject_drift,
        inject_dropout, inject_multivariate, inject_fail_low,
        inject_unstructured_anomaly,
    ]
    claimed_spans = {col: [] for col in columns}
    fault_counts = {fn: 0 for fn in fault_functions}
    rows_injected = 0
    station_id = str(df["station_id"].iloc[0]) if "station_id" in df.columns and len(df) else "unknown"
    events = []
    def try_inject(fault_fn, attempts_budget):
        nonlocal rows_injected
        attempts = 0
        while attempts < attempts_budget:
            attempts += 1
            idx = int(rng.integers(10, n_rows - 60))
            column = rng.choice(columns)
            cols_needed = _affected_parameters(fault_fn, column)
            candidate_end = min(idx + FAULT_MAX_LEN[fault_fn], n_rows - 1)
            if has_overlap(claimed_spans, cols_needed, idx, candidate_end):
                continue
            result = fault_fn(df, idx, column, rng)
            if result is None:
                continue
            if isinstance(result, tuple) and len(result) == 3:
                fault_type, start, end = result
            else:
                fault_type = result
                start = end = idx
            df.loc[start:end, "is_anomaly"] = True
            df.loc[start:end, "fault_type"] = fault_type
            event_number = len(events) + 1
            timestamp_start = df.loc[start, "timestamp"] if "timestamp" in df.columns else None
            timestamp_end = df.loc[end, "timestamp"] if "timestamp" in df.columns else None
            events.append({
                "episode_id": f"{station_id}:{seed}:{event_number:04d}",
                "station_id": station_id,
                "fault_type": fault_type,
                "parameters": cols_needed,
                "start_index": int(start),
                "end_index": int(end),
                "start_timestamp": timestamp_start,
                "end_timestamp": timestamp_end,
                "seed": int(seed),
            })
            for col in cols_needed:
                claimed_spans[col].append((start, end))
            rows_injected += (end - start + 1)
            fault_counts[fault_fn] += 1
            return True
        return False
    scaled_min_events = (
        0 if ANOMALY_DENSITY_MULTIPLIER == 0
        else max(1, round(MIN_EVENTS_PER_TYPE * ANOMALY_DENSITY_MULTIPLIER))
    )
    for fault_fn in fault_functions:
        placed = 0
        while placed < scaled_min_events:
            if not try_inject(fault_fn, attempts_budget=n_rows):
                break
            placed += 1
    weight_fns = list(FAULT_WEIGHTS.keys())
    weight_probs = np.array([FAULT_WEIGHTS[fn] for fn in weight_fns])
    weight_probs = weight_probs / weight_probs.sum()
    max_total_attempts = n_rows * 3
    total_attempts = 0
    while rows_injected < target_anomalous_rows and total_attempts < max_total_attempts:
        total_attempts += 1
        fault_fn = weight_fns[rng.choice(len(weight_fns), p=weight_probs)]
        try_inject(fault_fn, attempts_budget=1)
    if return_events:
        return df, pd.DataFrame(events, columns=[
            "episode_id", "station_id", "fault_type", "parameters",
            "start_index", "end_index", "start_timestamp", "end_timestamp", "seed",
        ])
    return df
def main(output_dir: Path | None = None, seed: int = RANDOM_SEED):
    output_dir = Path(output_dir) if output_dir is not None else (
        Path(__file__).resolve().parent.parent / "evaluation" / "generated_replays" / f"seed_{seed}"
    )
    if output_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite generated replay directory: {output_dir}. "
            "Choose a new --output-dir."
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    print(
        "Injection density multiplier: "
        f"{ANOMALY_DENSITY_MULTIPLIER:g} "
        f"(base rate {INJECTION_RATE:.1%}; effective target "
        f"{INJECTION_RATE * ANOMALY_DENSITY_MULTIPLIER:.1%})\n"
    )
    station_files = sorted(
        p for p in DATA_DIR.glob("AWS-*.csv") if "_labeled" not in p.name
    )
    if len(station_files) < 7:
        print(f"Only {len(station_files)} station CSVs found -- check DATA_DIR / that data_fetch.py has run.")
    CENTER_STATION_IDS = {
        "AWS-DEL-011", "AWS-CHN-024", "AWS-MUM-007", "AWS-KOL-015",
        "AWS-BHO-030", "AWS-RAN-067", "AWS-VAR-052",
    }
    faulty_files = {p for p in station_files if p.stem in CENTER_STATION_IDS}
    if not faulty_files:
        selection_rng = np.random.default_rng(5)
        faulty_indices = selection_rng.choice(
            len(station_files), size=min(7, len(station_files)), replace=False
        )
        faulty_files = {station_files[i] for i in faulty_indices}
    print(f"Selected {len(faulty_files)} of {len(station_files)} stations to receive injected faults:")
    for f in sorted(faulty_files):
        print(f"  -> {f.stem}")
    print(f"Remaining {len(station_files) - len(faulty_files)} stations stay clean (real data only) -- these are your trustworthy spatial-consistency neighbors.\n")
    events = []
    for csv_path in station_files:
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        if csv_path in faulty_files:
            print(f"Injecting anomalies into {csv_path.name}...")
            station_seed = seed + station_files.index(csv_path)
            injected, station_events = inject_anomalies(df, seed=station_seed, return_events=True)
            events.extend(station_events.to_dict("records"))
            n_anomalies = injected["is_anomaly"].sum()
            print(f"  -> {n_anomalies} of {len(injected)} rows flagged as ground-truth anomalies")
            print(f"  -> fault type breakdown:\n{injected['fault_type'].value_counts()}\n")
        else:
            injected = df.copy()
            injected["is_anomaly"] = False
            injected["fault_type"] = None
            print(f"{csv_path.name}: left clean (0 anomalies) -- serves as a trustworthy neighbor\n")
        output_path = output_dir / csv_path.name.replace(".csv", "_labeled.csv")
        injected.to_csv(output_path, index=False)
    ledger = pd.DataFrame(events, columns=[
        "episode_id", "station_id", "fault_type", "parameters",
        "start_index", "end_index", "start_timestamp", "end_timestamp", "seed",
    ])
    if not ledger.empty:
        ledger["parameters"] = ledger["parameters"].map(json.dumps)
    ledger.to_csv(output_dir / "fault_events.csv", index=False)
    manifest = {
        "base_seed": int(seed),
        "station_seed_rule": "base_seed + index in sorted raw station files",
        "anomaly_rate": INJECTION_RATE,
        "density_multiplier": ANOMALY_DENSITY_MULTIPLIER,
        "faulted_stations": sorted(p.stem for p in faulty_files),
        "raw_station_files": [p.name for p in station_files],
        "event_count": int(len(ledger)),
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8",
    )
    print(f"Generated labeled replay bundle and {len(ledger)} event(s) in {output_dir}")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate labeled evaluation replays without overwriting source data.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    main(output_dir=args.output_dir, seed=args.seed)
