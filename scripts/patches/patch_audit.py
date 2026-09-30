
import re, sys, os
ROOT = os.path.dirname(os.path.abspath(__file__))
results = {}
def patch(filepath, old, new, label):
    full = os.path.join(ROOT, filepath)
    with open(full, 'r', encoding='utf-8') as f:
        text = f.read()
    if old in text:
        text = text.replace(old, new, 1)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(text)
        results[label] = 'OK'
    else:
        results[label] = 'NOT FOUND'
patch(
    'FRONTEND/src/components/alerts/AnomalyDetailModal.tsx',
    '<h4 className="sg-anomaly-modal__section-title">Root Cause Determination</h4>',
    '<h4 className="sg-anomaly-modal__section-title">Anomaly Indication</h4>',
    'UI-Modal: Root Cause Determination → Anomaly Indication'
)
patch(
    'FRONTEND/src/components/alerts/AnomalyDetailModal.tsx',
    '<h4 className="sg-anomaly-modal__section-title">Suggested Replacement Reading</h4>',
    '<h4 className="sg-anomaly-modal__section-title">Estimated Replacement (Temporal Baseline — Not a Correction)</h4>',
    'UI-Modal: Suggested Replacement → Estimated Replacement'
)
patch(
    'FRONTEND/src/components/alerts/AnomalyDetailModal.tsx',
    '{Math.round(anomaly.anomaly_score_pct)}% SCORE',
    'Evidence Strength: {Math.round(anomaly.anomaly_score_pct)}%',
    'UI-Modal: Score → Evidence Strength'
)
patch(
    'FRONTEND/src/components/alerts/LatestAnomalyBanner.tsx',
    '<span className="sg-latest-banner__block-label">Root Cause Determination</span>',
    '<span className="sg-latest-banner__block-label">Anomaly Indication</span>',
    'UI-Banner: Root Cause Determination → Anomaly Indication'
)
patch(
    'FRONTEND/src/components/alerts/LatestAnomalyBanner.tsx',
    'Active Anomaly: {latestAnomaly.type.replace(\'_\', \' \')}',
    'Anomaly Detected: {latestAnomaly.type.replace(\'_\', \' \')}',
    'UI-Banner: Active Anomaly → Anomaly Detected'
)
patch(
    'FRONTEND/src/components/alerts/LatestAnomalyBanner.tsx',
    'Score: {Math.round(latestAnomaly.anomaly_score_pct)}%',
    'Evidence Strength: {Math.round(latestAnomaly.anomaly_score_pct)}%',
    'UI-Banner: Score → Evidence Strength'
)
patch(
    'FRONTEND/src/components/alerts/RecentAnomaliesList.tsx',
    '<th scope="col">Root Cause</th>',
    '<th scope="col">Anomaly Indication</th>',
    'UI-Recent: Root Cause column → Anomaly Indication'
)
patch(
    'FRONTEND/src/components/alerts/RecentAnomaliesList.tsx',
    '{anom.root_cause}',
    '{anom.root_cause}',
    'UI-Recent: Root Cause content (no-op — header already changed)'
)
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    '{Math.round(score)}% confidence',
    '{Math.round(score)}% evidence strength',
    'UI-Explain: confidence → evidence strength'
)
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    "'Rule-based anomaly confirmation'",
    "'Rule evidence (no model explanation available)'",
    'UI-Explain: Rule-based anomaly confirmation → Rule evidence'
)
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    "'The deterministic safety rules confirmed an unusual sensor pattern.'",
    "'Deterministic rules detected a pattern that warrants investigation.'",
    'UI-Explain: confirmed → warrants investigation'
)
old_section_header = 
new_section_header = 
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    old_section_header,
    new_section_header,
    'UI-Explain: conditional model/rule section header'
)
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    '`${implicated.map(displayParameter).join(\', \')} is the most likely affected sensor channel.`',
    '`Suggested investigation target: ${implicated.map(displayParameter).join(\', \')}. This is an indication, not a confirmed diagnosis.`',
    'UI-Explain: sensor channel claim → suggestion language'
)
old_corroborate = 
new_corroborate = 
patch(
    'model/detect.py',
    old_corroborate,
    new_corroborate,
    'Backend: _corroborate_network double-call fix + documentation'
)
old_network_state = 
new_network_state = 
patch(
    'model/detect.py',
    old_network_state,
    new_network_state,
    'Backend: network_state=None when not anomalous'
)
old_regime = 
new_regime = 
patch(
    'model/detect.py',
    old_regime,
    new_regime,
    'Backend: 9-state regime classifier'
)
old_score_reading_def = 
new_score_reading_def = 
patch(
    'model/detect.py',
    old_score_reading_def,
    new_score_reading_def,
    'Backend: _classify_regime 9-state function inserted'
)
old_main_import_end = 
new_main_import_end = 
patch(
    'main.py',
    old_main_import_end,
    new_main_import_end,
    'Backend: decision_basis + model_status helpers in main.py'
)
old_latest_return = 
new_latest_return = 
patch(
    'main.py',
    old_latest_return,
    new_latest_return,
    'API: decision_basis + model_status in /anomalies/latest'
)
old_explain_return = 
new_explain_return = 
patch(
    'main.py',
    old_explain_return,
    new_explain_return,
    'API: decision_basis + model_status in /explain/{id}'
)
old_types = 
new_types = 
patch(
    'FRONTEND/src/types/index.ts',
    old_types,
    new_types,
    'Types: decision_basis + model_status on LatestAnomaly'
)
old_explain_type = 
new_explain_type = 
patch(
    'FRONTEND/src/types/index.ts',
    old_explain_type,
    new_explain_type,
    'Types: decision_basis + model_status on AnomalyExplanation'
)
old_model_split = 
new_model_split = 
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    old_model_split,
    new_model_split,
    'UI-Explain: decision_basis badge + model status label'
)
old_corr_text = 
new_corr_text = 
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    old_corr_text,
    new_corr_text,
    'UI-Explain: human-readable network corroboration text'
)
old_regime_text = 
new_regime_text = 
patch(
    'FRONTEND/src/components/analytics/ExplainabilityCommandCenter.tsx',
    old_regime_text,
    new_regime_text,
    'UI-Explain: regime with human-readable description'
)
print("\n=== Bug Audit Patch Report ===")
ok = [k for k, v in results.items() if v == 'OK']
fail = [k for k, v in results.items() if v != 'OK']
print(f"\nApplied ({len(ok)}):")
for k in ok:
    print(f"  OK: {k}")
if fail:
    print(f"\nNot found ({len(fail)}):")
    for k in fail:
        print(f"  MISS: {k}")
else:
    print("\nAll patches applied successfully.")
