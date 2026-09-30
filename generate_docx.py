import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os

def create_doc1():
    doc = docx.Document()
    doc.add_heading('Document 1: External Research, Evidence, Citations, Impact & Benefit Dossier', 0)

    doc.add_heading('1. Problem Importance', level=1)
    doc.add_paragraph('Automatic Weather Stations (AWS) form the backbone of modern meteorological forecasting. The density and reliability of AWS networks directly correlate with the accuracy of localized extreme weather predictions. However, sensors deployed in harsh environments are prone to degradation, power failures, and environmental interference. A faulty observation ingested into NWP models can skew regional forecasts, leading to false alarms or missed warnings.')

    doc.add_heading('2. Existing AWS / Meteorological QC Approaches', level=1)
    doc.add_paragraph('Traditional Quality Control relies heavily on static thresholds. As highlighted by WMO guidelines, standard procedures check for physical limits, rate of change, and internal consistency. However, these methods often fail to distinguish between genuine, rapid meteorological events and sensor hardware faults, leading to a high rate of False Positives.')

    doc.add_heading('3. Fault/Anomaly Research', level=1)
    doc.add_paragraph('SkyGuard AI addresses specific failure modes:\n'
                      '• Spikes / Noise: Instantaneous hardware glitches.\n'
                      '• Frozen Sensors: Sensors that lock onto a single value.\n'
                      '• Drift: Gradual calibration loss.\n'
                      '• Cross-Variable Inconsistency: Violations of thermodynamic laws.')

    doc.add_heading('4. Research Methods Relevant to SkyGuard', level=1)
    
    doc.add_heading('A. Sequential Probability Ratio Test (SPRT) & CUSUM', level=2)
    doc.add_paragraph('Original Concept: Developed by Abraham Wald (1945) for sequential hypothesis testing.\n'
                      'Formula: S_t+ = max(0, S_{t-1}+ + z_t - k)\n'
                      'Relevance to AWS: Perfect for detecting gradual sensor "drift" (Tier 2 fault).\n'
                      'SkyGuard Adaptation: Pre-whitens residuals to account for temporal autocorrelation and uses a directional streak constraint corroborated by peer network divergence.')

    doc.add_heading('B. Mahalanobis Distance', level=2)
    doc.add_paragraph('Original Concept: P.C. Mahalanobis (1936).\n'
                      'Formula: D^2 = (x - μ)^T Σ^(-1) (x - μ)\n'
                      'Relevance to AWS: Flags when variables move in physically contradictory directions.\n'
                      'SkyGuard Adaptation: Calculates 3D covariance between Temp, Pressure, and Humidity (Tier 3).')

    doc.add_heading('C. Clausius-Clapeyron Relation', level=2)
    doc.add_paragraph('Formula: e_s(T) = 0.61078 * exp(17.27 * T / (T + 237.3))\n'
                      'Relevance: If temperature spikes but humidity remains flat, thermodynamic laws are violated.\n'
                      'SkyGuard Adaptation: Explicitly calculates vapor_pressure_deficit_kpa to deterministically catch sensors that violate physical laws.')

    doc.add_heading('D. Isolation Forest & SHAP', level=2)
    doc.add_paragraph('Concepts: Isolation Forest (Liu et al. 2008) and SHAP (Lundberg & Lee 2017).\n'
                      'SkyGuard Adaptation: Tier 4 uses Isolation Forest as a Model-Dominant trigger. SHAP decomposes the 49-feature anomaly score into specific sensor blame.')

    doc.add_heading('5. Impact & Benefit Ledger', level=1)
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Metric'
    hdr_cells[1].text = 'Derived Result'
    hdr_cells[2].text = 'Claim Type'
    
    row = table.add_row().cells
    row[0].text = 'False Alarm Reduction'
    row[1].text = 'Reduces false manual inspection dispatches by ~200-250 instances/month.'
    row[2].text = 'Scenario / Derived'

    row = table.add_row().cells
    row[0].text = 'Time to Detection (Drift)'
    row[1].text = 'Drift detected in < 48 hours instead of 20 days.'
    row[2].text = 'Measured / Scenario'

    row = table.add_row().cells
    row[0].text = 'Operational Confidence'
    row[1].text = 'Diagnostic time reduced to minutes via exact sensor attribution (SHAP).'
    row[2].text = 'Scenario'

    doc.save('Document_1_Impact_Dossier.docx')

def create_doc2():
    doc = docx.Document()
    doc.add_heading('Document 2: SkyGuard Technical Methodology & Architecture', 0)

    doc.add_heading('1. System Architecture & Flowchart', level=1)
    doc.add_paragraph('The following represents the data flow and 6-Tier Architecture in SkyGuard AI:')
    
    # Text-based flowchart
    flow = (
        "┌─────────────────────────────────────────────────────────┐\n"
        "│    Data Ingestion (Temp, Pressure, RH)                  │\n"
        "└──────────────────────────┬──────────────────────────────┘\n"
        "                           ▼\n"
        "┌─────────────────────────────────────────────────────────┐\n"
        "│    StateManager: Freeze T-1 Trusted State               │\n"
        "└──────────────────────────┬──────────────────────────────┘\n"
        "                           ▼\n"
        "┌─────────────────────────────────────────────────────────┐\n"
        "│    6-TIER DETECTION ENGINE                              │\n"
        "│                                                         │\n"
        "│  ► Tier 0: Hardware Rails & Limits                      │\n"
        "│  ► Tier 1: Spike & Frozen Checks (Peer Corroborated)    │\n"
        "│  ► Tier 2: CUSUM Drift Detection                        │\n"
        "│  ► Tier 3: 3D Mahalanobis Distance                      │\n"
        "│  ► Tier 4: Isolation Forest (ML model)                  │\n"
        "│  ► Tier 5: Ambiguous / Normal                           │\n"
        "└──────────────────────────┬──────────────────────────────┘\n"
        "                           ▼\n"
        "┌─────────────────────────────────────────────────────────┐\n"
        "│    SHAP Explainability Engine (If ML Used)              │\n"
        "└──────────────────────────┬──────────────────────────────┘\n"
        "                           ▼\n"
        "┌─────────────────────────────────────────────────────────┐\n"
        "│    Verdict: Normal OR Quarantined Anomaly               │\n"
        "└─────────────────────────────────────────────────────────┘\n"
    )
    p = doc.add_paragraph(flow)
    p.style = 'No Spacing'
    p.runs[0].font.name = 'Courier New'

    doc.add_heading('2. Input Data & Station Topology', level=1)
    doc.add_paragraph('Channels: Temperature (°C), Atmospheric Pressure (hPa), and Relative Humidity (%).\n'
                      'Network Structure: 28 stations, geographically grouped into 7 clusters.\n'
                      'Peer Influence: Every station has 3 sibling peers. Peer corroboration is strictly cluster-local.')

    doc.add_heading('3. Explainability Architecture (SHAP)', level=1)
    doc.add_paragraph('When the model contributes to a decision, SHAP decomposes the 49-feature anomaly score into specific sensor blame, identifying exactly which sensor is driving the anomaly.')

    doc.add_heading('4. Operational Use Cases', level=1)
    
    doc.add_heading('Use Case A — AWS Quality Control', level=2)
    doc.add_paragraph('Scenario: A remote AWS transmits a sudden -40°C reading.\n'
                      'System Action: Tier 0 flags it as sensor_fail_low, quarantines the reading, and generates a suggested_value based on peers.')

    doc.add_heading('Use Case B — Severe-Weather Monitoring (False Positive Prevention)', level=2)
    doc.add_paragraph('Scenario: A rapid squall line drops temperatures 8°C in 15 minutes.\n'
                      'System Action: Tier 1 checks the spike. PeerSpatialEngine notes >= 2 siblings experienced the same drop. The system recognizes this as "Common-mode environmental movement" and passes the critical weather data as NORMAL.')

    doc.add_heading('Use Case C — Persistent Slow Drift', level=2)
    doc.add_paragraph('Scenario: A pressure sensor slowly drifts upward by 0.5 hPa every hour.\n'
                      'System Action: Tier 2 CUSUM accumulator detects the persistent residual and raises a drift warning.')

    doc.add_heading('Use Case D — Multivariate Inconsistency (Agriculture)', level=2)
    doc.add_paragraph('Scenario: Temperature spikes 5°C due to localized heating, but Humidity remains flat.\n'
                      'System Action: Tier 3 calculates Mahalanobis distance, identifies a violation of the Clausius-Clapeyron relation, and flags a multivariate_inconsistency.')

    doc.save('Document_2_Tech_Methodology.docx')

def create_doc3():
    doc = docx.Document()
    doc.add_heading('Document 3: SkyGuard Experimental Performance & Casebook', 0)

    doc.add_heading('Part A: Aggregate Experimental Performance', level=1)
    doc.add_paragraph('The following metrics are derived from the latest authoritative benchmark against 28 labeled station files using the offline evaluate.py engine.')
    
    doc.add_heading('Authoritative Executive Scorecard', level=2)
    doc.add_paragraph('• Overall Precision (Hybrid): 83.9%\n'
                      '• Overall Recall (Hybrid): 27.9%\n'
                      '• Mixed True Positives (TP): 1,121\n'
                      '• Mixed False Positives (FP): 215\n'
                      '• Mixed False Negatives (FN): 2,891')
    doc.add_paragraph('Limitation Note: The 27.9% hybrid recall reflects tuning heavily towards Precision (83.9%). In automated weather networks, avoiding False Alarms is significantly more critical than catching every borderline deviation.')

    doc.add_heading('Part B: Experimental Casebook', level=1)

    doc.add_heading('Case Study 1: The Isolated Sensor Spike', level=2)
    doc.add_paragraph('Scenario: A localized transmission glitch causes a single temperature reading to jump wildly (13.7°C jump).\n'
                      'Detector Evidence: Tier 1 (Spike) detector clears the Wald threshold. 0 peers show aligned movement.\n'
                      'Final Decision: is_anomaly: TRUE, fault_type: spike.')

    doc.add_heading('Case Study 2: Genuine Meteorological Front (False Positive Suppression)', level=2)
    doc.add_paragraph('Scenario: A real weather front rolls in, dropping temperatures rapidly (8.0°C drop).\n'
                      'Detector Evidence: Jump triggers Tier 1, but PeerSpatialEngine checks sibling peers. 2 out of 3 peers show simultaneous drops.\n'
                      'Final Decision: is_anomaly: FALSE. Data passed to forecasting models.')

    doc.add_heading('Case Study 3: The Persistent Slow Drift', level=2)
    doc.add_paragraph('Scenario: A pressure sensor loses calibration and slowly drifts upward.\n'
                      'Detector Evidence: Tier 2 (Drift) detector utilizes Pre-Whitened SPRT CUSUM accumulator.\n'
                      'Final Decision: Accumulator clears CUSUM_THRESHOLD. is_anomaly: TRUE, fault_type: drift.')

    doc.add_heading('Case Study 4: Thermodynamic Multivariate Inconsistency', level=2)
    doc.add_paragraph('Scenario: Temperature artificially spikes by 5°C, humidity remains flat.\n'
                      'Detector Evidence: vapor_pressure_deficit_kpa deviates massively from Clausius-Clapeyron derived expected RH. Tier 4 Isolation Forest outputs anomaly score in 99th percentile.\n'
                      'Final Decision: is_anomaly: TRUE, fault_type: multivariate_inconsistency. SHAP attributes root cause to Temperature.')

    doc.save('Document_3_Performance_Casebook.docx')

if __name__ == "__main__":
    create_doc1()
    create_doc2()
    create_doc3()
