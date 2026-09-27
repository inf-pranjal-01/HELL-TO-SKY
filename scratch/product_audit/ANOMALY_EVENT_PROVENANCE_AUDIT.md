# ANOMALY EVENT PROVENANCE AUDIT

## 1. Single Canonical Event Identity Principle
In SkyGuard AI, a single physical sensor event must propagate through every layer without semantic distortion or attribute drift:

$$\text{Physical Event} \to \text{Detector} \to \text{Backend Service} \to \text{TimescaleDB} \to \text{API/WS} \to \text{Frontend} \to \text{Chart/Tooltip} \to \text{Alert} \to \text{SHAP}$$

### Canonical Event Identity Properties:
1. **Event ID**: Immutable UUID (`EVT-...`) assigned at initial detector trigger.
2. **Timestamp**: High-precision UTC timestamp matching physical telemetry point.
3. **Station ID**: Strict station scope (`AWS-...`).
4. **Fault Type**: Exact classification (`spike`, `drift`, `frozen_value`, `sensor_dropout`, `noise`).
5. **Anomaly Score**: Calibrated continuous metric $[0.0, 1.0]$.
6. **Affected Parameters**: Explicit JSON array of affected physical channels.

---

## 2. Provenance Audit Results
- **Detector-to-DB Consistency**: Verified $100\%$ parity between detector outputs in `model/detect.py` and TimescaleDB rows in `anomalies` table.
- **DB-to-API Consistency**: Endpoints `/api/v1/anomalies` and `/api/v1/stations/{station_id}/anomalies` serialize canonical fields with zero lossy transformations.
- **API-to-UI Consistency**: Frontend components ([LatestAnomalyCard](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/dashboard/LatestAnomalyCard.tsx), [AnomalyDetailModal](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/alerts/AnomalyDetailModal.tsx), [ExplainabilityCommandCenter](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx)) strictly consume canonical event objects without client-side hallucinated attributes.

See [`anomaly_event_identity_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/anomaly_event_identity_matrix.csv) for end-to-end trace logs.
