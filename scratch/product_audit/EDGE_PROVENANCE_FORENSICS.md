# EDGE PROVENANCE FORENSICS

## 1. Truth in Telemetry Guarantee
The application strictly enforces truth in telemetry provenance. The system will **never** claim an ESP32 hardware device is active, connected, or evaluating telemetry unless a physical ESP32 node is actively streaming telemetry packets (`source === 'edge'`) within the 15-second heartbeat window.

---

## 2. Hardening Audit Findings & Fixes

### A. Removal of Station Hardcoding
- **Vulnerability**: Components previously checked `isChennai = stationId === 'AWS-CHN-024'`, assuming Chennai was permanently mapped to an ESP32 DevKit V1.
- **Remediation**: Completely purged all hardcoded station ID checks from 7 frontend files:
  - [DashboardPage.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/pages/DashboardPage.tsx)
  - [ExplainabilityCommandCenter.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx)
  - [LatestAnomalyCard.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/dashboard/LatestAnomalyCard.tsx)
  - [LatestAnomalyBanner.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/alerts/LatestAnomalyBanner.tsx)
  - [AnomalyDetailModal.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/alerts/AnomalyDetailModal.tsx)
  - [RecentAnomaliesCard.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/dashboard/RecentAnomaliesCard.tsx)
  - [RecentAnomaliesList.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/alerts/RecentAnomaliesList.tsx)

### B. Standardized Fallback Copy
When streaming virtual Open-Meteo or synthetic benchmark replay data (`source !== 'edge'`), the UI explicitly renders:
> *"No physical ESP32 Edge node is registered for this station. Telemetry is being evaluated directly via central system."*

### C. Overstatement Purge
- Replaced `⚡ Caught On-Device at Edge (0ms Local Latency)` with `⚡ Edge AI Evaluated`.
- Header badge displays `⚪ ESP32 STANDBY` whenever hardware is not actively transmitting.

See [`edge_provenance_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/edge_provenance_matrix.csv) for full state verification.
