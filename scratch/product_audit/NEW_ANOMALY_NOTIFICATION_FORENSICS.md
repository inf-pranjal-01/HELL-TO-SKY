# SKYGUARD AI — NEW ANOMALY NOTIFICATION FORENSICS

## 1. Lifecycle Requirements & Implementation
The new anomaly notification indicator on the `"Anomaly Alerts"` navigation item in `Sidebar.tsx` adheres to strict operational semantics:

1. **Initial Hydration Immunity**:
   - On initial application load, `AlertNotificationContext` calls `GET /api/anomalies/recent?limit=100`.
   - All received historical anomaly IDs are immediately added to `knownAnomalyIdsRef`.
   - `isHydratedRef.current` is set to `true`.
   - Result: Existing historical anomalies never trigger false "New Alert" pulses upon loading.

2. **Dynamic Live Arrival Triggering**:
   - When a WebSocket frame of type `ANOMALY_EVENT` arrives:
     - Check `knownAnomalyIdsRef.has(data.id)`.
     - If not present and `isHydratedRef.current === true`:
       - Add `data.id` to `knownAnomalyIdsRef`.
       - If current pathname is not `/alerts`: set `hasNewAlert = true` and increment `newAlertCount`.
   - Result: Genuinely new anomaly events trigger the pulsing indicator immediately.

3. **Route Navigation & Acknowledgment**:
   - When operator navigates to `/alerts`:
     - `useLocation()` hook triggers `clearNewAlerts()`.
     - `hasNewAlert` resets to `false`, `newAlertCount` resets to `0`.
     - Pulse stops. Historical records remain intact in database and alerts table.

4. **Network Reconnect & Polling Deduplication**:
   - When WebSocket disconnects and reconnects, replayed or polled frames check `knownAnomalyIdsRef`.
   - Previously seen IDs are rejected idempotently, preventing phantom pulses.

5. **Reset DB Invariant**:
   - When database reset / purge is executed, `resetAlertNotifications()` is invoked, clearing `knownAnomalyIdsRef`, `hasNewAlert`, and `newAlertCount`.
   - Historical rehydration following reset does not trigger false pulses.
