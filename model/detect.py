"""
SkyGuard AI — Detection engine (rebuilt around SKYGUARD_ARCHITECTURE_DRAFT_2.md).

Combines the trained Isolation Forest with SEVEN independent rule
checks into one fused verdict per reading, PLUS the per-station,
per-PARAMETER "circuit breaker" (mark a specific sensor OFFLINE and
stop trusting its data).

THIS IS A FULL REDESIGN, not a patch on the old cascade. Read this
before touching anything below.

===========================================================================
WHAT CHANGED FROM THE OLD detect.py, AND WHY
===========================================================================

1. SPATIAL FEATURES REMOVED ENTIRELY (Draft 2 §9). `SPATIAL_COLS`,
   `compute_raw_spatial_devs`, the `spatial_baselines` z-scoring block,
   and the `_raw_spatial_devs` verdict key are all gone. `score_reading`
   still ACCEPTS `cluster_neighbor_buffers=`/`spatial_baselines=` as
   optional, silently-ignored kwargs -- not because they do anything,
   but because state.py still passes them and hasn't been updated yet
   (state.py isn't in this pass's scope). Remove them from the call
   site when state.py gets its turn; until then this keeps state.py
   from crashing.

2. FROZEN (§1) is now deterministic, not calibrated. features.py
   computes `{prefix}_floor_frozen_match` once (floor(reading) equal
   across the last 3 readings) -- this file just reads that boolean off
   the feature row. No variance/range floors, no consec_diff threshold.
   The old Phase-1 variance/range experiment is RETIRED (see Draft 2 §0
   postmortem: it inflated false positives on ordinary calm weather).
   `config.py`'s `FROZEN_VARIANCE_FLOOR`/`FROZEN_RANGE_FLOOR` are dead
   and intentionally NOT imported here anymore.

3. DRIFT (§2) is now CUSUM, not a calibrated 24h-delta threshold. A
   fresh S+/S- accumulator is recomputed from the station's own causal
   buffer every call (see `_cusum_evidence` / `_featurize_buffer`) --
   stateless by construction, consistent with how this file has always
   treated `history_df` as the single source of truth rather than
   carrying hidden state across calls. `CUSUM_DRIFT_ALLOWANCE`/
   `CUSUM_THRESHOLD` are domain-estimated placeholders (see constants
   block) pending a real calibration pass once evaluate.py can run
   against CUSUM-compatible (direction-consistent) injected drift.

4. MULTIVARIATE INCONSISTENCY is a NEW rule (didn't exist as an
   explicit rule before -- it only ever lived implicitly inside the
   Isolation Forest's feature space). Built on the existing
   `temp_humidity_coupling_signal` / `pressure_inconsistency` cross-
   parameter features. Per §4/§8: a single qualifying reading is
   "suspicious" (lower confidence, does NOT force OFFLINE on its own);
   2 CONSECUTIVE qualifying readings is "confirmed" (high confidence,
   forces immediate OFFLINE via the fast-path set). This is also the
   reference implementation of §8's worked example: fault_type
   resolution is not a fixed priority table, it's just "whichever rule
   currently has the highest confidence wins" -- see `_fuse_and_score`.

5. SENSOR FAIL-LOW is a NEW rule (§5b), distinct from spike. Fires only
   once persisted for `FAIL_LOW_CONSECUTIVE_REQUIRED` consecutive
   readings at/below a per-parameter near-zero floor -- by construction
   it never fires on a single occurrence, so every fail-low firing is
   already a confirmed fast-path OFFLINE event.

6. EVIDENCE FUSION REPLACES THE OLD HARD-GATE CASCADE (§7). The old
   `HARD_RULE_TYPES`/`SOFT_RULE_TYPES`/`HARD_RULE_FLOOR`/`SOFT_RULE_FLOOR`
   architecture is GONE. That architecture is the confirmed root cause
   of Phase 1's failure (see Draft 2 §0): `SOFT_RULE_FLOOR` and
   `IS_ANOMALY_THRESHOLD` were numerically identical, so ANY soft rule
   firing was an unconditional, undampened anomaly verdict -- a rule's
   raw false-positive rate propagated 1:1 into the confusion matrix.
   Replaced with: every rule carries its own confidence (0-100,
   `RULE_BASE_CONFIDENCE`), the strongest single piece of rule evidence
   this reading is `rule_confidence_pct`, and:

       overall = 0.6 * model_pct + 0.4 * rule_confidence_pct
       is_anomaly = overall > 55  OR  model_pct > 80  OR  rule_confidence_pct > 90

   REBALANCED (config.py, this pass): the constants previously in place
   here (FUSION_ANOMALY_THRESHOLD=90, MODEL_ALONE_OVERRIDE_THRESHOLD=100)
   reproduced Phase 1's exact deadlock under a different name --
   MODEL_ALONE_OVERRIDE_THRESHOLD=100 meant the (0-100 clipped) model
   could NEVER independently flag anything, and FUSION_ANOMALY_THRESHOLD
   =90 meant no rule below RULE_CONFIDENCE_BYPASS could clear the
   blended threshold even with a maximal model score -- so in practice
   `is_anomaly` reduced to `rule_confidence_pct > 90`, i.e. whichever
   rules happened to sit above that line (frozen/fail-low/drift/spike/
   multivariate_confirmed, all 95) fired unconditionally, exactly the
   retired hard-gate pattern. Confirmed independently by both the
   context-pass math and the technical-assessment audit. Fixed by
   lowering FUSION_ANOMALY_THRESHOLD to 55 and MODEL_ALONE_OVERRIDE_
   THRESHOLD to 80, and by moving multivariate_confirmed's own
   confidence below RULE_CONFIDENCE_BYPASS (95 -> 82) since its trigger
   shape is the one most directly built around anomaly_injector.py's
   specific implementation (see _multivariate_evidence's docstring) --
   see config.py for the full reasoning per constant.

   `anomaly_score_pct` / severity (90/70/55) keep their exact existing
   scale and meaning -- this changes what feeds the score, not the
   contract, same principle every prior phase already committed to.

7. `verdict` now carries `model_confidence_pct` and `rule_confidence_pct`
   as new additive fields -- direct request from Draft 2 ("produce a
   model confidence score in each reading"). Nothing existing reads
   these yet; they don't remove or rename anything.

8. SensorHealthTracker is now PER-PARAMETER internally (§1's "a frozen
   pressure sensor shouldn't take temp/humidity offline with it", §6's
   per-(station,parameter) 10h/24h counters, §4/§5b's per-parameter
   fast paths). Its EXTERNAL surface (`.status`, `.offline_reason`,
   `.record()`, `.should_include_in_baseline()`) is kept intact so
   state.py keeps working unmodified for now -- `.status`/
   `.offline_reason` are now a station-level AGGREGATE computed from the
   richer per-parameter state (`self.param_status`, new, not yet
   consumed anywhere -- exposed for when state.py/main.py get their own
   pass to surface real per-sensor status to the frontend).

   KNOWN LIMITATION, FLAGGED NOT FIXED (belongs to state.py's next
   pass): `should_include_in_baseline()` is still a single station-wide
   boolean, because state.py's raw history buffer stores whole rows
   (all 3 params together) -- excluding just one OFFLINE parameter's
   value while keeping the other two needs columnar buffering, which
   is a state.py redesign, not something fixable from inside this file.
   For now: ANY parameter OFFLINE excludes the WHOLE row, same
   conservative behavior as before.

   ALSO FLAGGED: state.py's `StationBuffer.mark_repaired()` currently
   pokes `self.health.status`/`self.health.offline_reason`/
   `self.health._clean_streak` directly. Those station-level attributes
   still exist here for compatibility, but repairing a station no
   longer resets the new PER-PARAMETER streaks/counters underneath them
   -- a real gap, needs a state.py-side fix when that file's turn comes.

9. UNIFIED 10h/24h WINDOW (§6): general, MIXED-fault-type, per-parameter
   counters, running alongside every rule's own specific mechanism, not
   instead of it. `WINDOW_10H_TRIGGER`/`WINDOW_24H_TRIGGER` are picked
   at 4 (within the user's stated "4-5" range) -- one readings-per-hour
   assumption, same simplification `HEALTH_WINDOW_SIZE` already made
   pre-redesign.

10. `RECOVERY_CLEAN_STREAK_REQUIRED` is still imported from `config.py`
    (currently 5 there) rather than hardcoded -- when config.py's own
    pass lands and drops it to 3 (locked, Draft 2 §11.1), this file
    picks the new value up automatically, no further edit needed here.

===========================================================================
CONSTANTS NOT YET IN config.py
===========================================================================
Per Draft 2 §11's file order, config.py is a LATER step. Everything new
this file needs (CUSUM allowance/threshold, multivariate thresholds,
fail-low floors, fusion weights, window triggers) is defined locally
below, same style the pre-redesign file already used for
IS_ANOMALY_THRESHOLD/MODEL_ONLY_THRESHOLD/HARD_RULE_FLOOR etc. These are
DOMAIN-ESTIMATED PLACEHOLDERS pending a real evaluate.py run -- flagged
individually below, not silently presented as tuned.
"""

import sys
from collections import deque
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from model.features import (
    build_features_for_latest,
    add_temporal_features,
    add_cross_parameter_features,
    RULE_ONLY_PREFIXES,
    get_threshold,
)
from model.explain import likely_faulty_params
from model.seasonal_baseline import get_expected_roc

from config import (
    score_to_severity,
    RECOVERY_CLEAN_STREAK_REQUIRED,
    MODEL_WEIGHT,
    RULE_WEIGHT,
    FUSION_ANOMALY_THRESHOLD,
    MODEL_ALONE_OVERRIDE_THRESHOLD,
    RULE_CONFIDENCE_BYPASS,
    SPIKE_REVERSION_RATIO,
    SPIKE_DEVIATION_MULTIPLIER,
    RULE_BASE_CONFIDENCE,
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
    MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT,
    MULTIVARIATE_ATTRIBUTION_DOMINANCE,
    FAIL_LOW_FLOOR,
    FAIL_LOW_CONSECUTIVE_REQUIRED,
    WINDOW_10H_SIZE,
    WINDOW_10H_TRIGGER,
    WINDOW_24H_SIZE,
    WINDOW_24H_TRIGGER,
)

ARTIFACTS_PATH = Path(__file__).parent.parent / "model_artifacts" / "isolation_forest.pkl"

# Same hard physical ceilings used in anomaly_injector.py's clip step --
# duplicated intentionally, not imported: this is a genuinely
# independent check (what CAN physically be true), not shared
# fault-generation logic.
PHYSICAL_BOUNDS = {
    "temperature_c": (-10.0, 55.0),
    "pressure_hpa": (850.0, 1080.0),
    "humidity_pct": (0.0, 100.0),
}

# (raw_column -> features.py prefix), single source of truth imported
# from features.py.
PARAM_PREFIXES = dict(RULE_ONLY_PREFIXES)
PARAMS = list(PARAM_PREFIXES.keys())


# ---------------------------------------------------------------------
# Rule confidence (§7) -- replaces the old HARD/SOFT floor tiers.
# Each is "how sure is this ONE piece of evidence, on its own, that
# something is really wrong" -- fusion combines the strongest one with
# the model score, it does not stack multiple simultaneous rules.
#
# physical_bounds / dropout: unambiguous facts (100) -- unchanged from
#   before, these were always the "certain" tier.
# frozen_value: deterministic floor-match, no calibration uncertainty,
#   but still just 3 readings -- 90, not 100.
# sensor_fail_low: fires only once persistence-confirmed (see
#   FAIL_LOW_CONSECUTIVE_REQUIRED) -- 95.
# drift: CUSUM already requires sustained one-directional accumulation
#   to cross its threshold at all -- 85.
# spike: single-reading by definition (§3) -- deliberately modest (60)
#   so one spike alone rarely clears the fusion threshold unassisted;
#   frequency-based escalation is the health tracker's job (§6), not
#   this rule's own confidence.
# multivariate_single / multivariate_confirmed: §4/§8's worked example
#   -- one qualifying reading is suspicious only (55), two consecutive
#   is confirmed (95) and also triggers the fast-path OFFLINE set.
# ---------------------------------------------------------------------
def load_model():
    """
    Loads the trained model artifact ONCE -- call this at API startup, not per-request.

    Track A (blueprint §1): also loads fault_helper.pkl if it exists alongside
    isolation_forest.pkl.  When both are present, score_reading() OR's the
    helper's alert into is_anomaly, matching evaluate.py's offline eval pipeline
    exactly (previously the live path never called fault_helper, so demo metrics
    and eval metrics diverged).

    Graceful fallback: if fault_helper.pkl is missing (e.g. not yet trained),
    a warning is logged and the system continues with the Isolation Forest + rules
    alone.  The artifact dict gets a None 'fault_helper' key so score_reading()
    can always check `artifact.get('fault_helper')` without an attribute error.
    """
    import logging
    _log = logging.getLogger(__name__)

    if not ARTIFACTS_PATH.exists():
        raise FileNotFoundError(f"No trained model at {ARTIFACTS_PATH} -- run model/train.py first.")
    artifact = joblib.load(ARTIFACTS_PATH)
    if "rule_thresholds" not in artifact:
        raise KeyError(
            "Loaded artifact has no 'rule_thresholds' key -- it was saved by an older "
            "train.py, before calibrate_rule_thresholds() was added. Retrain with the "
            "current train.py before running detection."
        )

    # Load fault_helper (Track A).
    fault_helper_path = ARTIFACTS_PATH.parent / "fault_helper.pkl"
    if fault_helper_path.exists():
        try:
            artifact["fault_helper"] = joblib.load(fault_helper_path)
            _log.info("[detect] fault_helper loaded from %s", fault_helper_path)
        except Exception as exc:
            _log.warning("[detect] Could not load fault_helper.pkl: %s -- continuing without it.", exc)
            artifact["fault_helper"] = None
    else:
        _log.warning(
            "[detect] fault_helper.pkl not found at %s -- "
            "live detection uses Isolation Forest + rules only. "
            "Run model/fault_helper.py training to restore evaluate.py parity.",
            fault_helper_path,
        )
        artifact["fault_helper"] = None

    return artifact



def _model_score_to_pct(raw_reading: dict, feature_row: pd.Series, artifact: dict) -> float:
    """
    Converts Isolation Forest's raw decision_function output into a
    0-100 "anomaly score." Centered on 0 (the model's own contamination-
    calibrated outlier boundary), NOT training_score_mean. Unchanged
    from before -- this math was never the problem.
    """
    model = artifact["model"]
    X = feature_row[artifact["feature_columns"]].values.reshape(1, -1).astype(np.float64)

    if np.isnan(X).any():
        return None

    raw_score = model.decision_function(X)[0]
    z = (0.0 - raw_score) / (artifact["training_score_std"] + 1e-9)
    pct = 100 / (1 + np.exp(-1.5 * z))
    return float(np.clip(pct, 0, 100))


def _featurize_buffer(history_df: pd.DataFrame) -> pd.DataFrame:
    """
    Shared helper for the two rule checks (CUSUM, multivariate) that
    need more than the single latest feature row -- runs the same
    add_temporal_features -> add_cross_parameter_features pipeline
    build_features_for_latest uses internally, but returns the WHOLE
    featured buffer instead of just the last row, computed ONCE per
    score_reading() call and shared by both checks rather than each
    re-deriving it separately.

    FIXED: this previously called add_temporal_features only, despite
    the docstring above already claiming otherwise -- add_
    cross_parameter_features didn't exist in features.py yet at the
    time this was written. It exists now (dewpoint_depression_c,
    vapor_pressure_deficit_kpa, vapor_pressure_consistency_dev); wiring
    it in here is what _multivariate_evidence's new physics-based path
    below actually needs.
    """
    df = history_df.sort_values("timestamp").reset_index(drop=True)
    df = add_temporal_features(df)
    df = add_cross_parameter_features(df)
    return df


def _cusum_evidence(
    featured_buffer: pd.DataFrame,
    prefix: str,
    param: str,
    station_id: str = "",
    current_hour: int = 0,
):
    """
    Recomputes the CUSUM S+/S- accumulator from scratch over the
    station's own causal buffer every call -- stateless by construction
    (see module docstring #3).

    DIURNAL HARDENING (SEA6/CUSUM3 in bug audit):
    Instead of accumulating the raw normalized_roc_1h, we accumulate
    the RESIDUAL:  (actual_roc - expected_roc) / rolling_std.

    UNIT FIX: the previous version subtracted raw °C/h (from
    seasonal_baseline) from normalized_roc_1h (a dimensionless z-score:
    roc_1h / rolling_std).  This unit mismatch made the seasonal
    hardening completely non-functional — normal morning warming at
    +1.7°C/h produced norm_roc=3.83 minus expected=1.95 = residual
    +1.88, which accumulated and triggered false drift.  Fixed: use
    raw roc_1h, subtract expected_roc in matching °C/h units, THEN
    divide by rolling_std to normalize.

    expected_roc comes from seasonal_baseline.py which loads the real
    3-month historical CSV (Open-Meteo data) once and caches it.  A
    normal sunrise warming trend (e.g. +1.7°C/h at hour 8) has an
    expected_roc ~+1.95°C/h at that hour, so its raw residual ≈ -0.25
    and the normalized residual ≈ -0.06σ — CUSUM stays near 0.  A real
    sensor drift fault deviates from the seasonal baseline, so its
    residual accumulates.

    Fallback: if no historical data exists for this station (new station,
    warm-up), get_expected_roc returns 0.0, reproducing the original
    pre-hardening behavior exactly -- safe, not silent.

    The data source is swappable: replace seasonal_baseline._load_csv()
    with a TimescaleDB or API call without changing this function.
    """
    roc_col = f"{prefix}_roc_1h"
    std_col = f"{prefix}_rolling_std"
    if roc_col not in featured_buffer.columns:
        return None

    # We need both raw ROC and rolling_std to compute the correct residual.
    valid_mask = featured_buffer[roc_col].notna()
    if std_col in featured_buffer.columns:
        valid_mask = valid_mask & featured_buffer[std_col].notna() & (featured_buffer[std_col] > 0)
    valid_indices = featured_buffer.index[valid_mask]
    if valid_indices.empty:
        return None

    # Build per-step hours for hour-aware baseline lookup.
    if "timestamp" in featured_buffer.columns:
        step_hours = pd.to_datetime(featured_buffer.loc[valid_indices, "timestamp"]).dt.hour.to_numpy()
    else:
        step_hours = np.full(len(valid_indices), current_hour, dtype=int)

    raw_rocs = featured_buffer.loc[valid_indices, roc_col].to_numpy()
    stds = (
        featured_buffer.loc[valid_indices, std_col].to_numpy()
        if std_col in featured_buffer.columns
        else np.ones(len(valid_indices))
    )

    s_pos = s_neg = 0.0
    for raw_roc, std_val, h in zip(raw_rocs, stds, step_hours):
        if raw_roc is None or not np.isfinite(raw_roc):
            continue
        raw_roc = float(raw_roc)
        std_val = float(std_val) if (std_val is not None and np.isfinite(std_val) and std_val > 0) else 1.0
        # Subtract the expected diurnal ROC (same raw units: °C/h)
        # THEN normalize by rolling_std so the accumulator is in σ-units.
        expected = get_expected_roc(station_id, prefix, int(h))
        residual = (raw_roc - expected) / std_val
        # Direction-preserving accumulation on the normalized residual.
        s_pos = max(0.0, s_pos + residual - CUSUM_DRIFT_ALLOWANCE) if residual > 0 else 0.0
        s_neg = max(0.0, s_neg - residual - CUSUM_DRIFT_ALLOWANCE) if residual < 0 else 0.0

    raw_steps = featured_buffer[param].diff().dropna().to_numpy()
    direction_consistent = False
    if len(raw_steps) >= CUSUM_DIRECTION_STREAK_REQUIRED:
        recent_steps = raw_steps[-CUSUM_DIRECTION_STREAK_REQUIRED:]
        # Allow up to 2 steps to go against the trend (natural noise overriding the drift)
        direction_consistent = (
            np.sum(recent_steps > 0) >= CUSUM_DIRECTION_STREAK_REQUIRED - 2
            or np.sum(recent_steps < 0) >= CUSUM_DIRECTION_STREAK_REQUIRED - 2
        )
    if direction_consistent and (s_pos > CUSUM_THRESHOLD or s_neg > CUSUM_THRESHOLD):
        return ("drift", param, RULE_BASE_CONFIDENCE["drift"])
    return None


def _multivariate_evidence(featured_buffer: pd.DataFrame):
    """
    §4/§8's reference implementation. TWO independent trigger paths
    (see config.py's MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD comment
    for why there are now two, not one):

      (a) LEVEL-based co-occurrence (original): temp+humidity both
          deviate from baseline, same direction, pressure stays flat.
      (b) NEW -- direct vapor-pressure-conservation violation, via
          features.py's vapor_pressure_consistency_dev. This is the
          general case: (a) additionally requires pressure to stay
          flat, which is true of THIS injector's implementation but
          not a fact about real cross-talk/short-circuit faults in
          general (a real fault could move pressure too, and (a) alone
          would then miss it). (b) looks only at whether the observed
          T/RH pair is consistent with itself one reading back, so it
          doesn't inherit that injector-specific assumption.

    A single qualifying reading (either path) is suspicious only (does
    not force OFFLINE); 2 CONSECUTIVE qualifying readings (either path,
    not necessarily the same one on both readings) is confirmed
    (forces OFFLINE via the fast-path set).

    ATTRIBUTION FIX: this used to blanket-mark BOTH temperature_c and
    humidity_pct on every confirmed hit, with no magnitude comparison
    at all -- a real regression against §4's explicit ask ("inspect
    which raw parameter(s) are actually driving the inconsistency...
    temp weighted more heavily than humidity in ambiguous joint
    moves"), introduced to stop detect.py/evaluate.py disagreeing on
    which sensor gets marked, but which threw out the weighting logic
    in the process instead of porting it correctly. evaluate.py's
    parallel rule engine already had this right; this brings detect.py
    in line with it -- same MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT (1.5)
    and same MULTIVARIATE_ATTRIBUTION_DOMINANCE (0.7) ratio-of-dominant
    check evaluate.py uses, so the two engines can't silently blame
    different sensors for the same event again.

    One deliberate difference from evaluate.py, not an oversight:
    evaluate.py computes this ratio from {prefix}_normalized_roc_1h
    (its own multivariate TRIGGER is roc-based, via the coupling/
    pressure_inconsistency features). THIS file's level-based path (a)
    reads the SAME level signals that drove path (a)'s own trigger, not
    a second, independently-chosen signal family -- using roc here
    instead would reintroduce exactly the kind of "two derivations of
    the same idea that can drift apart" bug this project has hit before
    (see RULE_ONLY_PREFIXES's own comment in features.py). Attribution
    for path (b)-only hits falls back to the same temp/humidity_dev
    comparison, since vapor_pressure_consistency_dev doesn't itself
    say which sensor is "wrong" -- only that the pair, together, is.

    Pressure is the "should have moved but didn't" reference signal
    used only to help path (a) FIRE -- it is never itself implicated
    (§4).
    """
    if len(featured_buffer) == 0:
        return [], set()

    def _fires(row) -> bool:
        temp_dev = row.get("temp_deviation")
        humidity_dev = row.get("humidity_deviation")
        pressure_dev = row.get("pressure_deviation")
        level_fires = (
            pd.notna(temp_dev) and pd.notna(humidity_dev) and pd.notna(pressure_dev)
            and abs(temp_dev) > MULTIVARIATE_TEMP_DEVIATION_THRESHOLD
            and abs(humidity_dev) > MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD
            and (temp_dev * humidity_dev) > 0  # same direction -- §4's "temp up, humidity ALSO up"
            and abs(pressure_dev) < MULTIVARIATE_PRESSURE_FLAT_THRESHOLD
        )
        vapor_dev = row.get("vapor_pressure_consistency_dev")
        physics_fires = pd.notna(vapor_dev) and abs(vapor_dev) > MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD
        return level_fires or physics_fires

    latest = featured_buffer.iloc[-1]
    if not _fires(latest):
        return [], set()

    confirmed = len(featured_buffer) >= 2 and _fires(featured_buffer.iloc[-2])

    confidence = (
        RULE_BASE_CONFIDENCE["multivariate_confirmed"] if confirmed
        else RULE_BASE_CONFIDENCE["multivariate_single"]
    )

    # --- weighted attribution: which param(s) actually implicated ---
    temp_dev = latest.get("temp_deviation")
    humidity_dev = latest.get("humidity_deviation")
    temp_mag = abs(temp_dev) * MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT if pd.notna(temp_dev) else 0.0
    humidity_mag = abs(humidity_dev) if pd.notna(humidity_dev) else 0.0
    dominant_mag = max(temp_mag, humidity_mag) or 1.0

    implicated = []
    if temp_mag / dominant_mag >= MULTIVARIATE_ATTRIBUTION_DOMINANCE:
        implicated.append("temperature_c")
    if humidity_mag / dominant_mag >= MULTIVARIATE_ATTRIBUTION_DOMINANCE:
        implicated.append("humidity_pct")
    if not implicated:
        # Guard only -- the dominant param always clears its own 1.0
        # ratio against itself, so this shouldn't trigger in practice.
        # Kept so a confirmed multivariate hit can never silently
        # implicate nobody.
        implicated = ["temperature_c"] if temp_mag >= humidity_mag else ["humidity_pct"]

    evidence = [("multivariate_inconsistency", param, confidence) for param in implicated]
    fast_path = set(implicated) if confirmed else set()
    return evidence, fast_path


def _confirmed_spikes(featured_buffer: pd.DataFrame, thresholds: dict, station_id: str) -> list[dict]:
    """Confirm the prior reading as a spike once a current reading reverts.

    At time t+1, t+2, or t+3 we can finally distinguish `normal -> extreme(s) -> normal`
    from a real, sustained weather move. The returned event belongs to
    the bad raw reading, not the confirming reading.
    """
    confirmed = []
    n = len(featured_buffer)
    if n < 3:
        return confirmed

    current = featured_buffer.iloc[-1]
    
    for param, prefix in PARAM_PREFIXES.items():
        spike_threshold = get_threshold(thresholds, "spike", prefix, station_id)
        current_val = current.get(param)
        if pd.isna(current_val):
            continue
            
        # Check if the current reading confirms a candidate spike from 1, 2, or 3 steps ago
        for step in range(1, 4):
            if n < step + 2:
                break
                
            candidate = featured_buffer.iloc[-(step + 1)]
            before = featured_buffer.iloc[-(step + 2)]
            
            before_val = before.get(param)
            candidate_val = candidate.get(param)
            
            if pd.isna(before_val) or pd.isna(candidate_val):
                continue
                
            jump = abs(candidate_val - before_val)
            if jump == 0:
                continue
                
            candidate_dev = candidate.get(f"{prefix}_deviation")
            if pd.isna(candidate_dev) or abs(candidate_dev) <= spike_threshold * SPIKE_DEVIATION_MULTIPLIER:
                continue
                
            # If it reverted to baseline NOW
            if abs(current_val - before_val) <= jump * SPIKE_REVERSION_RATIO:
                confirmed.append({
                    "parameter": param,
                    "timestamp": pd.Timestamp(candidate["timestamp"]),
                    "observed_value": float(candidate_val),
                    "suggested_value": round(float((before_val + current_val) / 2), 2),
                })
                break  # we confirmed a spike for this parameter, stop checking older steps
                
    return confirmed


def _rule_checks(raw_reading: dict, feature_row: pd.Series, history_df: pd.DataFrame, artifact: dict) -> dict:
    """
    Seven independent checks, each computed on its own terms -- no rule
    here "wins" over another; that resolution happens in
    _fuse_and_score via confidence, not here (§8).

    Returns {"fired": [(rule_type, param, confidence), ...], "any": bool,
    "fast_path_offline_params": set(param)} -- the fast-path set is
    populated by rules whose OWN persistence/confirmation criteria are
    already the full bar for immediate OFFLINE (confirmed multivariate,
    confirmed fail-low), so SensorHealthTracker doesn't need to
    re-derive that persistence logic a second time.
    """
    fired = []
    fast_path_offline_params = set()
    thresholds = artifact["rule_thresholds"]
    station_id = raw_reading.get("station_id") or history_df["station_id"].iloc[-1]

    # physical_bounds -- unambiguous, unchanged.
    for param, (low, high) in PHYSICAL_BOUNDS.items():
        val = raw_reading.get(param)
        if val is not None and not pd.isna(val) and not (low <= val <= high):
            fired.append(("physical_bounds", param, RULE_BASE_CONFIDENCE["physical_bounds"]))

    # frozen_value -- §1, deterministic floor-match computed once in
    # features.py; this file just reads the boolean off feature_row.
    for param, prefix in PARAM_PREFIXES.items():
        req = FROZEN_CONSECUTIVE_REQUIRED_PRESSURE if param == "pressure_hpa" else FROZEN_CONSECUTIVE_REQUIRED
        if feature_row.get(f"{prefix}_frozen_streak", 0) >= req:
            fired.append(("frozen_value", param, RULE_BASE_CONFIDENCE["frozen_value"]))

    # dropout -- unambiguous, unchanged.
    for param in PHYSICAL_BOUNDS:
        if raw_reading.get(param) is None or pd.isna(raw_reading.get(param)):
            fired.append(("dropout", param, RULE_BASE_CONFIDENCE["dropout"]))

    # sensor_fail_low -- §5b. Persistence-gated by construction: this
    # ONLY fires once already held for FAIL_LOW_CONSECUTIVE_REQUIRED
    # consecutive readings, so every firing is already a confirmed
    # fast-path event, no separate "single vs confirmed" split needed
    # the way multivariate has one.
    recent_raw = history_df.sort_values("timestamp").tail(FAIL_LOW_CONSECUTIVE_REQUIRED)
    if len(recent_raw) >= FAIL_LOW_CONSECUTIVE_REQUIRED:
        for param, prefix in PARAM_PREFIXES.items():
            if param not in recent_raw.columns:
                continue
            vals = recent_raw[param]
            if vals.notna().all() and (vals <= FAIL_LOW_FLOOR[prefix]).all():
                fired.append(("sensor_fail_low", param, RULE_BASE_CONFIDENCE["sensor_fail_low"]))
                fast_path_offline_params.add(param)

    # drift (CUSUM, §2) + multivariate_inconsistency (§4) share one
    # featurized-buffer pass -- computed once, used by both.
    featured_buffer = _featurize_buffer(history_df)
    confirmed_spikes = _confirmed_spikes(featured_buffer, thresholds, station_id)

    # Extract current hour once for the CUSUM diurnal baseline lookup.
    try:
        current_hour = pd.to_datetime(
            raw_reading.get("timestamp") or history_df["timestamp"].iloc[-1]
        ).hour
    except Exception:
        current_hour = 0

    for param, prefix in PARAM_PREFIXES.items():
        cusum_hit = _cusum_evidence(
            featured_buffer, prefix, param,
            station_id=station_id, current_hour=current_hour,
        )
        if cusum_hit:
            fired.append(cusum_hit)

    mv_evidence, mv_fast_path = _multivariate_evidence(featured_buffer)
    fired.extend(mv_evidence)
    fast_path_offline_params |= mv_fast_path

    return {
        "fired": fired,
        "any": len(fired) > 0,
        "fast_path_offline_params": fast_path_offline_params,
        "confirmed_spikes": confirmed_spikes,
    }


def _fuse_and_score(model_pct, rule_evidence: list):
    """
    §7/§8 in one place: the fused 0-100 score, the is_anomaly verdict,
    and which fault_type gets reported -- all from the SAME confidence
    numbers, no separate priority table (§8's worked example: whichever
    rule currently has the highest confidence wins the label).

    HIGH-CONFIDENCE BYPASS: caught during smoke-testing this rewrite --
    the pure 0.6/0.4 blend means even a MAXIMUM-confidence rule
    (100, physical_bounds/dropout -- an unambiguous fact) only
    contributes 40 points, which can never alone clear the 50 fusion
    threshold if the model happens to score that same reading low. A
    physically impossible reading (humidity=150%) must be flagged
    regardless of what the model's opinion is -- it isn't a statistical
    judgment to blend, it's a fact. Same reasoning extends to every
    near-certain rule (frozen's deterministic floor-match, confirmed
    fail-low, confirmed multivariate): once a rule's OWN persistence/
    certainty bar is fully cleared, RULE_CONFIDENCE_BYPASS (90) forces
    is_anomaly regardless of the blended score. Weaker evidence (a
    single spike at 60, a single suspicious multivariate reading at 55)
    still has to earn its way past the blend with model support, which
    is the intended, correct behavior for those two.
    """
    if rule_evidence:
        rule_confidence = max(c for _, _, c in rule_evidence)
        fault_type = max(rule_evidence, key=lambda e: e[2])[0]
    else:
        rule_confidence = 0.0
        fault_type = None

    if model_pct is None:
        # No usable model score (incomplete feature vector, e.g. still
        # in the rolling-window warm-up period) -- fall back to
        # rule-only evidence rather than silently treating a missing
        # model score as "definitely normal."
        overall = rule_confidence
    else:
        overall = MODEL_WEIGHT * model_pct + RULE_WEIGHT * rule_confidence

    is_anomaly = (
        overall > FUSION_ANOMALY_THRESHOLD
        or (model_pct is not None and model_pct > MODEL_ALONE_OVERRIDE_THRESHOLD)
        # Frozen floor-match is confidence 90 but remains evidence for
        # fusion, per Draft 2 §1; it must not recreate the retired
        # "rule fires = automatic anomaly" hard gate. Only confidence
        # strictly above the configured boundary receives this escape
        # hatch (physical/dropout facts and confirmed 95-point rules).
        or rule_confidence > RULE_CONFIDENCE_BYPASS
    )

    if is_anomaly and fault_type is None:
        fault_type = "statistical_anomaly"

    return overall, is_anomaly, fault_type, rule_confidence


def _corroborate_network(raw_reading: dict, history_df: pd.DataFrame, neighbor_buffers: dict, fault_type: str, implicated_params: list) -> str:
    """
    Network corroboration check -- classifies anomaly as LOCALIZED, REGIONAL,
    or INSUFFICIENT_CORROBORATION based on whether eligible cluster peers show
    similar deviations in the same direction.

    Performance fix: target_features is computed ONCE before the peer loop.
    Each peer's features are also computed once per peer (not per param).

    Returns None when neighbor_buffers is None/empty (no check performed),
    which the caller must distinguish from INSUFFICIENT_CORROBORATION (peers
    exist but were all stale/unhealthy). See audit §13.6.
    """
    if not neighbor_buffers:
        # No peer data available -- cannot perform network check.
        # Caller should surface this as INSUFFICIENT_CORROBORATION with reason.
        return "INSUFFICIENT_CORROBORATION"

    target_time = pd.to_datetime(raw_reading.get("timestamp") or history_df["timestamp"].iloc[-1])

    # Compute target station features ONCE before the peer loop.
    try:
        target_features = build_features_for_latest(history_df)
    except Exception:
        return "INSUFFICIENT_CORROBORATION"

    eligible_peers = 0
    corroborating_peers = 0

    for nid, n_df in neighbor_buffers.items():
        if n_df is None or n_df.empty:
            continue
        n_latest = n_df.iloc[-1]
        n_time = pd.to_datetime(n_latest["timestamp"])

        # Freshness check: peer reading must be within 1h of target.
        if abs((n_time - target_time).total_seconds()) > 3600:
            continue

        eligible_peers += 1

        # Compute peer features ONCE per peer (not per implicated parameter).
        try:
            n_features = build_features_for_latest(n_df)
        except Exception:
            eligible_peers -= 1  # don't count peers whose features failed
            continue

        # Check whether any implicated parameter shows a same-direction
        # deviation > 2.0 sigma in the peer.
        is_corroborating = False
        for param in implicated_params:
            prefix = PARAM_PREFIXES.get(param)
            if not prefix:
                continue
            target_dev = target_features.get(f"{prefix}_deviation", 0)
            peer_dev = n_features.get(f"{prefix}_deviation", 0)
            if pd.notna(target_dev) and pd.notna(peer_dev):
                if abs(peer_dev) > 2.0 and (target_dev * peer_dev > 0):
                    is_corroborating = True
                    break

        if is_corroborating:
            corroborating_peers += 1

    if eligible_peers < 1:
        return "INSUFFICIENT_CORROBORATION"
    elif corroborating_peers > 0:
        return "REGIONAL"
    else:
        return "LOCALIZED"


def _classify_regime(feature_row: "pd.Series", raw_reading: dict, history_df: "pd.DataFrame") -> str:
    """
    Classifies the current station environmental context into one of 9 regimes
    per audit §12.5. Uses the already-computed feature_row from build_features_for_latest
    to avoid double featurization.

    States:
      DAYTIME_WARMING       hour 6-18, temp trending up relative to baseline
      NIGHTTIME_COOLING     hour 18-6, temp trending down
      STABLE                low volatility, minimal rate-of-change all params
      HIGH_HEAT             temp > 35°C or temp_deviation > 2.5σ
      HIGH_HUMIDITY         humidity > 85% or humidity_deviation > 2.0σ
      PRESSURE_SHIFT        significant pressure rate-of-change over 3h
      HIGH_VOLATILITY       any parameter volatility_z > 2.0
      REGIME_TRANSITION     direction reversal in recent temp readings
      UNKNOWN_INSUFFICIENT_DATA   NaN features (warm-up period)
      UNKNOWN_CONTEXT_FAILURE     exception during classification
    """
    try:
        hour = pd.to_datetime(
            raw_reading.get("timestamp") or history_df["timestamp"].iloc[-1]
        ).hour

        # Pull scalar values from feature_row with safe fallbacks.
        def get(col, default=None):
            v = feature_row.get(col)
            if v is None or (hasattr(v, '__float__') and pd.isna(float(v))):
                return default
            return float(v)

        temp_c         = get("temperature_c")
        humidity_pct   = get("humidity_pct")
        temp_dev       = get("temp_deviation")
        humidity_dev   = get("humidity_deviation")
        temp_roc_1h    = get("temp_roc_1h", 0.0)
        temp_roc_3h    = get("temp_roc_3h", 0.0)
        pressure_roc_3h = get("pressure_roc_3h", 0.0)
        temp_vol_z     = get("temp_volatility_z", 0.0)
        pressure_vol_z = get("pressure_volatility_z", 0.0)
        humidity_vol_z = get("humidity_volatility_z", 0.0)

        # UNKNOWN_INSUFFICIENT_DATA: primary indicators are NaN
        if temp_dev is None or humidity_dev is None:
            return "UNKNOWN_INSUFFICIENT_DATA"

        # HIGH_VOLATILITY: any param's volatility z-score > 2.0
        if (temp_vol_z is not None and abs(temp_vol_z) > 2.0
                or pressure_vol_z is not None and abs(pressure_vol_z) > 2.0
                or humidity_vol_z is not None and abs(humidity_vol_z) > 2.0):
            return "HIGH_VOLATILITY"

        # PRESSURE_SHIFT: sustained pressure rate-of-change over 3h
        if pressure_roc_3h is not None and abs(pressure_roc_3h) > 2.0:
            return "PRESSURE_SHIFT"

        # HIGH_HEAT: extreme temperature by absolute value or deviation
        if (temp_c is not None and temp_c > 35.0) or (temp_dev is not None and temp_dev > 2.5):
            return "HIGH_HEAT"

        # HIGH_HUMIDITY: extreme humidity by absolute value or deviation
        if (humidity_pct is not None and humidity_pct > 85.0) or (humidity_dev is not None and humidity_dev > 2.0):
            return "HIGH_HUMIDITY"

        # REGIME_TRANSITION: recent direction reversal in temperature
        if len(history_df) >= 3:
            recent_temps = pd.to_numeric(history_df["temperature_c"].tail(4), errors="coerce").dropna().to_numpy()
            if len(recent_temps) >= 3:
                diffs = [recent_temps[i+1] - recent_temps[i] for i in range(len(recent_temps)-1)]
                signs = [1 if d > 0 else (-1 if d < 0 else 0) for d in diffs]
                non_zero = [s for s in signs if s != 0]
                if len(non_zero) >= 2 and non_zero[-1] != non_zero[-2]:
                    return "REGIME_TRANSITION"

        # STABLE: small roc and deviation across all parameters
        if (abs(temp_roc_3h) < 0.5 and abs(temp_dev) < 0.5
                and abs(pressure_roc_3h) < 0.5):
            return "STABLE"

        # DAYTIME_WARMING / NIGHTTIME_COOLING
        if 6 <= hour < 18:
            if temp_roc_3h is not None and temp_roc_3h > 0 and temp_dev > 0.2:
                return "DAYTIME_WARMING"
            return "STABLE"
        else:
            if temp_roc_3h is not None and temp_roc_3h < 0:
                return "NIGHTTIME_COOLING"
            return "STABLE"

    except Exception:
        return "UNKNOWN_CONTEXT_FAILURE"


def score_reading(raw_reading: dict, history_df: pd.DataFrame, artifact: dict,
                  neighbor_buffers: dict = None, explainer=None) -> dict:
    """
    Main entry point: scores ONE new reading given its station's recent
    causal history buffer. Returns the verdict dict state.py/main.py
    consume.

    Spatial inputs are intentionally absent: Draft 2 removes them from
    both serving and the model vector.
    """
    feature_row = build_features_for_latest(history_df)
    # A suggestion must be available for every reportable bad reading,
    # including the first hours before a 48h rolling baseline is warm.  Use
    # the causal rolling mean when it exists; otherwise use the most recent
    # valid earlier observation.  Never use the current raw value as its own
    # replacement (especially important for a dropout/spike).
    suggested_values = {}
    for param, prefix in PARAM_PREFIXES.items():
        candidate = feature_row.get(f"{prefix}_rolling_mean")
        if pd.isna(candidate):
            prior = pd.to_numeric(history_df[param].iloc[:-1], errors="coerce").dropna()
            candidate = prior.iloc[-1] if not prior.empty else None
        if pd.notna(candidate):
            suggested_values[param] = round(float(candidate), 2)

    model_pct = _model_score_to_pct(raw_reading, feature_row, artifact)
    rules = _rule_checks(raw_reading, feature_row, history_df, artifact)

    # Frozen-specific model gate: frozen_value fires at confidence=80 (below
    # RULE_CONFIDENCE_BYPASS=90) and goes through fusion. When model_pct is
    # below FROZEN_MIN_MODEL_CORROBORATION, real stable-weather streaks and
    # actual frozen sensors are indistinguishable -- suppress frozen evidence
    # so it cannot drive an anomaly verdict without model corroboration.
    fired = rules["fired"]
    if model_pct is None or model_pct < FROZEN_MIN_MODEL_CORROBORATION:
        fired = [(rt, p, c) for (rt, p, c) in fired if rt != "frozen_value"]
    else:
        fired = fired  # model agrees -- frozen evidence kept

    score_pct, is_anomaly, fault_type, rule_confidence = _fuse_and_score(model_pct, fired)
    severity = score_to_severity(score_pct)

    # Track A (blueprint §1) — fault_helper live-path wiring.
    # OR the fault_helper's binary alert into is_anomaly so the live demo
    # matches evaluate.py's offline pipeline exactly.  Gracefully skipped if
    # fault_helper was not loaded (artifact["fault_helper"] is None).
    fault_helper_artifact = artifact.get("fault_helper")
    if fault_helper_artifact is not None and not is_anomaly:
        try:
            from config import HELPER_ALERT_THRESHOLD
            from model.fault_helper import feature_columns, build_network_features
            # Minimal single-station "network" for live scoring (no peer rows).
            single_row = pd.DataFrame([{**raw_reading, "is_anomaly": False, "fault_type": None}])
            fh_model, fh_cols = fault_helper_artifact
            # build_network_features requires cluster context; skip if columns missing
            fh_featured = build_network_features(single_row)
            available_cols = [c for c in fh_cols if c in fh_featured.columns]
            if available_cols:
                fh_prob = fh_model.predict_proba(fh_featured[available_cols])[:, 1][0]
                if fh_prob >= HELPER_ALERT_THRESHOLD:
                    is_anomaly = True
                    if fault_type is None:
                        fault_type = "drift"  # conservative default label for helper-only alerts
                    score_pct = max(score_pct, round(fh_prob * 100, 1))
                    severity = score_to_severity(score_pct)
        except Exception as _fh_exc:
            import logging
            logging.getLogger(__name__).debug("[detect] fault_helper scoring skipped: %s", _fh_exc)


    shap_features_public, likely_sensors = [], []
    if is_anomaly and explainer is not None:
        try:
            shap_features = explainer.explain(feature_row)
            likely_sensors = likely_faulty_params(shap_features)
            shap_features_public = [
                {"name": f["name"], "impact": f["impact"]}
                for f in shap_features
            ]
        except Exception as e:
            print(
                f"[detect] explanation failed for this reading, "
                f"returning verdict without it: {e!r}"
            )

    # Regime classification — 9-state taxonomy per audit §12.5.
    # Uses the already-computed feature_row so no extra featurization cost.
    regime = _classify_regime(feature_row, raw_reading, history_df)

    # Network corroboration is only meaningful when an anomaly was detected.
    # When is_anomaly=False, return None explicitly (not INSUFFICIENT_CORROBORATION)
    # so the frontend and API can distinguish "no check needed" from "check ran but
    # peers were unavailable." See audit §13.6.
    network_state = None
    if is_anomaly:
        implicated = likely_sensors
        if not implicated and rules["fired"]:
            implicated = list(set(r[1] for r in rules["fired"]))
        neighbor_buffers_safe = neighbor_buffers or {}
        network_state = _corroborate_network(
            raw_reading, history_df, neighbor_buffers_safe, fault_type, implicated
        )

    return {
        "anomaly_score_pct": round(score_pct, 1),
        "model_confidence_pct": round(model_pct, 1) if model_pct is not None else None,
        "rule_confidence_pct": round(rule_confidence, 1),
        "is_anomaly": bool(is_anomaly),
        "severity": severity,
        "fault_type": fault_type,
        "rules_fired": rules["fired"],
        "fast_path_offline_params": rules["fast_path_offline_params"],
        "confirmed_spikes": rules["confirmed_spikes"],
        "suggested_values": suggested_values,
        "shap_features": shap_features_public,
        "likely_faulty_sensors": likely_sensors,
        "regime": regime,
        "network_corroboration": network_state,
    }


class SensorHealthTracker:
    """
    The circuit breaker -- now PER-PARAMETER internally (§1/§6), with a
    station-level AGGREGATE kept on `.status`/`.offline_reason` so
    state.py's existing calls keep working unmodified. See module
    docstring #8 for the full explanation and the known state.py-side
    gaps this leaves (row-wise buffer exclusion, repair not resetting
    per-parameter counters).

    Two fast paths bypass the general 10h/24h counters entirely and
    force OFFLINE immediately: confirmed multivariate_inconsistency and
    any sensor_fail_low firing (which is always already confirmed by
    construction -- see _rule_checks). Every other rule type
    accumulates through the general per-parameter 10h/24h counters.
    """

    def __init__(self, station_id: str):
        self.station_id = station_id

        self.param_status = {p: "HEALTHY" for p in PARAMS}
        self.param_offline_reason = {p: None for p in PARAMS}
        self._param_recent_10h = {p: deque(maxlen=WINDOW_10H_SIZE) for p in PARAMS}
        self._param_recent_24h = {p: deque(maxlen=WINDOW_24H_SIZE) for p in PARAMS}
        self._param_clean_streak = {p: 0 for p in PARAMS}

        # Station-level aggregate -- external contract, unchanged shape.
        self.status = "HEALTHY"
        self.offline_reason = None
        self._clean_streak = 0  # kept for state.py's mark_repaired() compatibility; see module docstring #8

    def record(self, verdict: dict):
        fired_params = {}
        for rule_type, param, _confidence in verdict.get("rules_fired", []):
            fired_params.setdefault(param, set()).add(rule_type)
        fast_path = verdict.get("fast_path_offline_params", set())
        # A causal spike is attributed to the preceding raw reading,
        # but discovered only when this reading arrives.  It therefore
        # contributes exactly one event to the 10h/24h policy without
        # flagging the confirming reading itself as anomalous.
        confirmed_spike_params = set(verdict.get("confirmed_spike_params", set()))

        for p in PARAMS:
            anomalous_this_reading = p in fired_params or p in confirmed_spike_params
            self._param_recent_10h[p].append(anomalous_this_reading)
            self._param_recent_24h[p].append(anomalous_this_reading)

            if self.param_status[p] == "OFFLINE":
                if anomalous_this_reading:
                    self._param_clean_streak[p] = 0
                else:
                    self._param_clean_streak[p] += 1
                    if self._param_clean_streak[p] >= RECOVERY_CLEAN_STREAK_REQUIRED:
                        self.param_status[p] = "HEALTHY"
                        self.param_offline_reason[p] = None
                        self._param_clean_streak[p] = 0
                continue

            if p in fast_path:
                self.param_status[p] = "OFFLINE"
                self.param_offline_reason[p] = (
                    f"{p}: confirmed fault (multivariate/fail-low persistence) -- "
                    f"immediate offline, critical, needs maintenance."
                )
                continue

            count_10h = sum(self._param_recent_10h[p])
            count_24h = sum(self._param_recent_24h[p])

            if len(self._param_recent_10h[p]) >= WINDOW_10H_SIZE and count_10h >= WINDOW_10H_TRIGGER:
                self.param_status[p] = "OFFLINE"
                self.param_offline_reason[p] = (
                    f"{p}: {count_10h} anomalous readings (any fault type, mixed "
                    f"counts) in the last {WINDOW_10H_SIZE}h -- hard threshold, "
                    f"critical, needs maintenance."
                )
            elif len(self._param_recent_24h[p]) >= WINDOW_24H_SIZE and count_24h >= WINDOW_24H_TRIGGER:
                self.param_status[p] = "WARNING"
                self.param_offline_reason[p] = None

            else:
                self.param_status[p] = "HEALTHY"
                self.param_offline_reason[p] = None

        statuses = list(self.param_status.values())
        if "OFFLINE" in statuses:
            self.status = "OFFLINE"
            offline_params = [p for p in PARAMS if self.param_status[p] == "OFFLINE"]
            self.offline_reason = "; ".join(self.param_offline_reason[p] for p in offline_params)
        elif "WARNING" in statuses:
            self.status = "WARNING"
            self.offline_reason = None
        else:
            self.status = "HEALTHY"
            self.offline_reason = None

    def should_include_in_baseline(self) -> bool:
        """
        Station-wide boolean -- see module docstring #8's KNOWN
        LIMITATION note. ANY parameter OFFLINE excludes the whole raw
        row for now; true per-parameter exclusion needs columnar
        buffering in state.py.
        """
        return self.status != "OFFLINE"


def _make_synthetic_history(n_hours: int = 72, seed: int = 0) -> pd.DataFrame:
    """
    Smoke-test helper only -- NOT used by score_reading in real
    operation (state.py owns the real causal buffer). Builds a plain,
    boring, non-anomalous station history so main() below has
    something to run score_reading() against without needing a live
    data_fetch.py pull or a trained model tuned on real data.
    """
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-01 00:00:00")
    timestamps = [start + pd.Timedelta(hours=i) for i in range(n_hours)]
    hours = np.array([t.hour for t in timestamps])

    temp = 22 + 5 * np.sin(2 * np.pi * hours / 24) + rng.normal(0, 0.3, n_hours)
    pressure = 1013 + rng.normal(0, 0.5, n_hours)
    humidity = 55 + 10 * np.sin(2 * np.pi * (hours - 6) / 24) + rng.normal(0, 1.0, n_hours)

    return pd.DataFrame({
        "station_id": "AWS-DEMO-001",
        "timestamp": timestamps,
        "temperature_c": temp,
        "pressure_hpa": pressure,
        "humidity_pct": np.clip(humidity, 0, 100),
    })


def main():
    """
    Standalone smoke test: NOT part of the real pipeline (state.py/
    main.py own the actual live buffer + call site). This exists so
    score_reading() and SensorHealthTracker can be sanity-checked in
    isolation -- same purpose features.py's own main() serves for
    build_feature_matrix -- without needing the rest of the backend
    wired up first.

    Two passes:
      1. A clean synthetic history + one more ordinary reading ->
         expect is_anomaly=False, no rules fired.
      2. The same history + one injected-by-hand frozen reading
         (last 3 temperature readings forced to the same integer
         part) -> expect frozen_value evidence and, since frozen's
         confidence (90) clears RULE_CONFIDENCE_BYPASS, is_anomaly=True
         even though nothing else about the reading looks unusual.
    """
    try:
        artifact = load_model()
    except FileNotFoundError as e:
        print(f"[detect] {e}")
        print("[detect] Skipping the model-scored part of the smoke test -- "
              "rule checks alone can still be exercised by calling "
              "_rule_checks()/_fuse_and_score() directly if needed.")
        artifact = None

    history = _make_synthetic_history()

    print("=== Pass 1: ordinary next reading (expect HEALTHY) ===")
    next_reading = {
        "station_id": "AWS-DEMO-001",
        "timestamp": history["timestamp"].iloc[-1] + pd.Timedelta(hours=1),
        "temperature_c": float(history["temperature_c"].iloc[-1]) + 0.2,
        "pressure_hpa": float(history["pressure_hpa"].iloc[-1]) - 0.1,
        "humidity_pct": float(history["humidity_pct"].iloc[-1]) + 0.5,
    }
    buffer_1 = pd.concat([history, pd.DataFrame([next_reading])], ignore_index=True)

    if artifact is not None:
        verdict_1 = score_reading(next_reading, buffer_1, artifact)
        print(f"  is_anomaly={verdict_1['is_anomaly']}  "
              f"score={verdict_1['anomaly_score_pct']}  "
              f"fault_type={verdict_1['fault_type']}  "
              f"rules_fired={verdict_1['rules_fired']}")

    print("\n=== Pass 2: hand-injected frozen temperature (expect frozen_value) ===")
    buffer_2 = buffer_1.copy()
    frozen_val = float(np.floor(buffer_2["temperature_c"].iloc[-1]))
    buffer_2.loc[buffer_2.index[-3:], "temperature_c"] = frozen_val
    frozen_reading = dict(next_reading)
    frozen_reading["temperature_c"] = frozen_val

    if artifact is not None:
        verdict_2 = score_reading(frozen_reading, buffer_2, artifact)
        print(f"  is_anomaly={verdict_2['is_anomaly']}  "
              f"score={verdict_2['anomaly_score_pct']}  "
              f"fault_type={verdict_2['fault_type']}  "
              f"rules_fired={verdict_2['rules_fired']}")

        tracker = SensorHealthTracker("AWS-DEMO-001")
        tracker.record(verdict_1)
        tracker.record(verdict_2)
        print(f"\nSensorHealthTracker after both readings: "
              f"status={tracker.status}  param_status={tracker.param_status}")


if __name__ == "__main__":
    main()
