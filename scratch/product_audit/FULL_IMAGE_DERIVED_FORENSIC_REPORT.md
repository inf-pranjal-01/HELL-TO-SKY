# FULL IMAGE-DERIVED FORENSIC REPORT

## 1. Executive Summary
This report provides an exhaustive, adversarial forensic breakdown of the user-observed phenomena and screenshot evidence across 55 test cases. Every image anomaly, UI contradiction, edge provenance claim, and data reconciliation issue has been verified against the canonical TimescaleDB store, backend detection pipeline, and React frontend.

---

## 2. Image Evidence & Forensic Reproduction Matrix

### Image 1: Isolated Chart Marker & Coordinate Mapping
- **Observed**: Anomaly marker renders at a sharp downward excursion on a single channel.
- **Forensic Verification**: Confirms that SVG coordinate mapping is functional. The failure pattern occurs when multiple metrics exist or when single-channel faults bleed across unrelated metric traces.
- **Root Cause**: Anomaly marker predicate `isMetricAnomalous` was previously missing metric-specific parameter checks.
- **Resolution**: Bound marker rendering to `affected_parameters` list in telemetry point data.

### Image 2: Chennai (`AWS-CHN-024`) Edge Attribution & Drop to -1 hPa
- **Observed**: UI displayed `ESP32 HARDWARE`, `Hardware Source: ESP32 DevKit V1 (N4)`, and `ESP32 STANDBY` simultaneously during benchmark replay, with a pressure drop to -1 hPa.
- **Forensic Verification**: Station `AWS-CHN-024` was hardcoded in frontend components as a default ESP32 hardware device, even when streaming synthetic benchmark data or virtual Open-Meteo polling.
- **Root Cause**: `|| stationId === 'AWS-CHN-024'` hardcoded check across 7 frontend components.
- **Resolution**: Removed all station ID checks; edge badges render ONLY when `currentReading?.source === 'edge'` and `streamMode !== 'replay'`. When virtual, renders: *"No physical ESP32 Edge node is registered for this station. Telemetry is being evaluated directly via central system."*

### Images 3–5: Multi-Channel Temperature, Pressure, and Humidity Plots
- **Observed**: Separate channel plots showing anomaly markers across different parameters.
- **Forensic Verification**: Single-channel faults (e.g. Temperature Spike) must not mark Pressure or Humidity traces. Multivariate faults (e.g. frozen value) must mark all participating parameters.
- **Root Cause**: Marker engine treated `is_anomaly` as a global boolean without filtering by channel.
- **Resolution**: Channel-specific isolation fully enforced in [TrendChart.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/dashboard/TrendChart.tsx) and [AnalyticsTrendChart.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/analytics/AnalyticsTrendChart.tsx).

---

## 3. Forensic Case Breakdown (Cases 01–55)
See [`full_image_case_reconciliation.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/full_image_case_reconciliation.csv) for the serial breakdown of all 55 cases with first broken layer, root cause, and verification status.

---

## 4. Certification
All 55 forensic cases have been resolved, regression tested, and verified.
