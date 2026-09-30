import { CurrentSensorReading } from '../types';
import { MOCK_CURRENT_READINGS } from '../mock/currentReadingData';
import { API_CONFIG, isMockMode } from '../config/api.config';
import { apiClient, RequestOptions } from './apiClient';
import { validateCurrentReading } from './validators';
import { ApiError } from './apiError';
export const currentReadingService = {
  async getCurrentReading(stationId: string, options?: RequestOptions): Promise<CurrentSensorReading> {
    if (isMockMode()) {
      return new Promise((resolve, reject) => {
        setTimeout(() => {
          const data = MOCK_CURRENT_READINGS[stationId];
          if (!data) {
            reject(new ApiError(`No current sensor reading available for station "${stationId}".`, {
              status: 404,
              code: 'MOCK_ERROR',
            }));
            return;
          }
          const jitter = (Math.random() - 0.5) * 0.2;
          const liveReading: CurrentSensorReading = {
            ...data,
            timestamp: new Date().toISOString(),
            temperature_c: {
              ...data.temperature_c,
              value: Number((data.temperature_c.value + jitter).toFixed(1)),
            },
            pressure_hpa: {
              ...data.pressure_hpa,
              value: Number((data.pressure_hpa.value + jitter * 0.5).toFixed(1)),
            },
            humidity_pct: {
              ...data.humidity_pct,
              value: Number(Math.min(100, Math.max(10, data.humidity_pct.value - jitter)).toFixed(1)),
            },
          };
          resolve(liveReading);
        }, 60);
      });
    }
    const rawData = await apiClient.get<unknown>(
      API_CONFIG.endpoints.currentReading,
      { station_id: stationId },
      options
    );
    return validateCurrentReading(rawData);
  },
};
