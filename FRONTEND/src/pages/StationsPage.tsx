import React from 'react';
import { useStationNetworkData } from '../hooks/useStationNetworkData';
import {
  StationNetworkHeader,
  SelectedStationCard,
  NetworkOverview,
  SpatialComparison,
  SpatialConsistencyCard,
  NeighborStationTable,
  FutureSpatialNotice,
} from '../components/stations';
import { EmptyState } from '../components/common/EmptyState';
import './StationsPage.css';

/**
 * StationsPage
 * 
 * Step 9 — Station Network & Spatial Validation
 * 
 * Displays geographical station network topology, Haversine distance proximity,
 * and cross-station spatial telemetry consistency comparisons to help operators
 * distinguish genuine regional meteorological events from localized sensor anomalies.
 * 
 * [API: GET /api/stations — INTEGRATED]
 * [FRONTEND ONLY — DERIVED FROM STATION COORDINATES & DEMO TELEMETRY]
 */
export const StationsPage: React.FC = () => {
  const {
    selectedStation,
    stations,
    selectStation,
    scenario,
    setScenario,
    statusFilter,
    setStatusFilter,
    currentReading,
    latestAnomaly,
    neighbors,
    filteredNeighbors,
    spatialSummary,
    isLoading,
    error,
    refresh,
  } = useStationNetworkData();

  // ── No station selected ──────────────────────────────────────────────────────
  if (!isLoading && !selectedStation) {
    return (
      <main className="sg-stations-page" aria-label="Station Network & Spatial Validation page">
        <div className="sg-stations-page__no-station">
          <EmptyState
            title="No Station Selected"
            description="Please select a meteorological station from the navigation bar to begin spatial validation."
          />
        </div>
      </main>
    );
  }

  // ── Error state ──────────────────────────────────────────────────────────────
  if (error && !isLoading) {
    return (
      <main className="sg-stations-page" aria-label="Station Network & Spatial Validation page">
        <StationNetworkHeader
          selectedStation={selectedStation}
          scenario={scenario}
          onScenarioChange={setScenario}
          onRefresh={refresh}
          isLoading={false}
        />
        <div className="sg-stations-page__error">
          <div className="sg-stations-page__error-box" role="alert">
            <h2>Station Network Unavailable</h2>
            <p>{error}</p>
          </div>
        </div>
      </main>
    );
  }

  // ── Main Layout ──────────────────────────────────────────────────────────────
  return (
    <main className="sg-stations-page" aria-label="Station Network & Spatial Validation Dashboard">
      {/* ── Page Header ── */}
      <StationNetworkHeader
        selectedStation={selectedStation}
        scenario={scenario}
        onScenarioChange={setScenario}
        onRefresh={refresh}
        isLoading={isLoading}
      />

      {/* ── Selected Station Identity & Telemetry Snapshot ── */}
      <SelectedStationCard
        station={selectedStation}
        currentReading={currentReading}
        latestAnomaly={latestAnomaly}
        isLoading={isLoading}
      />

      {/* ── Network Topology Map ── */}
      <p className="sg-stations-page__section-label" aria-hidden="true">
        Spatial Topology & Proximity Mapping — [FRONTEND ONLY] [DERIVED FROM COORDINATES]
      </p>
      <NetworkOverview
        stations={stations}
        selectedStation={selectedStation}
        onSelectStation={selectStation}
        isLoading={isLoading}
      />

      {/* ── Spatial Consistency Verdict & Operational Story ── */}
      <p className="sg-stations-page__section-label" aria-hidden="true">
        Regional Spatial Consistency Analysis — [FRONTEND DEMO LOGIC]
      </p>
      <SpatialConsistencyCard summary={spatialSummary} isLoading={isLoading} />

      {/* ── 3-Metric Spatial Delta Comparisons ── */}
      <SpatialComparison summary={spatialSummary} isLoading={isLoading} />

      {/* ── Neighboring Stations Directory Table ── */}
      <p className="sg-stations-page__section-label" aria-hidden="true">
        Neighboring Observatories Directory — [DEMO SPATIAL COMPARISON]
      </p>
      <NeighborStationTable
        neighbors={neighbors}
        filteredNeighbors={filteredNeighbors}
        statusFilter={statusFilter}
        onFilterChange={setStatusFilter}
        onSelectStation={selectStation}
        isLoading={isLoading}
      />

      {/* ── Future Backend Seam Notice ── */}
      <FutureSpatialNotice />
    </main>
  );
};

export default StationsPage;
