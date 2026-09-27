# SKYGUARD AI — ANOMALY EVENT PIPELINE FORENSIC AUDIT

## 1. Executive Summary
This forensic audit documents the end-to-end investigation and verification of the single canonical event identity pipeline across SkyGuard AI, specifically addressing:
- **Problem A**: Anomaly records existed and were visible in incidents/tooltips, but telemetry charts failed to render anomaly markers.
- **Problem B**: The sidebar "Anomaly Alerts" navigation link did not visibly notify the operator when new anomalies arrived.

## 2. Source-to-UI Pipeline Architecture
```
+---------------------------------------------------------------------------------------------------+
| 1. DETECTOR (Physics/Stats/ML Engine)                                                             |
|    - Evaluates readings (e.g. frozen_value, spike, drift, dropout)                                |
|    - Emits is_anomaly=True, fault_type, severity, risk_score, affected_parameters                |
+-------------------------------------------------+-------------------------------------------------+
                                                  |
                                                  v
+-------------------------------------------------+-------------------------------------------------+
| 2. BACKEND API & WEBSOCKET ENGINE (FastAPI/SQLAlchemy)                                            |
|    - Persists AnomalyEvent to database with canonical UUID id                                     |
|    - Broadcasts JSON frame: {"type": "ANOMALY_EVENT", "data": {...}}                              |
|    - Telemetry API returns historical points with is_anomaly, fault_type, risk_score, severity    |
+-------------------------------------------------+-------------------------------------------------+
                                                  |
                                                  v
+-------------------------------------------------+-------------------------------------------------+
| 3. FRONTEND STATE & NOTIFICATION LAYER (React/Context)                                            |
|    - AlertNotificationContext: Seeds knownAnomalyIds on initial hydration                         |
|    - Dynamic ingestion: On incoming ANOMALY_EVENT, checks if id is known; if new, triggers pulse  |
|    - TrendChart / AnalyticsTrendChart: Maps point timestamps to SVG coords                        |
+-------------------------------------------------+-------------------------------------------------+
                                                  |
                                                  v
+-------------------------------------------------+-------------------------------------------------+
| 4. OPERATOR INTERFACE (SVG Visualizations & Sidebar)                                              |
|    - Chart: SVG circle (r=4.5, fill=#ef4444, stroke=#ffffff, strokeWidth=2, drop-shadow pulse)   |
|    - Sidebar: Red pulsing indicator dot on "Anomaly Alerts" (sg-sidebar__alert-dot)               |
+---------------------------------------------------------------------------------------------------+
```

## 3. Root Cause Analysis
### Problem A (Missing Anomaly Markers on Chart)
- **Root Cause**: `isMetricAnomalous(pt, metric)` in `TrendChart.tsx` and `AnalyticsTrendChart.tsx` had an overly strict fallback: `return false;`. For general station faults (`frozen_value`, `dropout`, `statistical_anomaly`) where `suggested_*` is null during baseline warmup and `affected_parameters` is empty, `isMetricAnomalous` returned `false`, causing the SVG circle to render with normal series color (`activeCfg.color`, $r=2.5$) even when `pt.is_anomaly === true`!
- **Resolution**: Updated `isMetricAnomalous` so that if `pt.is_anomaly` is true, and it is not explicitly restricted to another channel, it returns `true`.

### Problem B (Missing Navigation Indicator for New Alerts)
- **Root Cause**: There was no active notification broker or dedicated navigation badge/dot in `Sidebar.tsx` to alert operators on other views (Dashboard, Stations, SHAP, Diagnostics) of newly incoming anomalies.
- **Resolution**: Created `AlertNotificationContext.tsx` with deduplicated ID tracking and route-aware clearing, and styled `.sg-sidebar__alert-dot` and `.sg-sidebar__icon-dot` with `@keyframes sg-alert-pulse` in `Sidebar.css`.
