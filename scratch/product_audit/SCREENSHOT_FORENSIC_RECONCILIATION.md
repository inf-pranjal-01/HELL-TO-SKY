# SKYGUARD AI — SCREENSHOT FORENSIC RECONCILIATION DOSSIER

## 1. Executive Summary
This forensic investigation traces every attached screenshot (`media_1790436034185.png`, `media_1790436044930.png`, `media_1790436046633.png`) to its exact row in `data/all_stations.csv` and follows the complete lifecycle through the detector, backend state, database, API, and frontend presentation layers.

---

## 2. Screenshot Forensic Trace Matrix

### SCREENSHOT 1 & 2: `media_1790436034185.png` & `media_1790436044930.png`
- **Station**: Sehore (`AWS-BHO-101`)
- **Displayed Timestamp**: `Jan 1 12:30 PM` (IST / Local time)
- **Exact UTC Timestamp**: `2025-01-01 07:00:00 UTC` (Row 36727 in `data/all_stations.csv`)
- **CSV Values**: Temperature `11.2°C` | Pressure `959.8 hPa` | Relative Humidity `97.0%`
- **Ground Truth**: Clean meteorological observation (no artificial injection in static CSV).
- **Detector Output**: `frozen_value` (Tier 1 statistical freeze detection on 5 consecutive hours of `97%` relative humidity).
- **DB Output**: `frozen_value`
- **API Output**: `fault_type = "frozen_value"`, `decision_basis = "RULE ONLY STATISTICAL"`
- **Frontend Output**: `[AWS-BHO-101] Frozen Value Jan 1 12:30 PM` | Strongest evidence: `Humidity Deviation` | `Observed: Humidity 97.0%`
- **Root Cause Classification**: **CLASS A — DETECTOR FALSE POSITIVE** (Atmospheric cold-morning humidity stagnation flagged by static zero-variance rule).
- **Fix Required**: **NO** (Strictly per research freeze policy; detector mathematics preserved).

---

### SCREENSHOT 3: `media_1790436046633.png`
- **Station**: Sehore (`AWS-BHO-101`)
- **Displayed Timestamp**: `Jan 01, 12:30 PM` (IST / Local time)
- **Exact UTC Timestamp**: `2025-01-01 07:00:00 UTC`
- **CSV Values**: Temperature `11.2°C` | Pressure `959.8 hPa` | Relative Humidity `97.0%`
- **Ground Truth**: Clean temperature curve (normal diurnal cooling).
- **Detector Output**: Anomaly on `humidity_pct` (`frozen_value`).
- **DB / Backend Memory Output**: `trend_history` recorded `is_anomaly = True` but omitted `fault_type` and `affected_parameters`.
- **API Output**: `/api/trends` emitted `is_anomaly = True` without channel breakdown.
- **Frontend Display**: Red marker appeared on the **Temperature** chart curve; tooltip rendered `Fault: anomaly`.
- **Root Cause Classification**: **CLASS F — FRONTEND PRESENTATION BUG & TELEMETRY SERIALIZATION**
  1. *Generic Fallback*: `TrendChart.tsx` fell back to `'anomaly'` when `fault_type` was null in `trend_history`.
  2. *Cross-Channel Leakage*: `isMetricAnomalous()` lacked `affected_parameters` awareness and painted all 3 channels red.
- **Fix Required**: **YES** (Fixed: `trend_history` now retains full verdict metadata and `isMetricAnomalous` strictly isolates channels).

---

## 3. End-to-End Layer Agreement Table

| Layer | Actual Value | Expected Value | Match? | Layer Responsibility |
|---|---|---|---|---|
| **Screenshot 1 & 2** | `Frozen Value` on Humidity | `Frozen Value` on Humidity | **YES** | Explainability Command Center |
| **Screenshot 3 Tooltip** | `Fault: anomaly` | `Fault: Frozen Value` | **FIXED** | Dashboard TrendChart Tooltip |
| **Screenshot 3 Marker** | Red marker on Temperature | No red marker on Temperature | **FIXED** | Channel Isolation (`affected_parameters`) |
| **API (`/api/trends`)** | `affected_parameters: ['humidity_pct']` | `affected_parameters: ['humidity_pct']` | **YES** | FastAPI / `main.py` |
| **Backend State** | `trend_history` carries full verdict | Rich verdict retained in memory | **YES** | `model/simulator.py` |
| **Detector** | `frozen_value` (Tier 1) | `frozen_value` (Tier 1) | **YES** | Detector Research Freeze |
| **CSV Source** | Row 36727: 11.2°C, 959.8hPa, 97% | Row 36727: 11.2°C, 959.8hPa, 97% | **YES** | `data/all_stations.csv` |
| **Ground Truth** | Clean (Winter Morning) | Clean (Winter Morning) | **YES** | Ground Truth Reference |
