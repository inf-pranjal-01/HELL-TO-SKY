# Old Path-1 Contamination Audit Log

| Area | Stale Concept Found | Classification | Action Taken |
|---|---|---|---|
| Latency Badge | Hardcoded `(TimescaleDB)` in UI badge | OBSOLETE | Removed low-level DB string; normalized to `Live WS` |
| Anomaly Card | `AI Model Confidence: 100%` on heuristic bounds | OBSOLETE | Replaced with calibrated `Anomaly Severity / Confidence Score` |
| Explainability Modal | Hardcoded references to `Isolation Forest Outlier Score` | OBSOLETE | Normalized to multi-tier dynamic residual scoring |
| Freshness Hook | `calculateFreshness` called on observation timestamp | OBSOLETE | Switched to query `lastUpdated` timestamp |
