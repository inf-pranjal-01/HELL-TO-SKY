import os

ASSETS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS\assets"

# -------------------------------------------------------------
# DOC 1 FIG 4: Impact & False Alarm Suppression Flow
# -------------------------------------------------------------
doc1_fig4 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 160" width="100%" height="160">
  <defs>
    <marker id="arr2" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 8 5 L 0 9 z" fill="#64748b" />
    </marker>
  </defs>
  <rect width="100%" height="100%" fill="#ffffff" rx="8" />

  <g transform="translate(15, 20)">
    <!-- Step 1: Raw Observations -->
    <rect x="0" y="20" width="180" height="90" rx="6" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>
    <rect x="0" y="20" width="180" height="22" rx="6" fill="#334155"/>
    <text x="90" y="35" fill="#ffffff" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">1. Continuous Ingestion</text>
    <text x="90" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="8" text-anchor="middle">1,000 National AWS</text>
    <text x="90" y="76" fill="#64748b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">96,000 Obs / Day</text>
    <text x="90" y="94" fill="#dc2626" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">~960 Raw Alerts (1% Noise)</text>

    <!-- Arrow 1 -> 2 -->
    <line x1="185" y1="65" x2="225" y2="65" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr2)"/>

    <!-- Step 2: Automated Arbitration -->
    <rect x="230" y="10" width="200" height="110" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="2"/>
    <rect x="230" y="10" width="200" height="22" rx="6" fill="#1e3a8a"/>
    <text x="330" y="25" fill="#ffffff" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">2. Automated QC &amp; Spatial Veto</text>
    <text x="330" y="48" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="8" font-weight="bold" text-anchor="middle">• Tier 0-4 Physics &amp; ML Isolation</text>
    <text x="330" y="66" fill="#334155" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">• Tier 5 Sibling Peer Corroboration</text>
    <text x="330" y="84" fill="#059669" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">768 False Alarms Suppressed (80%)</text>
    <text x="330" y="102" fill="#475569" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Sub-2ms Algorithmic Execution</text>

    <!-- Arrow 2 -> 3 -->
    <line x1="435" y1="65" x2="475" y2="65" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr2)"/>

    <!-- Step 3: Actionable Output -->
    <rect x="480" y="20" width="180" height="90" rx="6" fill="#f0fdf4" stroke="#86efac" stroke-width="1.5"/>
    <rect x="480" y="20" width="180" height="22" rx="6" fill="#047857"/>
    <text x="570" y="35" fill="#ffffff" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">3. High-Fidelity Triage</text>
    <text x="570" y="60" fill="#166534" font-family="Inter, sans-serif" font-size="8" font-weight="bold" text-anchor="middle">192 Valid Hardware Faults</text>
    <text x="570" y="76" fill="#334155" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">SHAP Diagnostic Attribution</text>
    <text x="570" y="94" fill="#059669" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">Zero Baseline Pollution</text>

    <!-- Arrow 3 -> 4 -->
    <line x1="665" y1="65" x2="705" y2="65" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr2)"/>

    <!-- Step 4: Operational Benefit -->
    <rect x="710" y="20" width="160" height="90" rx="6" fill="#fdf4ff" stroke="#f0abfc" stroke-width="1.5"/>
    <rect x="710" y="20" width="160" height="22" rx="6" fill="#86198f"/>
    <text x="790" y="35" fill="#ffffff" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">4. Defensible Benefit</text>
    <text x="790" y="56" fill="#701a75" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">3.2 Shifts Saved / Day</text>
    <text x="790" y="72" fill="#701a75" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">(25.6 Cumulative Hrs)</text>
    <text x="790" y="92" fill="#4a044e" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">Protects NWP Grids</text>
  </g>
</svg>"""

with open(os.path.join(ASSETS_DIR, "doc1_fig4_impact.svg"), "w", encoding="utf-8") as f:
    f.write(doc1_fig4)

# -------------------------------------------------------------
# DOC 2 FIG 4: Decision Flowchart
# -------------------------------------------------------------
doc2_fig4 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 220" width="100%" height="220">
  <defs>
    <marker id="arr3" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 8 5 L 0 9 z" fill="#475569" />
    </marker>
  </defs>
  <rect width="100%" height="100%" fill="#ffffff" rx="8" />

  <text x="450" y="22" fill="#0f172a" font-family="Inter, sans-serif" font-size="11" font-weight="bold" text-anchor="middle">SEQUENTIAL DECISION ARBITRATION FLOW (model/detect.py: DecisionEngine.decide)</text>

  <!-- Step 1 -->
  <g transform="translate(15, 45)">
    <rect width="125" height="150" rx="6" fill="#fee2e2" stroke="#ef4444"/>
    <text x="62" y="20" fill="#991b1b" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">Step 1: Tier 0 Invariant</text>
    <text x="62" y="45" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Rail: 0.0V / ADC cap</text>
    <text x="62" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">T ∉ [-40, 60°C]</text>
    <text x="62" y="75" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">P ∉ [800, 1100 hPa]</text>
    <line x1="10" y1="90" x2="115" y2="90" stroke="#f87171"/>
    <text x="62" y="110" fill="#b91c1c" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">If True → FAULT</text>
    <text x="62" y="125" fill="#7f1d1d" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Immediate Quarantine</text>
  </g>

  <line x1="145" y1="120" x2="165" y2="120" stroke="#475569" stroke-width="1.5" marker-end="url(#arr3)"/>

  <!-- Step 2 -->
  <g transform="translate(170, 45)">
    <rect width="125" height="150" rx="6" fill="#ffedd5" stroke="#f97316"/>
    <text x="62" y="20" fill="#9a3412" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">Step 2: Tier 1 Specialist</text>
    <text x="62" y="45" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Spike Jump LLR &gt; 5σ</text>
    <text x="62" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Frozen F-Ratio Collapse</text>
    <text x="62" y="75" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">(4h Target vs Peers)</text>
    <line x1="10" y1="90" x2="115" y2="90" stroke="#fdba74"/>
    <text x="62" y="110" fill="#c2410c" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">If True → FAULT</text>
    <text x="62" y="125" fill="#7c2d12" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Specialist Fast Trigger</text>
  </g>

  <line x1="300" y1="120" x2="320" y2="120" stroke="#475569" stroke-width="1.5" marker-end="url(#arr3)"/>

  <!-- Step 3 -->
  <g transform="translate(325, 45)">
    <rect width="125" height="150" rx="6" fill="#fef9c3" stroke="#eab308"/>
    <text x="62" y="20" fill="#854d0e" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">Step 3: Tier 2 SPRT</text>
    <text x="62" y="45" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Pre-Whitened Residual</text>
    <text x="62" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Sequential CUSUM</text>
    <text x="62" y="75" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Cumulative S_t &gt; h</text>
    <line x1="10" y1="90" x2="115" y2="90" stroke="#fde047"/>
    <text x="62" y="110" fill="#a16207" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">If True → FAULT</text>
    <text x="62" y="125" fill="#713f12" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Low-SNR Drift Catch</text>
  </g>

  <line x1="455" y1="120" x2="475" y2="120" stroke="#475569" stroke-width="1.5" marker-end="url(#arr3)"/>

  <!-- Step 4 -->
  <g transform="translate(480, 45)">
    <rect width="125" height="150" rx="6" fill="#e0e7ff" stroke="#6366f1"/>
    <text x="62" y="20" fill="#3730a3" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">Step 4: Tier 3 Mahalanobis</text>
    <text x="62" y="45" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">3D Distance D² (T,P,RH)</text>
    <text x="62" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Clausius-Clapeyron</text>
    <text x="62" y="75" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">p-value &lt; 10⁻³</text>
    <line x1="10" y1="90" x2="115" y2="90" stroke="#a5b4fc"/>
    <text x="62" y="110" fill="#4338ca" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">If True → FAULT</text>
    <text x="62" y="125" fill="#312e81" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Thermodynamic Error</text>
  </g>

  <line x1="610" y1="120" x2="630" y2="120" stroke="#475569" stroke-width="1.5" marker-end="url(#arr3)"/>

  <!-- Step 5 -->
  <g transform="translate(635, 45)">
    <rect width="125" height="150" rx="6" fill="#f3e8ff" stroke="#a855f7"/>
    <text x="62" y="20" fill="#6b21a8" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">Step 5: Tier 4 IF Model</text>
    <text x="62" y="45" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">49-Feature Matrix</text>
    <text x="62" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">100 Isolation Trees</text>
    <text x="62" y="75" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Tail z_score &gt; 3.0</text>
    <line x1="10" y1="90" x2="115" y2="90" stroke="#d8b4fe"/>
    <text x="62" y="110" fill="#7e22ce" font-family="Inter, sans-serif" font-size="7.5" font-weight="bold" text-anchor="middle">If True → FAULT</text>
    <text x="62" y="125" fill="#581c87" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">SHAP Feature Attribution</text>
  </g>

  <line x1="765" y1="120" x2="785" y2="120" stroke="#475569" stroke-width="1.5" marker-end="url(#arr3)"/>

  <!-- Step 6 -->
  <g transform="translate(790, 45)">
    <rect width="95" height="150" rx="6" fill="#dcfce7" stroke="#22c55e"/>
    <text x="47" y="20" fill="#15803d" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">Step 6: Tier 5</text>
    <text x="47" y="45" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Spatial Veto</text>
    <text x="47" y="60" fill="#1e293b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">3 Sibling Peers</text>
    <line x1="8" y1="80" x2="87" y2="80" stroke="#86efac"/>
    <text x="47" y="100" fill="#166534" font-family="Inter, sans-serif" font-size="8" font-weight="bold" text-anchor="middle">NORMAL</text>
    <text x="47" y="116" fill="#166534" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Assimilated</text>
    <line x1="8" y1="126" x2="87" y2="126" stroke="#86efac"/>
    <text x="47" y="140" fill="#92400e" font-family="Inter, sans-serif" font-size="7" font-weight="bold" text-anchor="middle">AMBIGUOUS</text>
  </g>
</svg>"""

with open(os.path.join(ASSETS_DIR, "doc2_fig4_decision_flow.svg"), "w", encoding="utf-8") as f:
    f.write(doc2_fig4)

# -------------------------------------------------------------
# DOC 2 FIG 5: State Machine Lifecycle
# -------------------------------------------------------------
doc2_fig5 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 170" width="100%" height="170">
  <defs>
    <marker id="arr4" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 8 5 L 0 9 z" fill="#475569" />
    </marker>
  </defs>
  <rect width="100%" height="100%" fill="#ffffff" rx="8" />

  <text x="450" y="22" fill="#0f172a" font-family="Inter, sans-serif" font-size="11" font-weight="bold" text-anchor="middle">CAUSAL GROUND-TRUTH ISOLATION &amp; SENSOR HEALTH STATE MACHINE (model/state.py)</text>

  <g transform="translate(30, 45)">
    <!-- Node 1: Raw Ingestion -->
    <rect x="0" y="25" width="140" height="60" rx="6" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5"/>
    <text x="70" y="50" fill="#0f172a" font-family="Inter, sans-serif" font-size="9" font-weight="bold" text-anchor="middle">RAW INGESTION</text>
    <text x="70" y="68" fill="#64748b" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Unverified Telemetry (T,P,RH)</text>

    <!-- Arrow to Eval -->
    <line x1="145" y1="55" x2="195" y2="55" stroke="#475569" stroke-width="1.5" marker-end="url(#arr4)"/>

    <!-- Node 2: Arbitration -->
    <rect x="200" y="15" width="160" height="80" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="2"/>
    <text x="280" y="42" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="9.5" font-weight="bold" text-anchor="middle">DECISION ARBITER</text>
    <text x="280" y="60" fill="#334155" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">Tier 0-5 Priority Logic</text>
    <text x="280" y="76" fill="#334155" font-family="Inter, sans-serif" font-size="7.5" text-anchor="middle">3-Peer Spatial Consensus</text>

    <!-- Branch Up: Normal -->
    <path d="M 365 45 L 430 20 L 490 20" stroke="#16a34a" stroke-width="2" fill="none" marker-end="url(#arr4)"/>
    <text x="420" y="15" fill="#16a34a" font-family="Inter, sans-serif" font-size="8" font-weight="bold">NORMAL</text>

    <!-- Node 3: Trusted State -->
    <rect x="495" y="0" width="170" height="50" rx="6" fill="#f0fdf4" stroke="#86efac" stroke-width="1.5"/>
    <text x="580" y="22" fill="#166534" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">TRUSTED BASELINE</text>
    <text x="580" y="38" fill="#14532d" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Assimilated into StationBuffer deque</text>

    <!-- Branch Down: Fault -->
    <path d="M 365 75 L 430 95 L 490 95" stroke="#dc2626" stroke-width="2" fill="none" marker-end="url(#arr4)"/>
    <text x="420" y="108" fill="#dc2626" font-family="Inter, sans-serif" font-size="8" font-weight="bold">FAULT</text>

    <!-- Node 4: Quarantined -->
    <rect x="495" y="70" width="170" height="50" rx="6" fill="#fef2f2" stroke="#fca5a5" stroke-width="1.5"/>
    <text x="580" y="92" fill="#991b1b" font-family="Inter, sans-serif" font-size="8.5" font-weight="bold" text-anchor="middle">QUARANTINED STATE</text>
    <text x="580" y="108" fill="#7f1d1d" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">Causal Exclusion (Zero Baseline Pollution)</text>

    <!-- Health State Arrow -->
    <line x1="670" y1="95" x2="715" y2="95" stroke="#475569" stroke-width="1.5" marker-end="url(#arr4)"/>

    <!-- Node 5: Health Tracker -->
    <rect x="720" y="45" width="120" height="70" rx="6" fill="#fdf4ff" stroke="#d8b4fe" stroke-width="1.5"/>
    <text x="780" y="65" fill="#6b21a8" font-family="Inter, sans-serif" font-size="8" font-weight="bold" text-anchor="middle">HEALTH TRACKER</text>
    <text x="780" y="80" fill="#581c87" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">NORMAL (0 errors)</text>
    <text x="780" y="93" fill="#c2410c" font-family="Inter, sans-serif" font-size="7" text-anchor="middle">WARNING (1-2 errors)</text>
    <text x="780" y="106" fill="#b91c1c" font-family="Inter, sans-serif" font-size="7" font-weight="bold" text-anchor="middle">OFFLINE (&gt;3 errors)</text>
  </g>
</svg>"""

with open(os.path.join(ASSETS_DIR, "doc2_fig5_state_machine.svg"), "w", encoding="utf-8") as f:
    f.write(doc2_fig5)

print("All supplementary SVG diagrams successfully generated!")
