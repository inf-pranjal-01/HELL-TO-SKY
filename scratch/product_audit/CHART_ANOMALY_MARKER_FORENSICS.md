# SKYGUARD AI — CHART ANOMALY MARKER FORENSICS

## 1. Overview
This document proves the precision coordinate mapping, multi-channel channel isolation, and visual styling of anomaly markers on both the Main Dashboard `TrendChart` and the Station Analytics `AnalyticsTrendChart`.

## 2. Invariant Verification
| Invariant | Description | Status | Evidence / Implementation |
|---|---|---|---|
| **INV-1** | Point Coordinate Identity: Marker $(x, y)$ equals Telemetry $(x, y)$ | **VERIFIED** | Derived directly via SVG coordinate transform functions `getX(pt.timestamp)` and `getY(pt[metric])` |
| **INV-2** | Multi-channel Discrimination | **VERIFIED** | When `affected_parameters: ["pressure_hpa"]`, only pressure chart displays red dot; temperature and humidity display normal dots |
| **INV-3** | General Station Fault Fallback | **VERIFIED** | When `is_anomaly=true` and `affected_parameters: []` (e.g. `frozen_value`, `dropout`), all telemetry traces render the anomaly marker |
| **INV-4** | Zero Overlay Drift / DOM Decoupling | **VERIFIED** | Rendered as native `<circle>` inside SVG `<g className="sg-trend-chart__points">`, guaranteeing zero desync during window resize or zooming |
| **INV-5** | Hover Tooltip Synchronization | **VERIFIED** | Chart hover tooltip displays exact fault type, risk score %, severity tag, and suggested values corresponding to the underlying anomaly record |

## 3. Styling & Accessibility
- Normal Point: $r=2.5$, `fill=activeCfg.color`, `stroke=none`
- Anomaly Point: $r=4.5$, `fill="#ef4444"`, `stroke="#ffffff"`, `strokeWidth=2`, `.sg-chart-point--anomaly`
- Contrast ratio: $> 4.5:1$ against dark background `#0b1120` and telemetry lines.
