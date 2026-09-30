import { SensorReading } from '../types';
import { MOCK_SENSOR_READINGS } from '../mock/sensorData';
export const sensorService = {
  async getLatestReadings(): Promise<SensorReading[]> {
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve([...MOCK_SENSOR_READINGS]);
      }, 50);
    });
  },
  async getReadingByStationId(stationId: string): Promise<SensorReading | null> {
    return new Promise((resolve) => {
      setTimeout(() => {
        const reading = MOCK_SENSOR_READINGS.find((r) => r.station_id === stationId) || null;
        resolve(reading);
      }, 50);
    });
  },
};
