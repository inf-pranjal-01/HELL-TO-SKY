import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { API_CONFIG } from '../config/api.config';
import { EdgeInference } from '../types';

export interface EdgeStatusContextType {
  isEdgeOnline: boolean;
  latencyMs: number | null;
  lastEdgeTimestamp: Date | null;
  edgeStationId: string;
  latestEdgeInference: EdgeInference | null;
  isPipelineModalOpen: boolean;
  openPipelineModal: () => void;
  closePipelineModal: () => void;
}

const EdgeStatusContext = createContext<EdgeStatusContextType | undefined>(undefined);

export const EdgeStatusProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isEdgeOnline, setIsEdgeOnline] = useState<boolean>(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [lastEdgeTimestamp, setLastEdgeTimestamp] = useState<Date | null>(null);
  const [edgeStationId, setEdgeStationId] = useState<string>('AWS-CHN-024');
  const [latestEdgeInference, setLatestEdgeInference] = useState<EdgeInference | null>(null);
  const [isPipelineModalOpen, setIsPipelineModalOpen] = useState<boolean>(false);

  const lastSeenRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);

  // Heartbeat check: Dim to standby if no edge telemetry arrived for >15 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      if (lastSeenRef.current > 0 && now - lastSeenRef.current > 15000) {
        setIsEdgeOnline(false);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Real-time WebSocket connection to monitor edge telemetry packets
  useEffect(() => {
    let unmounted = false;
    let reconnectTimeout: number | null = null;

    const connect = () => {
      try {
        const socket = new WebSocket(API_CONFIG.wsUrl);
        wsRef.current = socket;

        socket.onmessage = (event) => {
          if (unmounted) return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'MODE_CHANGE' && data.mode !== 'edge') {
              lastSeenRef.current = 0;
              setIsEdgeOnline(false);
            } else if (data.type === 'EDGE_STATUS') {
              if (data.edge_status && !data.edge_status.connected) {
                lastSeenRef.current = 0;
                setIsEdgeOnline(false);
              } else if (data.edge_status && data.edge_status.connected) {
                const now = Date.now();
                lastSeenRef.current = now;
                setIsEdgeOnline(true);
                if (data.edge_status.station_id) {
                  setEdgeStationId(data.edge_status.station_id);
                }
              }
            } else {
              const isEdgeMessage =
                data.mode === 'edge' ||
                data.source === 'edge' ||
                (data.edge_inference && Object.keys(data.edge_inference).length > 0) ||
                (data.anomaly && data.anomaly.source === 'edge') ||
                (data.anomaly && data.anomaly.edge_inference);

              if (isEdgeMessage) {
                const now = Date.now();
                lastSeenRef.current = now;
                setIsEdgeOnline(true);
                setLastEdgeTimestamp(new Date());

                if (data.station_id) {
                  setEdgeStationId(data.station_id);
                }

                // Compute turnaround latency
                let measuredLatency: number = 12;
                if (data.ingest_time_ms && typeof data.ingest_time_ms === 'number') {
                  const diff = now - data.ingest_time_ms;
                  measuredLatency = diff >= 0 && diff < 5000 ? Math.max(1, diff) : 12;
                } else if (data.edge_inference?.latency_ms) {
                  measuredLatency = data.edge_inference.latency_ms;
                }
                setLatencyMs(measuredLatency);

                if (data.edge_inference) {
                  setLatestEdgeInference(data.edge_inference);
                } else if (data.anomaly?.edge_inference) {
                  setLatestEdgeInference(data.anomaly.edge_inference);
                }
              }
            }
          } catch {
            // Ignore malformed messages
          }
        };

        socket.onclose = () => {
          if (!unmounted) {
            reconnectTimeout = window.setTimeout(connect, 3000);
          }
        };

        socket.onerror = () => {
          try {
            socket.close();
          } catch {
            // ignore
          }
        };
      } catch {
        if (!unmounted) {
          reconnectTimeout = window.setTimeout(connect, 3000);
        }
      }
    };

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const openPipelineModal = useCallback(() => setIsPipelineModalOpen(true), []);
  const closePipelineModal = useCallback(() => setIsPipelineModalOpen(false), []);

  return (
    <EdgeStatusContext.Provider
      value={{
        isEdgeOnline,
        latencyMs,
        lastEdgeTimestamp,
        edgeStationId,
        latestEdgeInference,
        isPipelineModalOpen,
        openPipelineModal,
        closePipelineModal,
      }}
    >
      {children}
    </EdgeStatusContext.Provider>
  );
};

export const useEdgeStatus = (): EdgeStatusContextType => {
  const context = useContext(EdgeStatusContext);
  if (!context) {
    throw new Error('useEdgeStatus must be used within an EdgeStatusProvider');
  }
  return context;
};
