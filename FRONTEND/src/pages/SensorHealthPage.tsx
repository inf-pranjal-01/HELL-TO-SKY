import React, { useState, useEffect, useRef } from 'react';
import { HardDrive, RefreshCw, Pause, Play, MapPin } from 'lucide-react';
import { useStation } from '../context/StationContext';
import { useDashboardData } from '../hooks/useDashboardData';
import { sensorHealthService } from '../services/sensorHealthService';
import { formatUserErrorMessage } from '../services/apiError';
import { RepairSensorResponse } from '../types';
import { Button } from '../components/common/Button';
import { StatusBadge } from '../components/common/StatusBadge';
import {
  SensorHealthHero,
  HealthSummaryCards,
  HealthHistoryChart,
  SensorChannelOverview,
  AnomalyContextNotice,
  FutureDiagnosticsNotice,
} from '../components/sensor-health';
import './SensorHealthPage.css';

export const SensorHealthPage: React.FC = () => {
  const { selectedStation } = useStation();
  const stationId = selectedStation?.station_id;

  const {
    currentReading,
    sensorHealth,
    latestAnomaly,
    isLoadingReading,
    isLoadingHealth,
    healthError,
    refreshHealth,
    refreshReading,
    lastUpdated,
    isPaused,
    togglePause,
    staleStatusText,
  } = useDashboardData(stationId, { autoPoll: true });

  const [isRepairing, setIsRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState<RepairSensorResponse | null>(null);
  const [repairError, setRepairError] = useState<string | null>(null);
  const activeStationRef = useRef<string | undefined>(stationId);

  // Clear repair feedback when station changes
  useEffect(() => {
    activeStationRef.current = stationId;
    setRepairResult(null);
    setRepairError(null);
    setIsRepairing(false);
  }, [stationId]);

  const handleRepair = async () => {
    if (!stationId || isRepairing) return;
    const targetStationId = stationId;
    setIsRepairing(true);
    setRepairError(null);

    try {
      const result = await sensorHealthService.repairSensor(targetStationId);
      if (activeStationRef.current !== targetStationId) return;
      setRepairResult(result);
      refreshHealth();
    } catch (err) {
      if (activeStationRef.current !== targetStationId) return;
      setRepairError(formatUserErrorMessage(err, 'Failed to initiate sensor repair.'));
    } finally {
      if (activeStationRef.current === targetStationId) {
        setIsRepairing(false);
      }
    }
  };

  const handleRefresh = async () => {
    await Promise.all([refreshHealth(), refreshReading()]);
  };

  return (
    <div className="sg-health-page" role="main" aria-label="Sensor Health & Hardware Reliability">
      {/* Page Header */}
      <header className="sg-health-page__header">
        <div className="sg-health-page__title-area">
          <div className="sg-health-page__title-row">
            <HardDrive size={26} className="text-accent" aria-hidden="true" />
            <h1 className="sg-health-page__title">Sensor Health & Reliability</h1>
          </div>
          <p className="sg-health-page__subtitle">
            Monitor sensor hardware reliability, subsystem diagnostics, and telemetry integrity for
            the selected automatic weather station.
          </p>
        </div>

        <div className="sg-health-page__header-controls">
          {selectedStation && (
            <div className="sg-health-page__station-badge">
              <MapPin size={14} className="text-accent" aria-hidden="true" />
              <span>{selectedStation.name} ({selectedStation.station_id})</span>
            </div>
          )}

          <StatusBadge
            status={
              staleStatusText === 'LIVE'
                ? 'optimal'
                : staleStatusText === 'DATA DELAYED'
                ? 'moderate'
                : 'critical'
            }
            label={staleStatusText}
            size="sm"
          />

          <Button
            variant="outline"
            size="sm"
            onClick={togglePause}
            leftIcon={isPaused ? <Play size={14} /> : <Pause size={14} />}
            ariaLabel={isPaused ? 'Resume polling' : 'Pause polling'}
          >
            {isPaused ? 'Resume' : 'Pause'}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            leftIcon={<RefreshCw size={14} />}
            ariaLabel="Refresh sensor health telemetry"
          >
            Refresh
          </Button>
        </div>
      </header>

      {/* 1. Overall Sensor Health Hero Section */}
      <SensorHealthHero
        health={sensorHealth}
        lastUpdated={lastUpdated}
        isLoading={isLoadingHealth}
        error={healthError}
        onRetry={refreshHealth}
        onRepair={handleRepair}
        isRepairing={isRepairing}
        repairResult={repairResult}
        repairError={repairError}
      />

      {/* 2. Health Summary KPI Cards */}
      <HealthSummaryCards
        health={sensorHealth}
        reading={currentReading}
        staleStatusText={staleStatusText}
        isLoading={isLoadingHealth || isLoadingReading}
      />

      {/* 3. Anomaly Context Disambiguation Notice (Health vs Anomaly Risk) */}
      <AnomalyContextNotice latestAnomaly={latestAnomaly} />

      {/* 4. Sensor Health History Visualization */}
      <HealthHistoryChart stationId={stationId} />

      {/* 5. Monitored Sensor Channels Overview */}
      <SensorChannelOverview
        reading={currentReading}
        health={sensorHealth}
        isLoading={isLoadingReading}
      />

      {/* 6. Future Hardware Diagnostics Capability Seam */}
      <FutureDiagnosticsNotice />
    </div>
  );
};
