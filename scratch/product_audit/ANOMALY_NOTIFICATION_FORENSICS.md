# ANOMALY NOTIFICATION FORENSICS

## 1. Objective
Ensure that the "Anomaly Alerts" navigation badge and alert notifications trigger exclusively on **genuinely new real-time anomaly arrivals**, completely eliminating spurious alerts on page load, WebSocket reconnect, or database rehydration.

---

## 2. Notification Pipeline & Deduplication

### A. Initial Set Seeding
In [AlertNotificationContext.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/context/AlertNotificationContext.tsx):
```typescript
// On initial mount or fetch, seed all existing IDs into knownAnomaliesRef without firing animations
useEffect(() => {
  const initialIds = new Set(initialAnomalies.map(a => a.id));
  knownAnomaliesRef.current = initialIds;
  isInitializedRef.current = true;
}, [initialAnomalies]);
```

### B. Real-Time Arrival Detection
When an anomaly packet arrives via WebSocket:
```typescript
const handleNewAnomaly = (newAnomaly: AnomalyEvent) => {
  if (!isInitializedRef.current) return;
  if (!knownAnomaliesRef.current.has(newAnomaly.id)) {
    knownAnomaliesRef.current.add(newAnomaly.id);
    setHasUnreadNewAlert(true);
    triggerPulseAnimation();
    playAlertSound();
  }
};
```

### C. Acknowledgment & Clearing
- Navigating to the Alerts page or clicking the alert card marks all current anomalies as acknowledged, instantly clearing the pulsing badge indicator.
- Muted stations do not trigger audio or visual toast banners.

See [`notification_event_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/notification_event_matrix.csv) for lifecycle verification.
