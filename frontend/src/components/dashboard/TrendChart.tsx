import React, { useState, useRef, useId } from 'react';
import { createPortal } from 'react-dom';
import { LineChart as LineChartIcon, Clock } from 'lucide-react';
import { Card } from '../common/Card';
import { Skeleton } from '../common/Skeleton';
import { TrendPoint } from '../../types';
import { windowTrendPoints } from '../../utils/chartWindow';
import { formatChartTime } from '../../utils/chartTime';
import { suggestedFromTrendPoint } from '../../utils/suggestedValues';
import { SuggestedValues } from '../common/SuggestedValues';
import './TrendChart.css';

export type MetricType = 'temperature' | 'pressure' | 'humidity';

export interface TrendChartProps {
  points?: TrendPoint[];
  hours?: number;
  onHoursChange?: (hours: number) => void;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  className?: string;
}

const METRIC_CONFIG = {
  temperature: {
    label: 'Temperature',
    unit: '°C',
    color: '#3b82f6',
    key: 'temperature_c' as const,
  },
  pressure: {
    label: 'Pressure',
    unit: 'hPa',
    color: '#06b6d4',
    key: 'pressure_hpa' as const,
  },
  humidity: {
    label: 'Humidity',
    unit: '%',
    color: '#10b981',
    key: 'humidity_pct' as const,
  },
};

export const getAffectedMetricLabels = (pt: TrendPoint): string[] => {
  const affected: Set<string> = new Set();

  if (pt.affected_parameters && pt.affected_parameters.length > 0) {
    for (const p of pt.affected_parameters) {
      const lower = p.toLowerCase();
      if (lower.includes('temp')) affected.add('Temperature');
      else if (lower.includes('press')) affected.add('Pressure');
      else if (lower.includes('humid') || lower.includes('dew') || lower.includes('rh')) affected.add('Humidity');
    }
  }

  if (pt.suggested_temperature_c != null) affected.add('Temperature');
  if (pt.suggested_pressure_hpa != null) affected.add('Pressure');
  if (pt.suggested_humidity_pct != null) affected.add('Humidity');

  const ft = (pt.fault_type || '').toLowerCase();
  if (ft.includes('temp')) affected.add('Temperature');
  if (ft.includes('press')) affected.add('Pressure');
  if (ft.includes('humid') || ft.includes('dew')) affected.add('Humidity');

  // If still empty but is_anomaly is true, check physical bounds on raw values
  if (affected.size === 0 && pt.is_anomaly) {
    if (typeof pt.humidity_pct === 'number' && (pt.humidity_pct < 0 || pt.humidity_pct > 100 || Math.abs(pt.humidity_pct) < 0.05)) {
      affected.add('Humidity');
    }
    if (typeof pt.temperature_c === 'number' && (pt.temperature_c < -60 || pt.temperature_c > 65 || Math.abs(pt.temperature_c - (-40)) < 0.05)) {
      affected.add('Temperature');
    }
    if (typeof pt.pressure_hpa === 'number' && (pt.pressure_hpa < 750 || pt.pressure_hpa > 1100 || Math.abs(pt.pressure_hpa) < 0.05)) {
      affected.add('Pressure');
    }
  }

  return Array.from(affected);
};

export const isMetricAnomalous = (pt: TrendPoint, metric: MetricType): boolean => {
  if (!pt.is_anomaly) return false;

  const labels = getAffectedMetricLabels(pt);
  const metricLabel = METRIC_CONFIG[metric].label;

  if (labels.length > 0) {
    return labels.includes(metricLabel);
  }

  const ft = (pt.fault_type || '').toLowerCase();
  if (ft.includes('multivariate') || ft.includes('network') || ft.includes('spatial')) {
    return true;
  }

  return true;
};

export const TrendChart: React.FC<TrendChartProps> = ({
  points = [],
  hours = 10,
  onHoursChange,
  isLoading = false,
  error = null,
  onRetry,
  className = '',
}) => {
  const [selectedMetric, setSelectedMetric] = useState<MetricType>('temperature');
  const [hoveredPoint, setHoveredPoint] = useState<{ point: TrendPoint; x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const chartId = useId();

  const activeCfg = METRIC_CONFIG[selectedMetric];
  const { points: windowedPoints, windowStart, windowEnd } = windowTrendPoints(points, hours);

  const renderToolbar = () => (
    <div className="sg-trend-header">
      <div className="sg-trend-title-group">
        <div className="sg-trend-title">
          <LineChartIcon size={18} className="text-accent" aria-hidden="true" />
          <h3 id={chartId}>Sensor Telemetry Trends</h3>
        </div>
        <span className="sg-trend-notice">● {hours}H WINDOW</span>
      </div>

      <div className="sg-trend-actions">
        <div className="sg-metric-tabs" role="tablist" aria-label="Select telemetry metric to graph">
          {(Object.keys(METRIC_CONFIG) as MetricType[]).map((metricKey) => {
            const cfg = METRIC_CONFIG[metricKey];
            const isSelected = selectedMetric === metricKey;
            return (
              <button
                key={metricKey}
                type="button"
                role="tab"
                aria-selected={isSelected}
                className={`sg-metric-tab ${isSelected ? 'sg-metric-tab--active' : ''}`}
                onClick={() => setSelectedMetric(metricKey)}
              >
                <span
                  className="sg-metric-tab-dot"
                  style={{ backgroundColor: cfg.color }}
                  aria-hidden="true"
                />
                <span>{cfg.label}</span>
              </button>
            );
          })}
        </div>

        {onHoursChange && (
          <div className="sg-range-select" aria-label="Time window selection">
            <Clock size={13} className="text-muted" aria-hidden="true" />
            {[10, 24, 72].map((h) => (
              <button
                key={h}
                type="button"
                className={`sg-range-btn ${hours === h ? 'sg-range-btn--active' : ''}`}
                onClick={() => onHoursChange(h)}
              >
                {h}h
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  if (isLoading && (!points || points.length === 0)) {
    return (
      <Card variant="glass" className={`sg-trend-card ${className}`}>
        {renderToolbar()}
        <Skeleton className="sg-chart-skeleton" style={{ height: 240, width: '100%' }} />
      </Card>
    );
  }

  if (error && (!points || points.length === 0)) {
    return (
      <Card variant="glass" className={`sg-trend-card sg-trend-card--error ${className}`}>
        {renderToolbar()}
        <div className="sg-trend-error">
          <p>{error}</p>
          {onRetry && (
            <button type="button" className="sg-trend-retry-btn" onClick={onRetry}>
              Retry Trends
            </button>
          )}
        </div>
      </Card>
    );
  }

  if (!windowedPoints || windowedPoints.length === 0) {
    return (
      <Card variant="glass" className={`sg-trend-card ${className}`}>
        {renderToolbar()}
        <div className="sg-trend-empty">
          <p>No trend data in the selected {hours}h window for this station.</p>
        </div>
      </Card>
    );
  }

  // Filter only points that have a valid numeric measurement for the selected metric
  const validPoints = windowedPoints.filter(
    (p) =>
      p[activeCfg.key] !== null &&
      p[activeCfg.key] !== undefined &&
      typeof p[activeCfg.key] === 'number' &&
      !Number.isNaN(p[activeCfg.key])
  );

  if (validPoints.length === 0) {
    return (
      <Card variant="glass" className={`sg-trend-card ${className}`}>
        {renderToolbar()}
        <div className="sg-trend-empty">
          <p>No valid {activeCfg.label.toLowerCase()} readings in the selected {hours}h window.</p>
        </div>
      </Card>
    );
  }

  const values = validPoints.map((p) => p[activeCfg.key] as number);
  const minVal = Math.floor(Math.min(...values) - 0.5);
  const maxVal = Math.ceil(Math.max(...values) + 0.5);
  const valRange = maxVal - minVal || 1;

  const width = 800;
  const height = 240;
  const padLeft = 40;
  const padRight = 14;
  const padTop = 16;
  const padBottom = 26;

  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const span = Math.max(windowEnd - windowStart, 1000);
  const getX = (timestamp: string) => {
    const t = new Date(timestamp).getTime();
    const ratio = Math.max(0, Math.min(1, (t - windowStart) / span));
    return padLeft + ratio * plotWidth;
  };

  const getY = (val: number) => {
    return padTop + plotHeight - ((val - minVal) / valRange) * plotHeight;
  };

  // Generate SVG path commands strictly over valid points
  const pathD = validPoints.reduce((acc, point, i) => {
    const x = getX(point.timestamp);
    const y = getY(point[activeCfg.key] as number);
    return i === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  const areaD = validPoints.length > 1
    ? `${pathD} L ${getX(validPoints[validPoints.length - 1].timestamp)} ${padTop + plotHeight} L ${getX(validPoints[0].timestamp)} ${padTop + plotHeight} Z`
    : '';

  // Horizontal Grid Lines & Y Labels (4 steps)
  const yTicks = [0, 0.33, 0.66, 1].map((ratio) => {
    const val = minVal + ratio * valRange;
    const y = getY(val);
    return { val: Number(val.toFixed(1)), y };
  });

  // Real timestamp x-axis
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const time = windowStart + ratio * span;
    return {
      x: padLeft + ratio * plotWidth,
      label: formatChartTime(new Date(time).toISOString(), ratio === 0 || hours > 24),
    };
  });

  return (
    <Card variant="glass" className={`sg-trend-card ${className}`}>
      {renderToolbar()}

      {/* SVG Interactive Chart Canvas */}
      <div className="sg-chart-wrapper">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="sg-chart-svg"
          aria-labelledby={chartId}
          role="img"
        >
          {/* Grid lines */}
          {yTicks.map((tick, idx) => (
            <g key={idx}>
              <line
                x1={padLeft}
                y1={tick.y}
                x2={width - padRight}
                y2={tick.y}
                className="sg-chart-grid-line"
              />
              <text
                x={padLeft - 6}
                y={tick.y + 4}
                textAnchor="end"
                className="sg-chart-axis-text"
              >
                {tick.val}
              </text>
            </g>
          ))}

          {/* Bottom axis line */}
          <line
            x1={padLeft}
            y1={padTop + plotHeight}
            x2={width - padRight}
            y2={padTop + plotHeight}
            className="sg-chart-grid-line"
          />
          {xTicks.map((tick, idx) => (
            <text
              key={`x-${idx}`}
              x={tick.x}
              y={height - 8}
              textAnchor={idx === 0 ? 'start' : idx === xTicks.length - 1 ? 'end' : 'middle'}
              className="sg-chart-axis-text"
            >
              {tick.label}
            </text>
          ))}

          {/* Gradient Fill under curve */}
          <defs>
            <linearGradient id={`grad-${selectedMetric}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={activeCfg.color} stopOpacity="0.3" />
              <stop offset="100%" stopColor={activeCfg.color} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {areaD && <path d={areaD} fill={`url(#grad-${selectedMetric})`} />}

          {/* Single-point baseline guide */}
          {validPoints.length === 1 && (
            <line
              x1={padLeft}
              y1={getY(validPoints[0][activeCfg.key] as number)}
              x2={width - padRight}
              y2={getY(validPoints[0][activeCfg.key] as number)}
              stroke={activeCfg.color}
              strokeWidth="1.5"
              strokeDasharray="4 4"
              strokeOpacity="0.45"
            />
          )}

          {/* Line stroke */}
          {pathD && validPoints.length > 1 && (
            <path
              d={pathD}
              fill="none"
              stroke={activeCfg.color}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Points & Interactive Tooltip Anchors */}
          {validPoints.map((pt, i) => {
            const cx = getX(pt.timestamp);
            const cy = getY(pt[activeCfg.key] as number);
            const isAnomaly = isMetricAnomalous(pt, selectedMetric);
            const isLatest = i === validPoints.length - 1;

            return (
              <g key={`${pt.timestamp}-${i}`}>
                {isLatest && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={6}
                    fill="none"
                    stroke={isAnomaly ? '#ef4444' : activeCfg.color}
                    strokeWidth="1.5"
                    strokeOpacity="0.6"
                    className="sg-chart-latest-pulse"
                  />
                )}
                <circle
                  cx={cx}
                  cy={cy}
                  r={isAnomaly ? 3.5 : 2.5}
                  className={`sg-chart-point ${isAnomaly ? 'sg-chart-point--anomaly' : ''}`}
                  fill={isAnomaly ? '#ef4444' : activeCfg.color}
                  stroke="#ffffff"
                  strokeWidth={isAnomaly ? 1.5 : 1}
                  onMouseEnter={() => setHoveredPoint({ point: pt, x: cx, y: cy })}
                  onMouseLeave={() => setHoveredPoint(null)}
                  tabIndex={0}
                  role="button"
                  aria-label={
                    isAnomaly
                      ? `${activeCfg.label} anomaly (${pt.fault_type || 'fault'}): ${pt[activeCfg.key]} ${activeCfg.unit} at ${new Date(pt.timestamp).toLocaleTimeString()}`
                      : pt.is_anomaly
                      ? `${activeCfg.label}: ${pt[activeCfg.key]} ${activeCfg.unit} (Nominal, alert on other sensor) at ${new Date(pt.timestamp).toLocaleTimeString()}`
                      : `${activeCfg.label}: ${pt[activeCfg.key]} ${activeCfg.unit} at ${new Date(pt.timestamp).toLocaleTimeString()}`
                  }
                />
              </g>
            );
          })}
        </svg>

        {/* Floating tooltip anchored to hovered point */}
        {hoveredPoint && svgRef.current && createPortal(
          (() => {
            const pt = hoveredPoint.point;
            const isMetricAnomaly = isMetricAnomalous(pt, selectedMetric);
            const isStationAnomaly = Boolean(pt.is_anomaly);
            const affectedLabels = getAffectedMetricLabels(pt);
            const otherLabels = affectedLabels.filter((l) => l.toLowerCase() !== activeCfg.label.toLowerCase());
            const otherLabelsText = otherLabels.join(' & ');

            return (
              <div
                className="sg-chart-tooltip"
                style={{
                  position: 'fixed',
                  left: Math.min(
                    window.innerWidth - 270,
                    svgRef.current.getBoundingClientRect().left + (hoveredPoint.x / width) * svgRef.current.getBoundingClientRect().width + 10
                  ),
                  top: Math.max(
                    10,
                    svgRef.current.getBoundingClientRect().top + (hoveredPoint.y / height) * svgRef.current.getBoundingClientRect().height - 70
                  ),
                  zIndex: 9999,
                  pointerEvents: 'none',
                }}
              >
                <div className="sg-tooltip-time">
                  {formatChartTime(pt.timestamp, true)}
                </div>
                <div className="sg-tooltip-value">
                  <span className="sg-tooltip-label">{activeCfg.label}:</span>
                  <strong>
                    {pt[activeCfg.key]} {activeCfg.unit}
                  </strong>
                  <span className={`sg-tooltip-status-pill ${isMetricAnomaly ? 'sg-tooltip-status-pill--alert' : 'sg-tooltip-status-pill--normal'}`}>
                    {isMetricAnomaly ? 'FAULT' : 'NOMINAL'}
                  </span>
                </div>

                {isMetricAnomaly ? (
                  <div className="sg-tooltip-metric-fault">
                    <div className="sg-tooltip-score">
                      Fault: <strong>{pt.fault_type ? pt.fault_type.replace(/_/g, ' ') : 'Detected Anomaly'}</strong>
                    </div>
                    <div className="sg-tooltip-affected">
                      Affected: <strong>{activeCfg.label}</strong>
                    </div>
                    {pt.severity && (
                      <div className="sg-tooltip-score">Severity: {pt.severity}</div>
                    )}
                    {typeof pt.anomaly_score_pct === 'number' && (
                      <div className="sg-tooltip-score">
                        Risk Score: {pt.anomaly_score_pct}%
                      </div>
                    )}
                    <SuggestedValues
                      items={suggestedFromTrendPoint(pt, selectedMetric)}
                      compact
                      showHeading
                      emptyLabel="Suggested replacement unavailable during baseline warm-up"
                    />
                    {pt.health_status && <div className="sg-tooltip-time">Sensor: {pt.health_status}</div>}
                  </div>
                ) : isStationAnomaly ? (
                  <div className="sg-tooltip-cross-notice">
                    <div className="sg-tooltip-cross-header">
                      <span className="sg-tooltip-cross-badge">Station Alert</span>
                      <span className="sg-tooltip-cross-target">
                        on {otherLabelsText || 'Other Sensor'}
                      </span>
                    </div>
                    <div className="sg-tooltip-cross-fault">
                      Fault: <strong>{pt.fault_type ? pt.fault_type.replace(/_/g, ' ') : 'Detected Anomaly'}</strong>
                    </div>
                    {pt.severity && (
                      <div className="sg-tooltip-cross-sub">Severity: {pt.severity}</div>
                    )}
                    {typeof pt.anomaly_score_pct === 'number' && (
                      <div className="sg-tooltip-cross-sub">
                        Station Risk: {pt.anomaly_score_pct}%
                      </div>
                    )}
                    <div className="sg-tooltip-metric-ok">
                      ✓ {activeCfg.label} is operating normally.
                    </div>
                  </div>
                ) : (
                  typeof pt.anomaly_score_pct === 'number' && (
                    <div className="sg-tooltip-score sg-tooltip-score--low">
                      Risk Score: {pt.anomaly_score_pct}% (Nominal)
                    </div>
                  )
                )}
              </div>
            );
          })(),
          document.body
        )}
      </div>

      {/* Accessible Textual Summary for Screen Readers */}
      <details className="sg-chart-accessible-summary">
        <summary>View {activeCfg.label} data points table</summary>
        <div className="sg-accessible-table-wrapper">
          <table className="sg-accessible-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>{activeCfg.label} ({activeCfg.unit})</th>
              </tr>
            </thead>
            <tbody>
              {windowedPoints.map((pt, i) => (
                <tr key={`${pt.timestamp}-${i}`}>
                  <td>{formatChartTime(pt.timestamp)}</td>
                  <td>{pt[activeCfg.key]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  );
};
