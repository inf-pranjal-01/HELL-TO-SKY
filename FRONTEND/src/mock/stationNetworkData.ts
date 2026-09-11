import { StationNetworkReading, SpatialDemoScenario } from '../types';

/**
 * [DEMO TELEMETRY]
 * [FRONTEND ONLY]
 * 
 * Deterministic neighboring-station telemetry dataset for Step 9 spatial comparison demonstration.
 */

// Baseline regional readings (~31°C, ~1012 hPa, ~68% humidity)
export const MOCK_REGIONAL_BASELINE_READINGS: Record<string, StationNetworkReading> = {
  'ST-NDL-001': {
    station_id: 'ST-NDL-001',
    timestamp: new Date().toISOString(),
    temperature_c: 31.2,
    pressure_hpa: 1012.4,
    humidity_pct: 68.0,
    anomaly_score_pct: 12.0,
    sensor_health_pct: 94.0,
  },
  'ST-MUM-002': {
    station_id: 'ST-MUM-002',
    timestamp: new Date().toISOString(),
    temperature_c: 31.0,
    pressure_hpa: 1012.0,
    humidity_pct: 70.5,
    anomaly_score_pct: 28.0,
    sensor_health_pct: 76.0,
  },
  'ST-BLR-003': {
    station_id: 'ST-BLR-003',
    timestamp: new Date().toISOString(),
    temperature_c: 31.4,
    pressure_hpa: 1012.8,
    humidity_pct: 67.2,
    anomaly_score_pct: 8.0,
    sensor_health_pct: 99.0,
  },
  'ST-HYD-004': {
    station_id: 'ST-HYD-004',
    timestamp: new Date().toISOString(),
    temperature_c: 30.8,
    pressure_hpa: 1012.2,
    humidity_pct: 69.1,
    anomaly_score_pct: 35.0,
    sensor_health_pct: 42.0,
  },
  'ST-KOL-005': {
    station_id: 'ST-KOL-005',
    timestamp: new Date().toISOString(),
    temperature_c: 31.1,
    pressure_hpa: 1012.5,
    humidity_pct: 68.4,
    anomaly_score_pct: 0.0,
    sensor_health_pct: 0.0,
  },
};

/**
 * Returns deterministic network readings for all stations based on the requested scenario
 * and currently selected station.
 * 
 * - 'regional_consistency': All stations report readings within a tight ±0.5°C range.
 * - 'localized_deviation': Selected station reports a localized spike (e.g., 42.1°C), while neighbors remain around 31.0°C.
 */
export function getMockNetworkReadings(
  selectedStationId: string | null | undefined,
  scenario: SpatialDemoScenario = 'localized_deviation'
): Record<string, StationNetworkReading> {
  const readings: Record<string, StationNetworkReading> = {};

  // Copy baseline readings
  Object.keys(MOCK_REGIONAL_BASELINE_READINGS).forEach((id) => {
    readings[id] = { ...MOCK_REGIONAL_BASELINE_READINGS[id], timestamp: new Date().toISOString() };
  });

  if (scenario === 'localized_deviation' && selectedStationId && readings[selectedStationId]) {
    // Inject localized thermal/humidity deviation into selected station
    readings[selectedStationId] = {
      ...readings[selectedStationId],
      temperature_c: 42.1,
      pressure_hpa: 1013.2,
      humidity_pct: 42.0,
      anomaly_score_pct: 86.5,
      sensor_health_pct: readings[selectedStationId].sensor_health_pct,
    };
  }

  return readings;
}
