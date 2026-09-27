# CHANNEL MARKER FORENSICS

## 1. Objective
Ensure that anomaly markers rendered on multi-series charts accurately isolate single-channel vs multi-channel vs station-wide faults, with zero visual cross-contamination.

---

## 2. Forensic Investigation & Implementation

### Channel Isolation Logic:
In [TrendChart.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/dashboard/TrendChart.tsx) and [AnalyticsTrendChart.tsx](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/FRONTEND/src/components/analytics/AnalyticsTrendChart.tsx):
```typescript
const isMetricAnomalous = (pt: TelemetryPoint, metricKey: string): boolean => {
  if (!pt.is_anomaly) return false;
  if (!pt.affected_parameters || pt.affected_parameters.length === 0) {
    // If no specific parameter is tagged (e.g. frozen value, dropout), mark all active traces
    return true;
  }
  return pt.affected_parameters.includes(metricKey);
};
```

### Forensic Rules:
1. **Single-Channel Spikes/Drifts**: Only the affected parameter trace (e.g. `temperature`) receives a red SVG circle marker. Traces for `relative_humidity`, `surface_pressure`, etc., remain clean.
2. **Station-Wide Faults (`frozen_value`, `sensor_dropout`)**: All active traces render synchronized markers at the fault timestamp.
3. **SVG Coordinate Precision**: Markers are drawn directly on computed $(x, y)$ data coordinates within the SVG canvas. No CSS overlay approximations or fixed pixel offsets are used.
4. **Interactive Tooltips**: Hovering over an anomaly marker displays the exact physical fault type, continuous anomaly score, and full list of affected parameters.

See [`channel_marker_matrix.csv`](file:///c:/Users/PRANJAL%20TIWARI/Desktop/HELL%20TO%20SKY/scratch/product_audit/channel_marker_matrix.csv) for detailed test cases.
