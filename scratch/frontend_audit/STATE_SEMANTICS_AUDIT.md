# State Semantics & Circuit Breaker Audit — SkyGuard AI

## Anomaly & Circuit Breaker State Machine
SkyGuard AI tracks per-station and per-sensor health states:
- `HEALTHY`: Normal baseline operation. Readings included in historical statistics.
- `WARNING`: Anomaly detected or station undergoing post-repair recovery verification.
- `OFFLINE`: Persistent failure (bounds violation, physical dropout, or sensor fail-low). Station excluded from neighbor baselines.

### Recovery Mechanics & Fix (BUG-004)
- **Defect**: `POST /api/repair-sensor` triggered `AttributeError` in `model/state.py` due to non-existent `param_offline_reason` and `_param_clean_streak` attributes on `SensorHealthTracker`.
- **Fix**: Implemented safe `hasattr` checks and parameter deque clearing in `mark_repaired` and `force_recover`.
- **Verification**: Operator sensor reset transitions station to `WARNING` and requires 3 consecutive clean readings before returning to `HEALTHY`.
