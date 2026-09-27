# SKYGUARD AI — DATABASE SOURCE OF TRUTH RECONCILIATION

## 1. Persistence Layer Architecture

| Layer | Storage Engine | Purpose | Write Authority | Reset Behavior |
|---|---|---|---|---|
| **TimescaleDB Primary** | PostgreSQL 18.6 / Timescale Hypertable | Authoritative historical & live sensor telemetry | Ingest worker (`source == 'live'`) | `TRUNCATE TABLE sensor_readings` |
| **Local SSD Mirror** | CSV files (`data/history/*_history.csv`) | High-speed offline failover & replay buffer | `HistoryStore` append | Unlinked / Purged |
| **RAM Ring Buffers** | `sim.trend_history` | Low-latency 24h dashboard chart rendering | Simulation tick & edge ingest | `.clear()` |
| **RAM Deque** | `sim.recent_anomalies` | Fast anomaly alerts, modal, & X-Ray lookups | Level-2 scoring pipeline | `.clear()` |
| **WebSocket Stream** | `/ws/live` push broadcast | Real-time telemetry & anomaly distribution | `ws_manager.broadcast()` | `HISTORY_PURGED` broadcast |
