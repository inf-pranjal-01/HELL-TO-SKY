import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert, RefreshCw, Pause, Play, MapPin, Globe } from 'lucide-react';
import { useStation } from '../context/StationContext';
import { useDashboardData } from '../hooks/useDashboardData';
import { anomalyService } from '../services/anomalyService';
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
  const navigate = useNavigate();
  const { stations, selectedStation } = useStation();
  const [filters, setFilters] = useState<AnomalyFilterValues>({
    severity: 'all',
    type: 'all',
    searchQuery: '',
    stationId: 'all',
  });
  const isNetworkWide = !filters.stationId || filters.stationId === 'all';
  const effectiveStationId = isNetworkWide ? undefined : filters.stationId;
  const {
    latestAnomaly: stationLatestAnomaly,
    isPaused,
    togglePause,
    staleStatusText,
  } = useDashboardData(selectedStation?.station_id, { autoPoll: true });
  const [anomalies, setAnomalies] = useState<RecentAnomalyItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const fetchAnomalies = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await anomalyService.getRecentAnomalies(effectiveStationId, 100);
      setAnomalies(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load anomalies feed.');
    } finally {
      setIsLoading(false);
    }
  }, [effectiveStationId]);
  useEffect(() => {
    fetchAnomalies();
    if (isPaused) return;
    const interval = setInterval(fetchAnomalies, 15000);
    return () => clearInterval(interval);
  }, [fetchAnomalies, isPaused]);
  const handleOpenShap = (anomaly: RecentAnomalyItem) => {
    navigate(`/analytics?anomaly_id=${anomaly.anomaly_id}&station_id=${anomaly.station_id}`);
  };
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
      stationId: 'all',
    });
  };
  const sortedAnomalies = useMemo(() => {
    return [...anomalies].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [anomalies]);
  const filteredAnomalies = useMemo(() => {
    return sortedAnomalies.filter((anomaly) => {
      if (filters.stationId && filters.stationId !== 'all' && anomaly.station_id !== filters.stationId) {
        return false;
      }
      if (filters.severity !== 'all' && anomaly.severity !== filters.severity) {
        return false;
      }
      if (filters.type !== 'all' && anomaly.type !== filters.type) {
        return false;
      }
      if (filters.searchQuery.trim().length > 0) {
        const query = filters.searchQuery.toLowerCase();
        const matchesId = anomaly.anomaly_id.toLowerCase().includes(query);
        const matchesStation = anomaly.station_id.toLowerCase().includes(query);
        const matchesCause = anomaly.root_cause.toLowerCase().includes(query);
        const matchesDesc = anomaly.description.toLowerCase().includes(query);
        if (!matchesId && !matchesStation && !matchesCause && !matchesDesc) {
          return false;
        }
      }
      return true;
    });
  }, [sortedAnomalies, filters]);
  const featuredAnomaly = isNetworkWide
    ? ((sortedAnomalies[0] as unknown as LatestAnomaly) ?? null)
    : (stationLatestAnomaly ?? (sortedAnomalies[0] as unknown as LatestAnomaly) ?? null);
  const isFiltered = Boolean(
    filters.severity !== 'all' ||
    filters.type !== 'all' ||
    filters.searchQuery.trim().length > 0 ||
    (filters.stationId && filters.stationId !== 'all')
  );
  return (
    <div className="page-container sg-alerts-page" role="main" aria-label="Anomaly Alerts & Incident Investigation">
      {}
      <header className="sg-alerts-page__header">
        <div className="sg-alerts-page__title-area">
          <div className="sg-alerts-page__title-row">
            <ShieldAlert size={26} className="text-accent" aria-hidden="true" />
            <h1 className="sg-alerts-page__title">Anomaly Alerts & Incidents</h1>
          </div>
          <p className="sg-alerts-page__subtitle">
            Autonomous meteorological anomaly detection stream across all stations, classification analysis & root cause
            investigation.
          </p>
        </div>
        <div className="sg-alerts-page__header-controls">
          <div className="sg-alerts-page__station-badge">
            {isNetworkWide ? (
              <>
                <Globe size={14} className="text-accent" />
                <span>All Stations ({stations.length} Active)</span>
              </>
            ) : (
              <>
                <MapPin size={14} className="text-accent" />
                <span>Station: {filters.stationId}</span>
              </>
            )}
          </div>
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
            onClick={() => fetchAnomalies()}
            leftIcon={<RefreshCw size={14} />}
            ariaLabel="Refresh anomaly feeds"
          >
            Refresh
          </Button>
        </div>
      </header>
      {}
      <AlertSummaryCards
        latestAnomaly={featuredAnomaly}
        recentAnomalies={sortedAnomalies}
        isLoading={isLoading}
      />
      {}
      <LatestAnomalyBanner
        latestAnomaly={featuredAnomaly}
        isLoading={isLoading}
        error={error}
        onRetry={fetchAnomalies}
        onInvestigate={handleOpenModal}
        onOpenShap={(anom) => handleOpenShap(anom as unknown as RecentAnomalyItem)}
      />
      {}
      <AnomalyFilters
        filters={filters}
        onChange={setFilters}
        onReset={handleResetFilters}
        totalCount={sortedAnomalies.length}
        filteredCount={filteredAnomalies.length}
        stations={stations}
      />
      {}
      <RecentAnomaliesList
        anomalies={filteredAnomalies}
        isLoading={isLoading}
        error={error}
        onRetry={fetchAnomalies}
        onSelectAnomaly={handleOpenModal}
        onOpenShap={handleOpenShap}
        isFiltered={isFiltered}
        onClearFilters={handleResetFilters}
      />
      {}
      <AnomalyDetailModal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        anomaly={selectedAnomaly}
      />
    </div>
  );
};
export default AlertsPage;
