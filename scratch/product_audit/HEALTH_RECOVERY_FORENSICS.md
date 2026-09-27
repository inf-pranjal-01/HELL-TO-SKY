# HEALTH RECOVERY FORENSICS

## 1. Operational State Transitions
A monitoring system must accurately convey the health of stations, sensors, and ingestion pipelines, rapidly reflecting transitions between `NORMAL`, `DEGRADED`, `OFFLINE`, and `MAINTENANCE`.

---

## 2. Forensic Analysis of State Recovery

### A. Immediate Recovery Latch
- **Previous Defect**: When a station resumed sending telemetry after a network outage, the UI retained the `OFFLINE` status for a 10-minute rolling window.
- **Remediation**: Health state evaluator immediately clears `OFFLINE` upon receipt of the first valid telemetry packet, latching status back to `NORMAL` in $<50\text{ms}$.

### B. Sensor-Level vs Station-Level Distinction
- A single sensor failure (e.g. faulty temperature probe reading $>65^\circ\text{C}$) transitions station status to `DEGRADED` while keeping other sensor channels (humidity, pressure, wind) active and green.
- Station status transitions to `OFFLINE` only when all communication ceases for $>180\text{s}$.

### C. Historical Retained Charts during Offline
- When a station is offline, historical chart data is fully preserved and rendered, accompanied by a clear, non-intrusive `Station Offline / Communications Stale` status badge rather than wiping the chart canvas.

See [`health_recovery_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/health_recovery_matrix.csv) for full state transition benchmarks.
