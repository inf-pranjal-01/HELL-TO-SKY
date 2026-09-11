import React, { useMemo, useState, useRef } from 'react';
import { Network, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { Station } from '../../types';
import { Card } from '../common/Card';
import { Skeleton } from '../common/Skeleton';
import { Button } from '../common/Button';
import './NetworkOverview.css';

export interface NetworkOverviewProps {
  stations: Station[];
  selectedStation: Station | null;
  onSelectStation: (station: Station) => void;
  isLoading?: boolean;
  className?: string;
}

const CITY_FROM_CODE: Record<string, string> = {
  DEL: 'Delhi',
  MUM: 'Mumbai',
  CHN: 'Chennai',
  KOL: 'Kolkata',
  BHO: 'Bhopal',
};

function getStatusColor(status: string): string {
  switch (status) {
    case 'NORMAL':
      return '#10b981';
    case 'WARNING':
      return '#f59e0b';
    case 'CRITICAL':
      return '#ef4444';
    default:
      return '#64748b';
  }
}

function stationCity(station: Station): string {
  const match = station.station_id.match(/AWS-([A-Z]{3})/i);
  if (match && CITY_FROM_CODE[match[1].toUpperCase()]) {
    return CITY_FROM_CODE[match[1].toUpperCase()];
  }
  return station.name.split(/[\s-]/)[0];
}

function shortId(stationId: string): string {
  const tail = stationId.split('-').pop();
  return tail || stationId;
}

export const NetworkOverview: React.FC<NetworkOverviewProps> = ({
  stations,
  selectedStation,
  onSelectStation,
  isLoading = false,
  className = '',
}) => {
  const width = 900;
  const height = 520;
  const padding = 90;
  const minZoom = 1;
  const maxZoom = 5;

  const [zoom, setZoom] = useState(1.2);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ active: boolean; moved: boolean; startX: number; startY: number; panX: number; panY: number }>({
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    panX: 0,
    panY: 0,
  });
  const wrapperRef = useRef<HTMLDivElement>(null);

  const projectedStations = useMemo(() => {
    if (stations.length === 0) return [];
    const lats = stations.map((s) => s.lat).filter((l) => l != null && !Number.isNaN(l));
    const lons = stations.map((s) => s.lon).filter((l) => l != null && !Number.isNaN(l));
    if (lats.length === 0 || lons.length === 0) return [];

    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const latSpan = maxLat - minLat || 1;
    const lonSpan = maxLon - minLon || 1;

    const project = (station: Station) => ({
      x: padding + ((station.lon - minLon) / lonSpan) * (width - 2 * padding),
      y: height - padding - ((station.lat - minLat) / latSpan) * (height - 2 * padding),
    });

    const groups = new Map<string, Station[]>();
    stations.forEach((station) => {
      const key = stationCity(station);
      const list = groups.get(key) ?? [];
      list.push(station);
      groups.set(key, list);
    });

    const placed: Array<{
      station: Station;
      x: number;
      y: number;
      isSelected: boolean;
      city: string;
    }> = [];

    groups.forEach((group, city) => {
      const centroid = group.reduce(
        (acc, station) => {
          const point = project(station);
          return { x: acc.x + point.x / group.length, y: acc.y + point.y / group.length };
        },
        { x: 0, y: 0 }
      );
      group.forEach((station, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(group.length, 1) - Math.PI / 2;
        const radius = group.length > 1 ? 36 : 0;
        placed.push({
          station,
          x: centroid.x + Math.cos(angle) * radius,
          y: centroid.y + Math.sin(angle) * radius,
          isSelected: selectedStation?.station_id === station.station_id,
          city,
        });
      });
    });

    return placed;
  }, [stations, selectedStation]);

  const viewW = width / zoom;
  const viewH = height / zoom;
  const viewX = (width - viewW) / 2 - pan.x;
  const viewY = (height - viewH) / 2 - pan.y;

  const clampPan = (nextZoom: number, nextPan: { x: number; y: number }) => {
    const maxShiftX = ((nextZoom - 1) * width) / 2 + 40;
    const maxShiftY = ((nextZoom - 1) * height) / 2 + 40;
    return {
      x: Math.max(-maxShiftX, Math.min(maxShiftX, nextPan.x)),
      y: Math.max(-maxShiftY, Math.min(maxShiftY, nextPan.y)),
    };
  };

  const zoomAt = (nextZoom: number, clientX?: number, clientY?: number) => {
    const z = Math.max(minZoom, Math.min(maxZoom, nextZoom));
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!rect || clientX == null || clientY == null) {
      setZoom(z);
      setPan((prev) => clampPan(z, prev));
      return;
    }
    const cursorX = viewX + ((clientX - rect.left) / rect.width) * viewW;
    const cursorY = viewY + ((clientY - rect.top) / rect.height) * viewH;
    const nextViewW = width / z;
    const nextViewH = height / z;
    const nextViewX = cursorX - ((clientX - rect.left) / rect.width) * nextViewW;
    const nextViewY = cursorY - ((clientY - rect.top) / rect.height) * nextViewH;
    setZoom(z);
    setPan(
      clampPan(z, {
        x: (width - nextViewW) / 2 - nextViewX,
        y: (height - nextViewH) / 2 - nextViewY,
      })
    );
  };

  const handleWheel: React.WheelEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    zoomAt(zoom * (event.deltaY > 0 ? 0.86 : 1.16), event.clientX, event.clientY);
  };

  const handlePointerDown: React.PointerEventHandler<HTMLDivElement> = (event) => {
    if (event.button !== 0) return;
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      panX: pan.x,
      panY: pan.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove: React.PointerEventHandler<HTMLDivElement> = (event) => {
    if (!dragRef.current.active) return;
    const rect = wrapperRef.current?.getBoundingClientRect();
    const scaleX = width / (rect?.width || width);
    const dx = (event.clientX - dragRef.current.startX) * scaleX;
    const dy = (event.clientY - dragRef.current.startY) * scaleX;
    if (Math.abs(dx) + Math.abs(dy) > 4) dragRef.current.moved = true;
    setPan(clampPan(zoom, { x: dragRef.current.panX + dx, y: dragRef.current.panY + dy }));
  };

  const endDrag: React.PointerEventHandler<HTMLDivElement> = () => {
    dragRef.current.active = false;
  };

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
      aria-label="Station network map"
    >
      <div className="sg-network-overview__header">
        <div className="sg-network-overview__title-group">
          <Network size={18} className="text-accent" aria-hidden="true" />
          <h3 className="sg-network-overview__title">Observatory Network Map</h3>
        </div>
        <div className="sg-network-overview__zoom-controls">
          <Button variant="outline" size="sm" onClick={() => zoomAt(zoom - 0.4)} ariaLabel="Zoom out" leftIcon={<ZoomOut size={14} />}>
            Zoom out
          </Button>
          <span className="sg-network-overview__zoom-level">{Math.round(zoom * 100)}%</span>
          <Button variant="outline" size="sm" onClick={() => zoomAt(zoom + 0.4)} ariaLabel="Zoom in" leftIcon={<ZoomIn size={14} />}>
            Zoom in
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setZoom(1.2);
              setPan({ x: 0, y: 0 });
            }}
            ariaLabel="Reset map view"
            leftIcon={<Maximize2 size={14} />}
          >
            Reset
          </Button>
        </div>
      </div>

      <p className="sg-network-overview__desc">
        Locator only. Scroll to zoom, drag to pan, click a node to focus that observatory. Sites in
        the same city are spread so labels stay readable.
      </p>

      <div
        ref={wrapperRef}
        className="sg-network-overview__canvas-wrapper"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <svg
          viewBox={`${viewX} ${viewY} ${viewW} ${viewH}`}
          className="sg-network-overview__svg"
          role="img"
          aria-label="Interactive map of weather stations"
        >
          <defs>
            <pattern id="networkGrid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255, 255, 255, 0.045)" strokeWidth="1" />
            </pattern>
            <radialGradient id="selectedGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect width={width} height={height} fill="url(#networkGrid)" />

          {projectedStations.map((p) => {
            const statusColor = getStatusColor(p.station.status);
            return (
              <g
                key={`node-${p.station.station_id}`}
                className={`sg-network-overview__node ${p.isSelected ? 'sg-network-overview__node--selected' : ''}`}
                onClick={() => {
                  if (dragRef.current.moved) return;
                  onSelectStation(p.station);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectStation(p.station);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`Select station ${p.city} ${p.station.station_id}, status ${p.station.status}`}
              >
                {p.isSelected && <circle cx={p.x} cy={p.y} r="26" fill="url(#selectedGlow)" className="sg-network-overview__halo" />}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.isSelected ? 12 : 9}
                  fill="#07111f"
                  stroke={p.isSelected ? '#7dd3fc' : statusColor}
                  strokeWidth={p.isSelected ? 3 : 2.4}
                  className="sg-network-overview__circle"
                />
                <circle cx={p.x} cy={p.y} r={p.isSelected ? 4.8 : 3.4} fill={p.isSelected ? '#7dd3fc' : statusColor} />
                <text
                  x={p.x}
                  y={p.y - 22}
                  textAnchor="middle"
                  className={`sg-network-overview__node-label ${p.isSelected ? 'sg-network-overview__node-label--selected' : ''}`}
                >
                  {p.city}
                </text>
                <text x={p.x} y={p.y + 28} textAnchor="middle" className="sg-network-overview__node-id">
                  {shortId(p.station.station_id)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="sg-network-overview__legend">
        <div className="sg-network-overview__legend-item">
          <span className="sg-network-overview__legend-dot" style={{ background: '#38bdf8', boxShadow: '0 0 6px #38bdf8' }} />
          <span>Selected</span>
        </div>
        <div className="sg-network-overview__legend-item">
          <span className="sg-network-overview__legend-dot" style={{ background: '#10b981' }} />
          <span>Normal</span>
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
