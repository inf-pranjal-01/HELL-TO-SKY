import { SensorHealth, HealthHistoryPoint, RepairSensorResponse } from '../types';
import { MOCK_SENSOR_HEALTH, generateMockHealthHistory } from '../mock/sensorHealthData';
import { API_CONFIG, isMockMode } from '../config/api.config';
import { apiClient, RequestOptions } from './apiClient';
import { validateSensorHealth, validateRepairSensorResponse } from './validators';

/**
 * Sensor Health Service
 * 
 * Boundary interface for AWS hardware reliability and sensing subsystem health.
 * - [MOCK DATA]: Returns isolated mock fixtures when API_CONFIG.mode === 'mock'
 * - [API: GET /api/sensor-health?station_id={station_id} — INTEGRATED]: Dispatches real HTTP call when API_CONFIG.mode === 'real'
 */
export const sensorHealthService = {
  /**
   * Fetch current overall sensor health status for an Automatic Weather Station.
   * Request contract: GET /api/sensor-health?station_id={stationId}
   */
  async getSensorHealth(stationId: string, options?: RequestOptions): Promise<SensorHealth> {
    if (isMockMode()) {
      return new Promise((resolve) => {
        setTimeout(() => {
          const data = MOCK_SENSOR_HEALTH[stationId];
          if (!data) {
            resolve({
              station_id: stationId,
              sensor_health_pct: 95,
              sensor_health_status: 'HEALTHY',
            });
            return;
          }
          resolve({ ...data });
        }, 50);
      });
    }

    const rawData = await apiClient.get<unknown>(
      API_CONFIG.endpoints.sensorHealth,
      { station_id: stationId },
      options
    );
    return validateSensorHealth(rawData, stationId);
  },

  /**
   * Fetch historical sensor health records for trend visualization.
   * [FRONTEND DERIVED — DEMO HISTORY]
   * [NOT IN CURRENT API CONTRACT: Historical health endpoint]
   */
  async getHealthHistory(stationId: string, hours: number = 6): Promise<HealthHistoryPoint[]> {
    return new Promise((resolve) => {
      setTimeout(() => {
        const history = generateMockHealthHistory(stationId, hours);
        resolve(history);
      }, 60);
    });
  },

  /**
   * Request a sensor repair / recovery sweep for an Automatic Weather Station.
   * Request contract: POST /api/repair-sensor  { station_id }
   * [API: POST /api/repair-sensor — INTEGRATED]
   */
  async repairSensor(stationId: string, options?: RequestOptions): Promise<RepairSensorResponse> {
    if (isMockMode()) {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({
            success: true,
            station_id: stationId,
            status: 'WARNING',
            recovery_active: true,
            message: `Sensor marked for repair recovery. Clean readings will be evaluated before returning it to HEALTHY.`,
          });
        }, 60);
      });
    }

    const rawData = await apiClient.post<unknown>(
      API_CONFIG.endpoints.repairSensor,
      // The Health-page control is the operator's explicit force-recovery
      // action: immediately restore online/healthy state and clear counters.
      { station_id: stationId, force_recovery: true },
      options
    );
    return validateRepairSensorResponse(rawData, stationId);
  },
};
