
export type ApiMode = 'mock' | 'real';
export interface ApiEndpoints {
  stations: string;
  currentReading: string;
  trends: string;
  latestAnomaly: string;
  recentAnomalies: string;
  explainAnomaly: (anomalyId: string) => string;
  sensorHealth: string;
  injectAnomaly: string;
  maintenanceTicket: string;
  repairSensor: string;
  systemStatus: string;
  systemMode: string;
  refreshLive: string;
  networkStatus: string;
  clearHistory: string;
}
export interface ApiConfig {
  mode: ApiMode;
  baseUrl: string;
  wsUrl: string;
  timeoutMs: number;
  realtime: {
    strategy: 'polling';
    pollingIntervalMs: number;
    enabled: boolean;
  };
  endpoints: ApiEndpoints;
}
const rawApiMode = (
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_MODE) || 'real'
).toLowerCase();
const resolvedMode: ApiMode = rawApiMode === 'real' ? 'real' : 'mock';
export const API_CONFIG: ApiConfig = {
  mode: resolvedMode,
  baseUrl: (
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) || 'http://localhost:8000'
  ).replace(/\/+$/, ''),
  wsUrl: (
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_WS_BASE_URL) ||
    ((typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) || 'http://localhost:8000')
      .replace(/^http/, 'ws')
      .replace(/\/+$/, '') + '/ws/live'
  ),
  timeoutMs: 10000,
  realtime: {
    strategy: 'polling',
    pollingIntervalMs: 30 * 60 * 1000,
    enabled: true,
  },
  endpoints: {
    stations: '/api/stations',
    currentReading: '/api/current-reading',
    trends: '/api/trends',
    latestAnomaly: '/api/anomalies/latest',
    recentAnomalies: '/api/anomalies/recent',
    explainAnomaly: (anomalyId: string) => `/api/explain/${encodeURIComponent(anomalyId)}`,
    sensorHealth: '/api/sensor-health',
    injectAnomaly: '/api/inject-anomaly',
    maintenanceTicket: '/api/maintenance-ticket',
    repairSensor: '/api/repair-sensor',
    systemStatus: '/api/system-status',
    systemMode: '/api/system-mode',
    refreshLive: '/api/refresh-live',
    networkStatus: '/api/network-status',
    clearHistory: '/api/admin/clear-history',
  },
};
export function isMockMode(): boolean {
  return API_CONFIG.mode === 'mock';
}
