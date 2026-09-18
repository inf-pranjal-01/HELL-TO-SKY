# SkyGuardAI --- Full Comprehensive Bug Audit, Validation & Testing Plan

> **Document status:** Engineering investigation and validation plan.
>
> **Important:** This document is not proof that every listed issue
> exists. It is a structured audit checklist designed to uncover
> defects, hidden coupling, incorrect assumptions, misleading UI claims,
> data-quality failures, and production risks. Do not blindly implement
> every recommendation. First reproduce the current behaviour, capture
> evidence, establish a baseline, and validate each change through
> regression testing.

------------------------------------------------------------------------

## 1. Purpose

This plan expands the earlier issue list into a **full-system bug audit
and testing strategy** for SkyGuardAI.

The audit covers the complete chain:

``` text
Telemetry ingestion
    ↓
Validation and freshness
    ↓
History and state management
    ↓
Feature engineering
    ↓
Environmental context
    ↓
ML model inference
    ↓
Deterministic rules
    ↓
Evidence fusion
    ↓
Fault attribution
    ↓
Explainability / SHAP
    ↓
Spatial cluster and peer corroboration
    ↓
Suggested replacement estimation
    ↓
Sensor health and recovery
    ↓
Persistence and event lifecycle
    ↓
API contracts
    ↓
Frontend rendering
    ↓
Alerts, reports and operator actions
```

The goal is not simply to make the dashboard look correct. The goal is
to ensure that:

1.  A detection is mathematically and operationally defensible.
2.  Model and rule participation are accurately disclosed.
3.  Environmental changes are not automatically mistaken for sensor
    faults.
4.  Spatial and multi-parameter evidence is used appropriately.
5.  Suggested values are estimates with traceable uncertainty.
6.  Explanations match the actual decision path.
7.  Sensor health and recovery states remain consistent.
8.  Frontend claims never exceed backend evidence.
9.  The system remains reliable during missing, stale, malformed,
    delayed, duplicated, and contradictory data.
10. Improvements can be measured and rolled back.

------------------------------------------------------------------------

# 2. Core engineering principles

## 2.1 Preserve raw truth

Raw telemetry must remain immutable.

The system may create:

-   Cleaned values
-   Normalized values
-   Imputed values
-   Model features
-   Replacement suggestions
-   Operator-approved corrected values

However, these must never silently overwrite the original reading.

Every derived value should retain:

-   Source reading ID
-   Original timestamp
-   Processing timestamp
-   Derivation method
-   Model/configuration version
-   Confidence or uncertainty
-   Whether it is suitable for downstream analysis

## 2.2 Separate detection from interpretation

These are different questions:

1.  Is the observation unusual?
2.  Is the sensor likely faulty?
3.  Is the event localized?
4.  Is the event regionally corroborated?
5.  What should an operator do next?

A high anomaly score does not automatically prove sensor failure. A rule
trigger does not automatically prove a physical fault. Peer agreement
does not automatically prove a regional event.

## 2.3 Never hide missing evidence

The system must distinguish:

-   No evidence
-   Evidence not collected
-   Evidence unavailable
-   Evidence contradictory
-   Evidence failed due to an error
-   Evidence that genuinely indicates normality

`UNKNOWN`, `N/A`, `INSUFFICIENT_DATA`, and `FAILED` should not be
treated as interchangeable.

## 2.4 Make every decision traceable

Every alert should be reproducible from:

-   Station
-   Parameter
-   Event timestamp
-   Input readings
-   Historical window
-   Feature vector
-   Model artifact
-   Rule configuration
-   Context state
-   Peer data
-   Fusion calculation
-   Explanation output
-   Software version

## 2.5 Prefer calibrated language

Use:

-   Anomaly score
-   Rule evidence strength
-   Model support
-   Indication
-   Estimated value
-   Suggested replacement
-   Insufficient corroboration
-   Possible regional event

Avoid unsupported wording such as:

-   85% probability
-   Confirmed sensor failure
-   Guaranteed regional event
-   True cause
-   Corrected value
-   Model proved the fault

------------------------------------------------------------------------

# 3. Audit governance and evidence collection

## 3.1 Freeze a baseline before changing code

Record:

-   Git commit hash
-   Branch
-   Python/runtime version
-   Dependency lockfile
-   Model artifact checksum
-   Configuration checksum
-   Dataset version
-   Random seed
-   Database schema version
-   Frontend build version
-   API version
-   Environment variables that affect behaviour

Capture baseline metrics:

-   Precision
-   Recall
-   F1
-   False positives per station-day
-   False negatives by fault type
-   Detection latency
-   Model availability rate
-   SHAP availability rate
-   Context availability rate
-   Network corroboration availability rate
-   Suggested-value error
-   Recovery latency
-   API error rate
-   Dashboard refresh latency

Previously reported metrics must be regenerated from the current branch.
Do not reuse historical numbers without verifying the exact code, data,
and evaluation procedure.

## 3.2 Create a reproducible incident bundle

For every investigated event, save:

``` text
incident_id
station_id
parameter
event_timestamp
raw_input_window
feature_vector
model_version
model_status
rule_results
fusion_inputs
fusion_output
context_output
peer_output
health_state
replacement_candidates
API_response
frontend_snapshot
logs
```

The incident bundle should allow another developer to reproduce the same
outcome offline.

## 3.3 Classify every finding

Use the following labels:

-   `CONFIRMED_BUG`
-   `LIKELY_BUG`
-   `DESIGN_RISK`
-   `MISSING_FEATURE`
-   `DATA_LIMITATION`
-   `OBSERVABILITY_GAP`
-   `UI_MISREPRESENTATION`
-   `NOT_REPRODUCED`
-   `EXPECTED_BEHAVIOUR`

Every finding should include:

-   Evidence
-   Reproduction steps
-   Impact
-   Root cause
-   Recommended fix
-   Regression test
-   Owner
-   Priority
-   Residual risk

------------------------------------------------------------------------

# 4. Priority model

## P0 --- Decision integrity and safety

Issues that can make the system claim something unsupported or make a
materially incorrect operational decision:

-   Model-unavailable decisions displayed as model-supported
-   Rule scores displayed as probabilities
-   Incorrect fusion arithmetic
-   Silent fallback behaviour
-   Raw readings overwritten
-   Incorrect fault attribution
-   Health state inconsistent with actual evidence
-   Replacement values presented as ground truth
-   Frontend claims not supported by backend output

## P1 --- Detection correctness

-   Normal diurnal warming detected as drift
-   Genuine faults missed during warm-up
-   Feature leakage
-   Incorrect baseline construction
-   Wrong units or scaling
-   Timestamp misalignment
-   Model/rule disagreement handled incorrectly
-   Spatial corroboration not used or incorrectly used

## P2 --- Reliability and operational consistency

-   Missing or stale data
-   Duplicate readings
-   Out-of-order telemetry
-   Recovery-state errors
-   Event duplication
-   Database inconsistency
-   Broken API contracts
-   Reconnect and refresh problems
-   Performance degradation

## P3 --- Product quality and advanced capabilities

-   Improved visual explanations
-   More sophisticated regime classification
-   Advanced peer aggregation
-   More detailed analytics
-   Additional forecasting or maintenance features

------------------------------------------------------------------------

# 5. Data ingestion and telemetry audit

## 5.1 Schema validation

Verify:

-   Required fields are present.
-   Station IDs are valid.
-   Parameter names are canonical.
-   Units are explicit.
-   Numeric fields are numeric.
-   Timestamps are parseable and timezone-aware.
-   Values are finite.
-   Null values are handled intentionally.
-   Unknown fields do not break processing.
-   Duplicate event IDs are handled deterministically.

Test:

-   Missing station ID
-   Missing timestamp
-   Missing parameter
-   String instead of numeric value
-   NaN and infinity
-   Negative humidity
-   Pressure in the wrong unit
-   Celsius/Fahrenheit confusion
-   hPa/Pa confusion
-   Duplicate message
-   Empty payload
-   Extra unexpected field
-   Malformed JSON

## 5.2 Timestamp correctness

Audit:

-   Timezone conversion
-   Daylight-saving transitions where relevant
-   Future timestamps
-   Very old timestamps
-   Clock skew
-   Duplicate timestamps
-   Out-of-order events
-   Sampling interval irregularity
-   Event time versus processing time

A reading arriving late must not be treated as a current reading without
an explicit policy.

## 5.3 Freshness and staleness

Every station and parameter should expose:

-   Last received timestamp
-   Age of last reading
-   Expected sampling interval
-   Staleness threshold
-   Data quality state

Test:

-   One missing reading
-   Long outage
-   Intermittent outage
-   Delayed batch arrival
-   Stale temperature but fresh humidity
-   Station-level outage
-   Recovery after outage

Do not let stale values silently participate in current network
corroboration or replacement estimation.

## 5.4 Duplicate and replay handling

Verify whether duplicate telemetry:

-   Creates duplicate events
-   Increments CUSUM twice
-   Corrupts rolling windows
-   Changes health counters
-   Changes model features
-   Creates duplicate notifications
-   Produces inconsistent history

Replay processing should be deterministic and idempotent where possible.

## 5.5 Data quality state machine

Define explicit states such as:

``` text
VALID
MISSING
STALE
DUPLICATE
OUT_OF_ORDER
INVALID_RANGE
UNIT_ERROR
SUSPECT
RECOVERING
```

Test transitions and verify that each state has documented downstream
behaviour.

------------------------------------------------------------------------

# 6. History buffer and temporal feature audit

## 6.1 Warm-up behaviour

Investigate all features that use rolling windows.

For each feature, document:

-   Required history length
-   Minimum periods
-   Missing-value behaviour
-   Whether partial windows are allowed
-   Whether the feature is reliable during warm-up
-   Whether the model was trained with the same behaviour

A small number of calm night readings must not create a misleading
baseline for an entire daytime cycle.

Test:

-   First reading
-   First 2--5 readings
-   Minimum-period boundary
-   Full-window boundary
-   Restarted station
-   History reset
-   History loaded from persistence
-   History containing stale or invalid values

## 6.2 Feature alignment

Verify that every feature uses the correct:

-   Parameter
-   Time window
-   Station
-   Unit
-   Timestamp ordering
-   Missing-value policy

Common risks:

-   Temperature history accidentally used for pressure
-   One station's history mixed with another station
-   Future values included in a rolling statistic
-   Different windows used during training and inference
-   Rolling statistics calculated before filtering invalid values
-   Features calculated from imputed values without marking them

## 6.3 Leakage audit

Search for use of:

-   Future readings
-   Future labels
-   Repair status recorded after the event
-   Full-day statistics unavailable at prediction time
-   Post-event peer readings
-   Data cleaned using information from the future
-   Random train/test split for time-dependent sequences

Use chronological validation for temporal behaviour.

## 6.4 Feature numerical stability

Test:

-   Zero variance
-   Nearly zero variance
-   Very large values
-   Negative values where invalid
-   Empty windows
-   Single-value windows
-   Floating-point precision
-   Division by zero
-   Infinite normalized rate of change
-   Missing previous value

All numerical failures must result in explicit status fields rather than
silent default values.

------------------------------------------------------------------------

# 7. CUSUM and drift detection audit

## 7.1 Current failure hypothesis

A normal daily warming pattern can contain a long sequence of positive
changes:

``` text
09°C → 11°C → 13°C → 15°C → 17°C → 19°C → 21°C
```

A raw directional CUSUM detector may interpret this as drift because it
measures sustained directional movement rather than deviation from
expected station behaviour.

## 7.2 Instrument the detector

Log for every decision:

-   Raw reading
-   Previous reading
-   First difference
-   Rate of change
-   Normalized rate of change
-   Positive accumulator
-   Negative accumulator
-   Allowance
-   Threshold
-   Direction streak
-   Window length
-   Baseline state
-   Context state
-   Whether the station is warming or cooling naturally

## 7.3 Test cases

### Normal environmental behaviour

-   Sunrise warming
-   Afternoon cooling
-   Stable night
-   Cloudy-day delayed warming
-   Rapid but realistic weather change
-   Monsoon transition
-   Pressure change before rainfall
-   Humidity increase during cooling
-   Regional temperature movement

### Sensor fault behaviour

-   Positive drift
-   Negative drift
-   Slow offset
-   Step change
-   Intermittent drift
-   Drift with noise
-   Drift during regional warming
-   Drift during regime transition
-   Drift after station restart

## 7.4 Candidate solution

Investigate residual-based drift:

``` text
observed rate of change
− expected rate of change for the station and current context
```

Potential expected-rate sources:

-   Same station and same hour
-   Nearby days with comparable conditions
-   Station-specific robust diurnal curve
-   Regional baseline with station correction
-   Regime-conditioned historical baseline

The expected baseline must be:

-   Causal
-   Available at inference time
-   Robust to contamination
-   Station-aware
-   Able to fall back when history is sparse
-   Versioned and monitored

Do not only increase the threshold. This may hide genuine drift and
reduce recall.

## 7.5 Acceptance criteria

-   Normal diurnal cycles do not automatically generate drift alerts.
-   Genuine drift recall remains acceptable.
-   Drift precision improves on clean weather scenarios.
-   Warm-up behaviour is explicitly tested.
-   Regime transitions do not cause excessive alerts.
-   Results are compared against the original detector using the same
    evaluation set.

------------------------------------------------------------------------

# 8. ML model audit

## 8.1 Model artifact validation

Verify:

-   Correct model file is loaded.
-   Model version is recorded.
-   Feature order is fixed.
-   Feature names match training.
-   Scaling and preprocessing match training.
-   Missing-value handling matches training.
-   Model checksum is known.
-   Inference errors are captured.
-   Model loading failure is visible.

## 8.2 Model availability states

Use explicit states:

``` text
AVAILABLE
UNAVAILABLE_MISSING_FEATURES
UNAVAILABLE_WARMUP
FAILED_PREPROCESSING
FAILED_INFERENCE
ARTIFACT_MISSING
VERSION_MISMATCH
```

Return:

``` json
{
  "model_status": "UNAVAILABLE_MISSING_FEATURES",
  "model_score_pct": null,
  "missing_features": ["rolling_std_6h"],
  "feature_vector_complete": false,
  "model_error": null
}
```

A missing model score must never silently become a normal score.

## 8.3 Model/rule interaction

Test separately:

1.  Model only
2.  Rules only
3.  Model plus rules
4.  Model unavailable
5.  Model failed
6.  Rule bypass enabled
7.  Rule bypass disabled
8.  Conflicting model and rule evidence
9.  Model score at boundary values
10. Missing model score with high rule score

Verify:

-   Fusion weights sum to the intended total.
-   Scores use the correct scale.
-   Null values do not enter arithmetic accidentally.
-   Rule-only decisions are labelled.
-   Deterministic impossible-value rules are distinguished from
    statistical rules.
-   The same event does not receive contradictory labels across API and
    UI.

## 8.4 Threshold and calibration audit

Document:

-   Model score meaning
-   Rule score meaning
-   Fusion score meaning
-   Threshold source
-   Threshold version
-   Whether scores are calibrated
-   Whether thresholds differ by fault type or station
-   Whether thresholds are evaluated on clean and faulty data

If probabilities are displayed, validate calibration using:

-   Reliability diagrams
-   Brier score
-   Expected calibration error
-   Calibration by fault type
-   Calibration by station
-   Calibration by context regime
-   Calibration by model availability

Until calibrated, use `score` or `evidence strength`, not `probability`.

## 8.5 Model drift and data drift

Monitor:

-   Feature distribution changes
-   Missing-feature rate
-   Score distribution
-   Station-specific score shifts
-   New stations
-   Seasonal shifts
-   Sensor firmware changes
-   Unit changes
-   Changes in sampling frequency

Define a process for reviewing drift rather than automatically
retraining without evidence.

------------------------------------------------------------------------

# 9. Rule engine audit

## 9.1 Rule inventory

Create a complete inventory of every rule:

-   Rule name
-   Parameters used
-   Units
-   Thresholds
-   Persistence requirement
-   Cooldown
-   Severity
-   Evidence score
-   Whether it can independently trigger
-   Whether it requires model support
-   Failure behaviour
-   Explanation text

## 9.2 Boundary testing

For each threshold, test:

-   Just below threshold
-   Exactly at threshold
-   Just above threshold
-   Missing value
-   Invalid value
-   Repeated value
-   Rapid reversal
-   Long persistence
-   Threshold crossing and return

## 9.3 Rule conflict testing

Examples:

-   Range rule says abnormal while peer stations agree.
-   Drift rule fires during normal warming.
-   Frozen-value rule fires during genuinely stable weather.
-   Physics rule fires because one parameter is stale.
-   Spike rule fires after delayed data arrives.
-   Multiple rules produce conflicting fault types.

The system must preserve individual rule results rather than collapsing
them into one opaque score.

## 9.4 Explainable rule output

Every triggered rule should include:

``` json
{
  "rule": "temperature_drift",
  "triggered": true,
  "observed_value": 16.5,
  "threshold": 12.0,
  "persistence": 6,
  "evidence_strength": 85,
  "independent_trigger": false,
  "reason": "Positive directional persistence exceeded the configured condition."
}
```

------------------------------------------------------------------------

# 10. Evidence fusion audit

## 10.1 Fusion invariants

Verify:

-   All weights are documented.
-   Weight totals are correct.
-   Missing evidence is not treated as zero without policy.
-   Evidence sources are not counted twice.
-   Rule-only fallback is explicit.
-   Fusion cannot create a false model explanation.
-   Fusion output includes a decision basis.
-   Scores remain within documented bounds.

## 10.2 Decision basis taxonomy

Use explicit values such as:

``` text
MODEL_CONFIRMED
MODEL_AND_RULE_SUPPORTED
RULE_ONLY_DETERMINISTIC
RULE_ONLY_STATISTICAL
PHYSICS_ONLY
NETWORK_SUPPORTED
MODEL_UNAVAILABLE
MODEL_FAILED
CONFLICTING_EVIDENCE
INSUFFICIENT_EVIDENCE
```

A rule may be sufficient to initiate an investigation, but the UI must
state whether the model ran and whether it contributed.

## 10.3 Metamorphic tests

Test properties that should remain true:

-   Reordering identical input records should not change a deterministic
    result.
-   Duplicating a record should not double-count it.
-   Adding an unrelated healthy station should not change a
    station-local rule result.
-   Removing all peers should change corroboration to an explicit
    unavailable state.
-   Changing a unit consistently should preserve the physical
    interpretation.
-   A missing model score should not generate a model explanation.
-   A raw reading should remain unchanged after replacement estimation.

------------------------------------------------------------------------

# 11. Explainability and TrueSHAP audit

## 11.1 Define what "TrueSHAP" means

The term must be specified in the project documentation. It may refer
to:

-   SHAP applied to the exact deployed model
-   Identical preprocessing between inference and explanation
-   A representative background dataset
-   Stable feature attribution
-   A combined model/rule explanation contract

It must not be used as an undefined quality label.

## 11.2 Model explanation requirements

Show SHAP only when:

-   The model actually executed.
-   The feature vector was valid.
-   The deployed model artifact was used.
-   Preprocessing matches inference.
-   The explanation corresponds to the selected event.
-   The explainer is compatible with the model.
-   Any approximation is disclosed.

Include:

-   Model version
-   Explainer version
-   Feature name
-   Feature value
-   SHAP contribution
-   Direction
-   Base value where relevant
-   Model score
-   Background dataset version
-   Explanation status

## 11.3 Separate three evidence layers

### Layer 1 --- Model attribution

What features influenced the model output?

### Layer 2 --- Rule and physics evidence

Which deterministic or statistical conditions were met?

### Layer 3 --- Operational interpretation

What should a human infer, and what remains uncertain?

Do not claim that SHAP proves physical causality or proves that a
particular sensor component has failed.

## 11.4 Explanation correctness tests

-   Feature ablation
-   Feature perturbation
-   Rank stability
-   Background sensitivity
-   Repeatability
-   Preprocessing consistency
-   Correct event selection
-   Correct model version
-   Missing-feature fallback
-   Model failure fallback
-   Contradictory evidence display

## 11.5 UI wording audit

Replace misleading text such as:

> What the model noticed

when no model explanation exists.

Use:

-   Model evidence
-   Rule evidence
-   Decision evidence
-   Explanation unavailable
-   Operational interpretation

------------------------------------------------------------------------

# 12. Station context and environmental regime audit

## 12.1 Why context is required

The same temperature movement may be normal in one context and
suspicious in another.

Relevant context includes:

-   Station-specific diurnal pattern
-   Temperature level and trend
-   Pressure movement
-   Humidity movement
-   Volatility
-   Time of day
-   Day of year
-   Data freshness
-   Recent station history
-   Regional context

## 12.2 Context availability bug

If the UI displays `Regime: UNKNOWN`, investigate whether:

1.  The backend actually returns `UNKNOWN`.
2.  The backend returns a different field name.
3.  The selected event is historical and lacks context.
4.  The context engine lacks enough history.
5.  The context engine failed.
6.  The frontend applies an incorrect fallback.
7.  API and frontend versions differ.
8.  Context is calculated only for new events.

Capture raw API output and compare it with the rendered UI.

## 12.3 Candidate context features

### Temperature

-   Current value
-   Rolling mean
-   Rolling standard deviation
-   Short and long slopes
-   Volatility
-   Same-hour baseline deviation
-   Day/night contrast

### Pressure

-   Current value
-   Short-term slope
-   Multi-window change
-   Volatility
-   Trend persistence

### Humidity

-   Current value
-   Slope
-   Volatility
-   Temperature--humidity relationship
-   Baseline deviation
-   Persistence

### Time and quality

-   Hour
-   Day of year
-   Month
-   Cyclical hour encoding
-   Cyclical annual encoding
-   Time since last valid reading
-   Sampling regularity
-   Missingness pattern

## 12.4 Context implementation stages

### Stage A --- Metadata only

Use context to explain the event without changing the detector.

### Stage B --- Context-conditioned thresholds

Use only after validating:

-   Threshold stability
-   Fallback behaviour
-   Regime misclassification
-   Rare-event handling
-   Auditability

### Stage C --- Context as model input

Requires:

-   Retraining
-   Chronological evaluation
-   Unknown-regime handling
-   Feature availability parity
-   Data leakage review
-   Ablation against the baseline

Start with metadata and evaluation before directly changing model
decisions.

## 12.5 Regime taxonomy

Begin with a small and testable taxonomy:

``` text
DAYTIME_WARMING
NIGHTTIME_COOLING
STABLE
HIGH_HEAT
HIGH_HUMIDITY
PRESSURE_SHIFT
HIGH_VOLATILITY
REGIME_TRANSITION
UNKNOWN_INSUFFICIENT_DATA
UNKNOWN_CONTEXT_FAILURE
```

Avoid creating a large taxonomy before measuring whether it improves
decisions.

------------------------------------------------------------------------

# 13. Spatial cluster and network corroboration audit

## 13.1 Cluster configuration

Verify for every station:

-   Latitude and longitude
-   Cluster ID
-   Peer list
-   Cluster generation version
-   Distance or similarity method
-   Cluster freshness
-   Whether the cluster is empty
-   Whether a station can belong to multiple clusters

A station without a valid cluster must return an explicit reason, not a
generic empty result.

## 13.2 Peer eligibility

A peer should be considered only if:

-   It belongs to the target station's valid cluster.
-   It reports the same parameter and unit.
-   Its timestamp is sufficiently aligned.
-   Its data is fresh.
-   Its health is acceptable.
-   It is not already invalid for the relevant parameter.
-   Its reading is not a duplicate or imputed value unless explicitly
    allowed.

## 13.3 Network evidence

Calculate and expose:

-   Eligible peer count
-   Corroborating peer count
-   Direction agreement
-   Magnitude similarity
-   Time alignment
-   Parameter consistency
-   Peer health
-   Peer volatility
-   Cluster distance or relationship
-   Missing peer count
-   Rejected peer reasons

## 13.4 Network interpretation states

``` text
LOCALIZED_ANOMALY_INDICATION
REGIONAL_EVENT_INDICATION
INSUFFICIENT_CORROBORATION
CONFLICTING_PEER_EVIDENCE
NETWORK_UNAVAILABLE
```

## 13.5 Human-readable examples

### Localized indication

> The Chennai station temperature increased sharply, while eligible
> nearby stations remained within their normal range. The change appears
> localized, so sensor and telemetry investigation is recommended.

### Regional indication

> Chennai temperature dropped rapidly. Several nearby stations showed a
> similar directional change, and humidity and pressure changed
> consistently. The pattern is corroborated across the network, so a
> regional environmental event is plausible. The Chennai sensor should
> not be blamed immediately.

These statements must be generated only from actual evidence and must be
presented as indications rather than definitive diagnoses.

## 13.6 Network failure reasons

Distinguish:

-   No cluster configured
-   No peers found
-   All peers stale
-   All peers unhealthy
-   Timestamp mismatch
-   Parameter mismatch
-   Missing peer history
-   Network service failure
-   Insufficient sample size
-   Conflicting peer movement

------------------------------------------------------------------------

# 14. Suggested replacement reading audit

## 14.1 Core concern

A suggested replacement value must not be treated as automatically
correct merely because it is mathematically convenient.

The system should distinguish:

-   Observed value
-   Baseline estimate
-   Physics-constrained estimate
-   Model reconstruction
-   Network estimate
-   Consensus estimate
-   Operator-approved replacement

## 14.2 Candidate sources

### Temporal baseline

-   Causal rolling median
-   Robust rolling mean
-   Same-hour historical baseline
-   Station trend
-   Regime-conditioned estimate

### Physics-based constraints

-   Physical range checks
-   Cross-parameter consistency
-   Temperature--humidity plausibility
-   Pressure movement plausibility
-   Rate-of-change constraints
-   Unit-aware constraints

### Model-based reconstruction

A separate reconstruction estimator may be evaluated, but anomaly
detection and reconstruction must not be assumed to be interchangeable.

The reconstruction estimator needs its own validation set and error
metrics.

### Network estimate

Use eligible peers only after filtering for:

-   Freshness
-   Health
-   Unit
-   Time alignment
-   Cluster membership
-   Comparable context
-   Non-contamination

## 14.3 Candidate response

``` json
{
  "observed_value": 16.5,
  "candidates": {
    "temporal_baseline": 9.8,
    "physics_estimate": 10.2,
    "model_reconstruction": 10.0,
    "network_estimate": 10.4
  },
  "consensus_value": 10.1,
  "spread": 0.6,
  "replacement_status": "SUGGESTION_ONLY",
  "uncertainty": "MEDIUM",
  "raw_value_preserved": true
}
```

If candidate estimates disagree materially:

``` text
REPLACEMENT_UNCERTAIN
```

## 14.4 Replacement validation metrics

-   Mean absolute error
-   Median absolute error
-   Root mean squared error
-   Error by station
-   Error by parameter
-   Error by regime
-   Error during regional events
-   Error during sensor faults
-   Coverage of uncertainty intervals
-   Rate of unsafe or implausible suggestions

Do not allow a suggested value to enter the primary data stream without
an explicit downstream policy.

------------------------------------------------------------------------

# 15. Fault attribution audit

## 15.1 Attribution must be evidence-backed

A statement such as:

> Temperature C is the most likely affected sensor channel.

must identify its source.

Possible sources:

-   Temperature-specific rule
-   Model feature attribution
-   Cross-parameter physics
-   Peer disagreement
-   Statistical heuristic
-   Fallback logic

## 15.2 Attribution object

``` json
{
  "parameter": "temperature_c",
  "attribution_basis": [
    "temperature_rule_trigger",
    "model_feature_contribution",
    "peer_disagreement"
  ],
  "certainty": "INDICATION",
  "limitations": [
    "The change may be environmental",
    "Peer coverage was incomplete"
  ]
}
```

## 15.3 Attribution test matrix

-   Temperature-only fault
-   Pressure-only fault
-   Humidity-only fault
-   Cross-parameter inconsistency
-   Multiple simultaneous faults
-   Regional weather event
-   Missing SHAP
-   Model unavailable
-   Conflicting rules
-   Conflicting peer evidence
-   Stale peer data
-   Fault during regime transition

------------------------------------------------------------------------

# 16. Sensor health and recovery audit

## 16.1 State machine

Document allowed states and transitions:

``` text
HEALTHY
  → SUSPECT
  → DEGRADED
  → RECOVERING
  → HEALTHY
```

Also define:

-   Fault recurrence
-   Manual maintenance
-   Station offline
-   Unknown state
-   Data-quality-only degradation

## 16.2 Required invariants

1.  A temperature fault must not automatically disable pressure and
    humidity.
2.  Repair must reset the correct parameter-specific counters.
3.  Recovery must require a documented clean streak.
4.  Stale fault status must not persist indefinitely.
5.  A station restart must not silently erase necessary state.
6.  Backend and frontend health indicators must agree.
7.  Historical events must not mutate unexpectedly after recovery.
8.  A single bad peer must not contaminate all network health decisions.

## 16.3 Recovery tests

-   Clean readings after a fault
-   Alternating clean and bad readings
-   Fault recurrence
-   Repair event
-   Missing data during recovery
-   Station restart during recovery
-   Multiple parameter recovery
-   Recovery after regional event
-   Manual override and rollback

------------------------------------------------------------------------

# 17. Event lifecycle and persistence audit

## 17.1 Event identity

Verify that event IDs are stable and unique.

Test:

-   Same reading processed twice
-   Same fault continuing across multiple timestamps
-   Fault ending and restarting
-   Multiple faults at one station
-   Multiple parameters at one timestamp
-   Replay of historical data
-   Database restart
-   Concurrent workers

## 17.2 Event deduplication

Determine whether the system should create:

-   One event per reading
-   One event per continuous incident
-   One event per parameter
-   One event per station
-   One event per fault type

Document and test the chosen policy.

## 17.3 Persistence consistency

Verify consistency between:

-   Current station status
-   Event history
-   Health history
-   Alert list
-   Analytics summaries
-   Reports
-   Suggested replacement records

Test partial database failures and transaction rollback.

------------------------------------------------------------------------

# 18. API and frontend contract audit

## 18.1 Required response contract

A decision response should include:

-   Event ID
-   Station ID
-   Parameter
-   Event timestamp
-   Processing timestamp
-   Observed value
-   Freshness
-   Model status
-   Model score and score type
-   Rule results
-   Fusion result
-   Decision basis
-   Fault attribution
-   Context and reliability
-   Network state
-   Peer counts
-   Suggested values
-   Uncertainty
-   Explanation status
-   Operator interpretation
-   Recommended action
-   Limitations
-   Schema version

## 18.2 Contract tests

Test:

-   Missing model score
-   Missing regime
-   Empty peer list
-   Historical event
-   Missing SHAP
-   Missing replacement candidates
-   Partial parameter data
-   Unknown fault type
-   Unknown decision basis
-   Backend/frontend version mismatch
-   Null versus empty array handling
-   Large event history
-   Invalid timestamp
-   Error response structure

## 18.3 UI truthfulness audit

Check every label and card:

-   Does it describe the actual backend state?
-   Does it distinguish score from probability?
-   Does it say model evidence exists only when the model ran?
-   Does it show why context is unknown?
-   Does it show why corroboration is insufficient?
-   Does it avoid calling a suggestion a correction?
-   Does it show uncertainty and limitations?
-   Does it preserve access to raw telemetry?

## 18.4 Loading and failure states

Test frontend behaviour for:

-   Slow API
-   Timeout
-   Partial response
-   Empty state
-   Backend unavailable
-   Stale cached response
-   Reconnection
-   Out-of-order response
-   User changing stations during loading
-   User selecting an old event
-   Model explanation loading separately

------------------------------------------------------------------------

# 19. Alerting and notification audit

Verify:

-   Duplicate notifications are prevented.
-   Alert severity is consistent.
-   Cooldown behaviour is documented.
-   Alerts close when incidents resolve.
-   Alert acknowledgement is persisted.
-   Notification failures are retried safely.
-   Operators can distinguish new evidence from repeated evidence.
-   A regional indication is not worded as a confirmed sensor failure.
-   Critical data-quality failures are not hidden by low anomaly scores.

Test notification storms caused by:

-   Repeated CUSUM triggers
-   Station restart
-   Database replay
-   Network outage
-   Peer data outage
-   Clock errors
-   Threshold oscillation

------------------------------------------------------------------------

# 20. Security and robustness audit

Even if the system is primarily a monitoring application, test:

## 20.1 Input security

-   Malformed JSON
-   Oversized payload
-   Unexpected strings
-   Injection-like station names
-   Invalid IDs
-   Excessive event frequency
-   Untrusted metadata
-   Invalid file/model path input

## 20.2 Access control

Verify that users can only:

-   View permitted stations
-   Change permitted configuration
-   Approve replacement values if authorized
-   Acknowledge alerts if authorized
-   Access appropriate reports

## 20.3 Audit logs

Log sensitive operations:

-   Configuration changes
-   Threshold changes
-   Model replacement
-   Manual health override
-   Replacement approval
-   Event deletion
-   Data correction

Logs should not expose secrets or credentials.

------------------------------------------------------------------------

# 21. Performance and reliability testing

## 21.1 Latency measurements

Measure separately:

-   Ingestion latency
-   Validation latency
-   Feature generation latency
-   Model inference latency
-   Rule evaluation latency
-   Network corroboration latency
-   Persistence latency
-   API response latency
-   Frontend render latency
-   Alert delivery latency

## 21.2 Load scenarios

-   One station, normal traffic
-   Many stations, normal traffic
-   Sudden telemetry burst
-   All stations reporting simultaneously
-   Large historical query
-   Many concurrent dashboard users
-   Many simultaneous anomalies
-   Network service degradation
-   Database slowdown

## 21.3 Reliability scenarios

-   Model artifact unavailable
-   Database unavailable
-   Peer service unavailable
-   Frontend reconnect
-   Process restart
-   Partial deployment
-   Configuration mismatch
-   Clock skew
-   Memory pressure
-   Long-running process

## 21.4 Polling versus streaming

Do not migrate to SSE/WebSockets merely because it appears modern.

First measure:

-   Current refresh latency
-   Data freshness
-   Server load
-   Client load
-   Reconnect behaviour
-   Duplicate event rate
-   Multi-client behaviour

Retain polling fallback if streaming is introduced.

------------------------------------------------------------------------

# 22. Testing strategy

## 22.1 Unit tests

Required areas:

-   Unit conversion
-   Range validation
-   Timestamp parsing
-   Freshness calculation
-   Rolling features
-   CUSUM accumulation
-   Threshold boundaries
-   Physics constraints
-   Fusion arithmetic
-   Decision-basis assignment
-   Context classification
-   Peer eligibility
-   Replacement estimation
-   Health transitions
-   Event deduplication
-   API serialization

## 22.2 Integration tests

Test the complete path:

``` text
Input telemetry
 → feature generation
 → model/rules
 → fusion
 → context
 → network
 → persistence
 → API
 → frontend contract
```

Use fixed fixtures and expected decision traces.

## 22.3 End-to-end tests

Scenarios:

-   Normal daytime warming
-   Genuine drift
-   Localized temperature spike
-   Regional temperature drop
-   Missing peer data
-   Model unavailable
-   SHAP unavailable
-   Suggested-value disagreement
-   Fault recovery
-   Station restart
-   Duplicate telemetry
-   Historical replay

## 22.4 Property-based testing

Generate varied inputs to test invariants:

-   Values remain within physical bounds after unit conversion.
-   Invalid data never becomes valid silently.
-   Duplicate records do not double-count.
-   Output scores remain in documented ranges.
-   No future data enters a causal feature.
-   Missing model output never produces a model explanation.
-   Replacement estimation never mutates raw data.
-   A station cannot corroborate itself as an independent peer.

## 22.5 Mutation testing

Intentionally modify:

-   Threshold comparisons
-   Fusion weights
-   Rule conditions
-   Feature ordering
-   Unit conversion
-   Timestamp alignment
-   Peer eligibility
-   Health transition conditions

Verify that the test suite detects the changes.

## 22.6 Regression testing

Maintain a permanent fixture set containing:

-   Previously detected bugs
-   Clean weather patterns
-   All supported fault types
-   Edge cases
-   Historical incidents
-   Context failures
-   Network failures
-   Model failures
-   Frontend contract failures

Every bug fix must add a regression test.

------------------------------------------------------------------------

# 23. Scenario matrix

  -----------------------------------------------------------------------
  Scenario                            Expected system behaviour
  ----------------------------------- -----------------------------------
  Normal sunrise warming              Avoid automatic drift conclusion;
                                      show context and evidence

  Normal afternoon cooling            Do not confuse natural reversal
                                      with negative drift

  Stable night                        Avoid frozen-value false positives
                                      when stability is expected

  Genuine positive drift              Detect when residual and
                                      persistence evidence support it

  Genuine negative drift              Detect without asymmetric bias

  Temperature spike                   Show spike evidence and assess peer
                                      corroboration

  Frozen temperature                  Consider sampling frequency and
                                      natural stability

  Fail-low sensor                     Show range/physics evidence and
                                      attribution

  Pressure shift before rain          Avoid immediate sensor-fault
                                      conclusion

  Humidity increase across peers      Consider regional interpretation

  Regional temperature drop           Use directional peer evidence

  Localized temperature jump          Use peer disagreement to support
                                      localized indication

  New station                         Mark context/model warm-up
                                      limitations

  Missing peer data                   Return insufficient corroboration
                                      with reason

  Stale peer data                     Exclude and report rejection reason

  Model unavailable                   Label decision basis explicitly

  SHAP unavailable                    Show rule evidence without fake
                                      model explanation

  Context unavailable                 Show reason rather than generic
                                      unknown

  Conflicting rules                   Preserve all evidence and mark
                                      conflict

  Multiple simultaneous faults        Avoid collapsing all faults into
                                      one channel

  Fault during regional event         Avoid blaming sensor without
                                      local-vs-regional analysis

  Recovery after repair               Require documented clean streak

  Duplicate telemetry                 Avoid duplicate accumulation and
                                      alerts

  Out-of-order data                   Apply explicit event-time policy

  Database restart                    Preserve required state and
                                      idempotency

  Frontend stale cache                Display freshness and avoid
                                      misleading current status
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 24. Ablation and comparative evaluation plan

Run changes independently before combining them.

  Version   Change
  --------- ----------------------------------------
  A         Current production baseline
  B         Model/rule evidence separation
  C         Confidence terminology correction
  D         Diurnal-aware residual drift
  E         Context metadata only
  F         Context as model features
  G         Spatial peer corroboration
  H         Replacement candidate ensemble
  I         Improved health/recovery state machine
  J         Combined selected system

For each version, record:

-   Detection metrics
-   False positives
-   False negatives
-   Detection latency
-   Model availability
-   Explanation availability
-   Context availability
-   Network interpretation quality
-   Replacement error
-   Recovery latency
-   Runtime cost
-   Regression failures

Do not combine all changes in one commit or one experiment.

------------------------------------------------------------------------

# 25. Evaluation metrics

## 25.1 Detection

-   Precision
-   Recall
-   F1
-   False positives per station-day
-   False negatives by fault type
-   Detection latency
-   Alert duplication rate

## 25.2 Interpretation

-   Localized/regional classification accuracy where labels exist
-   Insufficient-evidence rate
-   Peer eligibility accuracy
-   Peer rejection correctness
-   Attribution agreement
-   Context availability
-   Context stability

## 25.3 Explainability

-   Explanation availability
-   Explanation-to-model consistency
-   Feature rank stability
-   Perturbation agreement
-   Rule evidence completeness
-   Explanation latency
-   Percentage of misleading model claims

## 25.4 Replacement values

-   MAE
-   RMSE
-   Median absolute error
-   Error by parameter
-   Error by station
-   Error by regime
-   Uncertainty coverage
-   Unsafe suggestion rate

## 25.5 Operations

-   Ingestion latency
-   Inference latency
-   API latency
-   Alert delivery latency
-   Recovery latency
-   Data freshness
-   Availability
-   Error rate
-   Resource utilization

------------------------------------------------------------------------

# 26. Recommended implementation sequence

## Phase 0 --- Baseline and observability

1.  Freeze code, model, configuration, and data versions.
2.  Reproduce the Ranchi drift incident.
3.  Add decision trace logging.
4.  Capture model availability and missing features.
5.  Record individual rule outputs.
6.  Record fusion inputs and outputs.
7.  Add API response snapshots.

## Phase 1 --- Truthfulness fixes

8.  Separate evidence strength from probability.
9.  Add explicit decision basis.
10. Correct misleading model-explanation labels.
11. Show model-unavailable and explanation-unavailable states.
12. Preserve raw telemetry.
13. Add contract tests.

## Phase 2 --- Detection correctness

14. Build a clean diurnal-weather regression set.
15. Compare raw ROC CUSUM with residual-based CUSUM.
16. Validate warm-up behaviour.
17. Audit all rolling features for leakage.
18. Validate units, timestamps, and missing values.
19. Test rule boundaries and conflicts.

## Phase 3 --- Context and network reasoning

20. Trace the `UNKNOWN` context problem.
21. Implement causal station context.
22. Validate station-specific baselines.
23. Verify spatial cluster wiring.
24. Implement peer eligibility and rejection reasons.
25. Add localized, regional, conflicting, and insufficient states.

## Phase 4 --- Explainability and replacement

26. Define and validate model-aligned SHAP.
27. Separate model, rule, physics, and network explanations.
28. Add replacement candidates from independent sources.
29. Add disagreement and uncertainty.
30. Test replacement estimation separately from anomaly detection.

## Phase 5 --- Health, persistence, and reliability

31. Test the health state machine.
32. Validate parameter-specific recovery.
33. Test event deduplication and persistence.
34. Add restart and outage tests.
35. Measure latency and throughput.
36. Test alert cooldown and notification recovery.

## Phase 6 --- Final validation

37. Run the full scenario matrix.
38. Run unit, integration, end-to-end, property, and mutation tests.
39. Compare all ablation versions.
40. Review UI wording against actual backend evidence.
41. Document known limitations.
42. Freeze release artifacts and rollback procedures.

------------------------------------------------------------------------

# 27. Definition of done

The audit is complete only when:

-   The baseline is reproducible.
-   Every decision has an explicit decision basis.
-   Model availability is visible.
-   Rule evidence is not presented as probability.
-   Normal diurnal warming is tested and does not automatically imply
    drift.
-   Genuine drift recall is measured.
-   All rolling features are checked for leakage.
-   Unit and timestamp handling is tested.
-   Context output is available or has a specific failure reason.
-   Spatial clusters are wired and observable.
-   Peer eligibility is validated.
-   Network conclusions are expressed as indications.
-   Suggested readings include source and uncertainty.
-   Raw telemetry remains immutable.
-   SHAP explanations correspond to the deployed model.
-   Missing SHAP does not create a fake model explanation.
-   Health and recovery states are consistent.
-   Event persistence is idempotent where required.
-   API and frontend contracts are tested.
-   Performance and failure scenarios are measured.
-   Every confirmed bug has a regression test.
-   Known limitations are documented before deployment.

------------------------------------------------------------------------

# 28. Final decision checklist for every alert

SkyGuardAI should be able to answer:

1.  What was observed?
2.  Is the data fresh and valid?
3.  Which rules fired?
4.  Did the ML model run?
5.  What did the model contribute?
6.  Was the model explanation available?
7.  What physical consistency evidence exists?
8.  What is the station's environmental context?
9.  What did eligible nearby stations show?
10. Is the pattern localized, regional, conflicting, or unresolved?
11. Which parameter is implicated, and why?
12. Is the suggested value based on time, physics, model, network, or
    consensus?
13. How uncertain is the suggestion?
14. What is the current health state?
15. What should the operator investigate next?
16. What limitations prevent a stronger conclusion?

A robust output should look conceptually like:

``` text
A sustained temperature increase was detected.

Data quality: valid and fresh.
Model: available / unavailable, explicitly stated.
Rule evidence: directional persistence detected.
Context: normal warming / unknown / transition, with reliability.
Network: corroborated / localized / insufficient / conflicting.
Interpretation: an indication, not a definitive diagnosis.
Suggested value: estimate only, with source and uncertainty.
Operator action: investigate the sensor or environmental event as appropriate.
```

------------------------------------------------------------------------

# 29. Engineering position

The highest priority is **decision integrity**.

Before adding more advanced ML, visualizations, or communication
features, the system must prove that:

-   It knows when the model did not run.
-   It does not confuse rule evidence with probability.
-   It distinguishes normal environmental dynamics from sensor faults.
-   It uses station-specific and regional information responsibly.
-   It does not generate unsupported replacement values.
-   It explains decisions using the evidence that actually produced
    them.
-   It communicates uncertainty honestly.
-   It behaves predictably when data, models, peers, databases, or
    frontend services fail.

The final product should not simply state:

``` text
Drift confirmed — 85% confidence.
```

when the evidence is actually:

``` text
A sustained directional temperature pattern was detected.
The rule engine provided evidence strength of 85/100.
The model was unavailable or did not provide a complete explanation.
Normal environmental warming has not yet been ruled out.
Station context and peer corroboration are reported separately.
The event requires further investigation.
```

That distinction is central to building a trustworthy monitoring system.
