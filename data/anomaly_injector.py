"""
SkyGuard AI — Phase 1b: Synthetic anomaly injector.

Takes real, clean historical readings (from data_fetch.py) and
deliberately corrupts a small fraction of them in known, labeled ways.
This gives us ground truth to actually measure the model against later
(precision/recall/F1 in Phase 3) -- something that doesn't exist for
real AWS anomaly data.

Fault types implemented, each tied to a real AWS failure mode named in
the problem statement:
  - spike           : sensor malfunction -> reading jumps far outside
                       physically plausible range for a single instant
  - frozen_value    : communication/sensor fault -> same value repeats
                       for several consecutive readings (Day 42/43 logic:
                       zero variance over a window is itself anomalous)
  - drift           : calibration drift -> slow, growing offset over time
  - dropout         : communication failure -> missing/null reading

Ground truth (is_injected, fault_type) is stored alongside the data so
Phase 3 can compute real accuracy metrics.
"""

import numpy as np
import pandas as pd
from pathlib import Path

# This script lives in the SAME folder as your fetched CSVs
# (backend/data/AWS-*.csv), unlike data_fetch.py which saves INTO a
# ./data subfolder relative to itself. If your CSVs are somewhere else,
# change this to point at that folder directly.
DATA_DIR = Path(__file__).parent

# How much of the data to corrupt. Keep this modest and realistic --
# real sensor faults are rare events, not half your dataset.
# Base prevalence for the normal test dataset. Do not tune this per
# evaluation result; it represents the project's default scenario.
INJECTION_RATE = 0.05

# BACKEND-ONLY CONTROL KNOB -------------------------------------------------
# Relative amount of injected fault data. Change ONLY this value when you
# want a lighter or heavier replay dataset:
#   0.0 = no injected faults, 0.5 = roughly half normal density,
#   1.0 = normal density, 2.0 = roughly double normal density.
# It scales both the row target and the per-fault minimum, preserving the
# realistic fault-type mix instead of turning one type up in isolation.
ANOMALY_DENSITY_MULTIPLIER = 2.5

# Held-out replay seed: distinct placements and fault directions from
# the initial calibration replay. Change deliberately and record it in
# evaluation output; train.py never consumes these labelled files.
RANDOM_SEED = 42

# Fixed (not randomized) fail-low window length. §5b's detector rule
# triggers reclassification at 2-3 consecutive hours -- 3 sits right at
# that bar, guaranteeing every injected fail-low event is long enough
# to be caught, with no per-event variance to account for in eval.
FAIL_LOW_LENGTH = 3


def compute_bounds(series: pd.Series, z_thresh: float = 3.0):
    """
    Day 42 (z-score method): mean +/- z_thresh * std defines the
    'normal' envelope. We use this to make sure injected spikes are
    genuinely, unambiguously outside normal behavior -- not borderline.
    """
    mean = series.mean()
    std = series.std()
    return mean, std, mean + z_thresh * std, mean - z_thresh * std


# Hard physical ceilings that NO fault should cross, because they're
# not just statistically unusual -- they're physically impossible.
# Humidity is the critical one: it's a percentage, so a sensor CANNOT
# genuinely report 173% no matter how broken it is (a real malfunctioning
# sensor saturates/clips at its measurement limits, it doesn't exceed
# them). Pressure gets a generous real-world floor/ceiling too. This is
# NOT applied to inject_fail_low (which intentionally uses an even lower
# fixed sentinel to represent total sensor failure -- a different, valid
# fault archetype) or inject_dropout (NaN has no numeric bound to violate).
HARD_PHYSICAL_LIMITS = {
    "humidity_pct": (0.0, 100.0),
    "pressure_hpa": (800.0, 1100.0),
}


def clip_to_physical_limits(df: pd.DataFrame, column: str, start_idx: int, end_idx: int):
    """Clamps an injected window back within hard physical limits, if the column has any."""
    if column in HARD_PHYSICAL_LIMITS:
        low, high = HARD_PHYSICAL_LIMITS[column]
        df.loc[start_idx:end_idx, column] = df.loc[start_idx:end_idx, column].clip(low, high)


def spans_overlap(a_start, a_end, b_start, b_end):
    """True if interval [a_start, a_end] intersects [b_start, b_end]."""
    return not (a_end < b_start or a_start > b_end)


def has_overlap(claimed_spans, _cols, start, end):
    """True if a proposed event intersects *any* existing fault event.

    Ground truth has one row-level ``fault_type`` field. Allowing two
    different sensor faults at the same timestamp would overwrite that
    label and make both evaluation and operator diagnosis ambiguous.
    Reserve timestamps globally, including all multivariate spans.
    """
    return any(spans_overlap(start, end, claimed_start, claimed_end)
               for claimed_start, claimed_end in claimed_spans)


def inject_spike(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """Push one reading far from the clean distribution without clipping it.

    A clipped candidate (for example humidity ``100 -> 100``) is not a
    spike at all. Returning ``None`` lets the placement loop choose a
    different time/parameter instead of writing an invalid ground-truth
    label.
    """
    mean, std, upper, lower = compute_bounds(df[column])
    # Push well beyond the clean-data tail. The detector then confirms
    # the expected one-reading reversion before labeling it a spike.
    magnitude = rng.uniform(8.0, 10.0)
    low, high = HARD_PHYSICAL_LIMITS.get(column, (-np.inf, np.inf))
    candidates = [
        mean + magnitude * std,
        mean - magnitude * std,
    ]
    viable = [value for value in candidates if low <= value <= high]
    if not viable:
        return None
    value = float(rng.choice(viable))
    # An injected spike must be visibly distinct from both of its
    # neighbours. The future neighbour is checked by the detector; this
    # guard prevents an already-flat source point from being mislabeled.
    if abs(value - float(df.loc[idx, column])) < max(std * 4.0, 0.5):
        return None
    df.loc[idx, column] = value
    return "spike"


def inject_frozen(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """
    Repeat the value at idx for the next few rows -- a comms/sensor
    fault where the station keeps reporting stale data. Day 42/43:
    zero variance in a rolling window is itself a strong outlier signal.

    NOTE: bit-exact repeat, no jitter, for now. Sub-integer jitter that
    provably can't cross a floor() boundary is a later optimization --
    doing it now risks the ground truth silently breaking the detector's
    "same integer part across 3 readings" rule (§1) if a frozen value
    happens to sit near a .0 boundary. Correctness over realism until
    that's built properly.
    """
    freeze_length = rng.integers(6, 9)
    frozen_value = df.loc[idx, column]
    end_idx = min(idx + freeze_length, len(df) - 1)
    df.loc[idx:end_idx, column] = frozen_value
    return "frozen_value", idx, end_idx


def inject_drift(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """
    Calibration drift -- a slow, growing offset starting at idx and
    continuing to the end of the window. Unlike a spike, no single
    point looks extreme; only the trend over time reveals it.

    The generated fault is direction-consistent for its whole labeled
    span. This is essential: Draft 2's CUSUM detector is expressly
    designed for accumulating one-directional bias, so labels that
    reverse due to copied weather noise would make its ground truth
    invalid. Curvature is allowed, but every successive fault value
    moves in the same direction.
    """
    drift_length = rng.integers(20, 50)
    end_idx = min(idx + drift_length, len(df) - 1)
    direction = rng.choice([-1.0, 1.0])
    max_offset = df[column].std() * rng.uniform(20.0, 30.0)
    steps = end_idx - idx + 1

    # Linear or curved, but strictly monotonic. Replacing the span from
    # its start point prevents ordinary hour-to-hour weather movement
    # from reversing the intended injected fault direction.
    if rng.choice([True, False]):
        ramp = np.linspace(0, max_offset, steps)
    else:
        ramp = max_offset * (np.linspace(0, 1, steps) ** rng.uniform(1.3, 2.0))
    # A tiny positive increment prevents equal adjacent values in a
    # shallow curved ramp, while keeping the fault physically smooth.
    min_step = max(df[column].std() * 1e-4, 1e-6)
    ramp = np.maximum.accumulate(ramp + np.arange(steps) * min_step)
    start_value = float(df.loc[idx, column])
    df.loc[idx:end_idx, column] = start_value + direction * ramp
    clip_to_physical_limits(df, column, idx, end_idx)
    return "drift", idx, end_idx


def inject_dropout(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """Communication failure -- reading goes missing entirely."""
    df.loc[idx, column] = np.nan
    return "dropout"


def inject_fail_low(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """
    Hardware fail-low -- distinct from a spike. Real sensors often fail
    by clamping to a fixed physical floor or error sentinel rather than
    a random statistical outlier: a humidity sensor stuck reading ~0%,
    a pressure transducer that lost power reading near 0 hPa, a
    temperature probe reporting a fixed out-of-range error value. This
    is a flatline at an implausible LOW bound, held for a short window
    -- different from `frozen` (which freezes at whatever the last real
    reading happened to be) and different from `spike` (a brief
    statistical extreme in either direction).

    Window length is FIXED (FAIL_LOW_LENGTH), not randomized -- §5b's
    detector rule reclassifies fail-low at 2-3 consecutive hours, so a
    fixed 3-row window guarantees every injected event actually clears
    that bar, with no per-event variance to account for at eval time.
    """
    end_idx = min(idx + FAIL_LOW_LENGTH, len(df) - 1)

    # Physically-motivated failure floors per parameter, with a little
    # jitter so it's not a bit-exact repeated constant.
    floors = {
        "temperature_c": -15.0,   # implausible cold snap for tropical/plains stations
        "pressure_hpa": 50.0,     # near-total transducer failure reading
        "humidity_pct": 0.5,      # sensor stuck near-zero
    }
    floor_value = floors[column]
    noise = rng.normal(0, abs(floor_value) * 0.02 + 0.1, end_idx - idx + 1)
    df.loc[idx:end_idx, column] = floor_value + noise
    return "sensor_fail_low", idx, end_idx


def inject_multivariate(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """
    Multivariate inconsistency -- the PS's own example scenario: a
    station reports a temperature spike while pressure/humidity move
    in directions that don't physically make sense together (e.g. temp
    sharply up but humidity ALSO up and pressure barely reacting, which
    real weather physics wouldn't produce together). `column` is ignored
    here since this fault always touches all three parameters at once --
    it's the multivariate case the single-column fault functions can't
    represent.
    """
    window = rng.integers(2, 5)
    end_idx = min(idx + window, len(df) - 1)

    temp_std = df["temperature_c"].std()
    pressure_std = df["pressure_hpa"].std()
    humidity_std = df["humidity_pct"].std()

    # Temperature spikes up sharply (sensor fault)...
    df.loc[idx:end_idx, "temperature_c"] += rng.uniform(4.0, 6.0) * temp_std
    # ...while humidity ALSO rises (physically, a real heat spike should
    # usually correlate with humidity dropping, not rising)...
    df.loc[idx:end_idx, "humidity_pct"] += rng.uniform(2.0, 3.5) * humidity_std
    # ...and pressure barely moves, when a real weather event of this
    # magnitude would typically show a pressure change too.
    df.loc[idx:end_idx, "pressure_hpa"] += rng.normal(0, pressure_std * 0.1, end_idx - idx + 1)

    clip_to_physical_limits(df, "humidity_pct", idx, end_idx)
    clip_to_physical_limits(df, "pressure_hpa", idx, end_idx)

    return "multivariate_inconsistency", idx, end_idx


# Upper bound on window length per fault type, used to pre-check
# overlap BEFORE mutating df -- must stay in sync with each function's
# own rng.integers(...) upper bound (exclusive), or its fixed length.
FAULT_MAX_LEN = {
    inject_spike: 1,
    inject_frozen: 8,
    inject_drift: 49,
    inject_dropout: 1,
    inject_multivariate: 4,
    inject_fail_low: FAIL_LOW_LENGTH,
}

# inject_multivariate ignores its `column` arg and touches all three
# parameters at once (see its docstring) -- it must claim all three
# columns' spans, not just the sampled one, or it can silently overlap
# a same-timestamp fault injected on a different column.
MULTI_COLUMN_FAULTS = {inject_multivariate}

# Relative frequency weights for how often each fault type actually
# occurs on a real AWS network -- these are NOT row quotas, just
# relative draw probabilities. Transient sensor/comms glitches (spike,
# dropout) are the most common real-world failure mode. Slow-developing
# calibration drift and multi-column agreement events (multivariate)
# are rarer in practice. Numbers don't need to sum to 1 -- normalized
# at draw time.
FAULT_WEIGHTS = {
    inject_spike: 3.0,
    inject_dropout: 3.0,
    inject_frozen: 2.0,
    inject_fail_low: 1.5,
    inject_drift: 1.0,
    inject_multivariate: 1.0,
}

# Every fault type gets AT LEAST this many injected EVENTS, regardless
# of its weight above. Phase 3 needs enough samples per fault type to
# compute a meaningful per-type precision/recall -- a purely
# weighted-random draw could theoretically starve a rare type down to
# zero on an unlucky seed, which would silently break that eval.
MIN_EVENTS_PER_TYPE = 4


def inject_anomalies(df: pd.DataFrame, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """
    Walks through one station's dataframe and injects labeled faults
    at random locations across temperature/pressure/humidity columns.
    Returns a new dataframe with two extra columns: is_anomaly (bool)
    and fault_type (str or None) -- this is the ground truth label set.

    Non-overlap guarantee (§8): before any fault_fn runs, its MAX
    possible window is checked for real interval overlap against every
    span already claimed on the columns it touches. This is a
    conservative pre-check (uses the fault type's max length, not its
    actual randomly-drawn length), so a fault is never started, then
    reverted after the fact -- it's simply skipped and retried
    elsewhere. Overlap is tracked per column, not globally, so
    independent faults on different parameters can legitimately share
    a timestamp (§1's frozen-pressure-while-temp-moves-normally case).
    """
    rng = np.random.default_rng(seed)
    if ANOMALY_DENSITY_MULTIPLIER < 0:
        raise ValueError("ANOMALY_DENSITY_MULTIPLIER must be zero or positive")
    df = df.copy().reset_index(drop=True)
    df["is_anomaly"] = False
    df["fault_type"] = None

    columns = ["temperature_c", "pressure_hpa", "humidity_pct"]
    df[columns] = df[columns].astype(float)
    n_rows = len(df)

    # This is a TARGET, not a hard quota -- roughly ~5% of rows end up
    # contaminated, but the actual number is whatever the two passes
    # below naturally land on. No fault type is forced to a fixed
    # count anymore; only a floor (MIN_EVENTS_PER_TYPE) and a ceiling
    # (this target, approximately) apply.
    target_anomalous_rows = int(n_rows * INJECTION_RATE * ANOMALY_DENSITY_MULTIPLIER)
    fault_functions = [inject_spike, inject_frozen, inject_drift, inject_dropout, inject_multivariate, inject_fail_low]

    # One global timeline: a reading belongs to at most one injected
    # fault event. This deliberately prefers interpretable ground truth
    # over synthetic compound-fault density.
    claimed_spans = []
    fault_counts = {fn: 0 for fn in fault_functions}
    rows_injected = 0

    def try_inject(fault_fn, attempts_budget):
        nonlocal rows_injected
        attempts = 0
        while attempts < attempts_budget:
            attempts += 1
            idx = int(rng.integers(10, n_rows - 60))
            column = rng.choice(columns)
            cols_needed = list(columns) if fault_fn in MULTI_COLUMN_FAULTS else [column]

            # Conservative pre-check: reserve the fault type's MAX
            # possible window before running it, so we never have to
            # revert a mutation after the fact.
            candidate_end = min(idx + FAULT_MAX_LEN[fault_fn], n_rows - 1)
            if has_overlap(claimed_spans, cols_needed, idx, candidate_end):
                continue

            result = fault_fn(df, idx, column, rng)

            # An injector may decline an invalid candidate (notably a
            # would-be spike that physical clipping would erase). It
            # has made no mutation, so safely keep searching.
            if result is None:
                continue

            if isinstance(result, tuple) and len(result) == 3:
                fault_type, start, end = result
            else:
                fault_type = result
                start = end = idx

            df.loc[start:end, "is_anomaly"] = True
            df.loc[start:end, "fault_type"] = fault_type
            claimed_spans.append((start, end))
            rows_injected += (end - start + 1)
            fault_counts[fault_fn] += 1
            return True
        return False

    # Pass 1 -- guarantee the floor. Every fault type gets at least
    # MIN_EVENTS_PER_TYPE events before anything else happens, so a
    # rare-weighted or overlap-unlucky type can never end up at zero.
    # inject_multivariate goes through this pass too, and since it's
    # the only multi-column type, doing this BEFORE the weighted fill
    # below (which draws from all types in whatever order it likes)
    # still isn't enough on its own -- so we also run this floor pass
    # once per type up front, while every column still has the most
    # open space available, which is when a 3-column-agreement fault
    # has the best odds of finding room.
    scaled_min_events = (
        0 if ANOMALY_DENSITY_MULTIPLIER == 0
        else max(1, round(MIN_EVENTS_PER_TYPE * ANOMALY_DENSITY_MULTIPLIER))
    )
    for fault_fn in fault_functions:
        placed = 0
        while placed < scaled_min_events:
            if not try_inject(fault_fn, attempts_budget=n_rows):
                break  # genuinely no room left for this type -- move on
            placed += 1

    # Pass 2 -- fill the remaining row budget with weighted-random
    # draws across fault types. This is what makes the FINAL mix
    # reflect realistic relative frequency (more spikes/dropouts than
    # drift/multivariate) instead of a forced equal split, while still
    # respecting the overall ~5% contamination target and the
    # no-overlap guarantee from try_inject.
    weight_fns = list(FAULT_WEIGHTS.keys())
    weight_probs = np.array([FAULT_WEIGHTS[fn] for fn in weight_fns])
    weight_probs = weight_probs / weight_probs.sum()

    max_total_attempts = n_rows * 3  # generous safety valve
    total_attempts = 0
    while rows_injected < target_anomalous_rows and total_attempts < max_total_attempts:
        total_attempts += 1
        fault_fn = weight_fns[rng.choice(len(weight_fns), p=weight_probs)]
        try_inject(fault_fn, attempts_budget=1)

    return df


def main():
    print(
        "Injection density multiplier: "
        f"{ANOMALY_DENSITY_MULTIPLIER:g} "
        f"(base rate {INJECTION_RATE:.1%}; effective target "
        f"{INJECTION_RATE * ANOMALY_DENSITY_MULTIPLIER:.1%})\n"
    )
    # Only a RANDOM SUBSET of stations get faults -- not all 20.
    # If every station were corrupted simultaneously, there'd be no
    # clean neighbor left to compare against, which defeats spatial
    # consistency before it's even built (a neighbor comparison is only
    # meaningful if the neighbor is actually trustworthy). Real sensor
    # networks also don't have every unit fail at once -- a handful of
    # faulty stations among many healthy ones is the realistic picture.
    #
    # Separate seed from RANDOM_SEED (which controls fault content/
    # placement) so "which stations fail" and "what the fault looks
    # like" are independently reproducible.
    STATION_SELECTION_SEED = 7
    N_FAULTY_STATIONS = 3

    station_files = sorted(
        p for p in DATA_DIR.glob("AWS-*.csv") if "_labeled" not in p.name
    )

    if len(station_files) < N_FAULTY_STATIONS:
        print(f"Only {len(station_files)} station CSVs found -- check DATA_DIR / that data_fetch.py has run.")

    selection_rng = np.random.default_rng(STATION_SELECTION_SEED)
    faulty_indices = selection_rng.choice(
        len(station_files), size=min(N_FAULTY_STATIONS, len(station_files)), replace=False
    )
    faulty_files = {station_files[i] for i in faulty_indices}

    print(f"Selected {len(faulty_files)} of {len(station_files)} stations to receive injected faults:")
    for f in faulty_files:
        print(f"  -> {f.stem}")
    print(f"Remaining {len(station_files) - len(faulty_files)} stations stay clean (real data only) -- these are your trustworthy spatial-consistency neighbors.\n")

    for csv_path in station_files:
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])

        if csv_path in faulty_files:
            print(f"Injecting anomalies into {csv_path.name}...")
            # Each station gets its OWN seed, derived from the global
            # RANDOM_SEED plus its position in the sorted file list.
            # Without this, every faulty station picked the exact same
            # relative row pattern and fault-type mix (confirmed in
            # testing -- 3 stations, identical 60/60/60 breakdown),
            # which isn't realistic: independent sensor failures
            # shouldn't sync up like that.
            station_seed = RANDOM_SEED + station_files.index(csv_path)
            injected = inject_anomalies(df, seed=station_seed)
            n_anomalies = injected["is_anomaly"].sum()
            print(f"  -> {n_anomalies} of {len(injected)} rows flagged as ground-truth anomalies")
            print(f"  -> fault type breakdown:\n{injected['fault_type'].value_counts()}\n")
        else:
            # Clean station: still write a "_labeled" file for schema
            # consistency downstream (features.py can always expect
            # is_anomaly/fault_type columns to exist), just with
            # everything correctly labeled as non-anomalous.
            injected = df.copy()
            injected["is_anomaly"] = False
            injected["fault_type"] = None
            print(f"{csv_path.name}: left clean (0 anomalies) -- serves as a trustworthy neighbor\n")

        output_path = DATA_DIR / csv_path.name.replace(".csv", "_labeled.csv")
        injected.to_csv(output_path, index=False)


if __name__ == "__main__":
    main()
