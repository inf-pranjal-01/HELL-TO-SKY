import React from 'react';
import { Network, RefreshCw, Sparkles } from 'lucide-react';
import { Station, SpatialDemoScenario } from '../../types';
import { StatusBadge } from '../common/StatusBadge';
import { Button } from '../common/Button';
import './StationNetworkHeader.css';

export interface StationNetworkHeaderProps {
  selectedStation: Station | null;
  scenario: SpatialDemoScenario;
  onScenarioChange: (scenario: SpatialDemoScenario) => void;
  onRefresh: () => void;
  isLoading?: boolean;
}

export const StationNetworkHeader: React.FC<StationNetworkHeaderProps> = ({
  selectedStation,
  scenario,
  onScenarioChange,
  onRefresh,
  isLoading = false,
}) => {
  return (
    <header className="sg-station-header">
      <div className="sg-station-header__title-area">
        <div className="sg-station-header__title-row">
          <Network size={26} className="text-accent" aria-hidden="true" />
          <h1 className="sg-station-header__title">Station Network & Spatial Validation</h1>
        </div>
        <p className="sg-station-header__subtitle">
          Geospatial proximity mapping, cross-station telemetry comparisons, and regional
          consistency analysis to isolate localized sensor anomalies.
        </p>
      </div>

      <div className="sg-station-header__controls">
        {/* Selected Station Status Badge */}
        {selectedStation && (
          <div className="sg-station-header__status-group">
            <span className="sg-station-header__status-label">Network Status:</span>
            <StatusBadge
              status={
                selectedStation.status === 'NORMAL'
                  ? 'optimal'
                  : selectedStation.status === 'WARNING'
                  ? 'moderate'
                  : selectedStation.status === 'CRITICAL'
                  ? 'critical'
                  : 'offline'
              }
              label={selectedStation.status}
              size="sm"
            />
          </div>
        )}

        {/* [SIH DEMO] Scenario Switcher */}
        <div
          className="sg-station-header__scenario-selector"
          role="group"
          aria-label="Spatial demonstration scenario selector"
        >
          <div className="sg-station-header__scenario-tag">
            <Sparkles size={12} className="text-accent" aria-hidden="true" />
            <span>SIH DEMO</span>
          </div>
          <button
            type="button"
            className={`sg-station-header__scenario-btn ${
              scenario === 'localized_deviation' ? 'sg-station-header__scenario-btn--active' : ''
            }`}
            onClick={() => onScenarioChange('localized_deviation')}
            aria-pressed={scenario === 'localized_deviation'}
            title="Simulate localized anomaly: Selected station diverges from neighbors"
          >
            Localized Deviation
          </button>
          <button
            type="button"
            className={`sg-station-header__scenario-btn ${
              scenario === 'regional_consistency' ? 'sg-station-header__scenario-btn--active' : ''
            }`}
            onClick={() => onScenarioChange('regional_consistency')}
            aria-pressed={scenario === 'regional_consistency'}
            title="Simulate regional consistency: All stations agree within nominal bounds"
          >
            Regional Consistency
          </button>
        </div>

        {/* Refresh button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          isLoading={isLoading}
          leftIcon={<RefreshCw size={14} />}
          ariaLabel="Refresh station network data"
        >
          Refresh
        </Button>
      </div>
    </header>
  );
};
