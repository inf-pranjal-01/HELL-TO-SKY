# Full Master Bug Register — SkyGuard AI

| Bug ID | Severity | Category | Description | Affected Components | Status |
|---|---|---|---|---|---|
| **BUG-001** | P1 | Contract Mismatch | Backend returned `risk_level: 'nominal'`, causing frontend validator `ApiError.validationError` and crashing 5 metric cards. | `main.py`, `frontend/src/services/validators.ts` | **FIXED & VERIFIED** |
| **BUG-002** | P1 | Data Parsing | `history_store.py` dropped 4,368 historical CSV rows due to strict ISO timestamp parsing mismatch, truncating 10h charts to 1 point. | `history_store.py` | **FIXED & VERIFIED** |
| **BUG-003** | P2 | Runtime Dependency | Missing `websockets` package caused `/ws/live` to 404, silently forcing polling fallback. | Runtime Environment | **FIXED & VERIFIED** |
| **BUG-004** | P1 | Runtime Crash | `POST /api/repair-sensor` threw `AttributeError` on `SensorHealthTracker.param_offline_reason`. | `model/state.py` | **FIXED & VERIFIED** |
| **BUG-005** | P3 | Stale UI Copy | Low-level internal database terms and uncalibrated confidence text displayed in operator UI. | `frontend/src/components/` | **FIXED & VERIFIED** |
| **BUG-006** | P2 | WebSocket Contract | Edge observation ingestion broadcasted `ANOMALY_DETECTED` while frontend listened for `ANOMALY_EVENT`. | `main.py`, `useDashboardData.ts` | **FIXED & VERIFIED** |
| **BUG-007** | P2 | Detector Logic | Boolean contradiction `neighbor_buffers and len(neighbor_buffers) == 0` rendered Tier 5 ambiguity branch unreachable. | `model/detect.py` | **FIXED & VERIFIED** |
| **BUG-008** | P2 | Test Suite Imports | Missing `PHYSICAL_BOUNDS` and symbol exports from `model.detect` broke collection on 8 unit test files. | `model/detect.py`, `tests/` | **FIXED & VERIFIED** |
| **BUG-009** | P1 | Database DDL / Schema | Missing DDL creation caused fresh TimescaleDB instances to fail on undefined relation `sensor_readings`. | `history_store.py` | **FIXED & VERIFIED** |
| **BUG-010** | P1 | DB Connection Pool | Severed connections returned to pool without `close=True`, poisoning connection pool for workers. | `history_store.py` | **FIXED & VERIFIED** |
| **BUG-011** | P1 | DB Sync Timestamp | `sync_csv_to_db` called `tz_convert` on naive timestamps, throwing `TypeError` and aborting sync. | `history_store.py` | **FIXED & VERIFIED** |
| **BUG-012** | P2 | DB Parameter Mapping | `mark_spike` skipped TimescaleDB updates when parameter name was shorthand ('temp' vs 'temperature_c'). | `history_store.py` | **FIXED & VERIFIED** |
| **BUG-013** | P2 | DB Retention Purge | `clear_all(source=None)` only truncated `sensor_readings`, leaving `station_health_events` dirty in TimescaleDB. | `history_store.py` | **FIXED & VERIFIED** |
