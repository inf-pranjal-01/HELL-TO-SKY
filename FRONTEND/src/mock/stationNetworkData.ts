import { StationNetworkReading, SpatialDemoScenario } from '../types';
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
export function getMockNetworkReadings(
  selectedStationId: string | null | undefined,
  scenario: SpatialDemoScenario = 'localized_deviation',
  availableStations?: Array<{ station_id: string }>
): Record<string, StationNetworkReading> {
  const readings: Record<string, StationNetworkReading> = {};
  Object.keys(MOCK_REGIONAL_BASELINE_READINGS).forEach((id) => {
    readings[id] = { ...MOCK_REGIONAL_BASELINE_READINGS[id], timestamp: new Date().toISOString() };
  });
  if (availableStations && availableStations.length > 0) {
    availableStations.forEach((station, idx) => {
      if (!readings[station.station_id]) {
        const tempOffset = ((idx % 7) - 3) * 0.25;
        const pressOffset = ((idx % 5) - 2) * 0.3;
        const humOffset = ((idx % 6) - 2.5) * 0.8;
        readings[station.station_id] = {
          station_id: station.station_id,
          timestamp: new Date().toISOString(),
          temperature_c: +(31.2 + tempOffset).toFixed(1),
          pressure_hpa: +(1012.4 + pressOffset).toFixed(1),
          humidity_pct: +(68.0 + humOffset).toFixed(1),
          anomaly_score_pct: 5.0 + (idx % 10),
          sensor_health_pct: 95.0 - (idx % 8),
        };
      }
    });
  }
  if (scenario === 'localized_deviation' && selectedStationId && readings[selectedStationId]) {
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
