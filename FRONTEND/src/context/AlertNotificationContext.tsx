import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { API_CONFIG } from '../config/api.config';
import { anomalyService } from '../services/anomalyService';

export interface AlertNotificationContextType {
  hasNewAlert: boolean;
  newAlertCount: number;
  clearNewAlerts: () => void;
  recordNewAlert: (anomalyId: string) => void;
}

const AlertNotificationContext = createContext<AlertNotificationContextType | undefined>(undefined);

export const AlertNotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [hasNewAlert, setHasNewAlert] = useState<boolean>(false);
  const [newAlertCount, setNewAlertCount] = useState<number>(0);
  const location = useLocation();

  // Known anomaly IDs set for exact deduplication
  const knownAnomalyIdsRef = useRef<Set<string>>(new Set());
  const isHydratedRef = useRef<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);

  // Clear new alert badge when operator navigates to /alerts
  const clearNewAlerts = useCallback(() => {
    setHasNewAlert(false);
    setNewAlertCount(0);
  }, []);

  const recordNewAlert = useCallback((anomalyId: string) => {
    if (!anomalyId || knownAnomalyIdsRef.current.has(anomalyId)) return;
    knownAnomalyIdsRef.current.add(anomalyId);
    if (isHydratedRef.current && location.pathname !== '/alerts') {
      setHasNewAlert(true);
      setNewAlertCount((prev) => prev + 1);
    }
  }, [location.pathname]);

  // Initial historical baseline hydration (prevents old anomalies from triggering new alert badge)
  useEffect(() => {
    let isMounted = true;

    async function hydrateHistoricalAnomalies() {
      try {
        const recent = await anomalyService.getRecentAnomalies(undefined, 100);
        if (!isMounted) return;
        recent.forEach((a) => {
          const key = a.anomaly_id || `${a.station_id}-${a.timestamp}-${a.type}`;
          knownAnomalyIdsRef.current.add(key);
        });
      } catch {
        // Fallback: silent degradation
      } finally {
        if (isMounted) {
          isHydratedRef.current = true;
        }
      }
    }

    hydrateHistoricalAnomalies();

    return () => {
      isMounted = false;
    };
  }, []);

  // Automatically clear notification indicator when operator visits /alerts
  useEffect(() => {
    if (location.pathname === '/alerts') {
      clearNewAlerts();
    }
  }, [location.pathname, clearNewAlerts]);

  // Global WebSocket listener for real-time ANOMALY_EVENT
  useEffect(() => {
    let isUnmounted = false;

    function connectWs() {
      if (isUnmounted) return;
      try {
        const socket = new WebSocket(API_CONFIG.wsUrl);
        wsRef.current = socket;

        socket.onopen = () => {
          if (isUnmounted) {
            socket.close();
            return;
          }
          if (pingIntervalRef.current !== null) {
            clearInterval(pingIntervalRef.current);
          }
          pingIntervalRef.current = window.setInterval(() => {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send('ping');
            }
          }, 15000);
        };

        socket.onmessage = (event) => {
          if (isUnmounted) return;
          try {
            const data = JSON.parse(event.data);

            if (data.type === 'ANOMALY_EVENT' || data.type === 'ANOMALY_DETECTED') {
              const anom = data.anomaly;
              if (anom) {
                const key = anom.anomaly_id || `${anom.station_id}-${anom.timestamp}-${anom.type}`;
                if (!knownAnomalyIdsRef.current.has(key)) {
                  knownAnomalyIdsRef.current.add(key);
                  if (isHydratedRef.current) {
                    setHasNewAlert(true);
                    setNewAlertCount((prev) => prev + 1);
                  }
                }
              }
            } else if (data.type === 'TELEMETRY_TICK' && data.verdict?.is_anomaly) {
              const key = `tick-${data.station_id}-${data.timestamp}`;
              if (!knownAnomalyIdsRef.current.has(key)) {
                knownAnomalyIdsRef.current.add(key);
                if (isHydratedRef.current) {
                  setHasNewAlert(true);
                  setNewAlertCount((prev) => prev + 1);
                }
              }
            } else if (data.type === 'HISTORY_PURGED') {
              knownAnomalyIdsRef.current.clear();
              setHasNewAlert(false);
              setNewAlertCount(0);
            }
          } catch {
            // Silently ignore heartbeat / non-JSON
          }
        };

        socket.onclose = () => {
          if (pingIntervalRef.current !== null) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
          }
          if (!isUnmounted) {
            reconnectTimeoutRef.current = window.setTimeout(connectWs, 3000);
          }
        };

        socket.onerror = () => {
          socket.close();
        };
      } catch {
        if (!isUnmounted) {
          reconnectTimeoutRef.current = window.setTimeout(connectWs, 3000);
        }
      }
    }

    connectWs();

    return () => {
      isUnmounted = true;
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current !== null) {
        clearInterval(pingIntervalRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return (
    <AlertNotificationContext.Provider
      value={{
        hasNewAlert,
        newAlertCount,
        clearNewAlerts,
        recordNewAlert,
      }}
    >
      {children}
    </AlertNotificationContext.Provider>
  );
};

export const useAlertNotification = (): AlertNotificationContextType => {
  const context = useContext(AlertNotificationContext);
  if (!context) {
    throw new Error('useAlertNotification must be used within an AlertNotificationProvider');
  }
  return context;
};
