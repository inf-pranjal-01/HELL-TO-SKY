import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Station } from '../types';
import { stationService } from '../services/stationService';
import { formatUserErrorMessage } from '../services/apiError';

export interface StationContextType {
  stations: Station[];
  selectedStation: Station | null;
  setSelectedStation: (station: Station) => void;
  selectStationById: (stationId: string) => void;
  isLoading: boolean;
  error: string | null;
  refreshStations: () => Promise<void>;
}

const StationContext = createContext<StationContextType | undefined>(undefined);

export const StationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStation, setSelectedStationState] = useState<Station | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStations = useCallback(async (isInitial = false) => {
    if (isInitial) {
      setIsLoading(true);
    }
    setError(null);
    try {
      // [API: GET /api/stations — INTEGRATED]
      const data = await stationService.getAllStations();
      setStations(data);
      setSelectedStationState((prev) => {
        if (!prev) {
          return data.length > 0 ? data[0] : null;
        }
        const exists = data.find((s) => s.station_id === prev.station_id);
        return exists || (data.length > 0 ? data[0] : null);
      });
    } catch (err) {
      setError(formatUserErrorMessage(err, 'Failed to load meteorological stations.'));
    } finally {
      if (isInitial) {
        setIsLoading(false);
      }
    }
  }, []);

  const setSelectedStation = useCallback((station: Station) => {
    setSelectedStationState(station);
    // Background refresh to guarantee the selected station has fresh status
    fetchStations(false);
  }, [fetchStations]);

  const selectStationById = useCallback((stationId: string) => {
    setStations((currentStations) => {
      const target = currentStations.find((s) => s.station_id === stationId);
      if (target) {
        setSelectedStationState(target);
      }
      return currentStations;
    });
  }, []);

  useEffect(() => {
    fetchStations(true);
    const interval = setInterval(() => {
      fetchStations(false);
    }, 20000); // 20s background status polling

    const handleRefreshEvent = () => {
      fetchStations(false);
    };
    const handleSelectStationEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{ stationId: string }>;
      if (customEvent.detail?.stationId) {
        selectStationById(customEvent.detail.stationId);
      }
    };
    window.addEventListener('sg-refresh-stations', handleRefreshEvent);
    window.addEventListener('sg-select-station', handleSelectStationEvent);

    return () => {
      clearInterval(interval);
      window.removeEventListener('sg-refresh-stations', handleRefreshEvent);
      window.removeEventListener('sg-select-station', handleSelectStationEvent);
    };
  }, [fetchStations, selectStationById]);

  return (
    <StationContext.Provider
      value={{
        stations,
        selectedStation,
        setSelectedStation,
        selectStationById,
        isLoading,
        error,
        refreshStations: () => fetchStations(false),
      }}
    >
      {children}
    </StationContext.Provider>
  );
};

export const useStation = (): StationContextType => {
  const context = useContext(StationContext);
  if (!context) {
    throw new Error('useStation must be used within a StationProvider');
  }
  return context;
};
