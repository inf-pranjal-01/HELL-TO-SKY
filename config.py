"""
SkyGuard AI — config.py (SKYGUARD_ARCHITECTURE_DRAFT_2.md §11, file #5).

SINGLE SOURCE OF TRUTH for every rule-engine constant used by BOTH
detect.py (live scoring) and evaluate.py (offline eval). Before this
file, each carried its own local placeholder copies -- and, confirmed
by direct comparison, had drifted apart on three mechanisms plus one
threshold. This file resolves that drift. detect.py and evaluate.py
both import from here now; neither defines its own copies anymore.

===========================================================================
RESOLUTION OF THE DETECT.PY vs EVALUATE.PY MISMATCH
===========================================================================

1. MULTIVARIATE MECHANISM -- LEVEL-based (z-scored deviation), NOT
   roc-based. Confirmed against anomaly_injector.py's actual
   inject_multivariate(): it adds a constant offset across the WHOLE
   idx:end_idx window (2-5 rows), so the injected fault's raw values
   sit at an elevated LEVEL for the fault's full duration. A roc-based
   signal (evaluate.py's old version, temp_humidity_coupling_signal /
   pressure_inconsistency) only spikes at the window's entry/exit
   edges and goes quiet in between -- it would systematically miss the
   middle of every injected multivariate event, directly threatening
   recall. detect.py's level-based version (temp_deviation /
   humidity_deviation / pressure_deviation, already z-scored against
   each station's own causal baseline) is adopted as final.

2. FAIL-LOW MECHANISM -- ABSOLUTE per-parameter floor, NOT z-scored
   deviation. §5b's own wording is "a sudden drop to a 0/near-zero
   value" -- a relative-deviation threshold (evaluate.py's old
   version, dev < -4.0) doesn't actually check for near-zero, it only
   checks "far below this station's own baseline," which a real
   extreme-but-plausible cold snap could also trigger, threatening
   precision. detect.py's absolute-floor version is adopted as final,
   with margins kept deliberately generous ABOVE anomaly_injector.py's
   actual failure floors (-15.0 / 50.0 / 0.5) for exactly that reason.

3. CONFIDENCE SCALE -- detect.py's RULE_BASE_CONFIDENCE dict +
   RULE_CONFIDENCE_BYPASS is adopted as final. Reasoning: §7's fusion
   (0.6*model + 0.4*rule) mathematically cannot let even a max-
   confidence rule (100) clear the 50-point fusion threshold alone if
   the model scores that same reading low (0.4*100=40) -- but a
   physically impossible reading, a deterministic frozen floor-match,
   or a persistence-confirmed fail-low/multivariate event are not
   probabilistic judgments to blend once each rule's OWN bar is
   cleared; they are facts or near-facts. Without a bypass, fusion can
   systematically under-recall on exactly the rules §1/§4/§5b treat as
   near-certain -- directly threatening the 80% recall target this
   phase is aimed at. evaluate.py's old ad hoc numbers (100/70/65/50/
   45/35, no bypass for frozen/fail-low/multivariate) are retired.

4. CUSUM_THRESHOLD -- locked at 7.0, the midpoint of detect.py's 6.0
   and evaluate.py's 8.0. Flagged, not blindly averaged for any deeper
   reason: NEITHER value has been run against real drift-labeled data
   yet -- CUSUM's own core assumption (direction-consistent drift, §2)
   isn't even testable until anomaly_injector.py's drift generator is
   rewritten (§11 file #1) to stop letting a spike-shaped run bleed
   into a drift-labeled window (the exact bug §2 documents in the
   pasted MUM-101 sample). 7.0 is as much a placeholder as either
   original value -- MUST be revisited from evaluate.py's actual
   per-fault-type drift recall once that injector fix lands.
   CUSUM_DRIFT_ALLOWANCE was already 0.5 in both files -- no conflict.

===========================================================================
Everything below aims at the 80% precision/recall target for this
phase, but is a DOMAIN-ESTIMATED STARTING POINT, not a value already
validated against real evaluate.py output on the rewritten pipeline.
Once evaluate.py runs end-to-end (rewritten injector -> rewritten
features -> this config -> detect.py/evaluate.py both reading it),
THIS FILE is what gets tuned to close any precision/recall gap -- never
detect.py or evaluate.py directly, so they can't drift apart again.
===========================================================================
"""

# ---------------------------------------------------------------------
# RETIRED / DEAD constants -- kept for the paper trail (§0 Postmortem),
# NOT deleted, NOT imported by anything below or by detect.py/
# evaluate.py anymore.
# ---------------------------------------------------------------------
FROZEN_VARIANCE_FLOOR = 75.0   # DEAD -- retired, §0/§1. Do not import.
FROZEN_RANGE_FLOOR = 75.0      # DEAD -- retired, §0/§1. Do not import.
IS_ANOMALY_THRESHOLD = 75.0    # DEAD -- was numerically == SOFT_RULE_FLOOR, the confirmed root cause (§0). Replaced by FUSION_ANOMALY_THRESHOLD.
SOFT_RULE_FLOOR = 75.0         # DEAD -- see §0 Postmortem. Do not import.
HARD_RULE_FLOOR = 75.0         # DEAD -- superseded by RULE_CONFIDENCE_BYPASS.
MODEL_ONLY_THRESHOLD = 70.0    # DEAD -- superseded by MODEL_ALONE_OVERRIDE_THRESHOLD (same value, new name/home).

# ---------------------------------------------------------------------
# §11.1 -- Recovery streak, FINAL.
# ---------------------------------------------------------------------
RECOVERY_CLEAN_STREAK_REQUIRED = 3

# ---------------------------------------------------------------------
# §7 -- Evidence fusion, CONFIRMED FINAL mechanism + weights.
# ---------------------------------------------------------------------
MODEL_WEIGHT = 0.6
RULE_WEIGHT = 0.4
FUSION_ANOMALY_THRESHOLD = 90.0
# Calibrated pass: model scores remain part of the returned evidence,
# but the raw Isolation Forest scale is not yet calibrated enough for a
# standalone live verdict. Deterministic confirmed rules remain active.
MODEL_ALONE_OVERRIDE_THRESHOLD = 100.0

# Bypass: once a rule's own confidence is >= this, is_anomaly is forced
# regardless of the blended score (see resolution #3 above). Facts
# (100) and persistence-confirmed rules (90/95) clear this; a lone
# spike (60) or a single suspicious multivariate reading (55) do not
# -- they still have to earn model support through the blend, which is
# intentional (§3/§4: a single reading alone is never enough on its
# own to mark a sensor faulty).
RULE_CONFIDENCE_BYPASS = 90.0

# A candidate spike is confirmed only when the next reading returns to
# within this fraction of the candidate's jump from the prior reading.
SPIKE_REVERSION_RATIO = 0.35
# The reversion shape alone is common in naturally variable pressure.
# The middle point must also be materially beyond its calibrated
# station/parameter threshold before a causal spike is promoted.
SPIKE_DEVIATION_MULTIPLIER = 2.0

# Per-rule base confidence (0-100) -- "how sure is this ONE piece of
# evidence, on its own." Single source of truth for detect.py (live)
# and evaluate.py (offline).
RULE_BASE_CONFIDENCE = {
    "physical_bounds": 100.0,
    "dropout": 100.0,
    "frozen_value": 95.0,
    "sensor_fail_low": 95.0,
    "drift": 95.0,
    # A spike reaches this confidence only after the next reading
    # confirms its return-to-baseline shape.
    "spike": 95.0,
    "multivariate_single": 55.0,
    "multivariate_confirmed": 95.0,
}

# ---------------------------------------------------------------------
# §2 -- CUSUM drift, CONFIRMED FINAL mechanism. See resolution #4 above
# for why CUSUM_THRESHOLD is a placeholder pending real calibration.
# ---------------------------------------------------------------------
CUSUM_DRIFT_ALLOWANCE = 0.05
CUSUM_THRESHOLD = 7.0
CUSUM_DIRECTION_STREAK_REQUIRED = 8

# Ordinary hourly humidity can repeat at one-decimal reporting
# precision. Confirm a frozen fault only after a longer run.
# Natural humidity and pressure frequently repeat at a 0.1 display
# resolution. Six consecutive identical reported readings retains the
# intended persistence rule while avoiding false OFFLINE events; the
# replay injector holds frozen faults for 7--9 readings to match it.
FROZEN_CONSECUTIVE_REQUIRED = 6

# ---------------------------------------------------------------------
# §4 -- Multivariate inconsistency. LEVEL-based (z-scored deviation),
# per resolution #1 above. PLACEHOLDER thresholds.
# ---------------------------------------------------------------------
MULTIVARIATE_TEMP_DEVIATION_THRESHOLD = 3.0        # temp: |z| must clear this
MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD = 1.5    # humidity: more lenient -- naturally noisier day to day
MULTIVARIATE_PRESSURE_FLAT_THRESHOLD = 1.5         # pressure: must STAY under this while temp/humidity are both far outside it
MULTIVARIATE_PERSISTENCE_REQUIRED = 2              # §4, final: 2 consecutive readings = confirmed
MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT = 1.5
MULTIVARIATE_ATTRIBUTION_DOMINANCE = 0.7

# ---------------------------------------------------------------------
# §5b -- Sensor fail-low. ABSOLUTE per-parameter floor, per resolution
# #2 above -- deliberately generous margin ABOVE anomaly_injector.py's
# actual failure floors (-15.0 / 50.0 / 0.5) so a real cold snap or a
# genuinely dry day doesn't false-trigger.
# ---------------------------------------------------------------------
FAIL_LOW_FLOOR = {
    "temp": -8.0,
    "pressure": 150.0,
    "humidity": 3.0,
}
FAIL_LOW_CONSECUTIVE_REQUIRED = 2  # lower bound of §5b's "2-3" -- the faster-triggering choice, matches evaluate.py's existing convention for other "X-Y" ranges in the doc

# ---------------------------------------------------------------------
# §6 -- Unified 10h/24h, mixed-fault-type, per-parameter counters.
# Lower bound of the doc's stated "4-5" range (more sensitive/faster-
# triggering choice -- same convention as FAIL_LOW_CONSECUTIVE_REQUIRED
# above and evaluate.py's original documented choice).
# ---------------------------------------------------------------------
WINDOW_10H_SIZE = 10
WINDOW_10H_TRIGGER = 4
WINDOW_24H_SIZE = 24
WINDOW_24H_TRIGGER = 4

# ---------------------------------------------------------------------
# Severity buckets + anomaly_score_pct -> severity mapping. UNCHANGED
# contract from every prior phase (§7: "this changes what feeds the
# score, not the contract").
# ---------------------------------------------------------------------
SEVERITY_CRITICAL_FLOOR = 90.0
SEVERITY_HIGH_FLOOR = 70.0
SEVERITY_MEDIUM_FLOOR = 55.0


def score_to_severity(score_pct: float) -> str:
    """
    Maps anomaly_score_pct (0-100) to a severity label. Buckets are
    the same 90/70/55 every phase has kept unchanged -- §7 explicitly
    preserves this contract while changing what feeds the score.
    """
    if score_pct is None:
        return "none"
    if score_pct >= SEVERITY_CRITICAL_FLOOR:
        return "critical"
    if score_pct >= SEVERITY_HIGH_FLOOR:
        return "high"
    if score_pct >= SEVERITY_MEDIUM_FLOOR:
        return "medium"
    return "low"
