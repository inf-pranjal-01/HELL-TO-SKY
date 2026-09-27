import React from 'react';
import {
  Cpu,
  Wifi,
  Zap,
  Activity,
  Server,
  ArrowRight,
} from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import './PipelineInfoModal.css';

export interface PipelineInfoModalProps {
  isOpen: boolean;
  onClose: () => void;
  edgeStationId?: string;
  isEdgeOnline?: boolean;
  latencyMs?: number | null;
}

export const PipelineInfoModal: React.FC<PipelineInfoModalProps> = ({
  isOpen,
  onClose,
  edgeStationId = 'AWS-CHN-024',
  isEdgeOnline = false,
  latencyMs = null,
}) => {
  const steps = [
    {
      num: '01',
      title: 'Virtual / Physical Sensor Feed',
      icon: <Activity size={20} className="sg-pipeline-step-icon sg-pipeline-step-icon--amber" />,
      desc: 'Raw meteorological readings from saved CSV datasets stream over USB Serial into the physical ESP32 microcontroller (or directly from onboard BMP280/DHT22 sensors).',
      badge: 'USB Serial / I2C / GPIO',
    },
    {
      num: '02',
      title: 'Level 1 Edge AI (On-Device)',
      icon: <Cpu size={20} className="sg-pipeline-step-icon sg-pipeline-step-icon--emerald" />,
      desc: 'The ESP32 executes 5-Tier continuous-time online EWMA statistics, SPRT log-likelihood ratios (LLR), and TinyML Isolation Forest verdicts locally on-device (~184 B SRAM, <1.2ms latency).',
      badge: 'Zero-Leakage Dual Buffer · <1.2ms @ 240MHz',
    },
    {
      num: '03',
      title: 'Wi-Fi Ingestion & REST API',
      icon: <Wifi size={20} className="sg-pipeline-step-icon sg-pipeline-step-icon--cyan" />,
      desc: 'The ESP32 formats canonical ObservationPacket JSON payloads and posts them over Wi-Fi (POST /api/ingest/observation) to the Central Server with idempotency keys.',
      badge: 'POST /api/ingest/observation',
    },
    {
      num: '04',
      title: 'Level 2 Central Consensus & Frontend UI',
      icon: <Server size={20} className="sg-pipeline-step-icon sg-pipeline-step-icon--blue" />,
      desc: 'The backend executes multi-station spatial cross-verification, thermodynamic consistency checking, and streams live results to this Web Dashboard via WebSockets.',
      badge: 'TimescaleDB · WebSocket Live Push',
    },
  ];

  const modalFooter = (
    <div className="sg-pipeline-modal__footer">
      <div className="sg-pipeline-modal__status-info">
        <span className={`sg-pipeline-node-dot ${isEdgeOnline ? 'sg-pipeline-node-dot--online' : 'sg-pipeline-node-dot--standby'}`} />
        <span className="sg-pipeline-node-label">
          Status: {isEdgeOnline ? (
            <>Online (Node: <strong>{edgeStationId}</strong> · {latencyMs !== null ? `${latencyMs}ms latency` : 'Hardware Ingest'})</>
          ) : (
            <>Standby (No physical ESP32 node connected)</>
          )}
        </span>
      </div>
      <Button variant="primary" size="sm" onClick={onClose}>
        Close Architecture Overview
      </Button>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="SkyGuard Edge AI Data Pipeline Architecture"
      size="lg"
      footer={modalFooter}
    >
      <div className="sg-pipeline-modal">
        {/* Architecture Hero Banner */}
        <div className="sg-pipeline-hero">
          <div className="sg-pipeline-hero__header">
            <div className="sg-pipeline-hero__title-box">
              <span className="sg-pipeline-hero__eyebrow">
                <Zap size={14} /> DUAL-TIER HIERARCHICAL EDGE-CENTRAL ARCHITECTURE
              </span>
              <h3>Physical ESP32 Microcontroller → Central TimescaleDB Consensus</h3>
            </div>
            <div className="sg-pipeline-hero__tags">
              <span className="sg-pipeline-tag sg-pipeline-tag--chip">ESP32 DevKit V1 (N4)</span>
              <span className="sg-pipeline-tag sg-pipeline-tag--ram">184 B SRAM Footprint</span>
              <span className="sg-pipeline-tag sg-pipeline-tag--speed">&lt;1.2ms Latency</span>
            </div>
          </div>
          <p className="sg-pipeline-hero__sub">
            SkyGuard deploys a two-tier cooperative anomaly detection pipeline. Level 1 runs causal sequential 
            test statistics on ultra-low-power microcontrollers at the edge, while Level 2 verifies spatial network 
            consensus across 28 automatic weather stations in the cloud.
          </p>
        </div>

        {/* 4-Step Pipeline Flow */}
        <div className="sg-pipeline-flow">
          {steps.map((step, idx) => (
            <div key={step.num} className="sg-pipeline-step-card">
              <div className="sg-pipeline-step-card__top">
                <span className="sg-pipeline-step-card__num">{step.num}</span>
                <div className="sg-pipeline-step-card__icon-wrapper">{step.icon}</div>
                <div className="sg-pipeline-step-card__headings">
                  <h4>{step.title}</h4>
                  <span className="sg-pipeline-step-card__badge">{step.badge}</span>
                </div>
              </div>
              <p className="sg-pipeline-step-card__desc">{step.desc}</p>
              {idx < steps.length - 1 && (
                <div className="sg-pipeline-step-card__connector" aria-hidden="true">
                  <ArrowRight size={16} />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Technical Specification Summary Grid */}
        <div className="sg-pipeline-specs-grid">
          <div className="sg-pipeline-spec-item">
            <span className="sg-pipeline-spec-item__label">Hardware Target</span>
            <strong>ESP32-WROOM-32 (Tensilica Dual-Core @ 240MHz)</strong>
          </div>
          <div className="sg-pipeline-spec-item">
            <span className="sg-pipeline-spec-item__label">Level 1 Causal Engine</span>
            <strong>5-Tier Continuous-Time EWMA + SPRT LLR</strong>
          </div>
          <div className="sg-pipeline-spec-item">
            <span className="sg-pipeline-spec-item__label">Level 2 Spatial Engine</span>
            <strong>Isolation Forest + Spatial Cluster Delta + SHAP</strong>
          </div>
          <div className="sg-pipeline-spec-item">
            <span className="sg-pipeline-spec-item__label">Network Protocol</span>
            <strong>Canonical JSON / HTTP POST & WebSockets</strong>
          </div>
        </div>
      </div>
    </Modal>
  );
};
