import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useStation } from '../context/StationContext';
import { useAnalyticsData } from '../hooks/useAnalyticsData';
import {
  AnalyticsHeader,
  AnalyticsSummaryCards,
  MetricStatisticsCard,
  AnalyticsTrendChart,
  AnomalyAnalytics,
  AnomalyTimeline,
  SensorHealthTrend,
  AnalyticsInsights,
  ExplainabilityCommandCenter,
} from '../components/analytics';
import { EmptyState } from '../components/common/EmptyState';
import './AnalyticsPage.css';
const AnalyticsPage: React.FC = () => {
  const { stations, selectedStation, setSelectedStation, isLoading: isLoadingStation } = useStation();
  const [searchParams] = useSearchParams();
  const targetStationId = searchParams.get('station_id');
  const targetAnomalyId = searchParams.get('anomaly_id');
  useEffect(() => {
    if (targetStationId && stations.length > 0 && selectedStation?.station_id !== targetStationId) {
      const match = stations.find((s) => s.station_id === targetStationId);
      if (match) {
        setSelectedStation(match);
      }
    }
  }, [targetStationId, stations, selectedStation, setSelectedStation]);
  const stationId = selectedStation?.station_id ?? null;
  const {
    hours,
    setHours,
    selectedMetric,
    setSelectedMetric,
    trends,
    currentReading,
    anomalies,
    analyticsSummary,
    isLoading,
    error,
    staleStatusText,
    refresh,
  } = useAnalyticsData(stationId, 24);
  if (!isLoadingStation && !selectedStation) {
    return (
      <div className="page-container sg-analytics-page" role="main" aria-label="Analytics page">
        <div className="sg-analytics-page__no-station">
          <EmptyState
            title="No Station Selected"
            description="Please select a weather station from the navigation bar to view analytics data."
          />
        </div>
      </div>
    );
  }
  if (error && !isLoading) {
    return (
      <div className="page-container sg-analytics-page" role="main" aria-label="Analytics page">
        <AnalyticsHeader
          station={selectedStation}
          hours={hours}
          onHoursChange={setHours}
          staleStatusText={staleStatusText}
          onRefresh={refresh}
          isLoading={false}
        />
        <div className="sg-analytics-page__error">
          <div className="sg-analytics-page__error-box" role="alert">
            <h2>Analytics Unavailable</h2>
            <p>{error}</p>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="page-container sg-analytics-page" role="main" aria-label="Analytics & Insights Dashboard">
      {}
      <AnalyticsHeader
        station={selectedStation}
        hours={hours}
        onHoursChange={setHours}
        staleStatusText={staleStatusText}
        onRefresh={refresh}
        isLoading={isLoading}
      />
      {}
      <AnalyticsSummaryCards summary={analyticsSummary} isLoading={isLoading} />
      {}
      <MetricStatisticsCard
        temperatureStats={analyticsSummary?.temperature}
        pressureStats={analyticsSummary?.pressure}
        humidityStats={analyticsSummary?.humidity}
        currentReading={currentReading}
        isLoading={isLoading}
      />
      {}
      <AnalyticsTrendChart
        trends={trends}
        currentReading={currentReading}
        hours={hours}
        selectedMetric={selectedMetric}
        onSelectMetric={setSelectedMetric}
        isLoading={isLoading}
      />
      <ExplainabilityCommandCenter
        anomalies={anomalies}
        isLoading={isLoading}
        initialAnomalyId={targetAnomalyId ?? undefined}
      />
      {}
      <p className="sg-analytics-page__section-label" aria-hidden="true">
        Anomaly Distribution — DERIVED FROM LIVE BACKEND DATA
      </p>
      <AnomalyAnalytics analyticsSummary={analyticsSummary} isLoading={isLoading} />
      {}
      <AnomalyTimeline anomalies={anomalies} isLoading={isLoading} />
      {}
      <p className="sg-analytics-page__section-label" aria-hidden="true">
        Sensor Health Trend — DEMO TREND — FRONTEND DERIVED
      </p>
      <SensorHealthTrend stationId={stationId} />
      {}
      <AnalyticsInsights
        insights={analyticsSummary?.insights ?? []}
        isLoading={isLoading}
      />
    </div>
  );
};
export default AnalyticsPage;
export { AnalyticsPage };
