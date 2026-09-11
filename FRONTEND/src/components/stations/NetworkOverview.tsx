import React, { useMemo } from 'react';
import { Network, Compass } from 'lucide-react';
import { Station } from '../../types';
import { Card } from '../common/Card';
import { Skeleton } from '../common/Skeleton';
import { calculateDistanceKm, formatDistance } from '../../utils/geospatial';
import './NetworkOverview.css';

export interface NetworkOverviewProps {
  stations: Station[];
  selectedStation: Station | null;
  onSelectStation: (station: Station) => void;
  isLoading?: boolean;
  className?: string;
}

/**
 * Maps station status to theme color.
 */
function getStatusColor(status: string): string {
  switch (status) {
    case 'NORMAL':
      return '#10b981';
    case 'WARNING':
      return '#f59e0b';
    case 'CRITICAL':
      return '#ef4444';
    case 'OFFLINE':
    default:
      return '#64748b';
  }
}

export const NetworkOverview: React.FC<NetworkOverviewProps> = ({
  stations,
  selectedStation,
  onSelectStation,
  isLoading = false,
  className = '',
}) => {
  // SVG Chart Geometry
  const width = 760;
  const height = 360;
  const padding = 50;

  // Project lat/lon to 2D SVG canvas
  const projectedStations = useMemo(() => {
    if (stations.length === 0) return [];

    const lats = stations.map((s) => s.lat).filter((l) => l != null && !isNaN(l));
    const lons = stations.map((s) => s.lon).filter((l) => l != null && !isNaN(l));

    if (lats.length === 0 || lons.length === 0) return [];

    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const latSpan = maxLat - minLat || 1;
    const lonSpan = maxLon - minLon || 1;

    return stations.map((s) => {
      // Invert lat for SVG Y (higher lat = higher up = lower Y)
      const x = padding + ((s.lon - minLon) / lonSpan) * (width - 2 * padding);
      const y = height - padding - ((s.lat - minLat) / latSpan) * (height - 2 * padding);

      const isSelected = selectedStation?.station_id === s.station_id;
      const distance =
        selectedStation && !isSelected
          ? calculateDistanceKm(selectedStation.lat, selectedStation.lon, s.lat, s.lon)
          : 0;

      return {
        station: s,
        x: Math.round(x),
        y: Math.round(y),
        isSelected,
        distance,
      };
    });
  }, [stations, selectedStation, width, height, padding]);

  const selectedPoint = projectedStations.find((p) => p.isSelected);

  if (isLoading) {
    return (
      <Card variant="glass" className={`sg-network-overview-card ${className}`}>
        <div className="sg-network-overview__header">
          <Skeleton width="200px" height="1.3rem" />
          <Skeleton width="120px" height="1.1rem" />
        </div>
        <Skeleton width="100%" height="280px" style={{ marginTop: '1rem' }} />
      </Card>
    );
  }

  return (
    <Card
      variant="glass"
      className={`sg-network-overview-card ${className}`}
      role="region"
      aria-label="Station Network Topology Overview"
    >
      <div className="sg-network-overview__header">
        <div className="sg-network-overview__title-group">
          <Network size={18} className="text-accent" aria-hidden="true" />
          <h3 className="sg-network-overview__title">Observatory Network Topology</h3>
        </div>
        <div className="sg-network-overview__notice-group">
          <Compass size={14} className="text-accent" aria-hidden="true" />
          <span className="sg-network-overview__notice">
            [FRONTEND ONLY] [DERIVED FROM STATION COORDINATES]
          </span>
        </div>
      </div>

      <p className="sg-network-overview__desc">
        Visual representation of active automatic weather stations across the regional network.
        Select any node to change the primary focus observatory.
      </p>

      {/* SVG Network Canvas */}
      <div className="sg-network-overview__canvas-wrapper">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="sg-network-overview__svg"
          role="img"
          aria-label="Interactive map of weather stations network showing distance links to selected station"
        >
          {/* Subtle Grid Background */}
          <defs>
            <pattern id="networkGrid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(255, 255, 255, 0.03)"
                strokeWidth="1"
              />
            </pattern>
            <radialGradient id="selectedGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect width={width} height={height} fill="url(#networkGrid)" />

          {/* Connection Lines from Selected Station to Neighbors */}
          {selectedPoint &&
            projectedStations
              .filter((p) => !p.isSelected)
              .map((p) => {
                const midX = (selectedPoint.x + p.x) / 2;
                const midY = (selectedPoint.y + p.y) / 2;

                return (
                  <g key={`link-${p.station.station_id}`}>
                    {/* Dashed Link */}
                    <line
                      x1={selectedPoint.x}
                      y1={selectedPoint.y}
                      x2={p.x}
                      y2={p.y}
                      className="sg-network-overview__link"
                    />

                    {/* Distance Badge on Link */}
                    {p.distance != null && p.distance > 0 && (
                      <g className="sg-network-overview__distance-pill">
                        <rect
                          x={midX - 28}
                          y={midY - 9}
                          width="56"
                          height="18"
                          rx="4"
                          className="sg-network-overview__distance-bg"
                        />
                        <text
                          x={midX}
                          y={midY + 4}
                          textAnchor="middle"
                          className="sg-network-overview__distance-text"
                        >
                          {formatDistance(p.distance)}
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}

          {/* Station Nodes */}
          {projectedStations.map((p) => {
            const statusColor = getStatusColor(p.station.status);

            return (
              <g
                key={`node-${p.station.station_id}`}
                className={`sg-network-overview__node ${
                  p.isSelected ? 'sg-network-overview__node--selected' : ''
                }`}
                onClick={() => onSelectStation(p.station)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectStation(p.station);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`Select station ${p.station.name} (${p.station.station_id}), status ${p.station.status}`}
              >
                {/* Halo if selected */}
                {p.isSelected && (
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r="24"
                    fill="url(#selectedGlow)"
                    className="sg-network-overview__halo"
                  />
                )}

                {/* Outer Ring */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.isSelected ? 10 : 7}
                  fill="#0b1120"
                  stroke={p.isSelected ? '#38bdf8' : statusColor}
                  strokeWidth={p.isSelected ? 3 : 2}
                  className="sg-network-overview__circle"
                />

                {/* Center Core */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.isSelected ? 4 : 3}
                  fill={p.isSelected ? '#38bdf8' : statusColor}
                />

                {/* Station Label */}
                <text
                  x={p.x}
                  y={p.y + (p.isSelected ? 24 : 20)}
                  textAnchor="middle"
                  className={`sg-network-overview__node-label ${
                    p.isSelected ? 'sg-network-overview__node-label--selected' : ''
                  }`}
                >
                  {p.station.name.split(' ')[0]} ({p.station.station_id.replace('ST-', '')})
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="sg-network-overview__legend">
        <div className="sg-network-overview__legend-item">
          <span
            className="sg-network-overview__legend-dot"
            style={{ background: '#38bdf8', boxShadow: '0 0 6px #38bdf8' }}
          />
          <span>Primary Selected Station</span>
        </div>
        <div className="sg-network-overview__legend-item">
          <span className="sg-network-overview__legend-dot" style={{ background: '#10b981' }} />
          <span>Normal Status</span>
        </div>
        <div className="sg-network-overview__legend-item">
          <span className="sg-network-overview__legend-dot" style={{ background: '#f59e0b' }} />
          <span>Warning</span>
        </div>
        <div className="sg-network-overview__legend-item">
          <span className="sg-network-overview__legend-dot" style={{ background: '#ef4444' }} />
          <span>Critical</span>
        </div>
        <div className="sg-network-overview__legend-item">
          <span className="sg-network-overview__legend-dot" style={{ background: '#64748b' }} />
          <span>Offline</span>
        </div>
      </div>
    </Card>
  );
};
