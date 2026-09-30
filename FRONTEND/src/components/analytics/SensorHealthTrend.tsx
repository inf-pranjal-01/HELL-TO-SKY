import React from 'react';
import { HealthHistoryChart } from '../sensor-health/HealthHistoryChart';
import './SensorHealthTrend.css';
export interface SensorHealthTrendProps {
  stationId: string | null | undefined;
  className?: string;
}
export const SensorHealthTrend: React.FC<SensorHealthTrendProps> = ({
  stationId,
  className = '',
}) => {
  return (
    <section
      className={`sg-sensor-health-trend ${className}`}
      aria-label="Sensor health trend (analytics view)"
    >
      <HealthHistoryChart stationId={stationId} />
    </section>
  );
};
