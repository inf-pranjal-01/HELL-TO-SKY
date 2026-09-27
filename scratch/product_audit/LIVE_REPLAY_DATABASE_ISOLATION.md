# SKYGUARD AI — LIVE vs REPLAY DATABASE ISOLATION AUDIT

## 1. Isolation Architecture
1. **Replay Persistence Guarantee**: Replay telemetry is stored strictly in memory and local scratch buffers. It is completely isolated from production TimescaleDB live tables.
2. **Clear History Isolation**:
   - `target="replay"`: Purges replay scratch without touching live tables.
   - `target="all"`: Full clean reset.
3. **Data Bleed Immunity**: Ingesting replay anomalies dynamically updates replay state without contaminating the `_last_live_latest` cache.
