import React, { useState, useMemo } from 'react';
import { ShieldAlert, RefreshCw, Pause, Play, MapPin } from 'lucide-react';
import { useStation } from '../context/StationContext';
import { useDashboardData } from '../hooks/useDashboardData';
import { Button } from '../components/common/Button';
import { StatusBadge } from '../components/common/StatusBadge';
import {
  AlertSummaryCards,
  LatestAnomalyBanner,
  AnomalyFilters,
  AnomalyFilterValues,
  RecentAnomaliesList,
  AnomalyDetailModal,
} from '../components/alerts';
import { LatestAnomaly, RecentAnomalyItem } from '../types';
import './AlertsPage.css';

export const AlertsPage: React.FC = () => {
  const { selectedStation } = useStation();
  const stationId = selectedStation?.station_id;

  const {
    latestAnomaly,
    recentAnomalies,
    isLoadingAnomalies,
    anomaliesError,
    refreshAnomalies,
    isPaused,
    togglePause,
    staleStatusText,
  } = useDashboardData(stationId, { autoPoll: true });

  // Filtering state
  const [filters, setFilters] = useState<AnomalyFilterValues>({
    severity: 'all',
    type: 'all',
    searchQuery: '',
  });

  // Modal / Investigation state
  const [selectedAnomaly, setSelectedAnomaly] = useState<LatestAnomaly | RecentAnomalyItem | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  const handleOpenModal = (anomaly: LatestAnomaly | RecentAnomalyItem) => {
    setSelectedAnomaly(anomaly);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
  };

  const handleResetFilters = () => {
    setFilters({
      severity: 'all',
      type: 'all',
      searchQuery: '',
    });
  };

  // Combine latestAnomaly into recent list if not already present, ensuring full visibility
  const allStationAnomalies = useMemo(() => {
    const list = [...recentAnomalies];
    if (latestAnomaly && !list.some((a) => a.anomaly_id === latestAnomaly.anomaly_id)) {
      list.unshift(latestAnomaly);
    }
    // Sort newest first
    return list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [latestAnomaly, recentAnomalies]);

  // Apply filters
  const filteredAnomalies = useMemo(() => {
    return allStationAnomalies.filter((anomaly) => {
      // Severity filter
      if (filters.severity !== 'all' && anomaly.severity !== filters.severity) {
        return false;
      }

      // Type filter
      if (filters.type !== 'all' && anomaly.type !== filters.type) {
        return false;
      }

      // Search query filter (matches ID, root cause, or description)
      if (filters.searchQuery.trim().length > 0) {
        const query = filters.searchQuery.toLowerCase();
        const matchesId = anomaly.anomaly_id.toLowerCase().includes(query);
        const matchesCause = anomaly.root_cause.toLowerCase().includes(query);
        const matchesDesc = anomaly.description.toLowerCase().includes(query);
        if (!matchesId && !matchesCause && !matchesDesc) {
          return false;
        }
      }

      return true;
    });
  }, [allStationAnomalies, filters]);

  const isFiltered =
    filters.severity !== 'all' || filters.type !== 'all' || filters.searchQuery.trim().length > 0;

  return (
    <div className="sg-alerts-page" role="main" aria-label="Anomaly Alerts & Incident Investigation">
      {/* Page Header */}
      <header className="sg-alerts-page__header">
        <div className="sg-alerts-page__title-area">
          <div className="sg-alerts-page__title-row">
            <ShieldAlert size={26} className="text-accent" aria-hidden="true" />
            <h1 className="sg-alerts-page__title">Anomaly Alerts & Incidents</h1>
          </div>
          <p className="sg-alerts-page__subtitle">
            Autonomous meteorological anomaly detection stream, classification analysis & root cause
            investigation.
          </p>
        </div>

        <div className="sg-alerts-page__header-controls">
          {selectedStation && (
            <div className="sg-alerts-page__station-badge">
              <MapPin size={14} className="text-accent" />
              <span>{selectedStation.name} ({selectedStation.station_id})</span>
            </div>
          )}

          <StatusBadge
            status={staleStatusText === 'LIVE' ? 'optimal' : staleStatusText === 'DATA DELAYED' ? 'moderate' : 'critical'}
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
            onClick={() => refreshAnomalies()}
            leftIcon={<RefreshCw size={14} />}
            ariaLabel="Refresh anomaly feeds"
          >
            Refresh
          </Button>
        </div>
      </header>

      {/* Summary KPI Cards */}
      <AlertSummaryCards
        latestAnomaly={latestAnomaly}
        recentAnomalies={allStationAnomalies}
        isLoading={isLoadingAnomalies}
      />

      {/* Prominent Latest Anomaly Hero Banner */}
      <LatestAnomalyBanner
        latestAnomaly={latestAnomaly}
        isLoading={isLoadingAnomalies}
        error={anomaliesError}
        onRetry={refreshAnomalies}
        onInvestigate={handleOpenModal}
      />

      {/* Filtering Bar */}
      <AnomalyFilters
        filters={filters}
        onChange={setFilters}
        onReset={handleResetFilters}
        totalCount={allStationAnomalies.length}
        filteredCount={filteredAnomalies.length}
      />

      {/* Interactive Anomaly History Table */}
      <RecentAnomaliesList
        anomalies={filteredAnomalies}
        isLoading={isLoadingAnomalies}
        error={anomaliesError}
        onRetry={refreshAnomalies}
        onSelectAnomaly={handleOpenModal}
        isFiltered={isFiltered}
        onClearFilters={handleResetFilters}
      />

      {/* Investigation / Explainability Modal */}
      <AnomalyDetailModal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        anomaly={selectedAnomaly}
      />
    </div>
  );
};
