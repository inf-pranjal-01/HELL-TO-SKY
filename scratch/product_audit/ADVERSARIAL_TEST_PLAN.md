# SkyGuard AI — Adversarial Test Plan

## 1. Objectives & Scope
The adversarial test suite was designed to stress the application beyond normal developer testing by simulating hostile user behaviors, asynchronous network race conditions, invalid packet fuzzing, and state-bleed vectors.

## 2. Attack Vectors & Methodology
1. **Live <-> Replay Cross-Contamination**:
   - Injecting synthetic faults in replay mode while monitoring peer stations to verify zero state leakage.
   - Stopping replay and verifying that in-memory scratch buffers reset to live Open-Meteo feeds without lingering OFFLINE flags.
2. **High-Concurrency Race Conditions**:
   - 100 simultaneous requests switching stations and query parameters (`hours=10`, `hours=24`, `hours=72`).
   - Verifying station response routing parity and thread safety.
3. **Semantic Contradiction Engine**:
   - Validating that no station ever exhibits contradictory state pairings (e.g. `anomaly_score >= 80%` + `LOW RISK`, or `sensor_health = 100%` + `OFFLINE`).
4. **WebSocket Stress & Fuzzing**:
   - 20 rapid disconnect/reconnect cycles.
   - Injection of malformed JSON strings, binary data, and out-of-order sequence packets.
5. **Destructive Action Safety**:
   - Invocation of `/api/admin/clear-history` and invalid station IDs to verify strict HTTP 4xx error boundaries without server 500 crashes.
