import React, { useEffect, useMemo, useState } from 'react';
import { BrainCircuit, CheckCircle2, ChevronRight, Gauge, ShieldAlert, Sparkles } from 'lucide-react';
import { RecentAnomalyItem, AnomalyExplanation } from '../../types';
import { anomalyService } from '../../services/anomalyService';
import { Card } from '../common/Card';
import { Skeleton } from '../common/Skeleton';
import { SuggestedValues } from '../common/SuggestedValues';
import { suggestedFromRecord, formatSuggestedList } from '../../utils/suggestedValues';
import './ExplainabilityCommandCenter.css';

export interface ExplainabilityCommandCenterProps { anomalies: RecentAnomalyItem[]; isLoading?: boolean; className?: string; }

const displayParameter = (value: string) => value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
function explainFeature(name: string): string {
  const value = name.toLowerCase();
  const sensor = value.includes('temp') ? 'temperature' : value.includes('pressure') ? 'pressure' : value.includes('humidity') ? 'humidity' : 'weather pattern';
  if (value.includes('roc') || value.includes('change')) return `A rapid ${sensor} change disagreed with the previous hourly reading.`;
  if (value.includes('deviation')) return `The ${sensor} reading departed from this station's normal baseline.`;
  if (value.includes('rolling') || value.includes('mean') || value.includes('std')) return `The ${sensor} pattern differed from its recent stable behaviour.`;
  if (value.includes('hour') || value.includes('doy')) return `The ${sensor} reading was unusual for this time of day or season.`;
  return `${displayParameter(name)} added evidence to the anomaly decision.`;
}

export const ExplainabilityCommandCenter: React.FC<ExplainabilityCommandCenterProps> = ({ anomalies, isLoading = false, className = '' }) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<AnomalyExplanation | null>(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = useMemo(() => anomalies.find((anomaly) => anomaly.anomaly_id === selectedId) ?? anomalies[0] ?? null, [anomalies, selectedId]);

  useEffect(() => { if (selected && selected.anomaly_id !== selectedId) setSelectedId(selected.anomaly_id); }, [selected, selectedId]);
  useEffect(() => {
    if (!selected) { setExplanation(null); return; }
    let active = true;
    setLoadingExplanation(true); setError(null);
    anomalyService.getAnomalyExplanation(selected.anomaly_id)
      .then((value) => { if (active) setExplanation(value); })
      .catch(() => { if (active) setError('Explanation is not yet available for this incident.'); })
      .finally(() => { if (active) setLoadingExplanation(false); });
    return () => { active = false; };
  }, [selected?.anomaly_id]);

  if (isLoading) return <Card variant="glass" className={`sg-explain-card ${className}`}><Skeleton width="260px" height="1.2rem" /><Skeleton width="100%" height="220px" style={{ marginTop: '1rem' }} /></Card>;
  if (!selected) return <Card variant="glass" className={`sg-explain-card ${className}`}><div className="sg-explain-card__empty"><CheckCircle2 size={24} /><strong>Decision X-Ray is standing by</strong><span>When an anomaly is detected, SkyGuard will show the evidence behind its decision here.</span></div></Card>;

  const features = [...(explanation?.features ?? [])].sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact)).slice(0, 3);
  const top = features[0];
  const implicated = explanation?.affected_parameters?.length ? explanation.affected_parameters : selected.affected_parameters ?? [];
  const observed = suggestedFromRecord(explanation?.observed_values ?? selected.observed_values);
  const suggested = suggestedFromRecord(explanation?.suggested_values ?? selected.suggested_values);
  const score = explanation?.anomaly_score_pct ?? selected.anomaly_score_pct;

  return <Card variant="glass" className={`sg-explain-card ${className}`} role="region" aria-label="Plain-language anomaly explanation">
    <div className="sg-explain-card__header"><div><span className="sg-explain-card__eyebrow"><BrainCircuit size={15} /> EXPLAINABLE AI</span><h3>Decision X-Ray: why SkyGuard raised this alert</h3><p>Plain language evidence from the live model and deterministic safety rules.</p></div><span className="sg-explain-card__score"><Gauge size={16} /> {Math.round(score)}% evidence strength</span></div>
    <div className="sg-explain-card__selector" aria-label="Choose an anomaly to explain">{anomalies.slice(0, 5).map((anomaly) => <button key={anomaly.anomaly_id} type="button" onClick={() => setSelectedId(anomaly.anomaly_id)} className={anomaly.anomaly_id === selected.anomaly_id ? 'is-active' : ''}>{anomaly.type.replace(/_/g, ' ')} <span>{new Date(anomaly.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></button>)}</div>
    {loadingExplanation ? <Skeleton width="100%" height="180px" /> : error ? <p className="sg-explain-card__error">{error}</p> : <>
      <div className="sg-explain-card__hero"><div className="sg-explain-card__driver"><Sparkles size={18} /><div><span>Strongest evidence</span><strong>{top ? displayParameter(top.name) : 'Rule evidence (no model explanation available)'}</strong><p>{top ? explainFeature(top.name) : 'Deterministic rules detected a pattern that warrants investigation.'}</p></div></div><div className="sg-explain-card__split">
        <div>
          <span>Model evidence · 60% weight</span>
          <strong>
            {explanation?.model_confidence_pct == null
              ? (explanation?.model_status === 'UNAVAILABLE_WARMUP' ? 'Warming up — insufficient history' : 'Unavailable')
              : `${Math.round(explanation.model_confidence_pct)}% evidence strength`}
          </strong>
        </div>
        <div>
          <span>Rule evidence · 40% weight</span>
          <strong>{explanation?.rule_confidence_pct == null ? 'n.a.' : `${Math.round(explanation.rule_confidence_pct)}%`}</strong>
        </div>
        {(explanation?.decision_basis || selected?.decision_basis) && (
          <div style={{gridColumn:'1/-1'}}>
            <span>Decision basis</span>
            <strong style={{fontSize:'0.75rem', letterSpacing:'0.05em'}}>
              {(explanation?.decision_basis || selected?.decision_basis || '').replace(/_/g, ' ')}
            </strong>
          </div>
        )}
      </div></div>
      <div className="sg-explain-card__body">
        <section>
          <h4><ShieldAlert size={15} /> Station Context</h4>
          {(() => {
            const regime = explanation?.regime || selected?.regime;
            const regimeLabels: Record<string,string> = {
              DAYTIME_WARMING: 'Normal daytime warming pattern — environmental drift is expected.',
              NIGHTTIME_COOLING: 'Normal nighttime cooling pattern.',
              STABLE: 'Stable conditions with low environmental variability.',
              HIGH_HEAT: 'High heat conditions — elevated temperature anomaly risk.',
              HIGH_HUMIDITY: 'High humidity conditions.',
              PRESSURE_SHIFT: 'Significant pressure change — possible incoming weather system.',
              HIGH_VOLATILITY: 'High variability conditions — detection thresholds may be less reliable.',
              REGIME_TRANSITION: 'Environmental regime transition detected — false positives possible.',
              UNKNOWN_INSUFFICIENT_DATA: 'Context unavailable — station still in warm-up period (insufficient history).',
              UNKNOWN_CONTEXT_FAILURE: 'Context classification failed — check system logs.',
            };
            return <>
              <p className="sg-explain-card__muted">Regime: <strong>{regime ? regime.replace(/_/g, ' ') : 'Unknown'}</strong></p>
              {regime && regimeLabels[regime] && <p className="sg-explain-card__muted" style={{fontSize:'0.78rem'}}>{regimeLabels[regime]}</p>}
            </>;
          })()}
        </section>
        <section>
          <h4><ShieldAlert size={15} /> Network Evidence</h4>
          {(() => {
            const corr = explanation?.network_corroboration || selected?.network_corroboration;
            if (!corr) return <p className="sg-explain-card__muted">Network analysis not performed (no anomaly detected).</p>;
            const labels: Record<string,string> = {
              REGIONAL: 'Nearby stations show similar changes — regional environmental event possible. Sensor should not be blamed immediately.',
              LOCALIZED: 'Nearby stations are within normal range — pattern appears localized. Sensor or telemetry investigation recommended.',
              INSUFFICIENT_CORROBORATION: 'Insufficient peer data for network analysis. Cannot determine if event is localized or regional.',
            };
            return <>
              <p className="sg-explain-card__muted"><strong>{corr.replace(/_/g, ' ')}</strong></p>
              <p className="sg-explain-card__muted">{labels[corr] || 'Network state unknown.'}</p>
            </>;
          })()}
        </section>
        <section>
          <h4><ShieldAlert size={15} /> {features.length ? 'Model evidence' : 'Rule evidence'}</h4>
          {features.length ? (
            <ol>{features.map((feature) => <li key={feature.name}><span className={feature.impact >= 0 ? 'risk' : 'normal'}>{feature.impact >= 0 ? 'Raises risk' : 'Offsets risk'}</span><div><strong>{displayParameter(feature.name)}</strong><p>{explainFeature(feature.name)}</p></div><b>{Math.round(Math.abs(feature.impact) * 100)}%</b></li>)}</ol>
          ) : (
            <p className="sg-explain-card__muted">Model explanation unavailable — this event was assessed by deterministic safety rules only. Rule evidence is not a probability estimate.</p>
          )}
        </section>
        <section>
          <h4><ChevronRight size={15} /> Operator-ready conclusion</h4>
          <p className="sg-explain-card__conclusion">{implicated.length ? `Suggested investigation target: ${implicated.map(displayParameter).join(', ')}. This is an indication, not a confirmed diagnosis.` : 'The detector found a station-level pattern that requires review.'}</p>
          {observed.length > 0 && <p><strong>Observed:</strong> {formatSuggestedList(observed)}</p>}
          <SuggestedValues items={suggested} emptyLabel="Suggested replacement becomes available after the baseline warm-up." />
          <p className="sg-explain-card__action"><CheckCircle2 size={15} /> Suggested action: Keep raw telemetry visible; use the suggested reading for downstream analysis while investigating.</p>
        </section>
      </div>
    </>}
  </Card>;
};
