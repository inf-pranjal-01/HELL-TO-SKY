import os
import subprocess

DOCS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS"
ALT_DOCS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANTIGRAVITY RESEARCH DOCUMENT"
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ASSETS_DIR = os.path.join(DOCS_DIR, "assets")

os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(ALT_DOCS_DIR, exist_ok=True)

CSS_STYLES = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

@page {
    size: A4 portrait;
    margin: 15mm 14mm 15mm 14mm;
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-family: 'Inter', sans-serif;
        font-size: 7.5pt;
        color: #64748b;
    }
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 8.5pt;
    line-height: 1.45;
    color: #1e293b;
    background-color: #ffffff;
    margin: 0;
    padding: 0;
}

.doc-header {
    border-bottom: 2.5px solid #1e3a8a;
    padding-bottom: 10px;
    margin-bottom: 14px;
}

.doc-badge {
    display: inline-block;
    background: #1e3a8a;
    color: #ffffff;
    font-size: 7pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    padding: 2.5px 7px;
    border-radius: 3px;
    margin-bottom: 6px;
}

.doc-title {
    font-size: 18pt;
    font-weight: 800;
    color: #0f172a;
    line-height: 1.15;
    margin: 0 0 3px 0;
    letter-spacing: -0.4px;
}

.doc-subtitle {
    font-size: 9.5pt;
    font-weight: 600;
    color: #2563eb;
    margin: 0 0 8px 0;
}

.doc-meta-bar {
    display: flex;
    justify-content: space-between;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3.5px solid #1e3a8a;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 7.2pt;
    color: #475569;
}

.doc-meta-bar span {
    font-weight: 600;
    color: #0f172a;
}

h1 {
    font-size: 11.5pt;
    font-weight: 800;
    color: #0f172a;
    border-bottom: 1.5px solid #e2e8f0;
    padding-bottom: 2px;
    margin-top: 14px;
    margin-bottom: 6px;
    letter-spacing: -0.2px;
    page-break-after: avoid;
}

h2 {
    font-size: 9.8pt;
    font-weight: 700;
    color: #1e3a8a;
    margin-top: 10px;
    margin-bottom: 4px;
    page-break-after: avoid;
}

h3 {
    font-size: 8.8pt;
    font-weight: 700;
    color: #334155;
    margin-top: 8px;
    margin-bottom: 3px;
    page-break-after: avoid;
}

p {
    margin-top: 0;
    margin-bottom: 6px;
    text-align: justify;
}

ul, ol {
    margin-top: 0;
    margin-bottom: 6px;
    padding-left: 15px;
}

li {
    margin-bottom: 2px;
}

.figure-box {
    border: 1px solid #e2e8f0;
    background: #ffffff;
    border-radius: 5px;
    padding: 6px;
    margin: 8px 0 10px 0;
    text-align: center;
    page-break-inside: avoid;
}

.figure-box img, .figure-box svg {
    max-width: 100%;
    height: auto;
    border-radius: 3px;
}

.figure-caption {
    font-size: 7.2pt;
    color: #475569;
    margin-top: 4px;
    text-align: justify;
    line-height: 1.3;
}

.figure-caption strong {
    color: #0f172a;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.5pt;
    margin-top: 6px;
    margin-bottom: 10px;
    page-break-inside: avoid;
}

th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 700;
    text-align: left;
    padding: 4px 5px;
    border: 1px solid #cbd5e1;
}

td {
    padding: 3.5px 5px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
}

tr:nth-child(even) {
    background-color: #f8fafc;
}

.math-block {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #3b82f6;
    padding: 6px 10px;
    margin: 6px 0;
    border-radius: 0 4px 4px 0;
    font-family: 'Inter', sans-serif;
    page-break-inside: avoid;
}

.equation-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 9pt;
    font-weight: 600;
    color: #0f172a;
    margin-bottom: 3px;
}

.equation-num {
    font-size: 7.5pt;
    font-weight: 700;
    color: #64748b;
}

.math-desc {
    font-size: 7.2pt;
    color: #475569;
    line-height: 1.35;
}

.callout {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-left: 3.5px solid #16a34a;
    padding: 5px 8px;
    margin: 6px 0;
    border-radius: 0 4px 4px 0;
    font-size: 7.6pt;
    color: #14532d;
    page-break-inside: avoid;
}

.case-card {
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 8px;
    margin: 8px 0;
    background: #ffffff;
    page-break-inside: avoid;
}

.case-card-header {
    font-size: 8.8pt;
    font-weight: 800;
    color: #1e3a8a;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 3px;
    margin-bottom: 5px;
    display: flex;
    justify-content: space-between;
}

.case-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    font-size: 7.5pt;
}

.badge-demonstrated {
    background: #dcfce7;
    color: #166534;
    padding: 1.5px 5px;
    border-radius: 3px;
    font-weight: 700;
    font-size: 6.8pt;
    display: inline-block;
}

.badge-supported {
    background: #e0e7ff;
    color: #3730a3;
    padding: 1.5px 5px;
    border-radius: 3px;
    font-weight: 700;
    font-size: 6.8pt;
    display: inline-block;
}

.badge-future {
    background: #fef3c7;
    color: #92400e;
    padding: 1.5px 5px;
    border-radius: 3px;
    font-weight: 700;
    font-size: 6.8pt;
    display: inline-block;
}

.decision-box {
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-left: 3px solid #0f172a;
    padding: 4px 8px;
    font-size: 7.2pt;
    font-family: 'JetBrains Mono', monospace;
    margin: 4px 0;
    border-radius: 0 3px 3px 0;
}
"""

def build_doc1():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SkyGuard AI — Volume I: External Research, Evidence, Impact &amp; Benefit Dossier</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <div class="doc-header">
        <div class="doc-badge">SkyGuard AI Technical Documentation Suite &mdash; Volume I</div>
        <div class="doc-title">External Research, Evidence, Impact &amp; Benefit Dossier</div>
        <div class="doc-subtitle">Authoritative Research Foundations, Standards Compliance, and Traceable Operational Models</div>
        <div class="doc-meta-bar">
            <div>Target Domain: <span>Surface Automatic Weather Stations (AWS)</span></div>
            <div>Compliance: <span>WMO-No. 8 (Vol. III) Level I–III Quality Control</span></div>
            <div>Authoritative Scope: <span>28 Operational Stations / 7 Regional Clusters</span></div>
        </div>
    </div>

    <h1>1. Executive Summary</h1>
    <p>This research dossier establishes the authoritative scientific principles, international standards, and mathematically traceable operational impact models for <strong>SkyGuard AI</strong>. As national meteorological services rapidly scale high-temporal automatic weather station networks, ensuring telemetry data quality without human-in-the-loop bottlenecks is paramount. Ground-truth validation requires autonomous, low-latency, physics-grounded anomaly filtering to protect downstream Numerical Weather Prediction (NWP) initialization, extreme weather early warnings, and climate records.</p>
    <p>This document establishes direct traceability from peer-reviewed literature (Isolation Forests, Sequential Probability Ratio Tests, Clausius-Clapeyron thermodynamics, 3D Mahalanobis covariance, and SHAP game-theoretic attribution) to SkyGuard's implemented detection tiers. All workload and scalability models are derived transparently from verified benchmark latency figures, strictly rejecting unverified financial projections.</p>

    <h1>2. Automatic Weather Station (AWS) Observation Ecosystem</h1>
    <p>Automatic Weather Stations (AWS) have superseded manual observatories as the primary source of real-time surface meteorological data worldwide. AWS units measure core surface variables &mdash; Ambient Temperature (<em>T</em>), Atmospheric Station Pressure (<em>P</em>), and Relative Humidity (<em>RH</em>) &mdash; at high sampling cadences (1- to 15-minute intervals). In India, the India Meteorological Department (IMD) initiated an expansion of 200 high-density urban AWS nodes across four major metropolitan regions (50 stations each in Delhi, Mumbai, Chennai, and Pune) [R02], augmenting an existing national network of ~1,000 synoptic stations.</p>

    <div class="figure-box">
        <img src="assets/doc1_fig1_ecosystem.svg" alt="AWS Ecosystem Flowchart">
        <div class="figure-caption"><strong>Figure 1. Automatic Weather Station Ingestion &amp; Quality Control Flow.</strong> Raw surface telemetry undergoes real-time multi-tier screening in SkyGuard AI prior to assimilation into Numerical Weather Prediction (NWP) 4D-Var grids, extreme weather alerts, and maintenance tracking. Source: System Design Specification.</div>
    </div>

    <h1>3. AWS Telemetry Quality &amp; Fault Landscape</h1>
    <p>Because automated sensors operate unattended in harsh ambient conditions, they exhibit distinct physical and electrical failure modes. Unscreened bad data directly destabilizes data assimilation matrices in forecast models, while uncorroborated sensor spikes trigger false disaster alarms.</p>

    <div class="figure-box">
        <img src="assets/doc1_fig2_taxonomy.svg" alt="AWS Fault Taxonomy">
        <div class="figure-caption"><strong>Figure 2. Surface AWS Sensor Failure Taxonomy.</strong> Structural classification of hardware and transmission failures into instantaneous spikes, variance collapse, insidious calibration drift, and cross-channel thermodynamic errors. Source: WMO-No. 8 &amp; Meteorological Literature.</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 18%;">Fault Category</th>
                <th style="width: 25%;">Physical Mechanism</th>
                <th style="width: 30%;">Operational Consequence</th>
                <th style="width: 27%;">Standard Reference</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Instantaneous Spikes</strong></td>
                <td>Electromagnetic interference (EMI), voltage surges, ADC bit-flips</td>
                <td>Corrupts rate-of-change; triggers spurious heatwave/gale alarms</td>
                <td>WMO-No. 8 Level I Step Test [R01]</td>
            </tr>
            <tr>
                <td><strong>Variance Collapse (Frozen)</strong></td>
                <td>Mechanical port blockages, spider webs in barometer, ADC lock</td>
                <td>Blinds forecasters during genuine severe storm events</td>
                <td>WMO-No. 8 Persistence QC [R01]</td>
            </tr>
            <tr>
                <td><strong>Insidious Drift</strong></td>
                <td>Capacitive polymer aging, optical fouling, chemical decay</td>
                <td>Silently biases regional climate baselines and trend models</td>
                <td>Page (1954) Sequential QC [M02]</td>
            </tr>
            <tr>
                <td><strong>Thermodynamic Paradox</strong></td>
                <td>Single transducer channel failure within multi-sensor unit</td>
                <td>Violates Clausius-Clapeyron atmospheric moisture relations</td>
                <td>Mahalanobis (1936) [M05]</td>
            </tr>
        </tbody>
    </table>

    <h1>4. Research Foundations &amp; Methodological Adaptation</h1>
    <p>SkyGuard AI synthesizes five foundational mathematical and statistical principles into a cohesive real-time detection pipeline:</p>

    <div class="figure-box">
        <img src="assets/doc1_fig3_research_mapping.svg" alt="Research Mapping">
        <div class="figure-caption"><strong>Figure 3. Research Foundations to SkyGuard Methodological Adaptation.</strong> Direct mapping of international observation standards and peer-reviewed mathematical methods to SkyGuard's operational detection tiers. Source: Technical Reference Audit.</div>
    </div>

    <h2>4.1 Unsupervised Multi-Dimensional Isolation (Liu et al., 2008)</h2>
    <div class="math-block">
        <div class="equation-row">
            <span><em>s</em>(<em>x</em>, <em>n</em>) = 2<sup>&minus; <em>E</em>(<em>h</em>(<em>x</em>)) / <em>c</em>(<em>n</em>)</sup></span>
            <span class="equation-num">(Equation 1)</span>
        </div>
        <div class="math-desc"><strong>Where:</strong> <em>E</em>(<em>h</em>(<em>x</em>)) is the average path length across an ensemble of random partitioning trees (iTrees), and <em>c</em>(<em>n</em>) is the average path length of unsuccessful searches in a Binary Search Tree constructed over <em>n</em> samples.<br>
        <strong>Operational Adaptation:</strong> Deployed in Tier 4 on the 49-feature continuous matrix. Observations isolated near tree roots yield <em>s</em> &rarr; 1.0, identifying complex multivariate anomalies without labeled target data.</div>
    </div>

    <h2>4.2 Sequential Probability Ratio &amp; Cumulative Sum (Page, 1954; Wald, 1945)</h2>
    <div class="math-block">
        <div class="equation-row">
            <span><em>S</em><sub><em>t</em></sub> = max(0, <em>S</em><sub><em>t</em>&minus;1</sub> + <em>z</em><sub><em>t</em></sub> &minus; <em>k</em>)</span>
            <span class="equation-num">(Equation 2)</span>
        </div>
        <div class="math-desc"><strong>Where:</strong> <em>S</em><sub><em>t</em></sub> is the cumulative drift statistic, <em>z</em><sub><em>t</em></sub> is the standardized innovation residual, and <em>k</em> is the reference allowance parameter.<br>
        <strong>Operational Adaptation:</strong> Deployed in Tier 2 (Pre-Whitened SPRT Drift) on innovation residuals. Accumulates evidence over consecutive observations to flag slow calibration drift (+0.05&deg;C/hr) before static physical bounds are breached.</div>
    </div>

    <h2>4.3 Clausius-Clapeyron Psychrometric Boundary (Tetens Formulation)</h2>
    <div class="math-block">
        <div class="equation-row">
            <span><em>e</em><sub><em>s</em></sub>(<em>T</em>) = 6.112 &middot; exp( 17.67 &middot; <em>T</em> / (<em>T</em> + 243.5) )</span>
            <span class="equation-num">(Equation 3)</span>
        </div>
        <div class="math-desc"><strong>Where:</strong> <em>e</em><sub><em>s</em></sub>(<em>T</em>) is the saturation vapor pressure in hPa at ambient temperature <em>T</em> in &deg;C.<br>
        <strong>Operational Adaptation:</strong> Applied in Tier 0 and Tier 3 to compute Vapor Pressure Deficit (VPD = <em>e</em><sub><em>s</em></sub>(<em>T</em>) &middot; (1 &minus; <em>RH</em>/100)). Flags unphysical observations where relative humidity and temperature diverge counter to physical atmospheric physics.</div>
    </div>

    <h2>4.4 3D Mahalanobis Distance for Covariance Inconsistency (Mahalanobis, 1936)</h2>
    <div class="math-block">
        <div class="equation-row">
            <span><em>D</em><sup>2</sup> = (<strong>x</strong> &minus; <strong>&mu;</strong>)<sup>T</sup> <strong>&Sigma;</strong><sup>&minus;1</sup> (<strong>x</strong> &minus; <strong>&mu;</strong>)</span>
            <span class="equation-num">(Equation 4)</span>
        </div>
        <div class="math-desc"><strong>Where:</strong> <strong>x</strong> = [<em>z</em><sub><em>T</em></sub>, <em>z</em><sub><em>P</em></sub>, <em>z</em><sub><em>RH</em></sub>]<sup>T</sup> is the innovation residual vector, and <strong>&Sigma;</strong> is the empirical cross-channel covariance matrix.<br>
        <strong>Operational Adaptation:</strong> Deployed in Tier 3 to detect cross-channel breakdowns. If <em>D</em><sup>2</sup> exceeds &chi;<sup>2</sup><sub>3, 0.999</sub> = 16.27 (<em>p</em> &lt; 10<sup>&minus;3</sup>), the system quarantines the multivariate paradox.</div>
    </div>

    <h2>4.5 Additive Local Feature Attribution via SHAP (Lundberg &amp; Lee, 2017)</h2>
    <div class="math-block">
        <div class="equation-row">
            <span><em>f</em>(<em>x</em>) = &phi;<sub>0</sub> + &sum;<sub><em>i</em>=1..<em>M</em></sub> &phi;<sub><em>i</em></sub></span>
            <span class="equation-num">(Equation 5)</span>
        </div>
        <div class="math-desc"><strong>Where:</strong> &phi;<sub>0</sub> is the expected model base value, and &phi;<sub><em>i</em></sub> is the Shapley additive feature attribution for feature <em>i</em>.<br>
        <strong>Operational Adaptation:</strong> Wrapped around the Isolation Forest via <code>TreeExplainer</code>. Identifies which physical features contributed most to the anomaly score, informing targeted technician maintenance. <em>Note: Explains model decision space, not absolute physical causal proof.</em></div>
    </div>

    <h1>5. Traceable Operational &amp; Computational Impact Modeling</h1>
    <p>We evaluate operational impact through verifiable workload models derived from measured benchmark facts and stated network parameters, strictly omitting unsupported financial projections.</p>

    <div class="figure-box">
        <img src="assets/doc1_fig4_impact.svg" alt="Operational Impact Model">
        <div class="figure-caption"><strong>Figure 4. Operational Impact &amp; False Alarm Suppression Flow.</strong> Automated arbitration filters 80% of uncorroborated transient noise, mitigating 25.6 manual triage hours daily across a 1,000-station network. Source: Operational Workload Ledger.</div>
    </div>

    <div class="figure-box">
        <img src="assets/doc1_fig5_scaling_model.png" alt="Scaling Compute Model">
        <div class="figure-caption"><strong>Figure 5. National Scaling Compute Workload.</strong> Daily CPU compute time required across scaling station counts (100 to 10,000 AWS) at 5-minute sampling cadences, executing at p95 0.210 ms algorithmic inference latency. Source: Benchmark Execution Profile.</div>
    </div>

    <h2>5.1 Calculation Ledger</h2>
    <ul>
        <li><strong>[C01] National Telemetry Volume (Scenario Assumption):</strong> For <em>N</em> = 1,000 stations transmitting at 15-minute intervals (96 obs/day), total annual throughput is <strong>35,040,000 observations/year</strong>.</li>
        <li><strong>[C02] Compute Scalability (Derived Calculation):</strong> Across an expanded national network of 5,000 stations sampled at 5-minute cadences (1,440,000 readings/day), single-threaded CPU compute time is 1,440,000 &times; 0.210 ms = <strong>302.4 seconds (~5.04 minutes) of CPU time per day</strong>.</li>
        <li><strong>[C03] Operator Triage Mitigation (Scenario Assumption):</strong> In a 1,000-station network (96,000 obs/day) with a 1% baseline transient noise rate (960 raw alerts), Tier 5 spatial consensus suppresses ~80% of false alarms (768 alerts). At 2 minutes per manual review, this mitigates <strong>25.6 operator hours/day</strong>.</li>
    </ul>

    <h1>6. Evidence &amp; Source Traceability Register</h1>
    <p>This register maps every major technical claim directly to its underlying standard, primary citation, and implementation status:</p>

    <table>
        <thead>
            <tr>
                <th style="width: 12%;">Claim ID</th>
                <th style="width: 38%;">Claim Description</th>
                <th style="width: 25%;">Primary Source / Standard</th>
                <th style="width: 25%;">Implementation Status</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>C-001</strong></td>
                <td>WMO mandates Level I-III physical, temporal, and spatial Quality Control for AWS.</td>
                <td>WMO-No. 8 (Vol. III, Ch. 1) [R01]</td>
                <td><span class="badge-demonstrated">CURRENTLY DEMONSTRATED</span></td>
            </tr>
            <tr>
                <td><strong>C-002</strong></td>
                <td>IMD expansion adds 200 urban AWS across Delhi, Mumbai, Chennai, and Pune in 2026.</td>
                <td>IMD / PIB Press Releases [R02]</td>
                <td><span class="badge-demonstrated">EXTERNAL FACT</span></td>
            </tr>
            <tr>
                <td><strong>C-003</strong></td>
                <td>Single-reading algorithmic inference executes in p95 0.210 ms on standard CPU.</td>
                <td>Benchmark Profiler Artifact [E01]</td>
                <td><span class="badge-demonstrated">CURRENTLY DEMONSTRATED</span></td>
            </tr>
            <tr>
                <td><strong>C-004</strong></td>
                <td>Sequential SPRT / CUSUM accumulates low-SNR calibration drift evidence.</td>
                <td>Page (1954); Wald (1945) [M02]</td>
                <td><span class="badge-demonstrated">CURRENTLY DEMONSTRATED</span></td>
            </tr>
            <tr>
                <td><strong>C-005</strong></td>
                <td>Isolation Forests isolate high-dimensional anomalies with linear time complexity.</td>
                <td>Liu, Ting, Zhou (2008) [M01]</td>
                <td><span class="badge-demonstrated">CURRENTLY DEMONSTRATED</span></td>
            </tr>
            <tr>
                <td><strong>C-006</strong></td>
                <td>SHAP additive feature attributions provide component-level failure diagnostics.</td>
                <td>Lundberg &amp; Lee (2017) [M03]</td>
                <td><span class="badge-supported">CURRENTLY SUPPORTED</span></td>
            </tr>
            <tr>
                <td><strong>C-007</strong></td>
                <td>SkyGuard achieves ₹50 Crore in maintenance cost savings.</td>
                <td>Unverified Financial Claim</td>
                <td><span class="badge-future">REJECTED / PURGED</span></td>
            </tr>
            <tr>
                <td><strong>C-008</strong></td>
                <td>Centralized SkyGuard reduces AWS edge cellular bandwidth usage.</td>
                <td>Telemetry Network Architecture</td>
                <td><span class="badge-future">REJECTED / PURGED</span></td>
            </tr>
        </tbody>
    </table>

    <h1>7. References</h1>
    <ul>
        <li><strong>[R01]</strong> World Meteorological Organization (WMO). <em>Guide to Instruments and Methods of Observation (WMO-No. 8)</em>, Volume III &mdash; Observing Systems, Chapter 1: Quality Management. WMO, Geneva, Switzerland.</li>
        <li><strong>[R02]</strong> India Meteorological Department (IMD) / Press Information Bureau (PIB). <em>Expansion of High-Density Automatic Weather Station Networks in Metropolitan Areas</em>. Ministry of Earth Sciences, Govt. of India, 2024&ndash;2026.</li>
        <li><strong>[M01]</strong> Liu, F. T., Ting, K. M., and Zhou, Z.-H. "Isolation Forest." <em>Eighth IEEE International Conference on Data Mining (ICDM)</em>, Pisa, Italy, 2008, pp. 413&ndash;422. DOI: 10.1109/ICDM.2008.17.</li>
        <li><strong>[M02]</strong> Page, E. S. "Continuous Inspection Schemes." <em>Biometrika</em>, vol. 41, no. 1/2, 1954, pp. 100&ndash;115. DOI: 10.1093/biomet/41.1-2.100.</li>
        <li><strong>[M03]</strong> Lundberg, S. M., and Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." <em>Advances in Neural Information Processing Systems (NeurIPS 30)</em>, Long Beach, CA, 2017, pp. 4765&ndash;4774.</li>
        <li><strong>[M04]</strong> Iribarne, J. V., and Godson, W. L. <em>Atmospheric Thermodynamics</em>. 2nd ed., D. Reidel Publishing Company, Dordrecht, Netherlands.</li>
        <li><strong>[M05]</strong> Mahalanobis, P. C. "On the generalised distance in statistics." <em>Proceedings of the National Institute of Sciences of India</em>, vol. 2, no. 1, 1936, pp. 49&ndash;55.</li>
    </ul>
</body>
</html>"""

def build_doc2():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SkyGuard AI — Volume II: Technical Methodology, Architecture &amp; Use-Case Document</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <div class="doc-header">
        <div class="doc-badge">SkyGuard AI Technical Documentation Suite &mdash; Volume II</div>
        <div class="doc-title">Technical Methodology, Architecture &amp; Use-Case Document</div>
        <div class="doc-subtitle">Engineering Specification of the Deterministic 6-Tier Pipeline, Continuous Feature Space, and State Isolation</div>
        <div class="doc-meta-bar">
            <div>Architecture: <span>Tier 0–5 Deterministic Priority Hierarchy</span></div>
            <div>Feature Space: <span>49-D Continuous Physical-Time Matrix</span></div>
            <div>Latency Profile: <span>0.210 ms (p95) Single-Reading CPU Execution</span></div>
        </div>
    </div>

    <h1>1. Executive Summary</h1>
    <p>This engineering specification details the system architecture and mathematical implementation of <strong>SkyGuard AI</strong>. The platform is engineered to perform real-time Quality Assurance (QA) and anomaly detection across surface Automatic Weather Station (AWS) networks. SkyGuard integrates a deterministic <strong>Tier 0&ndash;5 Priority Arbitration Hierarchy</strong>, continuous physical-time feature extraction without row-shift leakage, causal ground-truth state isolation, and cluster-isolated spatial consensus.</p>

    <h1>2. End-to-End System Architecture</h1>
    <p>The processing lifecycle enforces strict modularity between ingestion, temporal alignment, feature generation, hierarchical detection, explainability attribution, and causal state maintenance:</p>

    <div class="figure-box">
        <img src="assets/doc2_fig1_architecture.svg" alt="SkyGuard End-to-End Architecture">
        <div class="figure-caption"><strong>Figure 1. SkyGuard AI End-to-End Modular System Architecture.</strong> Sequential progression from raw multi-channel telemetry ingestion through temporal alignment, 49-feature extraction, Tier 0–5 priority arbitration, SHAP attribution, and causal state buffer management. Source: System Design Specification.</div>
    </div>

    <h1>3. Spatial Topology &amp; Cluster Peer Isolation</h1>
    <p>To eliminate cross-regional train/serve mismatch and prevent microclimatic contamination (e.g., coastal marine boundaries vs. arid interior plains), SkyGuard structures the observation network into 7 discrete geographic clusters:</p>

    <div class="figure-box">
        <img src="assets/doc2_fig2_topology.svg" alt="28-Station Topology">
        <div class="figure-caption"><strong>Figure 2. 28-Station / 7-Cluster Spatial Isolation Topology.</strong> Each cluster comprises exactly 1 primary target center station (C) and 3 regional sibling peers (S). Spatial consensus queries operate strictly within cluster boundaries. Source: Network Configuration Blueprint.</div>
    </div>

    <h1>4. 49-Dimensional Continuous Physical-Time Feature Architecture</h1>
    <p>The feature engineering engine (<code>model/features.py</code>) strictly avoids positional row shifts (<code>.shift(n)</code>), utilizing exact physical timestamps and <code>pd.merge_asof</code> to compute continuous derivatives regardless of irregular sampling or dropped packets:</p>

    <div class="figure-box">
        <img src="assets/doc2_fig3_features.svg" alt="49-Feature Architecture">
        <div class="figure-caption"><strong>Figure 3. 49-Dimensional Continuous Feature Architecture.</strong> Structured hierarchy grouping raw measured channels, innovation residuals, multi-scale rate-of-change velocities, volatility, psychrometrics, cyclical encodings, robust statistics, rolling ranges, and diurnal baselines. Source: Feature Extraction Codebase.</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 15%;">Feature Range</th>
                <th style="width: 25%;">Category</th>
                <th style="width: 35%;">Mathematical Formulation</th>
                <th style="width: 25%;">Diagnostic Purpose</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>01 &ndash; 03</strong></td>
                <td>Raw Telemetry Channels</td>
                <td><em>x</em><sub><em>t</em></sub> = [<em>T</em><sub><em>t</em></sub>, <em>P</em><sub><em>t</em></sub>, <em>RH</em><sub><em>t</em></sub>]</td>
                <td>Base atmospheric observation state.</td>
            </tr>
            <tr>
                <td><strong>04 &ndash; 06</strong></td>
                <td>Innovation Residuals</td>
                <td><em>z</em><sub><em>t</em></sub> = (<em>x</em><sub><em>t</em></sub> &minus; &mu;<sub>diurnal</sub>) / &sigma;<sub>diurnal</sub></td>
                <td>Normalized deviation from local expectation.</td>
            </tr>
            <tr>
                <td><strong>07 &ndash; 12</strong></td>
                <td>Rate-of-Change Velocities</td>
                <td>&Delta;<em>x</em>/&Delta;<em>t</em> = (<em>x</em><sub><em>t</em></sub> &minus; <em>x</em><sub><em>t</em>&minus;&Delta;<em>t</em></sub>) / &Delta;<em>t</em><sub>hours</sub> (1h, 3h)</td>
                <td>Captures sudden atmospheric jumps vs. spikes.</td>
            </tr>
            <tr>
                <td><strong>13 &ndash; 15</strong></td>
                <td>Short-Term Volatility</td>
                <td>&sigma;<sub>3h</sub>(<em>x</em>) = [ (1/<em>N</em>) &sum;(<em>x</em><sub><em>i</em></sub> &minus; <em>x&#772;</em>)<sup>2</sup> ]<sup>0.5</sup></td>
                <td>Identifies turbulence vs. abnormal stillness.</td>
            </tr>
            <tr>
                <td><strong>16 &ndash; 17</strong></td>
                <td>Psychrometric Couplings</td>
                <td><em>T</em><sub>dew</sub> = <em>T</em> &minus; (100&minus;<em>RH</em>)/5; VPD = <em>e</em><sub><em>s</em></sub>(<em>T</em>)(1 &minus; <em>RH</em>/100)</td>
                <td>Clausius-Clapeyron thermodynamic consistency.</td>
            </tr>
            <tr>
                <td><strong>18 &ndash; 21</strong></td>
                <td>Cyclical Time Encodings</td>
                <td>sin/cos(2&pi;&middot;Hour/24), sin/cos(2&pi;&middot;DOY/365)</td>
                <td>Diurnal and seasonal cyclical phase alignment.</td>
            </tr>
            <tr>
                <td><strong>22</strong></td>
                <td>Elapsed Physical Interval</td>
                <td>&Delta;<em>t</em><sub>hours</sub> = (<em>t</em><sub><em>k</em></sub> &minus; <em>t</em><sub><em>k</em>&minus;1</sub>) / 3600.0</td>
                <td>Exact physical elapsed time tracking.</td>
            </tr>
            <tr>
                <td><strong>23 &ndash; 25</strong></td>
                <td>Robust Statistical Scales</td>
                <td>Scale<sub>robust</sub> = (<em>x</em><sub><em>t</em></sub> &minus; median) / IQR</td>
                <td>Outlier-resistant localized baseline scaling.</td>
            </tr>
            <tr>
                <td><strong>26 &ndash; 28</strong></td>
                <td>Sensor Gap Tracking</td>
                <td>&Delta;<em>t</em><sub>valid</sub> = Hours since last trusted observation</td>
                <td>Tracks quarantined sensor downtime duration.</td>
            </tr>
            <tr>
                <td><strong>29 &ndash; 46</strong></td>
                <td>Rolling Ranges &amp; Slopes</td>
                <td>Range<sub><em>W</em></sub> = max<sub><em>W</em></sub>(<em>x</em>) &minus; min<sub><em>W</em></sub>(<em>x</em>); Slope<sub><em>W</em></sub> = Cov(<em>t</em>,<em>x</em>)/Var(<em>t</em>)</td>
                <td>Multi-scale dispersion (1,3,6,24h) &amp; synoptic trend.</td>
            </tr>
            <tr>
                <td><strong>47 &ndash; 49</strong></td>
                <td>Diurnal Residual Baselines</td>
                <td><em>r</em><sub>diurnal</sub> = <em>x</em><sub><em>t</em></sub> &minus; Baseline(<em>h</em><sub>diurnal</sub>)</td>
                <td>Hour-of-day baseline residual tracking.</td>
            </tr>
        </tbody>
    </table>

    <h1>5. Deterministic Tier 0–5 Priority Hierarchy</h1>
    <p><code>DecisionEngine.decide</code> (<code>model/detect.py</code>) executes a strict top-down priority arbitration cascade where deterministic physical laws always take precedence over statistical models:</p>

    <div class="figure-box">
        <img src="assets/doc2_fig4_decision_flow.svg" alt="Decision Arbitration Flow">
        <div class="figure-caption"><strong>Figure 4. Tier 0–5 Priority Arbitration Decision Flow.</strong> Sequential evaluation from Tier 0 physical invariants down through specialist LLR, SPRT drift, 3D Mahalanobis, Isolation Forest, and Tier 5 spatial consensus veto. Source: DecisionEngine Codebase.</div>
    </div>

    <ul>
        <li><strong>TIER 0 (Hard Invariants &amp; Rails):</strong> Evaluates electrical ground faults (0.00V) and absolute physical bounds (<em>T</em> &notin; [&minus;40, +60&deg;C], <em>P</em> &notin; [800, 1100 hPa], <em>RH</em> &notin; [0, 100%]). Breaches immediately return <code>FAULT (CRITICAL)</code> and bypass all downstream computation.</li>
        <li><strong>TIER 1 (Specialist Jump &amp; Frozen LLR):</strong> Evaluates instantaneous dynamic acceleration (>5.0&sigma; jump LLR) and F-ratio variance collapse over contiguous 4-hour windows.</li>
        <li><strong>TIER 2 (Persistent SPRT Drift):</strong> Executes Sequential Probability Ratio Test on standardized innovation residuals to accumulate low-SNR calibration drift (+0.05&deg;C/hr) over time.</li>
        <li><strong>TIER 3 (Cross-Channel 3D Mahalanobis Covariance):</strong> Evaluates joint 3D covariance distance <em>D</em><sup>2</sup>. If <em>D</em><sup>2</sup> &gt; 16.27 (<em>p</em> &lt; 10<sup>&minus;3</sup>), flags multivariate thermodynamic breakdowns.</li>
        <li><strong>TIER 4 (Model-Dominant Isolation Forest):</strong> Evaluates the 49-feature continuous matrix through an ensemble of 100 Isolation Trees, isolating complex unstructured anomalies.</li>
        <li><strong>TIER 5 (Spatial Consensus Veto &amp; Arbiter):</strong> If an anomaly flag is raised by Tiers 1–4, the spatial consensus engine inspects the 3 sibling stations in the cluster. If &ge;2 peers exhibit matching directional rate-of-change movement, the anomaly is classified as a genuine regional weather event, and the alert is VETOED to <code>NORMAL</code>.</li>
    </ul>

    <h1>6. Causal State Management &amp; Sensor Health Lifecycle</h1>
    <p>To prevent corrupted telemetry from polluting future baseline estimates, <code>StateManager</code> (<code>model/state.py</code>) enforces strict ground-truth isolation:</p>

    <div class="figure-box">
        <img src="assets/doc2_fig5_state_machine.svg" alt="State Machine Diagram">
        <div class="figure-caption"><strong>Figure 5. Causal Ground-Truth Isolation &amp; Sensor Health State Machine.</strong> Anomalous observations are quarantined from the StationBuffer deque, preserving trusted rolling baselines, while the SensorHealthTracker manages operational states. Source: StateManager Codebase.</div>
    </div>

    <div class="callout">
        <strong>Causal Ground-Truth Exclusion Rule:</strong> When an observation is classified as <code>FAULT</code> (or when a sensor is in <code>OFFLINE</code> health state), the observation is strictly quarantined. It is recorded in the raw historical audit log but excluded from the internal sliding <code>StationBuffer</code> deque, ensuring that rolling means, variances, and diurnal baselines remain 100% uncontaminated.
    </div>

    <h1>7. Operational Use-Case Workflows</h1>
    <p>SkyGuard's capabilities map directly to concrete meteorological and field operations:</p>

    <div class="case-card">
        <div class="case-card-header">
            <span>Use Case 1: Automated Real-Time AWS Quality Control</span>
            <span class="badge-demonstrated">CURRENTLY DEMONSTRATED</span>
        </div>
        <div class="case-grid">
            <div><strong>Operational Workflow:</strong> Continuous real-time screening of raw surface streams (T, P, RH) across 28 national AWS stations at 0.210 ms (p95) latency.</div>
            <div><strong>Validation Status:</strong> Validated across 60,480 evaluation rows in authoritative 7-seed benchmark; achieves 97.27% mean recall.</div>
        </div>
    </div>

    <div class="case-card">
        <div class="case-card-header">
            <span>Use Case 2: NWP Data Assimilation Boundary Protection</span>
            <span class="badge-demonstrated">CURRENTLY DEMONSTRATED</span>
        </div>
        <div class="case-grid">
            <div><strong>Operational Workflow:</strong> Automatic quarantining of spurious sensor spikes and unphysical thermodynamic readings before ingestion into 4D-Var data assimilation grids.</div>
            <div><strong>Validation Status:</strong> Guaranteed via <code>StationBuffer</code> causal exclusion, preventing bad data from contaminating forecast model initialization.</div>
        </div>
    </div>

    <div class="case-card">
        <div class="case-card-header">
            <span>Use Case 3: Targeted Field Maintenance &amp; Sensor Health</span>
            <span class="badge-supported">CURRENTLY SUPPORTED</span>
        </div>
        <div class="case-grid">
            <div><strong>Operational Workflow:</strong> Uses SHAP local feature attributions and fault classification to dispatch technicians to specific degraded sensor modules.</div>
            <div><strong>Validation Status:</strong> Identifies active hardware failures and sensor health degradation; does not predict future failures prior to onset.</div>
        </div>
    </div>

    <div class="case-card">
        <div class="case-card-header">
            <span>Use Case 4: Embedded Microcontroller Edge Execution</span>
            <span class="badge-future">FUTURE ARCHITECTURAL APPLICATION</span>
        </div>
        <div class="case-grid">
            <div><strong>Operational Workflow:</strong> Running lightweight algorithmic inference directly on station datalogger firmware (ESP32 / ARM Cortex-M) to screen telemetry at the edge.</div>
            <div><strong>Validation Status:</strong> Feasible due to 0.210 ms execution speed; requires future C/C++ firmware porting and microcontroller deployment.</div>
        </div>
    </div>

    <h1>8. Current vs. Future Architectural Matrix</h1>
    <table>
        <thead>
            <tr>
                <th style="width: 25%;">Subsystem</th>
                <th style="width: 35%;">Current Implemented Architecture</th>
                <th style="width: 20%;">Demonstrated Status</th>
                <th style="width: 20%;">Future Scope</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Inference Engine</strong></td>
                <td>Vectorized NumPy / Scikit-Learn on CPU</td>
                <td><span class="badge-demonstrated">DEMONSTRATED</span></td>
                <td>C-optimized firmware (ESP32)</td>
            </tr>
            <tr>
                <td><strong>Temporal State Buffer</strong></td>
                <td>In-memory circular deques (<code>collections.deque</code>)</td>
                <td><span class="badge-demonstrated">DEMONSTRATED</span></td>
                <td>Distributed Redis state cache</td>
            </tr>
            <tr>
                <td><strong>Storage Layer</strong></td>
                <td>Flat-file CSV streaming (<code>HistoryStore</code>)</td>
                <td><span class="badge-demonstrated">DEMONSTRATED</span></td>
                <td>TimescaleDB / PostgreSQL cluster</td>
            </tr>
            <tr>
                <td><strong>Spatial Discovery</strong></td>
                <td>Static 7-cluster topology (4 stations/cluster)</td>
                <td><span class="badge-demonstrated">DEMONSTRATED</span></td>
                <td>Dynamic PostGIS radius queries</td>
            </tr>
            <tr>
                <td><strong>API &amp; Streaming</strong></td>
                <td>FastAPI REST endpoints + WebSockets</td>
                <td><span class="badge-demonstrated">DEMONSTRATED</span></td>
                <td>gRPC streaming gateway</td>
            </tr>
        </tbody>
    </table>

    <h1>9. References</h1>
    <ul>
        <li><strong>[M01]</strong> Liu, F. T., Ting, K. M., and Zhou, Z.-H. "Isolation Forest." <em>IEEE ICDM</em>, 2008.</li>
        <li><strong>[M02]</strong> Page, E. S. "Continuous Inspection Schemes." <em>Biometrika</em>, vol. 41, 1954, pp. 100&ndash;115.</li>
        <li><strong>[M03]</strong> Lundberg, S. M., and Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." <em>NeurIPS</em>, 2017.</li>
        <li><strong>[M05]</strong> Mahalanobis, P. C. "On the generalised distance in statistics." <em>Proc. Natl. Inst. Sci. India</em>, 1936.</li>
    </ul>
</body>
</html>"""

def build_doc3():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SkyGuard AI — Volume III: Experimental Performance &amp; Casebook</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <div class="doc-header">
        <div class="doc-badge">SkyGuard AI Technical Documentation Suite &mdash; Volume III</div>
        <div class="doc-title">Experimental Performance &amp; Casebook</div>
        <div class="doc-subtitle">Authoritative 7-Seed Empirical Benchmark, Fault-Class Performance, and Diagnostic Case Studies</div>
        <div class="doc-meta-bar">
            <div>Evaluation Corpus: <span>60,480 Rows (28 AWS Stations)</span></div>
            <div>Benchmark Scorecard: <span>97.27% Mean Recall / 72.35% Mean Precision</span></div>
            <div>Inference Speed: <span>0.210 ms (p95) Single-Reading CPU Latency</span></div>
        </div>
    </div>

    <h1>1. Executive Summary</h1>
    <p>This experimental casebook documents the authoritative empirical evaluation and diagnostic case studies for <strong>SkyGuard AI</strong>. Rejecting outdated historical benchmark metrics (such as the legacy 83.9% precision / 27.9% recall figures from earlier development stages), this document reports the locked <strong>authoritative 7-seed scorecard</strong> executed across <strong>60,480 continuous physical rows</strong> spanning a 28-station national topology (<code>calibration_seed_71001_full_audit_v8</code>).</p>
    <p>SkyGuard demonstrates <strong>97.27% &plusmn; 0.49% mean recall</strong> across all injected hardware failure modes, <strong>72.35% &plusmn; 1.56% mean precision</strong>, and a <strong>0.210 ms (p95)</strong> single-reading algorithmic inference latency. Furthermore, this document presents four reproducible diagnostic case studies detailing the exact multi-tier data flow from raw telemetry to spatial consensus.</p>

    <h1>2. Authoritative 7-Seed Benchmark Evaluation</h1>
    <p>The offline diagnostic harness (<code>evaluate.py</code>) processes historical observation streams chronologically, maintaining <em>T</em>&minus;1 state integrity exactly as in live deployment. Ground-truth labels are strictly stripped from incoming payloads to guarantee zero data leakage:</p>

    <div class="figure-box">
        <img src="assets/doc3_fig1_seed_scorecard.png" alt="7-Seed Scorecard">
        <div class="figure-caption"><strong>Figure 1. Authoritative 7-Seed Diagnostic Benchmark Scorecard.</strong> Precision, Recall, and F1 performance across 7 independent random calibration seeds evaluated over 60,480 continuous physical rows. Mean Recall: 97.27%, Mean Precision: 72.35%, Mean F1: 82.97%. Source: Benchmark Summary Artifact.</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 20%;">Evaluation Seed</th>
                <th style="width: 20%;">Evaluated Rows</th>
                <th style="width: 15%;">Precision (%)</th>
                <th style="width: 15%;">Recall (%)</th>
                <th style="width: 15%;">F1 Score (%)</th>
                <th style="width: 15%;">Time (s)</th>
            </tr>
        </thead>
        <tbody>
            <tr><td>Seed 42</td><td>60,480</td><td>71.68%</td><td>97.99%</td><td>82.79%</td><td>13.7 s</td></tr>
            <tr><td>Seed 101</td><td>60,480</td><td>72.41%</td><td>96.77%</td><td>82.84%</td><td>18.1 s</td></tr>
            <tr><td>Seed 202</td><td>60,480</td><td>74.38%</td><td>97.98%</td><td>84.57%</td><td>13.2 s</td></tr>
            <tr><td>Seed 2024</td><td>60,480</td><td>73.45%</td><td>96.81%</td><td>83.53%</td><td>17.1 s</td></tr>
            <tr><td>Seed 8888</td><td>60,480</td><td>72.97%</td><td>97.25%</td><td>83.38%</td><td>14.2 s</td></tr>
            <tr><td>Seed 20260924</td><td>60,480</td><td>72.48%</td><td>97.31%</td><td>83.08%</td><td>13.8 s</td></tr>
            <tr><td>Seed 454562314127</td><td>60,480</td><td>69.05%</td><td>96.81%</td><td>80.61%</td><td>15.5 s</td></tr>
            <tr style="background: #eff6ff; font-weight: bold;">
                <td>7-SEED MEAN</td><td>60,480</td><td>72.35%</td><td>97.27%</td><td>82.97%</td><td>15.09 s</td>
            </tr>
            <tr style="color: #64748b;">
                <td>Standard Deviation</td><td>&mdash;</td><td>&plusmn; 1.56%</td><td>&plusmn; 0.49%</td><td>&plusmn; 1.11%</td><td>&plusmn; 1.78 s</td>
            </tr>
        </tbody>
    </table>

    <h1>3. Fault-Class Performance &amp; Latency Profiles</h1>
    <p>Detection efficacy varies across specific failure modes, reflecting the specialized detector tiers responsible for each physical anomaly class:</p>

    <div class="figure-box">
        <img src="assets/doc3_fig2_fault_breakdown.png" alt="Fault Breakdown">
        <div class="figure-caption"><strong>Figure 2. Fault-Class Detection Recall Breakdown.</strong> Individual recall rates across seven distinct hardware failure modes evaluated in the authoritative benchmark. Source: Fault Ledger Diagnostic Matrix.</div>
    </div>

    <div class="figure-box">
        <img src="assets/doc3_fig3_latency_profile.png" alt="Latency Profile">
        <div class="figure-caption"><strong>Figure 3. Algorithmic Inference Latency vs. Operational Time Budget.</strong> Processing latency across execution stages (p50: 0.172 ms, p95: 0.210 ms, p99: 0.268 ms) relative to the 2,000 ms operational real-time limit. Source: Profile Latency Diagnostic.</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 25%;">Fault Taxonomy</th>
                <th style="width: 15%;">Target Rows</th>
                <th style="width: 15%;">True Positives</th>
                <th style="width: 15%;">False Negatives</th>
                <th style="width: 15%;">Recall (%)</th>
                <th style="width: 15%;">Primary Detector</th>
            </tr>
        </thead>
        <tbody>
            <tr><td>Sensor Dropout / Rail</td><td>69</td><td>69</td><td>0</td><td><strong>100.00%</strong></td><td>Tier 0 Invariant</td></tr>
            <tr><td>Instantaneous Spike</td><td>58</td><td>58</td><td>0</td><td><strong>100.00%</strong></td><td>Tier 1 Jump LLR</td></tr>
            <tr><td>Frozen Value Collapse</td><td>459</td><td>447</td><td>12</td><td><strong>97.39%</strong></td><td>Tier 1 F-Ratio</td></tr>
            <tr><td>Low-SNR Calibration Drift</td><td>2,354</td><td>2,163</td><td>191</td><td><strong>91.89%</strong></td><td>Tier 2 SPRT Drift</td></tr>
            <tr><td>Thermodynamic Inconsistency</td><td>279</td><td>279</td><td>0</td><td><strong>100.00%</strong></td><td>Tier 3 Mahalanobis</td></tr>
            <tr><td>Sensor Fail-Low</td><td>277</td><td>208</td><td>69</td><td><strong>75.09%</strong></td><td>Tier 0/1 Bound</td></tr>
            <tr><td>Unstructured Multi-Sensor</td><td>400</td><td>244</td><td>156</td><td><strong>61.00%</strong></td><td>Tier 4 Isolation Forest</td></tr>
        </tbody>
    </table>

    <h1>4. Diagnostic Case Studies (Standardized Analytical Chain)</h1>

    <!-- Case Study 1 -->
    <div class="case-card">
        <div class="case-card-header">
            <span>Case Study 1 &mdash; Instantaneous Sensor Spike Detection (AWS-MUM-007)</span>
            <span class="badge-demonstrated">TIER 1 DETECTOR</span>
        </div>
        <p style="font-size: 7.5pt; margin-bottom: 4px;"><strong>A. Operational Scenario:</strong> A power surge / electromagnetic interference (EMI) event causes a massive, instantaneous +14.2&deg;C jump in the temperature transducer at coastal station AWS-MUM-007.</p>
        
        <p style="font-size: 7.5pt; margin-bottom: 2px;"><strong>B. Input Data Snippet (Timestamped Telemetry Trace):</strong></p>
        <table>
            <thead>
                <tr><th>Timestamp</th><th>Station</th><th>Temp (&deg;C)</th><th>Pressure (hPa)</th><th>RH (%)</th><th>State</th></tr>
            </thead>
            <tbody>
                <tr><td>2025-01-02 21:00:00</td><td>AWS-MUM-007</td><td>27.81</td><td>1011.2</td><td>68.4%</td><td>NORMAL</td></tr>
                <tr><td>2025-01-02 22:00:00</td><td>AWS-MUM-007</td><td>27.79</td><td>1011.4</td><td>68.9%</td><td>NORMAL</td></tr>
                <tr style="background: #fee2e2; font-weight: bold;"><td>2025-01-02 23:00:00</td><td>AWS-MUM-007</td><td>42.02</td><td>1011.3</td><td>68.5%</td><td>FAULT (SPIKE)</td></tr>
                <tr><td>2025-01-03 00:00:00</td><td>AWS-MUM-007</td><td>27.65</td><td>1011.1</td><td>69.2%</td><td>NORMAL</td></tr>
            </tbody>
        </table>

        <p style="font-size: 7.5pt; margin-bottom: 4px;"><strong>C. Event / Fault Construction:</strong> Injected single-timestep spike (+14.2&deg;C) on <code>temperature_c</code> at index 47 (Seed 71001).</p>
        
        <div class="figure-box" style="margin: 4px 0;">
            <img src="assets/doc3_fig4_case1_spike.png" alt="Case Study 1 Spike Plot">
            <div class="figure-caption"><strong>Figure 4. Case Study 1 Time-Series Plot.</strong> Telemetry trace showing target station spike to 42.02&deg;C against steady sibling peer baselines (21.2&deg;C &plusmn; 0.3&deg;C). Flagged by Tier 1 Dynamic Jump LLR (6.2&sigma;) and quarantined. Source: Replay Case AWS-MUM-007:47.</div>
        </div>

        <div class="case-grid" style="margin-top: 4px;">
            <div>
                <strong>E. Detector Evidence:</strong> Tier 1 Jump LLR = 6.24&sigma; (threshold: 5.0&sigma;).<br>
                <strong>F. Peer / Spatial Evidence:</strong> Sibling stations (AWS-MUM-101, 102, 103) report steady rate-of-change (&Delta;T &lt; 0.3&deg;C).<br>
                <strong>G. Model Evidence:</strong> Bypassed (Specialist Tier 1 fast trigger).<br>
                <strong>H. SHAP Attribution:</strong> Not required (Deterministic Physics trigger).
            </div>
            <div>
                <strong>I. Final Decision:</strong> <code>FAULT (TIER_1_SPECIALIST_SPIKE)</code><br>
                <div class="decision-box">STATUS: FAULT | SEVERITY: CRITICAL | CONFIDENCE: 99.5%</div>
                <strong>J. Human Explanation:</strong> "Instantaneous non-physical temperature jump (+14.2C) exceeding 6.2 sigma without peer corroboration."<br>
                <strong>K. Recovery:</strong> Single-row quarantine; StateManager returns to trusted baseline at 00:00:00.
            </div>
        </div>
        <p style="font-size: 7.2pt; color: #475569; margin-top: 4px;"><strong>L. Evaluation Result:</strong> True Positive (0 lag). <strong>M. Interpretation:</strong> Proves instantaneous spike isolation. <strong>N. Limitation:</strong> Does not simulate compound multi-channel surges.</p>
    </div>

    <!-- Case Study 2 -->
    <div class="case-card">
        <div class="case-card-header">
            <span>Case Study 2 &mdash; Genuine Coastal Cold Front Spatial Consensus Veto (AWS-MUM-007)</span>
            <span class="badge-demonstrated">TIER 5 SPATIAL VETO</span>
        </div>
        <p style="font-size: 7.5pt; margin-bottom: 4px;"><strong>A. Operational Scenario:</strong> A rapid synoptic cold front passage across Mumbai coastal cluster causes temperatures to plunge by 8.2&deg;C in under 20 minutes across all stations.</p>
        
        <p style="font-size: 7.5pt; margin-bottom: 2px;"><strong>B. Input Data Snippet (Aligned Sibling Cluster Trace):</strong></p>
        <table>
            <thead>
                <tr><th>Station ID</th><th>Role</th><th>T (Pre-Front)</th><th>T (Post-Front)</th><th>&Delta;T Velocity</th><th>Spatial Veto Status</th></tr>
            </thead>
            <tbody>
                <tr style="font-weight: bold;"><td>AWS-MUM-007</td><td>Target Center (C)</td><td>28.5&deg;C</td><td>20.3&deg;C</td><td>&minus;8.2&deg;C / 20 min</td><td>Initial Tier 1 Jump Trigger</td></tr>
                <tr><td>AWS-MUM-101</td><td>Sibling Peer (S₁)</td><td>28.3&deg;C</td><td>20.5&deg;C</td><td>&minus;7.8&deg;C / 20 min</td><td>Corroborates Front (&ge;2 peers)</td></tr>
                <tr><td>AWS-MUM-102</td><td>Sibling Peer (S₂)</td><td>28.7&deg;C</td><td>20.3&deg;C</td><td>&minus;8.4&deg;C / 20 min</td><td>Corroborates Front (&ge;2 peers)</td></tr>
                <tr><td>AWS-MUM-103</td><td>Sibling Peer (S₃)</td><td>28.4&deg;C</td><td>20.3&deg;C</td><td>&minus;8.1&deg;C / 20 min</td><td>Corroborates Front (&ge;2 peers)</td></tr>
            </tbody>
        </table>

        <div class="figure-box" style="margin: 4px 0;">
            <img src="assets/doc3_fig5_case2_front.png" alt="Case Study 2 Front Plot">
            <div class="figure-caption"><strong>Figure 5. Case Study 2 Aligned Sibling Traces.</strong> Target station drop (&minus;8.2&deg;C) corroborated by simultaneous drops across all 3 sibling peers (&minus;7.8&deg;C, &minus;8.4&deg;C, &minus;8.1&deg;C). Tier 5 Spatial Consensus vetoes the alert, confirming genuine meteorology. Source: Replay Case AWS-MUM Cluster.</div>
        </div>

        <div class="case-grid" style="margin-top: 4px;">
            <div>
                <strong>E. Detector Evidence:</strong> Tier 1 initially flags rate-of-change jump.<br>
                <strong>F. Peer / Spatial Evidence:</strong> Spatial Consensus Engine identifies 3/3 sibling peers with matching directional plunge (&minus;7.8&deg;C to &minus;8.4&deg;C).<br>
                <strong>G. Model Evidence:</strong> Model alert overridden by spatial engine.<br>
                <strong>H. SHAP Attribution:</strong> Not applicable (Overridden by Tier 5 Veto).
            </div>
            <div>
                <strong>I. Final Decision:</strong> <code>NORMAL (SPATIAL_VETO_CONSENSUS)</code><br>
                <div class="decision-box">STATUS: NORMAL | VETO: CONFIRMED | COMMON_MODE: TRUE</div>
                <strong>J. Human Explanation:</strong> "Rapid temperature drop (-8.2C) corroborated by 3/3 cluster sibling peers. Classified as genuine regional cold front."<br>
                <strong>K. Recovery:</strong> Observation assimilated into StationBuffer; zero false alarms triggered.
            </div>
        </div>
        <p style="font-size: 7.2pt; color: #475569; margin-top: 4px;"><strong>L. Evaluation Result:</strong> False Positive Successfully Suppressed. <strong>M. Interpretation:</strong> Prevents blinding NWP during severe storms. <strong>N. Limitation:</strong> Relies on cluster peer network density.</p>
    </div>

    <!-- Case Study 3 -->
    <div class="case-card">
        <div class="case-card-header">
            <span>Case Study 3 &mdash; Thermodynamic Multivariate Inconsistency &amp; SHAP Attribution (AWS-CHN-024)</span>
            <span class="badge-demonstrated">TIER 3/4 &amp; SHAP</span>
        </div>
        <p style="font-size: 7.5pt; margin-bottom: 4px;"><strong>A. Operational Scenario:</strong> Polymer membrane degradation causes temperature on AWS-CHN-024 to drift upward (+5.0&deg;C) while relative humidity remains locked at 65%, creating an unphysical psychrometric paradox.</p>
        
        <p style="font-size: 7.5pt; margin-bottom: 2px;"><strong>B. Input Data Snippet (Multivariate Psychrometric Telemetry):</strong></p>
        <table>
            <thead>
                <tr><th>Timestamp</th><th>Station</th><th>Temp (&deg;C)</th><th>Pressure (hPa)</th><th>RH (%)</th><th>VPD (hPa)</th><th>Mahalanobis D²</th></tr>
            </thead>
            <tbody>
                <tr><td>2025-01-14 10:00:00</td><td>AWS-CHN-024</td><td>25.2</td><td>1008.4</td><td>65.1%</td><td>11.2</td><td>2.14 (Normal)</td></tr>
                <tr><td>2025-01-14 11:00:00</td><td>AWS-CHN-024</td><td>27.8</td><td>1008.2</td><td>65.0%</td><td>13.1</td><td>8.45 (Normal)</td></tr>
                <tr style="background: #fee2e2; font-weight: bold;"><td>2025-01-14 12:00:00</td><td>AWS-CHN-024</td><td>32.0</td><td>1008.1</td><td>65.0%</td><td>16.8</td><td>24.18 (Critical Breached)</td></tr>
            </tbody>
        </table>

        <div class="figure-box" style="margin: 4px 0;">
            <img src="assets/doc3_fig6_case3_multivariate.png" alt="Case Study 3 Multivariate Plot">
            <div class="figure-caption"><strong>Figure 6. Case Study 3 Divergence &amp; SHAP Attribution.</strong> Left: Dual-axis plot of temperature upward drift vs. static humidity. Right: SHAP feature importance identifying <code>temp_c_dev</code> (34%) and <code>vpd_deficit</code> (28%) as primary anomaly drivers. Source: Replay Case AWS-CHN-024.</div>
        </div>

        <div class="case-grid" style="margin-top: 4px;">
            <div>
                <strong>E. Detector Evidence:</strong> Tier 3 Mahalanobis D² = 24.18 (threshold: 16.27, p = 2.3 &times; 10<sup>&minus;5</sup>).<br>
                <strong>F. Peer / Spatial Evidence:</strong> Sibling stations show steady 26.0&deg;C &plusmn; 0.4&deg;C.<br>
                <strong>G. Model Evidence:</strong> Tier 4 Isolation Forest tail score z = 3.42.<br>
                <strong>H. SHAP Attribution:</strong> <code>temp_c_dev</code> (+34%), <code>vpd_deficit</code> (+28%), <code>temp_robust_scale</code> (+28%).
            </div>
            <div>
                <strong>I. Final Decision:</strong> <code>FAULT (TIER_3_MAHALANOBIS_CROSS_CHANNEL)</code><br>
                <div class="decision-box">STATUS: FAULT | TYPE: MULTIVARIATE_INCONSISTENCY | CONFIDENCE: 92.0%</div>
                <strong>J. Human Explanation:</strong> "Thermodynamic inconsistency: Temperature (+32.0C) unphysically diverged from Relative Humidity (65%), causing severe VPD deficit."<br>
                <strong>K. Recovery:</strong> Quarantined; system issues targeted maintenance ticket for temperature sensor.
            </div>
        </div>
        <p style="font-size: 7.2pt; color: #475569; margin-top: 4px;"><strong>L. Evaluation Result:</strong> True Positive (0 lag). <strong>M. Interpretation:</strong> Demonstrates cross-channel multivariate reasoning. <strong>N. Limitation:</strong> Requires valid multi-sensor coupling.</p>
    </div>

    <!-- Case Study 4 -->
    <div class="case-card">
        <div class="case-card-header">
            <span>Case Study 4 &mdash; Variance Collapse / Frozen Sensor Lockup (AWS-KOL-015)</span>
            <span class="badge-demonstrated">TIER 1 FROZEN</span>
        </div>
        <p style="font-size: 7.5pt; margin-bottom: 4px;"><strong>A. Operational Scenario:</strong> A spider web obstructs the barometer port at AWS-KOL-015, hard-locking pressure readings to 1012.40 hPa for 8 consecutive hours while environmental barometric tides continue.</p>
        
        <p style="font-size: 7.5pt; margin-bottom: 2px;"><strong>B. Input Data Snippet (Pressure Flatline Trace):</strong></p>
        <table>
            <thead>
                <tr><th>Timestamp</th><th>Station</th><th>Pressure (hPa)</th><th>Target Var (4h)</th><th>Peers Mean Var (4h)</th><th>F-Ratio</th></tr>
            </thead>
            <tbody>
                <tr><td>2025-02-10 16:00:00</td><td>AWS-KOL-015</td><td>1012.40</td><td>0.000</td><td>1.842</td><td>0.000 (FROZEN)</td></tr>
                <tr><td>2025-02-10 17:00:00</td><td>AWS-KOL-015</td><td>1012.40</td><td>0.000</td><td>1.912</td><td>0.000 (FROZEN)</td></tr>
                <tr><td>2025-02-10 18:00:00</td><td>AWS-KOL-015</td><td>1012.40</td><td>0.000</td><td>2.104</td><td>0.000 (FROZEN)</td></tr>
            </tbody>
        </table>

        <div class="figure-box" style="margin: 4px 0;">
            <img src="assets/doc3_fig7_case4_frozen.png" alt="Case Study 4 Frozen Plot">
            <div class="figure-caption"><strong>Figure 7. Case Study 4 Variance Collapse Trace.</strong> Target station pressure locked at 1012.40 hPa while sibling peers exhibit normal diurnal barometric tides (range ~2.8 hPa). Flagged by Tier 1 F-Ratio Variance Collapse. Source: Replay Case AWS-KOL-015.</div>
        </div>

        <div class="case-grid" style="margin-top: 4px;">
            <div>
                <strong>E. Detector Evidence:</strong> Tier 1 Frozen F-Ratio = 0.000 (threshold: 0.05, 5 consecutive identical rows).<br>
                <strong>F. Peer / Spatial Evidence:</strong> Sibling peers show active diurnal barometric tidal range (&gt;2.5 hPa).<br>
                <strong>G. Model Evidence:</strong> Bypassed (Specialist Tier 1 trigger).<br>
                <strong>H. SHAP Attribution:</strong> Not required (Deterministic zero-variance trigger).
            </div>
            <div>
                <strong>I. Final Decision:</strong> <code>FAULT (TIER_1_SPECIALIST_FROZEN)</code><br>
                <div class="decision-box">STATUS: FAULT | TYPE: FROZEN_VALUE | HEALTH: OFFLINE</div>
                <strong>J. Human Explanation:</strong> "Zero-variance pressure lockup (1012.40 hPa) detected over 5 consecutive intervals while sibling peers exhibit active diurnal fluctuation."<br>
                <strong>K. Recovery:</strong> SensorHealthTracker transitions station to OFFLINE; requires clean streak of 3 valid readings to recover.
            </div>
        </div>
        <p style="font-size: 7.2pt; color: #475569; margin-top: 4px;"><strong>L. Evaluation Result:</strong> True Positive (5-row detection threshold). <strong>M. Interpretation:</strong> Protects against silent mechanical lockups. <strong>N. Limitation:</strong> Requires active diurnal environmental noise.</p>
    </div>

    <h1>5. Evaluation Limitations &amp; Reproducibility Guide</h1>
    <p><strong>Controlled vs. Field Boundary:</strong> The benchmark metrics (97.27% recall, 72.35% precision) were evaluated against synthetically injected hardware failure events superimposed over clean historical baselines. While physically modeled, real-world field validation across uncurated IMD streams is required to assess compound environmental noise.</p>
    <p><strong>Reproducibility Protocol:</strong> Execute <code>python scripts/run_authoritative_benchmark.py --seed 71001</code> to regenerate the authoritative scorecard from the locked evaluation corpus.</p>

    <h1>6. References</h1>
    <ul>
        <li><strong>[E01]</strong> SkyGuard AI Authoritative 7-Seed Scorecard Artifact (<code>calibration_seed_71001_full_audit_v8/summary.json</code>).</li>
        <li><strong>[M01]</strong> Liu, F. T., et al. "Isolation Forest." <em>IEEE ICDM</em>, 2008.</li>
        <li><strong>[M02]</strong> Page, E. S. "Continuous Inspection Schemes." <em>Biometrika</em>, 1954.</li>
        <li><strong>[M03]</strong> Lundberg, S. M., &amp; Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." <em>NeurIPS</em>, 2017.</li>
        <li><strong>[R01]</strong> WMO. <em>Guide to Instruments and Methods of Observation (WMO-No. 8)</em>, Volume III.</li>
    </ul>
</body>
</html>"""

def compile_pdf(html_content, base_filename):
    html_file = os.path.join(DOCS_DIR, f"{base_filename}.html")
    pdf_file = os.path.join(DOCS_DIR, f"{base_filename}.pdf")
    alt_pdf_file = os.path.join(ALT_DOCS_DIR, f"{base_filename}.pdf")
    
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    cmd = [
        EDGE_PATH,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_file}",
        html_file
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    # Mirror into alternate directory
    if os.path.exists(pdf_file):
        with open(pdf_file, "rb") as f_src, open(alt_pdf_file, "wb") as f_dst:
            f_dst.write(f_src.read())
            
    print(f"Compiled: {pdf_file} | Size: {os.path.getsize(pdf_file) if os.path.exists(pdf_file) else 0} bytes")
    return os.path.exists(pdf_file)

if __name__ == "__main__":
    print("=== Compiling Final Publication-Grade SkyGuard Documentation Suite ===")
    ok1 = compile_pdf(build_doc1(), "SkyGuard_Document_1_External_Research_Impact_FINAL")
    ok2 = compile_pdf(build_doc2(), "SkyGuard_Document_2_Technical_Methodology_Architecture_UseCases_FINAL")
    ok3 = compile_pdf(build_doc3(), "SkyGuard_Document_3_Experimental_Performance_Casebook_FINAL")
    print(f"=== Compilation Finished: Doc1={ok1}, Doc2={ok2}, Doc3={ok3} ===")
