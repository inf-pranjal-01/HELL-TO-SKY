# LIVE AND REPLAY STATE ISOLATION AUDIT

## 1. Objective
Ensure complete, hermetic isolation between **Live Ingestion Mode** (real-time Open-Meteo polling and ESP32 hardware streaming) and **Benchmark Replay Mode** (deterministic offline validation dataset).

---

## 2. Leakage Vulnerability Analysis & Fixes

### A. Buffer Bleed Prevention
- **Issue**: Toggling between Live and Replay previously appended replay data into the live telemetry array.
- **Fix**: Mode toggle handler flushes telemetry buffers immediately, unmounts active streams, and triggers a clean re-fetch from the corresponding canonical data source.

### B. Controls & Indicator Isolation
- Replay playback scrubber, speed multiplier ($1\times, 2\times, 5\times$), and progress bars are strictly hidden when `streamMode === 'live'`.
- Live polling heartbeat and connection status are strictly hidden when `streamMode === 'replay'`.

### C. Database Isolation
- Benchmark replay runs purely in-memory and in client state; it never writes synthetic anomalies or telemetry into the persistent TimescaleDB tables.
- Reset DB operations during Replay reset replay cursor state without mutating the persistent production database.

See [`live_replay_state_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/live_replay_state_matrix.csv) for mode transition verification.
