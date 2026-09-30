import { TrendsResponse } from '../types';
import { generateMockTrends } from '../mock/trendData';
import { API_CONFIG, isMockMode } from '../config/api.config';
import { apiClient, RequestOptions } from './apiClient';
import { validateTrends } from './validators';
export const trendsService = {
  async getTrends(stationId: string, hours: number = 6, options?: RequestOptions): Promise<TrendsResponse> {
    if (isMockMode()) {
      return new Promise((resolve) => {
        setTimeout(() => {
          const trends = generateMockTrends(stationId, hours);
          resolve(trends);
        }, 75);
      });
    }
    const rawData = await apiClient.get<unknown>(
      API_CONFIG.endpoints.trends,
      { station_id: stationId, hours },
      { timeoutMs: 15000, ...options }
    );
    return validateTrends(rawData, hours);
  },
};
