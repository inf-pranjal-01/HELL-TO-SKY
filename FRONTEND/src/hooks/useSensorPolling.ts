import { useState, useEffect, useCallback, useRef } from 'react';
import { SensorReading, SystemStatusSummary } from '../types';
import { sensorService } from '../services/sensorService';
import { anomalyService } from '../services/anomalyService';
import { API_CONFIG } from '../config/api.config';

export interface UseSensorPollingResult {
  readings: SensorReading[];
  systemStatus: SystemStatusSummary | null;
  loading: boolean;
  error: string | null;
  isPolling: boolean;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
}

/**
 * Custom Hook: useSensorPolling
 * 
 * [REALTIME: HTTP POLLING]
 * Manages periodic HTTP polling for meteorological telemetry data and network status.
 * Fetches data from service boundary and provides manual refresh & polling controls.
 */
export function useSensorPolling(autoPoll: boolean = false): UseSensorPollingResult {
  const [readings, setReadings] = useState<SensorReading[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatusSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const timerRef = useRef<number | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [readingsData, statusData] = await Promise.all([
        sensorService.getLatestReadings(),
        anomalyService.getSystemStatus(),
      ]);
      setReadings(readingsData);
      setSystemStatus(statusData);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch meteorological telemetry data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    // [REALTIME: HTTP POLLING]
    // Live polling follows the configured 30-minute Open-Meteo cadence.
    if (autoPoll && API_CONFIG.realtime.enabled) {
      timerRef.current = window.setInterval(() => {
        fetchData();
      }, API_CONFIG.realtime.pollingIntervalMs);
    }

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, [fetchData, autoPoll]);

  return {
    readings,
    systemStatus,
    loading,
    error,
    isPolling: autoPoll && API_CONFIG.realtime.enabled,
    lastUpdated,
    refresh: fetchData,
  };
}
