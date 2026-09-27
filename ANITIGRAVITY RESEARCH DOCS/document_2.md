# SKYGUARD AI
## TECHNICAL METHODOLOGY, ARCHITECTURE & USE-CASE DOCUMENT

---

## 1. Verified System Architecture

SkyGuard AI is a Python/FastAPI backend system running an anomaly detection pipeline on telemetry streams (Temperature, Pressure, Humidity). It leverages physical rules, statistical outlier detection (Isolation Forests), spatial consensus, and temporal logic to produce a fused decision (NORMAL / FAULT / AMBIGUOUS).

---

## 2. End-to-End Data Flow

1.  **Ingestion:** Data is received via HTTP/WebSocket and enters the `StateManager.ingest_reading` in `model/state.py`.
2.  **Time Alignment:** The incoming reading's timestamp defines the atomic temporal boundary. Pre-timestamp history and atomic sibling network snapshots are synchronized.
3.  **Feature Construction:** `build_features_for_history` calculates rolling physical metrics, rates of change, robust scaled values, and cross-parameter physics (Clausius-Clapeyron deficit).
4.  **Detector Layers:** Multi-tiered logic (Tier 1 physical bounds to Tier 4 Isolation Forest).
5.  **Arbitration:** `DecisionEngine.decide` arbitrates conflicting evidence via priority weights and confidence scoring, vetoed if necessary by spatial consensus (Tier 5).
6.  **Explanation:** `ExplainerCache.explain` utilizes `shap.TreeExplainer` to perform localized feature attribution on the Isolation Forest score.
7.  **Final State:** The result updates the `StationBuffer.health` tracker. Genuine faults result in the row being quarantined (excluded from baseline calculations).
8.  **Persistence/Storage:** Appended to CSV-based `HistoryStore`.

---

## 3. Exact 49-Feature Inventory

The core `Isolation Forest` operates on a continuous, spatial-free physical feature vector (defined in `features.py`):
1-3: Raw sensor values (Temperature, Pressure, Humidity)
4-6: Deviations (z-score approximations)
7-12: Rates of change (1h, 3h)
13-15: Volatility
16-17: Cross-parameter physics (Dewpoint depression, Vapor pressure deficit)
18-21: Cyclical time components (Hour sin/cos, Day of Year sin/cos)
22: Elapsed physical time (`dt_hours`)
23-25: Robust statistical scales
26-28: Tracking hours since last valid reading
29-40: Rolling Ranges (1h, 3h, 6h, 24h)
41-46: Rolling Slopes (6h, 24h) via `merge_asof`
47-49: Same-hour residuals (comparing to historical diurnal baselines)

*Note: Spatial peer variables were explicitly removed from the model feature vector to eliminate train/serve mismatch and are instead resolved at the arbitration layer.*

---

## 4. Detector Inventory

*   **Tier 1: Specialist Jump / Frozen LLR:** Detects mathematically impossible physical values, immediate non-physical acceleration (spikes), and zero-variance dead sensors.
*   **Tier 2: Psychrometric Covariance LLR:** Identifies impossible thermodynamic states (e.g., temperature and humidity diverging unphysically).
*   **Tier 3: CUSUM Low-SNR Drift:** Tracks cumulative summation of standard innovation residuals over time to identify slow calibration drift.
*   **Tier 4: Calibrated Tail Isolation Forest:** Non-parametric isolation of unstructured multidimensional anomalies.
*   **Tier 5: Regional Weather Consensus Veto:** A 7-cluster strict boundary topology. If 2+ local sibling peers demonstrate similar movement, it vetoes the local anomaly flag as genuine regional weather.

---

## 5. Mathematical Metric Register

| Metric | Formula / Logic | Used Where | Purpose |
| :--- | :--- | :--- | :--- |
| **CUSUM** | $S_{t} = \max(0, S_{t-1} + z_{t} - k)$ | Tier 3 Detector | Detects slow persistent bias |
| **Robust Scale** | $(X - \text{median}) / \text{IQR}$ | Features 23-25 | Median-based scaling immune to spikes |
| **Clausius-Clapeyron** | Tetens empirical formula | Tier 2 Covariance | Checks thermodynamic consistency |
| **Isolation Score** | Derived from mean path length | Tier 4 Model | Computes unstructured outlierness |

---

## 6. Arbitration Logic

The `DecisionEngine` employs strict hierarchical tiering.
1. High-specificity detectors (Tier 1/2) override low-specificity scores.
2. The Isolation Forest score is threshold-calibrated to a predefined limit (e.g., score > 50.0 indicates anomaly, score > 95.0 hard override).
3. Ambiguity occurs when the model detects an anomaly, but the spatial veto engine registers matching activity in sibling nodes (state transitions to `AMBIGUOUS`).

---

## 7. State & Data Trust Logic

*   **Raw vs. Trusted:** In `state.py`, `StationBuffer.record_raw_reading` selectively excludes a row from entering the rolling baseline buffer if the row is marked as a confirmed anomaly (`is_anomaly=True`), or if the station is OFFLINE.
*   **Result:** Anomalous readings do *not* contaminate the rolling historical state context.

---

## 8. Explainability Architecture

*   **SHAP Implementation:** `model/explain.py` uses `shap.TreeExplainer` on the Isolation Forest to extract the top feature attributions.
*   **Fallback:** If the specific `shap` version fails or returns errors with `IsolationForest` outputs, it deterministically degrades to a robust feature magnitude ranking.

---

## 9. Confidence/Severity Logic

Severity is categorized based on the decision origin (e.g., a hard physical bounds violation yields CRITICAL, a marginal model drift yields WARNING). Confidence is derived from fusion rule weights (Rule Base + Model Score).

---

## 10. Sensor-Health & Recovery Logic

*   **Transitions:** The `SensorHealthTracker` moves from NORMAL -> WARNING (isolated anomaly) -> OFFLINE (repeated failures, >3).
*   **Recovery:** Operates on a count-based clean streak (e.g., 3 consecutive normal readings) to transition from OFFLINE back to NORMAL. Support exists for an instant `force_recover()` API call.

---

## 11. API / Frontend Contract

*   **APIs:** `GET /api/stations`, `GET /api/anomalies/latest`, `POST /api/repair-sensor`
*   **WebSocket:** `/ws` for streaming telemetry.
*   **Payloads:** Return exact confidence, severity, fault_type, and suggested_value fields matching frontend component types.

---

## 12. Storage & Database Status

*   **Current:** Local CSV tracking via `HistoryStore` and in-memory double-ended queues (`collections.deque`) in `StationBuffer`.
*   **Not Implemented:** Formal SQL/NoSQL external clusters (e.g., TimescaleDB).

---

## 13. Real-Time Timing Architecture

*   **Inference Latency:** Vectorized NumPy feature engineering combined with preloaded Sklearn isolation trees achieves roughly **0.210 ms** compute per row.
*   **Scope:** This bounds the CPU inference logic, excluding FastAPI routing and WebSocket serialization.

---

## 14. Deployment Status

*   **Current:** Dockerized `docker-compose.yml` for unified backend/frontend deployment. Readily deployable on PaaS environments via `Procfile`.
*   **Future Scope:** Migration to edge microcontrollers (e.g., ESP32/ARM) is physically plausible given low latency but is not presently implemented.

---

## 15. Use-Case Matrix

| Use Case | Operational Scenario | Current Capability | Demonstrated? | Limitations |
| :--- | :--- | :--- | :--- | :--- |
| **AWS Quality Control** | Screening bad hardware readings | Full Pipeline | YES | Real-world severe validation pending |
| **Predictive Maintenance** | Dispatching field techs to broken sensors | Component fault isolation | YES | Requires manual intervention UI |
| **Climate Archival** | Preventing corrupted databases | Contamination block in `state.py` | YES | None |

---

## 16. Limitations & Unresolved Questions

*   **Real-World Severity:** Empirical efficacy heavily relies on `anomaly_injector.py`. Absolute generalization to undocumented natural phenomena remains untested.
*   **End-to-End Latency:** 0.210 ms inference is measured, but full stack latency including WebSockets is unprofiled.

---

## 17. Current vs. Future Matrix

| Capability | Current | Demonstrated | Future Scope |
| :--- | :--- | :--- | :--- |
| SHAP Explanations | YES | YES | - |
| Spatial Consensus | YES | YES | - |
| Microcontroller Edge Run | NO | NO | YES |
| TimescaleDB Persistence | NO | NO | YES |

---

## 18. Technical Claim Register

| ID | Technical Claim | Verified | Safe to State? | Caveat |
| :--- | :--- | :--- | :--- | :--- |
| TC1 | 49-feature continuous matrix without positional shifts | YES | YES | State "continuous physical time". |
| TC2 | Strict 7-cluster spatial isolation | YES | YES | - |
| TC3 | Unsupervised Isolation Forest integration | YES | YES | - |

---

DOCUMENT 2 TECHNICAL EVIDENCE EXTRACTION COMPLETE
