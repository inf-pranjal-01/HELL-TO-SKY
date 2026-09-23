# Skyguard calibration diagnostic: seed 71001

## Benchmark scope

This is the label-masked **oracle diagnostic** on 60,480 rows from calibration seed 71001, not the production-faithful acceptance benchmark. Ground-truth labels were used only by the offline oracle baseline masking and by the report analysis. Detector input remained label-free. No held-out seed or station result was used to choose a detector change.

The full trace is in `oracle_predictions.csv`; fixed benchmark metrics and row/episode reason summaries are in `summary.json`. Candidate grid outputs are `dynamic_envelope_grid.csv`, `dynamic_envelope_station_aware.csv`, and `helper_candidate_metrics.json`.

## Current result

| View | Precision | Recall | TP | FP | FN |
|---|---:|---:|---:|---:|---:|
| Pooled row-level overall | 90.9% | 24.9% | 971 | 97 | 2,925 |
| Drift episodes | 15.1% | 41.4% | 29 | 163 | 41 |
| Frozen episodes | 62.5% | 14.3% | 10 | 6 | 60 |

Targets remain unmet. Overall recall misses by 55.1 percentage points; do not interpret high overall precision as progress toward the joint target.

## Trace-level failure attribution

### Drift

- Of 70 labeled events, 66 had local CUSUM rule evidence at least once; four had no local evidence.
- Only 29 events produced a correctly typed and parameter-matched alert. The matched events had a median confirmation delay of 26 hours.
- Among the 41 missed events, the event-level trace classified 32 as losing their drift evidence at the network-veto stage and five as having evidence survive at least once but no matching final drift alert. The remaining four had no local drift evidence.
- The current peer comparison can call a target regional when peers move similarly. It does not quantify a target’s accumulating 6–12 hour deviation from a leave-one-out cluster trajectory. Synthetic drift is an offset added to real weather, so raw direction agreement can hide a real sensor-specific ramp.

### Frozen

- Of 70 events, 65 had local flatness evidence at least once; five had no local evidence and one was removed by the model gate.
- Ten events matched. Of the remaining 59, 24 were suppressed by peer/regional decisions; 30 had local evidence survive at least once but failed to become a matched frozen episode.
- In those surviving rows, model confidence was commonly around 0–20% while frozen rule confidence was 80–89.5%. Fusion weights these to below the 50% alert threshold. Peer confirmation is capped below the 90% rule bypass, so even confirmed divergence often cannot raise the verdict to an alert.
- A calibration-only latch candidate using sustained local flatness plus at least one divergent peer reached 34/70 episode recall and 69.4% episode precision (34 TP, 15 FP, 36 FN). A two-of-three peer confirmation raised precision to 78.1% but lowered recall to 35.7%. Neither meets both frozen episode targets.

### False alarms and other missed faults

- There were 97 row false alarms: 81 were ML-only `unstructured_anomaly` alerts, including 43 with `REGIONAL_STABILITY` context and 38 without peer context. The other 16 were rule/fusion alerts (13 drift, two spike, one frozen).
- Raising the ML-only threshold from 95 to 97 moved overall precision/recall from 90.9%/24.9% to 94.8%/23.4% (TP 911, FP 50). This trades away recall and does not solve the joint target.
- Suppressing every regional-state ML alert removes 43 FP but also 122 TP: precision/recall becomes 94.0%/21.8%. A blanket regional veto is therefore rejected.
- 218 of 279 labeled multivariate rows were missed. The multivariate rule insertion is currently commented out in `model/detect.py`; 61 other rows were alerted under different fault types. Spikes had 25 misses; unstructured faults had 66 misses; sensor-fail-low had 19 misses.

## Candidate checks

- **Fault-helper role correction:** The intended role is classification after the detector has already marked a row anomalous. The loaded parent, `hello sky`, and `LULLABY-SKYGUARD-main` pickles expose only Boolean `False`/`True` classes (including their frozen specialists); they cannot identify `drift`, `frozen_value`, `spike`, or other fault types. The serving `score_reading` path currently lets this Boolean helper change the anomaly verdict and defaults a helper-only positive to `drift`, which does not match the intended role. My prior threshold sweep treated it as a second binary detector and is **not applicable** to your requested fault-label role; do not use those numbers to choose the anomaly detector. The replay evaluator loaded only `isolation_forest.pkl`, so helper influence is absent from the reported benchmark.
- **Multiclass labeler diagnostic:** A fresh ExtraTrees classifier trained on three sparse-replay seeds while excluding all seven test faulted stations labeled 971 rows that the base detector had already flagged correctly. On seed 71001, accuracy was 95.8% (macro F1 82.6%). Frozen labeling was weak: 1/12 correct (8.3% recall); drift was 188/204 (92.2%), multivariate 61/61, and spike 2/3. This is conditional label accuracy only; it does not change binary detection metrics. Results are in `fault_type_labeler_metrics.json`. It is a single calibration diagnostic over the same weather period, so class-wise results—especially frozen—need independent-seed and station-fold validation.
- **6/12-hour cluster envelope:** Initial pooled and station-aware residual-threshold grids were tested against this calibration replay. No tested setting achieved 80% precision; the best station-aware union point was about 44.3% precision/51.7% recall. The tested formulation is rejected. The reference idea needs a better weather-conditioned residual and persistence definition before implementation.
- **Frozen peer latch:** One divergent peer plus sustained local freeze is close to, but below, both episode thresholds. More peer persistence improves precision but suppresses too many episodes. Treat this as a candidate family for calibration, not a selected rule.

## Working plan for the next checkpoint

1. Keep the metric contract fixed: pooled row-level overall precision/recall, plus one-to-one frozen/drift event matching by station, parameter, fault type, and overlap. Do not mask onset rows from overall recall.
2. Keep the two responsibilities separate. The base detector decides anomaly versus normal and is the only component scored for overall detection precision/recall. A multiclass fault-type classifier may label an already-detected anomaly; it must never create or suppress anomaly verdicts. The current Boolean helper pickle cannot fill this classifier role, so train and name a separate typed classifier artifact only after validating its class coverage and label quality.
3. Use calibration seeds 71001–71003 only. Split candidate fitting from candidate selection by seed; retain faulted-station holdout folds. Do not inspect held-out seeds 82001–82003 until the candidate is frozen.
4. Fix frozen confirmation first: compare parameter-specific local persistence, one-peer versus quorum peer divergence, short confirmation windows, and an active incident latch that stays open only while causal freeze evidence remains. Log how each candidate crosses from rule evidence through network and final fusion.
5. Replace the drift point-comparison candidate with a leave-one-out cluster residual over 6/12-hour changes, conditioned on time-of-day and recent peer dispersion. Normalize by per-parameter clean residual distributions learned only from calibration training partitions. Require causal directional persistence; test against natural regional fronts and normal station-specific weather variation.
6. Re-enable and calibrate multivariate consistency as a separate fault path. Audit the ML-only override with temporal novelty and peer residual features; do not use a blanket regional veto. Keep physical bounds, dropout, and fail-low fast paths independent.
7. Compare the existing detector, each isolated change, and a combined candidate. Select only on held-in calibration validation with the complete FP/FN and event traces. Overall detection metrics must be computed before/without typed classification; also report per-fault label confusion on detected anomalies, especially frozen. Advance only if results improve without metric changes; otherwise report the remaining gap and revise the candidate.
8. After the next checkpoint is approved and a configuration is frozen, run production-faithful replay and held-out seeds/stations as the acceptance gate. Keep oracle-clean results labeled diagnostic.

## Work completed in this diagnostic round

Evaluation-only trace fields now preserve detected rules, rules after model gating, rules after network handling, model/rule confidence, peer counts, and final basis when explicitly requested by the evaluator. Live detector callers leave the option off. The corrected replay metrics exactly match the prior corrected run. Focused tests: 16 passed (`unittest`). No detector threshold or verdict behavior was changed in this round.

This plan is evidence-based but is not a guarantee of 80/80. The current data and candidate checks show that no safe one-line threshold or helper addition can meet the target; the next checkpoint must implement and validate the coupled temporal, spatial, and fault-specific changes on calibration data.
