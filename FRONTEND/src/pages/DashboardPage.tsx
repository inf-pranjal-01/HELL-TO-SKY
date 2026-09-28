import React, { useState, useRef, useEffect } from 'react';
import {
  Thermometer,
  Gauge,
  Droplets,
  RefreshCw,
  RotateCcw,
  Radio,
  Sparkles,
  Info,
  AlertTriangle,
  Cpu,
  Clock,
} from 'lucide-react';
import { useStation } from '../context/StationContext';
import { useDashboardData } from '../hooks/useDashboardData';
import { SensorMetricCard } from '../components/dashboard/SensorMetricCard';
import {
  AnomalyScoreCard,
  SensorHealthCard,
} from '../components/dashboard/StatusOverviewCards';
import { TrendChart } from '../components/dashboard/TrendChart';
import { LatestAnomalyCard } from '../components/dashboard/LatestAnomalyCard';
import { RecentAnomaliesCard } from '../components/dashboard/RecentAnomaliesCard';
import { EmptyState } from '../components/common/EmptyState';
import { Button } from '../components/common/Button';
import { Tooltip } from '../components/common/Tooltip';
import { anomalyInjectionService } from '../services/anomalyInjectionService';
import { systemStatusService } from '../services/systemStatusService';
import { API_CONFIG } from '../config/api.config';
import { formatUserErrorMessage, ApiError } from '../services/apiError';
import './DashboardPage.css';

export const DashboardPage: React.FC = () => {
  const { selectedStation, isLoading: isLoadingStation } = useStation();
  const [trendHours, setTrendHours] = useState<number>(10);
  const [isInjecting, setIsInjecting] = useState<boolean>(false);
  const [isPurging, setIsPurging] = useState<boolean>(false);
  const [injectionNotice, setInjectionNotice] = useState<string | null>(null);
  const [edgeTimeoutNotice, setEdgeTimeoutNotice] = useState<string | null>(null);
  const [isProviderBannerDismissed, setIsProviderBannerDismissed] = useState<boolean>(false);
  const activeStationRef = useRef<string | undefined>(selectedStation?.station_id);
  const noticeTimerRef = useRef<number | null>(null);
  const timeoutNoticeTimerRef = useRef<number | null>(null);

  const {
    currentReading,
    trends,
    latestAnomaly,
    recentAnomalies,
    isLoadingReading,
    isLoadingTrends,
    isLoadingAnomalies,
    readingError,
    trendsError,
    anomaliesError,
    lastUpdated,
    staleStatusText,
    pollStatusText,
    streamMode,
    providerStatus,
    edgeStatus,
    wsLatencyMs,
    isWsConnected,
    refreshAll,
    refreshReading,
    refreshTrends,
    refreshAnomalies,
    syncStreamStatus,
  } = useDashboardData(selectedStation?.station_id, {
    autoPoll: true,
    trendHours,
  });

  useEffect(() => {
    activeStationRef.current = selectedStation?.station_id;
    setInjectionNotice(null);
    setIsInjecting(false);
    setIsProviderBannerDismissed(false);
  }, [selectedStation?.station_id]);

  useEffect(() => {
    if (providerStatus?.status === 'HEALTHY') {
      setIsProviderBannerDismissed(false);
    }
  }, [providerStatus?.status]);

  useEffect(() => {
    const handleEdgeTimeout = (e: Event) => {
      const customEvt = e as CustomEvent;
      const msg = customEvt.detail?.message || 'ESP32 hardware link timed out (inactivity >330s). Auto-exited to Live Mode.';
      setEdgeTimeoutNotice(msg);
      if (timeoutNoticeTimerRef.current !== null) {
        clearTimeout(timeoutNoticeTimerRef.current);
      }
      timeoutNoticeTimerRef.current = window.setTimeout(() => {
        setEdgeTimeoutNotice(null);
      }, 10000);
    };

    window.addEventListener('sg-edge-timeout', handleEdgeTimeout);
    return () => {
      window.removeEventListener('sg-edge-timeout', handleEdgeTimeout);
      if (timeoutNoticeTimerRef.current !== null) {
        clearTimeout(timeoutNoticeTimerRef.current);
      }
      if (noticeTimerRef.current !== null) {
        clearTimeout(noticeTimerRef.current);
      }
    };
  }, []);

  // SIH Demo Anomaly Injection / Replay Trigger
  const handleSimulateInjection = async () => {
    if (!selectedStation || isInjecting) return;
    const targetStationId = selectedStation.station_id;
    setIsInjecting(true);

    if (noticeTimerRef.current !== null) {
      clearTimeout(noticeTimerRef.current);
    }

    try {
      const res = await anomalyInjectionService.injectAnomaly({
        station_id: targetStationId,
        type: 'spike',
      });
      if (activeStationRef.current !== targetStationId) return;
      setInjectionNotice(`Anomaly replay initiated [ID: ${res.anomaly_id}] — ${res.message}`);
      await syncStreamStatus();
      refreshAnomalies();
    } catch (err) {
      if (activeStationRef.current !== targetStationId) return;
      if (err instanceof ApiError && err.status === 409) {
        setInjectionNotice('Anomaly replay is already running across stations.');
      } else {
        setInjectionNotice(formatUserErrorMessage(err, 'Failed to initiate anomaly replay.'));
      }
    } finally {
      if (activeStationRef.current === targetStationId) {
        setIsInjecting(false);
      }
      noticeTimerRef.current = window.setTimeout(() => {
        setInjectionNotice(null);
      }, 7000);
    }
  };

  const handleRefresh = async () => {
    if (streamMode === 'live') {
      try {
        await systemStatusService.refreshLive(selectedStation?.station_id);
      } catch {
        // non-blocking
      }
    }
    await refreshAll();
    setIsProviderBannerDismissed(true);
  };

  const handleModeToggle = async () => {
    if (isInjecting) return;
    if (streamMode !== 'replay') {
      await handleSimulateInjection();
      return;
    }
    setIsInjecting(true);
    try {
      await systemStatusService.switchToLive();
      await syncStreamStatus();
      setInjectionNotice('Replay stopped. Dashboard is returning to live Open-Meteo data.');
      await refreshAll();
    } catch (err) {
      setInjectionNotice(formatUserErrorMessage(err, 'Failed to return to live mode.'));
    } finally {
      setIsInjecting(false);
    }
  };

  const handleEdgeToggle = async () => {
    if (isInjecting) return;
    setIsInjecting(true);
    try {
      if (streamMode === 'edge') {
        await systemStatusService.switchToLive();
        await syncStreamStatus();
        setInjectionNotice('ESP32 hardware testing closed. Switched to Live mode.');
      } else {
        await systemStatusService.switchToEdge(selectedStation?.station_id);
        await syncStreamStatus();
        setInjectionNotice('Switched to ESP32 Edge Ingestion mode. Waiting for hardware packets...');
      }
      await refreshAll();
    } catch (err) {
      setInjectionNotice(formatUserErrorMessage(err, 'Failed to toggle ESP32 mode.'));
    } finally {
      setIsInjecting(false);
    }
  };

  const handlePurgeHistory = async () => {
    if (isPurging) return;
    const confirmed = window.confirm(
      'Are you sure you want to purge all historical telemetry and anomalies from the database? This resets the dashboard to a clean, pristine state.'
    );
    if (!confirmed) return;

    setIsPurging(true);
    if (noticeTimerRef.current !== null) {
      clearTimeout(noticeTimerRef.current);
    }

    try {
      const res = await systemStatusService.clearHistory('all', selectedStation?.station_id);
      setInjectionNotice(res.message || 'Database purged. Telemetry reset to pristine state.');
      await refreshAll();
    } catch (err) {
      setInjectionNotice(formatUserErrorMessage(err, 'Failed to clear database history.'));
    } finally {
      setIsPurging(false);
      noticeTimerRef.current = window.setTimeout(() => {
        setInjectionNotice(null);
      }, 6000);
    }
  };

  // If no station is selected in context
  if (!isLoadingStation && !selectedStation) {
    return (
      <div className="page-container">
        <EmptyState
          title="No Station Selected"
          description="Please select an Automatic Weather Station (AWS) from the station selector dropdown in the navigation sidebar to monitor live telemetry."
          icon={<Radio size={48} className="text-accent" />}
        />
      </div>
    );
  }

  const stationName = selectedStation?.name || 'Observatory Telemetry';
  const stationId = selectedStation?.station_id || '';
  const isEdgeStation = streamMode === 'edge';

  return (
    <div className="page-container sg-dashboard-page">
      {/* Dashboard Top Header & Operational Banner */}
      <header className="sg-page-header">
        <div className="sg-dashboard-header-left">
          <div className="sg-dashboard-station-badge">
            <Radio size={16} className="text-accent" aria-hidden="true" />
            <span className="sg-station-title-id">{stationId}</span>
            <span className="sg-station-title-sep">•</span>
            <h2 className="sg-station-title-name">{stationName}</h2>
            {isEdgeStation && (
              <span className="sg-edge-hardware-tag" title="Connected to Physical ESP32 Microcontroller Node">
                [Hardware Source: ESP32 DevKit V1 (N4)]
              </span>
            )}
          </div>
          <p className="sg-page-sub">
            Real-time AWS sensor telemetry, anomaly risk index, and ML detection overview
          </p>
        </div>

        <div className="sg-page-actions">
          {/* Real-time Stream & Ingestion Mode Badge */}
          {streamMode === 'replay' ? (
            <div className="sg-latency-badge sg-latency-badge--replay">
              <Radio size={13} aria-hidden="true" />
              <span className="sg-latency-label">Replay Stream (2s)</span>
              <Tooltip
                position="bottom"
                content="Replay: benchmark dataset (2s/step)"
              >
                <button
                  type="button"
                  className="sg-badge-info-btn"
                  aria-label="Replay stream mode details"
                >
                  <Info size={11} />
                </button>
              </Tooltip>
            </div>
          ) : streamMode === 'edge' ? (
            <div className="sg-latency-badge sg-latency-badge--edge">
              <span className="sg-latency-dot" aria-hidden="true" />
              <span className="sg-latency-label">
                {edgeStatus?.connected
                  ? `⚡ ${wsLatencyMs !== null ? `${wsLatencyMs}ms` : '18ms'} ESP32 Direct`
                  : '📡 ESP32 Standby'}
              </span>
              <Tooltip
                position="bottom"
                content="ESP32 Microcontroller Edge Hardware Ingestion Mode"
              >
                <button
                  type="button"
                  className="sg-badge-info-btn"
                  aria-label="ESP32 Edge Mode details"
                >
                  <Info size={11} />
                </button>
              </Tooltip>
            </div>
          ) : (
            <div
              className={`sg-latency-badge ${isWsConnected ? 'sg-latency-badge--live' : 'sg-latency-badge--fallback'}`}
            >
              <span className="sg-latency-dot" aria-hidden="true" />
              <span className="sg-latency-label">
                {isWsConnected
                  ? `⚡ ${wsLatencyMs !== null ? `${wsLatencyMs}ms` : '85ms'} Live WS`
                  : '⚡ Polling Fallback'}
              </span>
              <Tooltip
                position="bottom"
                content={isWsConnected ? "Live WebSocket telemetry feed" : "HTTP polling fallback stream"}
              >
                <button
                  type="button"
                  className="sg-badge-info-btn"
                  aria-label="Live Mode details"
                >
                  <Info size={11} />
                </button>
              </Tooltip>
            </div>
          )}

          {/* Live Data Freshness Badge */}
          <div className="sg-live-badge-container">
            <span
              className={`sg-live-dot ${
                staleStatusText === 'LIVE'
                  ? 'sg-live-dot--live'
                  : staleStatusText === 'DATA DELAYED'
                  ? 'sg-live-dot--delayed'
                  : 'sg-live-dot--stale'
              }`}
              aria-hidden="true"
            />
            <span className="sg-live-text">{pollStatusText}</span>
            {lastUpdated && (
              <span className="sg-live-time">
                ({lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })})
              </span>
            )}
          </div>

          {/* Refresh Action Button */}
          <Tooltip content="Refresh telemetry across all sections" position="bottom">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              ariaLabel="Refresh all dashboard data"
              leftIcon={<RefreshCw size={14} />}
            >
              Refresh
            </Button>
          </Tooltip>

          {/* Purge / Reset DB Button */}
          <Tooltip content="Reset session and purge historical database records" position="bottom">
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePurgeHistory}
              disabled={isPurging || isInjecting}
              isLoading={isPurging}
              ariaLabel="Purge database history"
              leftIcon={<RotateCcw size={14} className="text-muted" />}
            >
              Reset DB
            </Button>
          </Tooltip>

          {/* Test ESP32 Node Mode Switcher */}
          <Tooltip content={streamMode === 'edge' ? 'Stop ESP32 hardware testing and return to live mode' : 'Enter ESP32 Node hardware ingestion test mode'} position="bottom">
            <Button
              variant={streamMode === 'edge' ? 'primary' : 'outline'}
              size="sm"
              onClick={handleEdgeToggle}
              disabled={isInjecting}
              isLoading={isInjecting && streamMode !== 'replay'}
              ariaLabel={streamMode === 'edge' ? 'Exit ESP32 test mode' : 'Test ESP32 node mode'}
              className={streamMode === 'edge' ? 'sg-edge-active-btn' : 'sg-edge-test-btn'}
              leftIcon={<Cpu size={14} className={streamMode === 'edge' ? 'text-white' : 'text-emerald-400'} />}
            >
              <span className="sg-edge-btn-text">
                {streamMode === 'edge' ? 'Exit ESP32 Mode' : 'Test ESP32 Node'}
              </span>
            </Button>
          </Tooltip>

          {/* Single source-of-truth mode toggle; replay and live share the chart. */}
          <Tooltip content={streamMode === 'replay' ? 'Stop replay and return to live mode' : 'Start historical anomaly replay'} position="bottom">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleModeToggle}
              disabled={isInjecting || !selectedStation}
              isLoading={isInjecting && streamMode === 'replay'}
              ariaLabel={streamMode === 'replay' ? 'Switch to live mode' : 'Switch to replay mode'}
              className="sg-sih-demo-btn"
              leftIcon={<Sparkles size={14} className="text-accent" />}
            >
              <span className="sg-sih-btn-text">
                {isInjecting ? 'Switching...' : streamMode === 'replay' ? 'Return to Live' : 'Start Replay'}
              </span>
            </Button>
          </Tooltip>
        </div>
      </header>

      {/* ESP32 Inactivity Auto-Exit Notice Banner (Small Announcement) */}
      {edgeTimeoutNotice && (
        <div className="sg-edge-timeout-banner" role="status" aria-live="polite">
          <div className="sg-edge-timeout-banner__content">
            <Clock size={15} className="sg-edge-timeout-icon" aria-hidden="true" />
            <span className="sg-edge-timeout-text">
              <strong>ESP32 Inactivity Timeout:</strong> No hardware packets received for &gt;330s (5.5m). Automatically returned to <strong>Live Mode</strong>.
            </span>
          </div>
          <button
            type="button"
            className="sg-edge-timeout-dismiss"
            onClick={() => setEdgeTimeoutNotice(null)}
            aria-label="Dismiss timeout announcement"
            title="Dismiss notification"
          >
            &times;
          </button>
        </div>
      )}

      {/* SIH Demo Notice Toast if triggered */}
      {injectionNotice && (
        <div className="sg-sih-toast" role="status" aria-live="polite">
          <Info size={16} className="text-accent" aria-hidden="true" />
          <span>{injectionNotice}</span>
        </div>
      )}

      {/* ESP32 Hardware Mode Banners */}
      {streamMode === 'edge' && (
        <>
          {(!edgeStatus || edgeStatus.status === 'WAITING' || !edgeStatus.connected) ? (
            <div className="sg-edge-waiting-banner" role="status">
              <div className="sg-edge-radar-icon">
                <Radio size={22} className="sg-radar-pulse text-emerald-400" aria-hidden="true" />
              </div>
              <div className="sg-edge-waiting-content">
                <div className="sg-edge-waiting-title">
                  📡 WAITING FOR ESP32 HARDWARE LINK...
                </div>
                <div className="sg-edge-waiting-sub">
                  Listening on <code>POST /api/ingest/observation</code> for live ObservationPacket frames. Run <code>python scripts/test_esp32_hardware.py</code> in terminal to begin automated CSV streaming. The dashboard will automatically lock onto the transmitting station.
                </div>
              </div>
            </div>
          ) : (
            <div className="sg-edge-connected-banner" role="status">
              <Radio size={18} className="text-emerald-400 flex-shrink-0" aria-hidden="true" />
              <div className="sg-edge-connected-content">
                <span className="sg-edge-connected-title">
                  🟢 ESP32 HARDWARE LINK ACTIVE — Station: {edgeStatus.station_id || stationId} &bull; Device: {edgeStatus.device_id || 'ESP32-DevKit-V1'}
                </span>
                <span className="sg-edge-connected-meta">
                  Packets Ingested: {edgeStatus.packet_count || 0} &bull; Turnaround Latency: {wsLatencyMs !== null ? `${wsLatencyMs}ms` : '18ms'} (Direct Stream)
                </span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Live Provider Health Warning Banner (Open-Meteo failure diagnosis) */}
      {streamMode === 'live' &&
        providerStatus &&
        providerStatus.status !== 'HEALTHY' &&
        !isProviderBannerDismissed &&
        (providerStatus.status === 'FAILING' ||
          (providerStatus.failing_stations &&
            providerStatus.failing_stations.includes(stationId))) && (
        <div className="sg-provider-alert-banner" role="alert">
          <AlertTriangle size={18} className="sg-provider-alert-icon" aria-hidden="true" />
          <div className="sg-provider-alert-content">
            <span className="sg-provider-alert-title">
              Open-Meteo Live Feed Alert ({providerStatus.status})
            </span>
            <span className="sg-provider-alert-text">
              {' '}&bull; {providerStatus.consecutive_failures} consecutive poll failures. Diagnosed Cause: {providerStatus.diagnosed_cause || 'Provider network timeout'}. Telemetry stream is gracefully skipping missing ticks and holding last verified physical state.
            </span>
          </div>
          <button
            type="button"
            className="sg-provider-alert-dismiss"
            onClick={() => setIsProviderBannerDismissed(true)}
            aria-label="Dismiss provider alert"
          >
            &times;
          </button>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* SECTION 1: REAL-TIME METRIC OVERVIEW CARDS            */}
      {/* ---------------------------------------------------- */}
      <section className="sg-dashboard-section" aria-label="Real-time sensor metrics overview">
        <div className="sg-section-title-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
            <h3 className="sg-section-title">Current Sensor Readings & Risk</h3>
            {isEdgeStation && (
              <span className="sg-edge-hardware-tag">
                [Hardware Source: ESP32 DevKit V1 (N4)]
              </span>
            )}
          </div>
          <span className="sg-endpoint-tag">
            ● {streamMode === 'edge' ? 'ESP32 HARDWARE INGEST' : streamMode === 'replay' ? 'ANOMALY REPLAY' : 'LIVE BACKEND'}
          </span>
        </div>

        <div className="sg-metric-grid">
          {/* Temperature Overview */}
          <SensorMetricCard
            title="Temperature"
            icon={<Thermometer size={18} />}
            value={currentReading?.temperature_c?.value}
            unit="°C"
            normalMin={currentReading?.temperature_c?.normal_min}
            normalMax={currentReading?.temperature_c?.normal_max}
            isLoading={isLoadingReading}
            error={readingError}
            onRetry={refreshReading}
            accentColor="#3b82f6"
            suggestedValue={
              currentReading?.is_anomaly ? currentReading.suggested_values?.temperature_c : undefined
            }
          />

          {/* Atmospheric Pressure Overview */}
          <SensorMetricCard
            title="Pressure"
            icon={<Gauge size={18} />}
            value={currentReading?.pressure_hpa?.value}
            unit="hPa"
            normalMin={currentReading?.pressure_hpa?.normal_min}
            normalMax={currentReading?.pressure_hpa?.normal_max}
            isLoading={isLoadingReading}
            error={readingError}
            onRetry={refreshReading}
            accentColor="#06b6d4"
            suggestedValue={
              currentReading?.is_anomaly ? currentReading.suggested_values?.pressure_hpa : undefined
            }
          />

          {/* Relative Humidity Overview */}
          <SensorMetricCard
            title="Humidity"
            icon={<Droplets size={18} />}
            value={currentReading?.humidity_pct?.value}
            unit="%"
            normalMin={currentReading?.humidity_pct?.normal_min}
            normalMax={currentReading?.humidity_pct?.normal_max}
            isLoading={isLoadingReading}
            error={readingError}
            onRetry={refreshReading}
            accentColor="#10b981"
            suggestedValue={
              currentReading?.is_anomaly ? currentReading.suggested_values?.humidity_pct : undefined
            }
          />

          {/* Anomaly Score & Risk Card */}
          <AnomalyScoreCard
            score={currentReading?.anomaly_score_pct}
            riskLevel={currentReading?.risk_level}
            modelStatus={currentReading?.model_status}
            isLoading={isLoadingReading}
            error={readingError}
            onRetry={refreshReading}
          />

          {/* Sensor Health Card */}
          <SensorHealthCard
            healthPct={currentReading?.sensor_health_pct}
            healthStatus={currentReading?.sensor_health_status}
            isLoading={isLoadingReading}
            error={readingError}
            onRetry={refreshReading}
          />
        </div>
      </section>

      {/* ---------------------------------------------------- */}
      {/* SECTION 2: SENSOR TELEMETRY TREND VISUALIZATION      */}
      {/* ---------------------------------------------------- */}
      <section className="sg-dashboard-section" aria-label="Sensor trend analysis">
        <TrendChart
          points={trends?.points}
          hours={trendHours}
          onHoursChange={setTrendHours}
          isLoading={isLoadingTrends}
          error={trendsError}
          onRetry={() => refreshTrends(trendHours)}
        />
        {selectedStation && (
          <div className="sg-history-export">
            <span>Retained station history: up to 30 days, including source, anomaly verdicts, and suggested values.</span>
            <a
              href={`${API_CONFIG.baseUrl}/api/history.csv?station_id=${encodeURIComponent(selectedStation.station_id)}`}
              className="sg-history-export__link"
            >
              Download full station CSV
            </a>
          </div>
        )}
      </section>

      {/* ---------------------------------------------------- */}
      {/* SECTION 3: ANOMALY SUMMARY (LATEST & RECENT)          */}
      {/* ---------------------------------------------------- */}
      <section className="sg-dashboard-section" aria-label="Anomaly diagnostics and history">
        <div className="sg-anomaly-grid">
          {/* Latest Anomaly Card */}
          <LatestAnomalyCard
            anomaly={latestAnomaly}
            isLoading={isLoadingAnomalies}
            error={anomaliesError}
            onRetry={refreshAnomalies}
            streamMode={streamMode}
          />

          {/* Recent Anomalies History Summary */}
          <RecentAnomaliesCard
            anomalies={recentAnomalies}
            isLoading={isLoadingAnomalies}
            error={anomaliesError}
            onRetry={refreshAnomalies}
            streamMode={streamMode}
          />
        </div>
      </section>
    </div>
  );
};

export default DashboardPage;
