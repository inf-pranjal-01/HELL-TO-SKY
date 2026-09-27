# Full Master Bug Register — SkyGuard AI

### Total Confirmed Bugs Discovered & Remediated: 19

1. **BUG-001 (P1 - Contract)**: Backend `'risk_level': 'nominal'` crashed TypeScript validators expecting `['low', 'medium', 'high', 'critical']`. -> FIXED.
2. **BUG-002 (P1 - Data Parsing)**: Strict ISO format dropped 4,368 historical CSV rows, truncating 10h trend curve to 2 points. -> FIXED.
3. **BUG-003 (P2 - Transport)**: Missing `websockets` Python package caused /ws/live to return 404. -> FIXED.
4. **BUG-004 (P1 - Runtime Crash)**: POST /api/repair-sensor crashed on `param_offline_reason` AttributeError. -> FIXED.
5. **BUG-005 (P3 - Stale Copy)**: Low-level database names leaked into operator badges. -> FIXED.
6. **BUG-006 (P2 - Event Contract)**: Edge ingestion broadcasted `ANOMALY_DETECTED` instead of `ANOMALY_EVENT`. -> FIXED.
7. **BUG-007 (P2 - Logic)**: Boolean contradiction in `detect.py` ambiguity branch. -> FIXED.
8. **BUG-008 (P2 - Imports)**: Missing exports in `detect.py` broke test collection on 8 test suites. -> FIXED.
9. **BUG-009 (P1 - DDL Bootstrap)**: Missing auto-bootstrap DDL crashed fresh TimescaleDB instances. -> FIXED.
10. **BUG-010 (P1 - Connection Pool)**: Dead sockets returned to pool without close=True. -> FIXED.
11. **BUG-011 (P1 - Naive Timestamps)**: `sync_csv_to_db` threw TypeError on naive timestamps. -> FIXED.
12. **BUG-012 (P2 - Parameter Shorthand)**: `mark_spike` skipped TimescaleDB updates for `"temp"`. -> FIXED.
13. **BUG-013 (P2 - Purge Retention)**: `clear_all` only truncated sensor_readings leaving health unpurged. -> FIXED.
14. **BUG-014 (P2 - Analytics Freshness)**: `useAnalyticsData` evaluated freshness against historical timestamp. -> FIXED.
15. **BUG-015 (P2 - Report Generation)**: `generateReport` failed to trigger fresh network fetch. -> FIXED.
16. **BUG-016 (P2 - Severity Casing)**: Uppercase severities failed string matching in analytics. -> FIXED.
17. **BUG-017 (P2 - Type Aliases)**: Shorthand anomaly types yielded zero counts in distribution charts. -> FIXED.
18. **BUG-018 (P2 - Spatial Coherence)**: Missing continuous peer evidence method on PeerSpatialEngine. -> FIXED.
19. **BUG-019 (P1 - Trend Monotonicity)**: `/api/trends` lacked explicit timestamp sorting, causing occasional non-monotonic rendering. -> FIXED.
