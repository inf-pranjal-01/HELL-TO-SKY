# MISSING TELEMETRY FORENSICS

## 1. Zero-Drop vs Gap Rendering
In meteorological telemetry, imputing missing time-series intervals with `0.0` creates catastrophic false anomalies (e.g. pressure dropping to $0\text{ hPa}$ triggers false explosive decompression alarms).

---

## 2. Telemetry Gap Handling Hardening

### A. Non-Imputed Visual Continuity
- Missing readings in time-series arrays are preserved as `null`/`undefined`.
- Chart rendering engines in [TrendChart.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/dashboard/TrendChart.tsx) render visual gaps (broken lines / dashed interpolation) rather than plotting step-drops to zero.

### B. Graceful Degradation on Partial Telemetry
- If a station transmits partial telemetry (e.g., solar radiation sensor is uninstalled or offline), the backend accepts the packet, marks unpopulated channels as null, and evaluates the ML anomaly detector on the remaining active features without throwing validation errors.

### C. Rate-Limit Backoff
- External Open-Meteo API $429\text{ Too Many Requests}$ responses are caught with exponential backoff and jitter, serving the latest cached telemetry point while logging a non-critical rate-limit advisory.

See [`missing_data_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/missing_data_matrix.csv) for full failure mode handling.
