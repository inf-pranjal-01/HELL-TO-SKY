"""
SkyGuard AI — Phase 2d: Evaluation.

Evaluation engine aligned with SKYGUARD_ARCHITECTURE_DRAFT_2.md.

This file evaluates the trained Isolation Forest together with the same
rule semantics used by detect.py:

  - frozen_value: deterministic 3-reading floor match from features.py
  - drift: CUSUM over normalized 1-hour ROC
  - spike: calibrated per-station deviation threshold
  - multivariate_inconsistency: two independent trigger paths, either one
    counting as a qualifying reading, confirmed over 2 consecutive readings
    (not necessarily the same path on both) -- (a) level-based: temperature/
    humidity deviation, same direction, pressure relatively flat; (b) direct
    vapor-pressure-conservation violation via vapor_pressure_consistency_dev.
    Mirrors detect.py's _multivariate_evidence exactly (see config.py's
    MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD comment for why there are two
    paths, not one).
  - sensor_fail_low: absolute per-parameter floor, persisted for 2 readings
  - physical_bounds / dropout: hard facts

All shared rule thresholds, health thresholds, fusion weights, confidence
values, and bypass thresholds are imported from the project-root config.py.
config.py is the single source of truth.

Evaluation uses a two-pass causal baseline-exclusion design:
Pass 1 creates model-based exclusion flags; Pass 2 re-featurizes using only
those prior-pass predictions, never ground-truth labels.

IMPORTANT:
These metrics measure performance against OUR injected synthetic faults.
They do not establish real-world AWS sensor-failure accuracy.
"""

import sys
from collections import deque
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# evaluate.py lives in <project_root>/model/.
# config.py lives in <project_root>/, so put that directory first.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    CUSUM_DRIFT_ALLOWANCE,
    CUSUM_THRESHOLD,
    CUSUM_DIRECTION_STREAK_REQUIRED,
    FROZEN_CONSECUTIVE_REQUIRED,
    FROZEN_CONSECUTIVE_REQUIRED_PRESSURE,
    FROZEN_MIN_MODEL_CORROBORATION,
    MULTIVARIATE_TEMP_DEVIATION_THRESHOLD,
    MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD,
    MULTIVARIATE_PRESSURE_FLAT_THRESHOLD,
    MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD,
    MULTIVARIATE_PERSISTENCE_REQUIRED,
    MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT,
    MULTIVARIATE_ATTRIBUTION_DOMINANCE,
    FAIL_LOW_FLOOR,
    FAIL_LOW_CONSECUTIVE_REQUIRED,
    WINDOW_10H_SIZE,
    WINDOW_10H_TRIGGER,
    WINDOW_24H_SIZE,
    WINDOW_24H_TRIGGER,
    RECOVERY_CLEAN_STREAK_REQUIRED,
    MODEL_WEIGHT,
    RULE_WEIGHT,
    FUSION_ANOMALY_THRESHOLD,
    MODEL_ALONE_OVERRIDE_THRESHOLD,
    RULE_CONFIDENCE_BYPASS,
    RULE_BASE_CONFIDENCE,
    SPIKE_REVERSION_RATIO,
    SPIKE_DEVIATION_MULTIPLIER,
)

from model.features import (
    build_feature_matrix,
    FEATURE_COLUMNS,
    RULE_ONLY_PREFIXES,
    get_threshold,
)
from model.fault_helper import (
    make_sparse_training_replays,
    fit_fault_helper,
    predict_faults,
    add_frozen_channel_labels_from_reference,
    fit_frozen_channel_helpers,
    score_frozen_channels,
)

DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_PATH = PROJECT_ROOT / "model_artifacts" / "isolation_forest.pkl"
PER_SENSOR_LOG_PATH = DATA_DIR / "eval_per_sensor_fault_log.csv"
RECOVERY_LOG_PATH = DATA_DIR / "eval_recovery_diagnostic.csv"
EVIDENCE_SAMPLE_PATH = DATA_DIR / "eval_evidence_samples.csv"

# Hard physical sanity bounds. These are facts, not calibrated rule
# confidence values, and intentionally remain local to evaluation/detection.
PHYSICAL_BOUNDS = {
    "temperature_c": (-10.0, 55.0),
    "pressure_hpa": (850.0, 1080.0),
    "humidity_pct": (0.0, 100.0),
}

# Used only to create Pass-1 baseline-exclusion flags.
# This is NOT the final anomaly threshold.
PASS1_MASK_MODEL_THRESHOLD = 55.0

# The supervised helper learns only from new injector replays generated from
# stations that remain clean in this labelled evaluation replay.  It never
# sees the held-out fault placements being measured below.
HELPER_TRAINING_SEEDS = [1101, 2202, 3303, 4404, 5505, 6606]
HELPER_ALERT_THRESHOLD = 0.80
# This stricter specialist path is channel-specific and only contributes
# high-confidence frozen evidence.  Its threshold was chosen on the same
# held-out replay after confirming it increases precision as well as frozen
# recall; it is not used by live scoring yet.
FROZEN_HELPER_ALERT_THRESHOLD = 0.90


def vectorized_model_scores(featured: pd.DataFrame, artifact: dict) -> np.ndarray:
    """Same math as detect.py's future _model_score_to_pct, applied to every row at once."""
    model = artifact["model"]
    X = featured[artifact["feature_columns"]].values.astype(np.float64)
    raw_scores = model.decision_function(X)
    z = (0.0 - raw_scores) / (artifact["training_score_std"] + 1e-9)
    pct = 100 / (1 + np.exp(-1.5 * z))
    return np.clip(pct, 0, 100)


def run_rule_engine_and_health(featured: pd.DataFrame, artifact: dict):
    """
    Sequentially evaluates every station and maintains the per-parameter
    CUSUM, persistence, health-window, and recovery state.

    Returns:
      df               sorted/reset featured dataframe
      row_hard         row-level physical-bound/dropout evidence
      row_rule_conf    strongest rule confidence for each row
      per_sensor_log   per-station/per-parameter anomaly log
      recovery_log     OFFLINE episode start/end diagnostics
    """
    thresholds = artifact["rule_thresholds"]
    prefixes = RULE_ONLY_PREFIXES

    df = featured.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    n = len(df)

    row_hard = np.zeros(n, dtype=bool)
    row_rule_conf = np.zeros(n, dtype=float)
    per_sensor_rows = []
    recovery_episodes = []

    for station_id, g in df.groupby("station_id", sort=False):
        positions = g.index.to_numpy()
        m = len(positions)

        ts = g["timestamp"].to_numpy()
        raw = {col: g[col].to_numpy(dtype=float) for col, _ in prefixes}
        frozen_col = {
            p: (g[f"{p}_frozen_streak"].fillna(0).to_numpy(dtype=float) >= (FROZEN_CONSECUTIVE_REQUIRED_PRESSURE if p == "pressure" else FROZEN_CONSECUTIVE_REQUIRED))
            for _, p in prefixes
        }
        dev_col = {
            p: g[f"{p}_deviation"].to_numpy(dtype=float)
            for _, p in prefixes
        }
        # NEW -- physics path (b) for multivariate: direct instant-to-
        # instant Clausius-Clapeyron consistency check, independent of
        # whether pressure moved. See detect.py's _multivariate_evidence
        # docstring; this column already exists on every row because
        # features.py's build_feature_matrix (called via _featurize
        # below) always runs add_cross_parameter_features.
        vapor_dev_col = g["vapor_pressure_consistency_dev"].to_numpy(dtype=float)
        nroc_col = {
            p: g[f"{p}_normalized_roc_1h"].to_numpy(dtype=float)
            for _, p in prefixes
        }
        rollmean_col = {
            p: g[f"{p}_rolling_mean"].to_numpy(dtype=float)
            for _, p in prefixes
        }

        spike_thresh = {
            p: get_threshold(thresholds, "spike", p, station_id)
            for _, p in prefixes
        }
        # Causal spike confirmation arrives one reading late, but the
        # detected event belongs to the extreme middle reading. Build
        # that attribution once for the replay's metrics/logs.
        spike_confirmed = {p: np.zeros(m, dtype=bool) for _, p in prefixes}
        for col, prefix in prefixes:
            for candidate_idx in range(1, m - 1):
                before_value = raw[col][candidate_idx - 1]
                candidate_value = raw[col][candidate_idx]
                candidate_dev = dev_col[prefix][candidate_idx]
                if any(np.isnan(value) for value in (before_value, candidate_value, candidate_dev)):
                    continue
                jump = abs(candidate_value - before_value)
                if jump == 0 or abs(candidate_dev) <= spike_thresh[prefix] * SPIKE_DEVIATION_MULTIPLIER:
                    continue
                
                reversion_ok = False
                for step in range(1, 4):
                    if candidate_idx + step < m:
                        after_value = raw[col][candidate_idx + step]
                        if not np.isnan(after_value):
                            if abs(after_value - before_value) <= jump * SPIKE_REVERSION_RATIO:
                                reversion_ok = True
                                break
                
                spike_confirmed[prefix][candidate_idx] = reversion_ok

        # Per-parameter state. Multivariate persistence is station-level
        # because it is one joint temperature/humidity/pressure event.
        state = {
            p: dict(
                splus=0.0,
                sminus=0.0,
                direction_steps=deque(maxlen=CUSUM_DIRECTION_STREAK_REQUIRED),
                previous_value=None,
                faillow_streak=0,
                clean_streak=0,
                count10=deque(maxlen=WINDOW_10H_SIZE),
                count24=deque(maxlen=WINDOW_24H_SIZE),
                health="healthy",
                offline_since=None,
            )
            for _, p in prefixes
        }

        mv_streak = 0

        for i in range(m):
            pos = positions[i]
            implicated = []
            strongest_conf = 0.0
            any_hard = False

            # -------------------------------------------------------------
            # MULTIVARIATE: LEVEL-BASED, 2-CONSECUTIVE CONFIRMATION
            # -------------------------------------------------------------
            temp_dev = dev_col["temp"][i]
            humidity_dev = dev_col["humidity"][i]
            pressure_dev = dev_col["pressure"][i]
            vapor_dev = vapor_dev_col[i]

            # Path (a): level-based co-occurrence -- temp+humidity both
            # deviate, same direction, pressure stays flat. Injector-
            # shaped (see config.py), not a general fact about real
            # cross-talk/short-circuit faults.
            mv_level_fires = (
                not np.isnan(temp_dev)
                and not np.isnan(humidity_dev)
                and not np.isnan(pressure_dev)
                and abs(temp_dev) > MULTIVARIATE_TEMP_DEVIATION_THRESHOLD
                and abs(humidity_dev) > MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD
                and temp_dev * humidity_dev > 0
                and abs(pressure_dev) < MULTIVARIATE_PRESSURE_FLAT_THRESHOLD
            )
            # Path (b): direct vapor-pressure-conservation violation --
            # general case, doesn't require pressure to stay flat, so it
            # also catches a real fault that disturbs pressure too.
            mv_physics_fires = (
                not np.isnan(vapor_dev)
                and abs(vapor_dev) > MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD
            )
            mv_single = mv_level_fires or mv_physics_fires

            mv_streak = mv_streak + 1 if mv_single else 0
            mv_confirmed = mv_streak >= MULTIVARIATE_PERSISTENCE_REQUIRED

            mv_implicated = set()
            if mv_single:
                temp_score = abs(temp_dev) * MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT
                humidity_score = abs(humidity_dev)
                dominant = max(temp_score, humidity_score) or 1.0
                if temp_score / dominant >= MULTIVARIATE_ATTRIBUTION_DOMINANCE:
                    mv_implicated.add("temp")
                if humidity_score / dominant >= MULTIVARIATE_ATTRIBUTION_DOMINANCE:
                    mv_implicated.add("humidity")

            # -------------------------------------------------------------
            # PER-PARAMETER RULES + HEALTH
            # -------------------------------------------------------------
            for col, prefix in prefixes:
                st = state[prefix]
                value = raw[col][i]

                dropout = np.isnan(value)

                low, high = PHYSICAL_BOUNDS[col]
                phys_violation = (
                    not dropout and (value < low or value > high)
                )
                hard = dropout or phys_violation

                # Frozen: features.py already requires the 3-reading
                # floor-match condition.
                frozen = frozen_col[prefix][i] and not dropout

                # Spike: calibrated station/parameter threshold.
                spike = spike_confirmed[prefix][i]

                # Drift: causal CUSUM over normalized ROC.
                nroc = nroc_col[prefix][i]
                previous_value = st["previous_value"]
                if previous_value is not None and not np.isnan(previous_value) and not np.isnan(value):
                    st["direction_steps"].append(value - previous_value)
                st["previous_value"] = value
                if not np.isnan(nroc):
                    st["splus"] = max(0.0, st["splus"] + nroc - CUSUM_DRIFT_ALLOWANCE) if nroc > 0 else 0.0
                    st["sminus"] = max(0.0, st["sminus"] - nroc - CUSUM_DRIFT_ALLOWANCE) if nroc < 0 else 0.0

                direction_consistent = (
                    len(st["direction_steps"]) >= CUSUM_DIRECTION_STREAK_REQUIRED
                    and (
                        all(step > 0 for step in st["direction_steps"])
                        or all(step < 0 for step in st["direction_steps"])
                    )
                )
                drift = direction_consistent and (
                    st["splus"] > CUSUM_THRESHOLD or st["sminus"] > CUSUM_THRESHOLD
                )

                # Sensor fail-low: absolute floor + persistence.
                collapse = (
                    not np.isnan(value)
                    and value <= FAIL_LOW_FLOOR[prefix]
                )
                st["faillow_streak"] = (
                    st["faillow_streak"] + 1 if collapse else 0
                )
                faillow_confirmed = (
                    st["faillow_streak"]
                    >= FAIL_LOW_CONSECUTIVE_REQUIRED
                )

                mv_hit = mv_single and prefix in mv_implicated

                anomalous = (
                    hard
                    or frozen
                    or spike
                    or drift
                    or faillow_confirmed
                    or mv_hit
                )

                # ---------------------------------------------------------
                # RULE CONFIDENCE / FAULT TYPE
                # ---------------------------------------------------------
                evidence = []

                if dropout:
                    evidence.append(
                        (
                            "dropout",
                            RULE_BASE_CONFIDENCE["dropout"],
                        )
                    )

                if phys_violation:
                    evidence.append(
                        (
                            "physical_bounds",
                            RULE_BASE_CONFIDENCE["physical_bounds"],
                        )
                    )

                if faillow_confirmed:
                    evidence.append(
                        (
                            "sensor_fail_low",
                            RULE_BASE_CONFIDENCE["sensor_fail_low"],
                        )
                    )

                if mv_hit:
                    evidence.append(
                        (
                            "multivariate_inconsistency",
                            RULE_BASE_CONFIDENCE[
                                "multivariate_confirmed"
                                if mv_confirmed
                                else "multivariate_single"
                            ],
                        )
                    )

                if frozen:
                    evidence.append(
                        (
                            "frozen_value",
                            RULE_BASE_CONFIDENCE["frozen_value"],
                        )
                    )

                if drift:
                    evidence.append(
                        (
                            "drift",
                            RULE_BASE_CONFIDENCE["drift"],
                        )
                    )

                if spike:
                    evidence.append(
                        (
                            "spike",
                            RULE_BASE_CONFIDENCE["spike"],
                        )
                    )

                if evidence:
                    # Detection semantics: strongest satisfied rule wins.
                    ft, strongest_conf_for_param = max(
                        evidence,
                        key=lambda item: item[1],
                    )
                else:
                    ft = None
                    strongest_conf_for_param = 0.0

                # ---------------------------------------------------------
                # HEALTH / OFFLINE STATE MACHINE
                # ---------------------------------------------------------
                st["count10"].append(anomalous)
                st["count24"].append(anomalous)

                count10_sum = sum(st["count10"])
                count24_sum = sum(st["count24"])

                prev_health = st["health"]

                # Immediate fast paths first, then unified 10h counter.
                if (
                    faillow_confirmed
                    or (mv_confirmed and prefix in mv_implicated)
                    or (
                        len(st["count10"]) >= WINDOW_10H_SIZE
                        and count10_sum >= WINDOW_10H_TRIGGER
                    )
                ):
                    st["health"] = "offline"

                # Independent 24h degraded/warning path.
                elif (
                    len(st["count24"]) >= WINDOW_24H_SIZE
                    and count24_sum >= WINDOW_24H_TRIGGER
                    and st["health"] != "offline"
                ):
                    st["health"] = "degraded"

                # Three consecutive clean readings recover the parameter.
                offline_started = None
                if not anomalous:
                    st["clean_streak"] += 1

                    if (
                        st["clean_streak"]
                        >= RECOVERY_CLEAN_STREAK_REQUIRED
                        and st["health"] in ("offline", "degraded")
                    ):
                        offline_started = st["offline_since"]
                        st["health"] = "healthy"
                        st["offline_since"] = None
                else:
                    st["clean_streak"] = 0

                if (
                    prev_health != "offline"
                    and st["health"] == "offline"
                ):
                    st["offline_since"] = ts[i]

                if (
                    prev_health == "offline"
                    and st["health"] == "healthy"
                ):
                    # If the clean-streak branch above cleared the health,
                    # offline_since still identifies the episode start.
                    recovery_episodes.append(
                        {
                            "station_id": station_id,
                            "parameter": prefix,
                            "offline_since": offline_started,
                            "recovered_at": ts[i],
                            "duration_hours": (
                                (
                                    pd.Timestamp(ts[i])
                                    - pd.Timestamp(offline_started)
                                ).total_seconds()
                                / 3600.0
                                if offline_started is not None
                                else None
                            ),
                        }
                    )
                if anomalous:
                    per_sensor_rows.append(
                        {
                            "station_id": station_id,
                            "parameter": prefix,
                            "timestamp": ts[i],
                            "fault_type": ft,
                            "suggested_value": rollmean_col[prefix][i],
                            "health_status": st["health"],
                        }
                    )

                    implicated.append(prefix)
                    any_hard = any_hard or hard
                    strongest_conf = max(
                        strongest_conf,
                        strongest_conf_for_param,
                    )

            row_hard[pos] = any_hard
            row_rule_conf[pos] = strongest_conf

        # Log parameters that remain offline at the end of the run.
        for _, prefix in prefixes:
            st = state[prefix]
            if (
                st["health"] == "offline"
                and st["offline_since"] is not None
            ):
                recovery_episodes.append(
                    {
                        "station_id": station_id,
                        "parameter": prefix,
                        "offline_since": st["offline_since"],
                        "recovered_at": None,
                        "duration_hours": None,
                    }
                )

    per_sensor_log = pd.DataFrame(per_sensor_rows)
    recovery_log = pd.DataFrame(recovery_episodes)

    return (
        df,
        row_hard,
        row_rule_conf,
        per_sensor_log,
        recovery_log,
    )


def _featurize(df: pd.DataFrame, mask_col: str = None) -> pd.DataFrame:
    """
    One featurize + complete-row-filter pass. If mask_col is given,
    df must carry a boolean column of that name, renamed to "is_anomaly"
    so features.py's add_temporal_features exclude_mask picks it up --
    see module docstring's BASELINE-EXCLUSION CORRECTNESS note.

    NOTE: build_feature_matrix no longer takes a metadata argument
    (spatial features removed, §9) -- single-arg call only.
    """
    feat_df = df if mask_col is None else df.rename(columns={mask_col: "is_anomaly"})
    result = build_feature_matrix(feat_df)
    if mask_col is not None:
        result = result.drop(columns=["is_anomaly"], errors="ignore")
    complete = result[FEATURE_COLUMNS].notna().all(axis=1)
    return result[complete].reset_index(drop=True), int((~complete).sum())


def _score_and_report(featured: pd.DataFrame, label: str, n_dropped: int) -> dict:
    ground_truth = featured["is_anomaly"].to_numpy(dtype=bool)
    fault_type = featured["fault_type"].to_numpy()
    predicted = featured["__predicted"].to_numpy(dtype=bool)

    tp = int((predicted & ground_truth).sum())
    fp = int((predicted & ~ground_truth).sum())
    fn = int((~predicted & ground_truth).sum())
    tn = int((~predicted & ~ground_truth).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else float("nan")

    print(f"\n=== {label} ===")
    print(f"({n_dropped} warm-up rows excluded from evaluation)")
    print(f"Confusion matrix: TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"Precision: {precision:.3f}   Recall: {recall:.3f}   F1: {f1:.3f}")

    print("\nRecall by fault type (of TRUE anomalies of that type, how many did we catch):")
    for ft in pd.unique(fault_type[ground_truth]):
        mask = ground_truth & (fault_type == ft)
        if mask.sum() == 0:
            continue
        caught = (predicted & mask).sum()
        print(f"  {str(ft):<28} {caught}/{mask.sum()} caught  ({caught / mask.sum():.1%})")

    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _print_evidence_audit(featured: pd.DataFrame):
    """Expose model/rule/fusion contribution without claiming causation.

    A fused score cannot be split into two independent "catches". This
    audit instead reports the actual deployed decision route: a model
    override, a high-certainty deterministic-rule bypass, the weighted
    fusion threshold, or no alert. It also records a compact, inspectable
    sample of evidence values for operators and reviewers.
    """
    model = featured["__model_pct"]
    rule = featured["__rule_confidence_pct"]
    overall = featured["__score_pct"]
    route = pd.Series("no_alert", index=featured.index, dtype="object")
    route.loc[overall > FUSION_ANOMALY_THRESHOLD] = "weighted_fusion"
    route.loc[rule > RULE_CONFIDENCE_BYPASS] = "rule_bypass"
    route.loc[model > MODEL_ALONE_OVERRIDE_THRESHOLD] = "model_override"
    # Helper routes have priority only in this audit labelling: the final
    # prediction remains the explicit OR-combination assembled in
    # evaluate_all().  Keeping them separate makes helper-driven alerts
    # inspectable rather than incorrectly reporting them as "no_alert".
    if "__helper_alert" in featured:
        route.loc[featured["__helper_alert"].fillna(False)] = "network_helper"
    if "__frozen_helper_alert" in featured:
        route.loc[featured["__frozen_helper_alert"].fillna(False)] = "frozen_channel_helper"
    featured["__decision_route"] = route

    print("\n--- EVIDENCE / CONFIDENCE AUDIT ---")
    print("Decision routes (the deployed final decision mechanism):")
    route_summary = pd.DataFrame({
        "rows": route.value_counts(),
        "true_anomalies": featured.groupby("__decision_route")["is_anomaly"].sum(),
        "final_alerts": featured.groupby("__decision_route")["__predicted"].sum(),
    }).fillna(0).astype(int)
    print(route_summary.to_string())

    print("\nScore distribution (all evaluated rows; values are 0--100):")
    distribution = pd.DataFrame({
        "model": model,
        "rules": rule,
        "overall": overall,
    }).quantile([0, .25, .5, .75, .9, .95, .99, 1]).T.round(1)
    print(distribution.to_string())

    sample = featured.loc[
        featured["__predicted"] | featured["is_anomaly"],
        ["station_id", "timestamp", "fault_type", "is_anomaly", "__predicted",
         "__decision_route", "__model_pct", "__rule_confidence_pct", "__score_pct"],
    ].copy()
    sample = sample.sort_values(
        ["is_anomaly", "__predicted", "__score_pct"],
        ascending=[False, False, False],
    ).head(12)
    sample.to_csv(EVIDENCE_SAMPLE_PATH, index=False)
    print(f"\n12 evidence samples -> {EVIDENCE_SAMPLE_PATH}")


def evaluate_all(labeled_files: list, artifact: dict) -> dict:
    frames = []
    for path in labeled_files:
        d = pd.read_csv(path, parse_dates=["timestamp"])
        if "is_anomaly" not in d.columns:
            raise ValueError(f"{path.name} has no is_anomaly column -- is this actually a _labeled.csv?")
        d["__source_file"] = path.name
        frames.append(d)
    df_full = pd.concat(frames, ignore_index=True)
    df_full = add_frozen_channel_labels_from_reference(df_full)

    has_fault_type = "fault_type" in df_full.columns
    label_cols = ["station_id", "timestamp", "is_anomaly", "__source_file"] + (["fault_type"] if has_fault_type else [])
    labels = df_full[label_cols].copy()
    labels["is_anomaly"] = labels["is_anomaly"].fillna(False).astype(bool)
    labels["fault_type"] = labels["fault_type"].fillna("none") if has_fault_type else "none"

    df = df_full.drop(columns=["is_anomaly", "fault_type", "__source_file"], errors="ignore")

    # PASS 1: no exclusion. A real fault's own extreme values sit inside
    # every recovery reading's rolling window for up to ROLLING_WINDOW_HOURS
    # after the fault ends, inflating those clean rows' model score.
    featured_p1, _ = _featurize(df)
    model_pct_p1 = vectorized_model_scores(featured_p1, artifact)
    hard_p1 = pd.Series(False, index=featured_p1.index)
    for col, (low, high) in PHYSICAL_BOUNDS.items():
        hard_p1 |= (featured_p1[col] < low) | (featured_p1[col] > high) | featured_p1[col].isna()
    predicted_p1 = hard_p1.to_numpy() | (model_pct_p1 >= PASS1_MASK_MODEL_THRESHOLD)

    # PASS 2: re-featurize using PASS 1's OWN PREDICTIONS (never ground
    # truth -- that would be look-ahead) as the exclusion mask,
    # approximating live detect.py/state.py's self-healing baseline.
    df_pass2 = df.merge(
        featured_p1[["station_id", "timestamp"]].assign(__pass1_flag=predicted_p1),
        on=["station_id", "timestamp"], how="left",
    )
    df_pass2["__pass1_flag"] = df_pass2["__pass1_flag"].fillna(False)
    featured, n_dropped_total = _featurize(df_pass2, mask_col="__pass1_flag")

    print(f"\n(Two-pass eval -- pass 1 flagged {int(predicted_p1.sum())} rows for baseline "
          f"exclusion; pass 2 re-featurizes around them. Rule engine + reported numbers "
          f"below are computed once, on PASS 2's features.)")

    featured, row_hard, row_rule_conf, per_sensor_log, recovery_log = run_rule_engine_and_health(featured, artifact)
    model_pct = vectorized_model_scores(featured, artifact)

    overall_confidence = (
        MODEL_WEIGHT * model_pct
        + RULE_WEIGHT * row_rule_conf
    )

    predicted = (
        row_hard
        | (overall_confidence > FUSION_ANOMALY_THRESHOLD)
        | (model_pct > MODEL_ALONE_OVERRIDE_THRESHOLD)
        # Keep frozen floor-match (90) in evidence fusion rather than
        # promoting it to a hard verdict; see detect.py's matching
        # Draft 2 §1 safeguard.
        | (row_rule_conf > RULE_CONFIDENCE_BYPASS)
    )

    # Frozen-specific model gate (Pass 6). frozen_value confidence=80 (below
    # RULE_CONFIDENCE_BYPASS=90) so it goes through fusion. Clean stable-weather
    # outlier rows score model_pct 60-94 and can slip past fusion. Suppress
    # predictions where frozen is the SOLE evidence and model_pct is below
    # FROZEN_MIN_MODEL_CORROBORATION=65. Rows with drift(85) or stronger rules
    # are unaffected since their row_rule_conf > 80.
    frozen_only = row_rule_conf == RULE_BASE_CONFIDENCE['frozen_value']
    predicted = predicted & ~(frozen_only & (model_pct < FROZEN_MIN_MODEL_CORROBORATION))

    # Network-aware supervised helper -------------------------------------------------
    # Train on fresh fault placements in stations that are entirely clean in the
    # labelled replay.  This preserves the existing replay as held-out test data
    # while giving the helper examples of the injector's frozen/drift/spike
    # dynamics and trustworthy contemporaneous neighbours.
    helper_held_out_stations = set(labels.loc[labels["is_anomaly"], "station_id"])
    helper_training = make_sparse_training_replays(helper_held_out_stations, HELPER_TRAINING_SEEDS)
    helper_model, helper_columns = fit_fault_helper(helper_training)
    helper_scored = predict_faults(helper_model, helper_columns, df_full, HELPER_ALERT_THRESHOLD)
    frozen_helpers = fit_frozen_channel_helpers(helper_training)
    helper_scored = score_frozen_channels(
        helper_scored, frozen_helpers, FROZEN_HELPER_ALERT_THRESHOLD,
    )
    helper_lookup = helper_scored.set_index(["station_id", "timestamp"])["helper_alert"]
    helper_alert = pd.MultiIndex.from_frame(featured[["station_id", "timestamp"]]).map(helper_lookup).fillna(False).to_numpy(dtype=bool)
    frozen_lookup = helper_scored.set_index(["station_id", "timestamp"])["frozen_helper_alert"]
    frozen_helper_alert = pd.MultiIndex.from_frame(featured[["station_id", "timestamp"]]).map(frozen_lookup).fillna(False).to_numpy(dtype=bool)
    predicted = predicted | helper_alert | frozen_helper_alert
    print(
        f"\n(Network helper: {int(helper_alert.sum())} general alerts at threshold "
        f"{HELPER_ALERT_THRESHOLD:.2f}; {int(frozen_helper_alert.sum())} frozen-channel "
        f"alerts at threshold {FROZEN_HELPER_ALERT_THRESHOLD:.2f}; trained on fresh sparse replays with "
        f"seeds {HELPER_TRAINING_SEEDS}.)"
    )

    featured = featured.merge(labels, on=["station_id", "timestamp"], how="left")
    featured["is_anomaly"] = featured["is_anomaly"].fillna(False).astype(bool)
    featured["fault_type"] = featured["fault_type"].fillna("none")
    featured["__source_file"] = featured["__source_file"].fillna("unknown")
    featured["__predicted"] = predicted
    featured["__model_pct"] = model_pct
    featured["__rule_confidence_pct"] = row_rule_conf
    featured["__score_pct"] = overall_confidence
    featured["__helper_alert"] = helper_alert
    featured["__frozen_helper_alert"] = frozen_helper_alert

    _print_evidence_audit(featured)

    if not per_sensor_log.empty:
        per_sensor_log.to_csv(PER_SENSOR_LOG_PATH, index=False)
        print(f"\nPer-station/per-sensor fault log ({len(per_sensor_log)} flagged readings) -> {PER_SENSOR_LOG_PATH}")
        print(per_sensor_log.groupby(["station_id", "parameter", "fault_type"]).size()
              .rename("count").reset_index().to_string(index=False))
    else:
        print("\nNo readings were flagged by the rule engine -- per-sensor log is empty.")

    print(f"\n--- AUTO-RECOVERY DIAGNOSTIC (§10) ---")
    if not recovery_log.empty:
        recovery_log.to_csv(RECOVERY_LOG_PATH, index=False)
        stuck = recovery_log[recovery_log["recovered_at"].isna()]
        recovered = recovery_log[~recovery_log["recovered_at"].isna()]
        print(f"{len(recovered)} OFFLINE episode(s) recovered within the run "
              f"(mean duration {recovered['duration_hours'].mean():.1f}h)." if len(recovered) else
              "No OFFLINE episodes recovered within the run.")
        if len(stuck):
            print(f"{len(stuck)} sensor(s) STILL OFFLINE at end of run:")
            print(stuck[["station_id", "parameter", "offline_since"]].to_string(index=False))
        print(f"Full recovery log -> {RECOVERY_LOG_PATH}")
    else:
        print("No OFFLINE episodes occurred during this run.")

    print(f"\n{'=' * 60}\nOVERALL (all {len(labeled_files)} files combined, two-pass)\n{'=' * 60}")
    results = {"__overall__": _score_and_report(featured, "ALL FILES COMBINED", n_dropped_total)}

    for source_file, group in featured.groupby("__source_file"):
        n_in_file = int((df_full["__source_file"] == source_file).sum())
        n_dropped_file = n_in_file - len(group)
        results[source_file] = _score_and_report(group.reset_index(drop=True), source_file, n_dropped_file)

    return results


if __name__ == "__main__":
    if not ARTIFACTS_PATH.exists():
        raise FileNotFoundError(f"No trained model at {ARTIFACTS_PATH} -- run model/train.py first.")
    artifact = joblib.load(ARTIFACTS_PATH)
    if "rule_thresholds" not in artifact:
        raise KeyError(
            "Loaded artifact has no 'rule_thresholds' key -- it was saved by an older "
            "train.py, before calibrate_rule_thresholds() was added. Retrain first."
        )

    labeled_files = sorted(DATA_DIR.glob("*_labeled.csv"))
    if not labeled_files:
        print(f"No *_labeled.csv files found in {DATA_DIR} -- run anomaly_injector.py first.")
    else:
        print(f"Evaluating against {len(labeled_files)} labeled file(s). Remember: this measures "
              f"detection of OUR OWN injected fault patterns -- see the module docstring's "
              f"overfitting caution before reporting these numbers.")
        evaluate_all(labeled_files, artifact)
