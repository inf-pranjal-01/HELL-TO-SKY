# SKYGUARD AI — RESET DB DATABASE FORENSIC AUDIT

## 1. Executive Summary & Root Cause of the 1,178 Rows Phenomenon
1. **The Root Cause**:
   - The Python runtime was missing the `psycopg2-binary` driver module at startup, triggering a `ModuleNotFoundError` during pool initialization.
   - `HistoryStore` swallowed this exception and set `self.use_db = False` (operating in offline CSV fallback mode).
   - When the user clicked "Reset DB", `HistoryStore.clear_all()` only cleared the local SSD CSV files and in-memory ring buffers, **never executing the TRUNCATE command on Tiger Cloud TimescaleDB**.
   - As a consequence, Tiger Cloud retained its historical snapshot of **1,178 rows** perpetually.
2. **The Remediated & Verified Behavior**:
   - `psycopg2-binary` was installed and verified.
   - Upon clicking "Reset DB", `TRUNCATE TABLE sensor_readings;` and `TRUNCATE TABLE station_health_events;` are executed directly against Tiger Cloud, dropping row count to **0 rows**.
   - A sentinel row (`TEST-SENTINEL-999`) was inserted, and Reset DB destroyed it with 100% verification.
   - Immediately following truncation, `sim.refresh_live_now()` queries the live Open-Meteo provider and inserts 28 fresh timestamps for all active stations into TimescaleDB.

---

## 2. Quantitative Verification Lifecycle

| Checkpoint | Database Row Count | Distinct Stations | Action Taken |
|---|---|---|---|
| **T0 (Before Reset)** | 1,178 rows | 28 | Initial state with historical live data |
| **T1 (Sentinel Added)** | 1,179 rows | 29 | Inserted `TEST-SENTINEL-999` |
| **T2 (Post-Truncate)** | 0 rows | 0 | `TRUNCATE TABLE sensor_readings;` executed & committed |
| **T3 (Live Repopulation)** | 28 rows | 28 | `sim.refresh_live_now()` inserted fresh live observations |
