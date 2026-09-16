"""
SkyGuard AI — config.py.

SINGLE SOURCE OF TRUTH for every rule-engine constant used by BOTH
detect.py (live scoring) and evaluate.py (offline eval). Neither file
defines its own local copies -- everything rule-related lives here.

This file reflects the current architecture: per-rule confidence values
(RULE_BASE_CONFIDENCE) blended with the model score via MODEL_WEIGHT/
RULE_WEIGHT, with RULE_CONFIDENCE_BYPASS/MODEL_ALONE_OVERRIDE_THRESHOLD
as escape hatches for near-certain evidence a pure blend would otherwise
under-weight. The old hard/soft rule-floor cascade is retired (kept
below for the paper trail only, not imported by anything).

===========================================================================
KEEP THIS IN SYNC WITH THE ACTUAL anomaly_injector.py -- READ BEFORE
CHANGING FAIL_LOW_FLOOR / FROZEN_CONSECUTIVE_REQUIRED
===========================================================================
The injector was rewritten to match real transducer physics (bounded
random-walk frozen values, drift superimposed on the real signal, dual
instant/decay spikes, TRUE hardware-rail fail-low values, and a
Clausius-Clapeyron-grounded multivariate fault). The values below are
calibrated against THAT injector, not an earlier draft:

  - inject_fail_low now writes at FAIL_LOW_RAIL_VALUE (temp=-40.0C,
    pressure=0.0 hPa, humidity=0.0%) plus small fixed jitter -- true
    electrical-rail values, not the old intermediate sentinels
    (-15.0 / 50.0 / 0.5). FAIL_LOW_FLOOR below is a REAL-WORLD
    plausibility boundary (how low a genuine reading could ever get),
    not a "margin above the injector's fault value" -- so it does NOT
    need to track the injector's exact numbers, and the current
    thresholds (-8.0 / 150.0 / 3.0) still correctly catch the new,
    more-extreme rail values with room to spare.
  - inject_frozen holds a value for freeze_length+1 = 7-9 readings
    (rng.integers(6,9) exclusive upper, plus the transition row), but
    the value WANDERS within that window (bounded random-walk ADC
    noise, not a bit-exact hold) -- so window length alone doesn't
    guarantee a long run of identical rounded readings.
    FROZEN_CONSECUTIVE_REQUIRED is 3, not a value close to that 7-9
    window (see its own comment below for the simulation showing why
    6 was actually failing on ~85% of the injector's own frozen
    events, not just hypothetical real ones).
  - inject_multivariate's humidity-side fault magnitude is now anchored
    to the physically-correct RH drop implied by the injected temp
    delta (Tetens/Clausius-Clapeyron), not a flat humidity-sigma guess.
    MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD below is UNVALIDATED
    against this new magnitude -- flagged, not yet re-tuned; this is
    exactly what Checkpoint evaluation against the rewritten injector
    needs to confirm before this placeholder is trusted.

===========================================================================
Everything below aims at the 80% precision/recall target, but is a
DOMAIN-ESTIMATED STARTING POINT, not a value already validated against
real evaluate.py output on the rewritten pipeline. Once evaluate.py runs
end-to-end (rewritten injector -> features.py -> this config ->
detect.py/evaluate.py both reading it), THIS FILE is what gets tuned to
close any precision/recall gap -- never detect.py or evaluate.py
directly, so they can't drift apart again.
===========================================================================
"""

# ---------------------------------------------------------------------
# RETIRED / DEAD constants -- kept for the paper trail only. NOT
# imported by detect.py/evaluate.py. Original values were per-parameter
# dicts; these are sentinel placeholders marking "no longer meaningful,"
# not a claim about what the old dict values were.
# ---------------------------------------------------------------------
FROZEN_VARIANCE_FLOOR = None   # DEAD -- retired variance/range-floor frozen check.
FROZEN_RANGE_FLOOR = None      # DEAD -- retired variance/range-floor frozen check.
IS_ANOMALY_THRESHOLD = None    # DEAD -- replaced by FUSION_ANOMALY_THRESHOLD.
SOFT_RULE_FLOOR = None         # DEAD -- replaced by RULE_BASE_CONFIDENCE + fusion.
HARD_RULE_FLOOR = None         # DEAD -- replaced by RULE_BASE_CONFIDENCE + fusion.
MODEL_ONLY_THRESHOLD = None    # DEAD -- replaced by MODEL_ALONE_OVERRIDE_THRESHOLD.

# ---------------------------------------------------------------------
# §11.1 -- Recovery streak, FINAL.
# ---------------------------------------------------------------------
RECOVERY_CLEAN_STREAK_REQUIRED = 3

# ---------------------------------------------------------------------
# §7 -- Evidence fusion, CONFIRMED FINAL mechanism + weights.
# ---------------------------------------------------------------------
MODEL_WEIGHT = 0.6
RULE_WEIGHT = 0.4
# REBALANCED (was 90.0). At 90, the math worked out to a deadlock
# functionally identical to Phase 1's retired bug: with RULE_WEIGHT=0.4,
# no rule below RULE_CONFIDENCE_BYPASS can ever push `overall` past 90
# even with a maximal model score (0.6*100 + 0.4*89 = 95.6 is the only
# way in, i.e. only near-bypass-confidence rules could ever clear this
# with model help; anything at multivariate_single's old 55 needed
# model_pct > 113, impossible). Lowered to 55 so genuine model
# corroboration of a moderate-confidence rule can actually register --
# see the worked numbers next to RULE_CONFIDENCE_BYPASS below.
FUSION_ANOMALY_THRESHOLD = 55.0
# REBALANCED (was 100.0, i.e. literally unreachable since model_pct is
# clipped to [0,100] -- the model could never independently flag
# anything no matter how confident). Lowered to 80: a very high model
# score alone (no rule agreement at all) can still surface an anomaly
# the rule layer has no explicit check for -- which is the whole point
# of keeping a trained model in the loop instead of it being a rule
# nobody asked for a second opinion from.
MODEL_ALONE_OVERRIDE_THRESHOLD = 80.0

# Bypass: once a rule's own confidence is >= this, is_anomaly is forced
# regardless of the blended score. UNCHANGED at 90 -- this is still the
# right escape hatch for TRUE facts (physical_bounds/dropout, 100) and
# for mechanisms that are near-certain once their own persistence bar
# is cleared (frozen_value/sensor_fail_low/drift/spike, still 95, see
# RULE_BASE_CONFIDENCE below). What changed is which rules are ALLOWED
# to sit above this line: multivariate_confirmed is deliberately moved
# BELOW it now (82, not 95) -- see that constant's own comment for why
# multivariate specifically, not the others, needed to lose its
# automatic-override status.
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
#
# multivariate_single/multivariate_confirmed LOWERED from 55/95 to
# 45/82 (audit-recommended rebalancing). Multivariate's own trigger
# condition (temp+humidity deviate together, same direction, pressure
# stays flat) is the rule in this file most directly shaped around
# anomaly_injector.py's specific implementation choices -- "pressure
# barely moves" is literally what inject_multivariate does, not a
# general fact about real sensor cross-talk or short circuits, which
# could easily move pressure too. Keeping multivariate_confirmed above
# RULE_CONFIDENCE_BYPASS meant a co-occurrence matching that exact
# shape got an automatic verdict with zero model corroboration required
# -- the same failure pattern as Phase 1, just relocated to a different
# rule. 82 sits below RULE_CONFIDENCE_BYPASS (90) so a confirmed
# multivariate hit now has to clear FUSION_ANOMALY_THRESHOLD (55) via
# the blend -- in practice a real co-occurring deviation this large
# should still score well on the model too, so this is not expected to
# meaningfully cost real recall, just remove the unconditional pass.
RULE_BASE_CONFIDENCE = {
    "physical_bounds": 100.0,
    "dropout": 100.0,
    "frozen_value": 95.0,
    "sensor_fail_low": 95.0,
    "drift": 95.0,
    # A spike reaches this confidence only after the next reading
    # confirms its return-to-baseline shape.
    "spike": 95.0,
    "multivariate_single": 45.0,
    "multivariate_confirmed": 82.0,
}

# ---------------------------------------------------------------------
# §2 -- CUSUM drift, CONFIRMED FINAL mechanism. See resolution #4 above
# for why CUSUM_THRESHOLD is a placeholder pending real calibration.
# ---------------------------------------------------------------------
CUSUM_DRIFT_ALLOWANCE = 0.05
CUSUM_THRESHOLD = 7.0
CUSUM_DIRECTION_STREAK_REQUIRED = 8

# CORRECTED (was 6). That value assumed a run of readings staying
# EXACTLY (to 0.1 precision) identical for most of the injector's
# 7-9-reading freeze window -- true for the old bit-exact injector, not
# for the current one. inject_frozen's random walk uses
# ADC_NOISE_FLOOR_STD of 0.05 (temp/humidity) or 0.03 (pressure) per
# step, which is comparable to the 0.1 rounding bin features.py's
# floor_frozen_match uses -- simulating 20,000 injected freeze events
# at these exact parameters, a run of >=6 identical rounded readings
# occurred in only ~15% of temp/humidity events (median max streak: 4)
# and ~41% of pressure events (median max streak: 5). Requiring 6 was
# failing on the great majority of the injector's OWN frozen faults,
# not just hypothetical real ones -- an under-fitting bug, not an
# overfitting one. Lowered to 3, which is also the value Draft 2 §1
# originally locked before this drifted upward against a different
# injector assumption. A real stuck sensor at this noise level clears
# 3 far more reliably, and 3 identical-to-0.1 readings in a row is
# still well outside what real (non-frozen) atmospheric noise produces
# except during genuinely calm, stable conditions -- which is exactly
# why this rule ALSO no longer auto-bypasses model corroboration for
# borderline cases (see RULE_CONFIDENCE_BYPASS): a lowered threshold
# widens the net, but fusion still requires the model to agree except
# when frozen_value's own 95 confidence clears the bypass line, which
# a 3-reading match at real noise levels should still do reliably once
# combined with the near-zero rolling_std that accompanies it.
FROZEN_CONSECUTIVE_REQUIRED = 3

# ---------------------------------------------------------------------
# §4 -- Multivariate inconsistency. TWO independent trigger paths now
# (see detect.py's _multivariate_evidence), not one:
#
#   (a) LEVEL-based co-occurrence (original): temp+humidity both
#       deviate from baseline, same direction, pressure stays flat.
#       PLACEHOLDER thresholds, unchanged below.
#   (b) NEW -- direct physics violation: features.py's
#       vapor_pressure_consistency_dev measures the actual gap between
#       observed humidity and what Clausius-Clapeyron/vapor-pressure
#       conservation implies given the temperature change. This is the
#       general case (a); (a) additionally requires pressure to stay
#       flat, which is true of THIS injector's implementation but not
#       a fact about real cross-talk/short-circuit faults in general --
#       a real fault could move pressure too and (a) would miss it,
#       while (b) still catches it since it only looks at T/RH.
#
# Either path firing counts as multivariate evidence; MULTIVARIATE_
# VAPOR_CONSISTENCY_THRESHOLD is a NEW placeholder (not yet validated
# against real evaluate.py output, same status as CUSUM_THRESHOLD) --
# picked as "well beyond the RH noise a real, physically-consistent
# reading should show against its own conservation-implied value,"
# not tuned against this injector's specific sigma choices.
# ---------------------------------------------------------------------
MULTIVARIATE_TEMP_DEVIATION_THRESHOLD = 3.0        # temp: |z| must clear this
MULTIVARIATE_HUMIDITY_DEVIATION_THRESHOLD = 1.5    # humidity: more lenient -- naturally noisier day to day
MULTIVARIATE_PRESSURE_FLAT_THRESHOLD = 1.5         # pressure: must STAY under this while temp/humidity are both far outside it
MULTIVARIATE_VAPOR_CONSISTENCY_THRESHOLD = 8.0     # NEW, placeholder: |RH_actual - RH_physically_expected| percentage points
MULTIVARIATE_PERSISTENCE_REQUIRED = 2              # §4, final: 2 consecutive readings = confirmed
MULTIVARIATE_TEMP_ATTRIBUTION_WEIGHT = 1.5
MULTIVARIATE_ATTRIBUTION_DOMINANCE = 0.7

# ---------------------------------------------------------------------
# §5b -- Sensor fail-low. ABSOLUTE per-parameter floor: "how low could a
# genuine reading plausibly ever get at these stations" -- NOT a margin
# pinned to the injector's exact fault value (see the file-level note
# above). anomaly_injector.py's inject_fail_low now writes true hardware
# rail values (-40.0C / 0.0 hPa / 0.0%), which sit comfortably below
# every floor here, so these thresholds still fire correctly. The floors
# themselves are picked from real-climate plausibility so a genuine cold
# snap or dry day doesn't false-trigger.
# ---------------------------------------------------------------------
FAIL_LOW_FLOOR = {
    "temp": -8.0,
    "pressure": 150.0,
    "humidity": 3.0,
}
FAIL_LOW_CONSECUTIVE_REQUIRED = 2  # lower bound of §5b's "2-3" -- the faster-triggering choice. anomaly_injector.py's FAIL_LOW_LENGTH=3 (4 rows held) comfortably clears this.

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
