/**
 * SkyGuard AI — Centralized API Configuration & Endpoints Registry
 * 
 * [BACKEND INTEGRATED — Steps 13A–13K Complete]
 * Backend Maturity: LEVEL 3 — REAL FastAPI backend live at http://127.0.0.1:8000
 * 
 * The app connects to the local FastAPI backend by default. Set
 * VITE_API_MODE=mock only when deliberately working with the isolated fixtures.
 */

export type ApiMode = 'mock' | 'real';

export interface ApiEndpoints {
  // 1. GET /api/stations
  stations: string;
  // 2. GET /api/current-reading?station_id=...
  currentReading: string;
  // 3. GET /api/trends?station_id=...&hours=6
  trends: string;
  // 4. GET /api/anomalies/latest?station_id=...
  latestAnomaly: string;
  // 5. GET /api/anomalies/recent?station_id=...&limit=5
  recentAnomalies: string;
  // 6. GET /api/explain/{anomaly_id}
  explainAnomaly: (anomalyId: string) => string;
  // 7. GET /api/sensor-health?station_id=...
  sensorHealth: string;
  // 8. POST /api/inject-anomaly
  injectAnomaly: string;
  // 9. POST /api/maintenance-ticket
  maintenanceTicket: string;
  // 10. POST /api/repair-sensor
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

const resolveBaseUrl = (): string => {
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    const customUrl = String(import.meta.env.VITE_API_BASE_URL).trim();
    if (customUrl.length > 0) {
      return customUrl.replace(/\/+$/, '');
    }
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    // If running in local Vite development mode (e.g. port 5173), point to port 8000
    if (window.location.port === '5173' || window.location.port === '3000') {
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    // In production (served by Nginx on port 80/443), Nginx proxies /api and /docs directly at same origin
    return window.location.origin;
  }
  return 'https://35-200-179-39.sslip.io';
};

const resolvedBaseUrl = resolveBaseUrl();

const resolveWsUrl = (): string => {
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL;
  }
  const wsProtocol = resolvedBaseUrl.startsWith('https') ? 'wss' : 'ws';
  const cleanHost = resolvedBaseUrl.replace(/^https?:\/\//, '');
  return `${wsProtocol}://${cleanHost}/ws/live`;
};

export const API_CONFIG: ApiConfig = {
  // Mode switch: 'mock' or 'real' (FastAPI backend)
  mode: resolvedMode,
  
  // Base URL for backend requests (auto-resolves to http://35.200.179.39:8000)
  baseUrl: resolvedBaseUrl,

  // WebSocket Live Push URL
  wsUrl: resolveWsUrl(),
  
  // Default network request timeout (10 seconds)
  timeoutMs: 10000,
  
  // Real-time telemetry polling configuration
  realtime: {
    strategy: 'polling',
    pollingIntervalMs: 30 * 60 * 1000,
    enabled: true,
  },
  
  // Approved 10 API Endpoints Contract
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

/**
 * Helper to check if the application is currently running in mock mode.
 */
export function isMockMode(): boolean {
  return API_CONFIG.mode === 'mock';
}
