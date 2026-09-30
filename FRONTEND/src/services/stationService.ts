import { Station } from '../types';
import { MOCK_STATIONS } from '../mock/stationData';
import { API_CONFIG, isMockMode } from '../config/api.config';
import { apiClient, RequestOptions } from './apiClient';
import { validateStations } from './validators';
export const stationService = {
  async getAllStations(options?: RequestOptions): Promise<Station[]> {
    if (isMockMode()) {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve([...MOCK_STATIONS]);
        }, 50);
      });
    }
    const rawData = await apiClient.get<unknown>(API_CONFIG.endpoints.stations, undefined, options);
    return validateStations(rawData);
  },
  async getStationById(stationId: string, options?: RequestOptions): Promise<Station | null> {
    const all = await this.getAllStations(options);
    return all.find((s) => s.station_id === stationId) || null;
  },
};
