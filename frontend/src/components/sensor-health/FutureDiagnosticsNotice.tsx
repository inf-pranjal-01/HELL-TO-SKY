import React from 'react';
import { Cpu, CheckCircle2, AlertTriangle, AlertOctagon } from 'lucide-react';
import { SecularCalibrationAudit } from '../../types';
import './FutureDiagnosticsNotice.css';

export interface FutureDiagnosticsNoticeProps {
  audit?: SecularCalibrationAudit | null;
  className?: string;
}

export const FutureDiagnosticsNotice: React.FC<FutureDiagnosticsNoticeProps> = ({
  audit = null,
  className = '',
}) => {
  if (audit) {
    const isAdvisory = audit.status === 'RECALIBRATION_ADVISORY';
    const isCritical = audit.status === 'CRITICAL_RECALIBRATION_REQUIRED';

    return (
      <aside
        className={`sg-future-notice sg-future-notice--active-audit ${
          isCritical
            ? 'sg-future-notice--critical'
            : isAdvisory
            ? 'sg-future-notice--advisory'
            : 'sg-future-notice--nominal'
        } ${className}`}
        role="region"
        aria-label="WMO-No. 8 Supervisory Diurnal Drift Watchdog"
      >
        <div className="sg-future-notice__left">
          <div className="sg-future-notice__icon-box">
            {isCritical ? (
              <AlertOctagon size={18} className="text-critical" aria-hidden="true" />
            ) : isAdvisory ? (
              <AlertTriangle size={18} className="text-warning" aria-hidden="true" />
            ) : (
              <CheckCircle2 size={18} className="text-optimal" aria-hidden="true" />
            )}
          </div>
          <div className="sg-future-notice__content">
            <div className="sg-future-notice__header-row">
              <span className="sg-future-notice__title">
                WMO-No. 8 Supervisory Diurnal Drift Auditor (Active Network Invariant)
              </span>
              <span className="sg-future-notice__badge">
                {audit.wmo_compliance || 'WMO-No. 8 Compliant'}
              </span>
            </div>
            <p className="sg-future-notice__text">
              24-hour moving diurnal harmonic integration cancels primary solar forcing oscillations (S₁, S₂).
              Supervisory auditor evaluates geopotential elevation-compensated pairwise cluster differences:
              Secular Divergence: <strong>{audit.secular_divergence_c > 0 ? `+${audit.secular_divergence_c}` : audit.secular_divergence_c}°C</strong>,
              Peer Spread: <strong>±{audit.peer_coherence_c}°C</strong>.
            </p>
          </div>
        </div>
        <div className="sg-future-notice__right">
          <span className="sg-future-notice__tag">
            ASYNCHRONOUS DAILY AUDITOR — ZERO INLINE FALSE ALARMS
          </span>
        </div>
      </aside>
    );
  }

  return (
    <aside
      className={`sg-future-notice ${className}`}
      role="note"
      aria-label="Future backend capabilities notice"
    >
      <div className="sg-future-notice__left">
        <Cpu size={16} className="text-muted" aria-hidden="true" />
        <p className="sg-future-notice__text">
          Advanced Hardware Diagnostics (Battery voltage, solar power, RF signal RSSI, predictive
          degradation) — Future backend telemetry capabilities.
        </p>
      </div>
      <span className="sg-future-notice__tag">
        PLANNED CAPABILITY — NOT IN CURRENT API CONTRACT
      </span>
    </aside>
  );
};
