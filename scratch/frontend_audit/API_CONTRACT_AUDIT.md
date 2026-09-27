# API Contract Audit Report — SkyGuard AI

## Executive Summary
A comprehensive contract verification was performed across all frontend TypeScript validators (`frontend/src/services/validators.ts`) and FastAPI backend routes (`main.py`).

| Endpoint | Method | Expected Contract | Actual Backend Response | Status | Action Taken |
|---|---|---|---|---|---|
| `/api/stations` | `GET` | Array of `Station` objects | 28 Station objects with lat/lon/type | **PASS** | Validated |
| `/api/current-reading` | `GET` | `CurrentReading` with `risk_level: 'low'|'medium'|'high'|'critical'` | Returned `'risk_level': 'nominal'` | **FIXED (BUG-001)** | Aligned backend to `'low'` and widened validator to normalize `'nominal'` -> `'low'` |
| `/api/trends` | `GET` | `TrendResponse` with `station_id`, `hours`, `points`, `anomaly_windows` | Full 10-hour telemetry point array | **FIXED (BUG-002)** | Fixed Pandas timestamp parsing in `history_store.py` |
| `/api/anomalies/latest` | `GET` | `AnomalyAlert` or `null` | Single alert object or null | **PASS** | Validated |
| `/api/anomalies/recent` | `GET` | Array of `AnomalyAlert` | Sorted list of past incidents | **PASS** | Validated |
| `/api/sensor-health` | `GET` | `SensorHealth` with per-channel status | Health percentage, parameter status map | **PASS** | Validated |
| `/api/network-status` | `GET` | `NetworkStatus` aggregate metrics | Summary across all 28 stations | **PASS** | Validated |
| `/api/system-status` | `GET` | `SystemStatus` operational mode | Mode ('replay'/'live'), poll intervals | **PASS** | Validated |
| `/api/repair-sensor` | `POST` | Reset station health to `WARNING` | Returned 500 (`AttributeError`) | **FIXED (BUG-004)** | Fixed missing attribute references in `model/state.py` |
| `/api/force-recover` | `POST` | Immediate override to `HEALTHY` | Returns 200 OK | **PASS** | Validated |
| `/api/maintenance-ticket` | `POST` | Ticket creation payload | Returns 200 OK or 404 for missing anomaly | **PASS** | Validated |
