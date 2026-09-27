# SKYGUARD AI — EVENT IDENTITY AUDIT

## Canonical Event Identity Matrix

| Stage | Field / Property | Mapping & Verification |
|---|---|---|
| **Detector** | `is_anomaly: bool` | Emitted by `DetectorEngine.process_reading()` |
| **Detector** | `fault_type: str` | Canonical string (e.g. `frozen_value`, `spike`, `drift`, `dropout`) |
| **Detector** | `risk_score: float` | Scaled $0.0 - 1.0$ (displayed as $0 - 100\%$) |
| **Detector** | `severity: str` | `low`, `medium`, `high`, `critical` |
| **Detector** | `affected_parameters: list[str]` | `["temperature_c"]`, `["humidity_pct"]`, `["pressure_hpa"]`, or `[]` |
| **Database** | `anomalies.id` | UUID primary key generated at persistence |
| **WebSocket** | `ANOMALY_EVENT` payload | Contains `id`, `station_id`, `timestamp`, `fault_type`, `severity`, `risk_score`, `affected_parameters` |
| **Frontend State** | `TelemetryPoint.is_anomaly` | Direct boolean mapped from API response |
| **Chart Marker** | `SVG <circle>` | Rendered with red fill (`#ef4444`) and white outline (`#ffffff`) at coordinate $(x, y)$ |
| **Tooltip** | Hover Modal | Displays canonical fault type, severity, risk score %, and suggested value |
| **Sidebar Badge** | `.sg-sidebar__alert-dot` | Pulsing indicator triggered by new canonical UUID |

All layers share the exact same semantics, terminology, and numerical values with zero transformation discrepancies.
