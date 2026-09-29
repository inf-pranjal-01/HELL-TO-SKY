import os

ASSETS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS\assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" width="100%" height="100%" style="background-color: #0f172a; font-family: 'Inter', -apple-system, sans-serif;">
  <defs>
    <linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#1e3a8a" />
      <stop offset="50%" stop-color="#3b82f6" />
      <stop offset="100%" stop-color="#1d4ed8" />
    </linearGradient>
    <linearGradient id="coreGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#1e293b" />
      <stop offset="100%" stop-color="#0f172a" />
    </linearGradient>
    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e293b" />
      <stop offset="100%" stop-color="#334155" />
    </linearGradient>
    <linearGradient id="dbGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#0284c7" />
      <stop offset="100%" stop-color="#0369a1" />
    </linearGradient>
    <linearGradient id="appGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#4d7c0f" />
      <stop offset="100%" stop-color="#3f6212" />
    </linearGradient>
    <linearGradient id="verdictGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#b91c1c" />
      <stop offset="50%" stop-color="#d97706" />
      <stop offset="100%" stop-color="#15803d" />
    </linearGradient>
    
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.4" />
    </filter>
    
    <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8" />
    </marker>
    <marker id="arrowGreen" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#4ade80" />
    </marker>
  </defs>

  <!-- OUTER SYSTEM FRAME (16:9 Aspect Ratio) -->
  <rect x="20" y="20" width="1560" height="860" rx="16" fill="#0f172a" stroke="#334155" stroke-width="2" />
  
  <!-- SYSTEM HEADER BANNER -->
  <rect x="40" y="35" width="1520" height="46" rx="8" fill="url(#headerGrad)" filter="url(#shadow)" />
  <text x="800" y="58" text-anchor="middle" fill="#ffffff" font-size="18" font-weight="800" letter-spacing="1">SKYGUARD AI SYSTEM — SYSTEM ARCHITECTURE</text>
  <text x="800" y="73" text-anchor="middle" fill="#93c5fd" font-size="11" font-weight="600">Intelligent Real-Time AWS Anomaly Detection &amp; Quality Control Pipeline</text>

  <!-- SECTION 1: OBSERVATION SOURCES -->
  <g transform="translate(50, 95)">
    <rect x="0" y="0" width="450" height="470" rx="12" fill="#1e293b" stroke="#475569" stroke-width="1.5" />
    <text x="20" y="26" fill="#38bdf8" font-size="13" font-weight="700" letter-spacing="0.5">1. OBSERVATION SOURCES</text>
    
    <!-- AWS Network Box -->
    <rect x="15" y="40" width="205" height="415" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1" />
    <text x="117" y="62" text-anchor="middle" fill="#f8fafc" font-size="12" font-weight="700">AWS NETWORK</text>
    <text x="117" y="80" text-anchor="middle" fill="#94a3b8" font-size="10">• 28 AWS STATIONS</text>
    <text x="117" y="94" text-anchor="middle" fill="#94a3b8" font-size="10">• 7 Regional Clusters</text>
    <text x="117" y="108" text-anchor="middle" fill="#94a3b8" font-size="10">• T / P / RH Telemetry</text>
    
    <circle cx="117" cy="135" r="14" fill="#1e3a8a" stroke="#3b82f6" stroke-width="1.5" />
    <text x="117" y="139" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">S</text>
    <text x="117" y="162" text-anchor="middle" fill="#cbd5e1" font-size="10" font-weight="600">Sensors Stream</text>

    <line x1="117" y1="172" x2="117" y2="200" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />

    <!-- ESP32 Module Box -->
    <rect x="25" y="202" width="185" height="135" rx="6" fill="#1e293b" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" />
    <text x="117" y="220" text-anchor="middle" fill="#fbbf24" font-size="10" font-weight="700">STATION-SIDE ESP32 MCU</text>
    <text x="117" y="234" text-anchor="middle" fill="#d1d5db" font-size="9">(Optional Edge Tier)</text>
    <text x="117" y="254" text-anchor="middle" fill="#9ca3af" font-size="9">• Physical Bound Checks</text>
    <text x="117" y="268" text-anchor="middle" fill="#9ca3af" font-size="9">• Electrical Fail-Low / Ground</text>
    <text x="117" y="282" text-anchor="middle" fill="#9ca3af" font-size="9">• TinyML Fixed-Point Q8.8</text>
    <text x="117" y="296" text-anchor="middle" fill="#9ca3af" font-size="9">• 512-Slot SRAM Ring Buffer</text>
    <text x="117" y="310" text-anchor="middle" fill="#9ca3af" font-size="9">• Edge Tagging &amp; Relay</text>

    <line x1="117" y1="337" x2="117" y2="440" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Open Meteo Box -->
    <rect x="230" y="40" width="205" height="415" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1" />
    <text x="332" y="62" text-anchor="middle" fill="#f8fafc" font-size="12" font-weight="700">OPEN-METEO API</text>
    <text x="332" y="80" text-anchor="middle" fill="#94a3b8" font-size="10">Replay &amp; Synthetic Stream</text>
    
    <rect x="245" y="105" width="175" height="45" rx="5" fill="#1e293b" stroke="#475569" stroke-width="1" />
    <text x="332" y="124" text-anchor="middle" fill="#e2e8f0" font-size="10">Meteorological Stream</text>
    <text x="332" y="138" text-anchor="middle" fill="#94a3b8" font-size="9">AWS-like Baseline</text>
    
    <line x1="332" y1="150" x2="332" y2="180" stroke="#38bdf8" stroke-width="1.5" marker-end="url(#arrow)" />
    
    <rect x="245" y="180" width="175" height="45" rx="5" fill="#1e293b" stroke="#ef4444" stroke-width="1" />
    <text x="332" y="199" text-anchor="middle" fill="#fca5a5" font-size="10">Controlled Anomaly Injector</text>
    <text x="332" y="213" text-anchor="middle" fill="#94a3b8" font-size="9">7 Fault Modes (Spike, Drift...)</text>

    <line x1="332" y1="225" x2="332" y2="255" stroke="#38bdf8" stroke-width="1.5" marker-end="url(#arrow)" />

    <rect x="245" y="255" width="175" height="50" rx="5" fill="#1e293b" stroke="#10b981" stroke-width="1" />
    <text x="332" y="275" text-anchor="middle" fill="#6ee7b7" font-size="10">Replay &amp; Benchmark Engine</text>
    <text x="332" y="291" text-anchor="middle" fill="#94a3b8" font-size="9">60,480 Evaluation Rows</text>

    <line x1="332" y1="305" x2="332" y2="440" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />
  </g>

  <!-- FLOW LINES TO CORE -->
  <path d="M 167 535 L 167 560 L 510 560 L 510 180 L 530 180" fill="none" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />
  <path d="M 382 535 L 382 560 L 510 560" fill="none" stroke="#38bdf8" stroke-width="2" />

  <!-- SECTION 2: SKYGUARD CORE (CENTRAL VM) -->
  <g transform="translate(520, 95)">
    <rect x="0" y="0" width="560" height="470" rx="12" fill="#1e293b" stroke="#3b82f6" stroke-width="2" filter="url(#shadow)" />
    <text x="20" y="26" fill="#60a5fa" font-size="13" font-weight="700" letter-spacing="0.5">2. SKYGUARD CORE (CENTRAL ENGINE / CLOUD VM)</text>
    
    <!-- Step 1: FastAPI Ingestion -->
    <rect x="25" y="42" width="510" height="42" rx="6" fill="#0f172a" stroke="#38bdf8" stroke-width="1.5" />
    <text x="280" y="68" text-anchor="middle" fill="#f8fafc" font-size="12" font-weight="700">FastAPI Ingestion / Stream Gateway &amp; Telemetry Parsing</text>

    <line x1="280" y1="84" x2="280" y2="105" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Step 2: State Manager -->
    <rect x="25" y="105" width="510" height="42" rx="6" fill="#0f172a" stroke="#818cf8" stroke-width="1.5" />
    <text x="280" y="131" text-anchor="middle" fill="#f8fafc" font-size="12" font-weight="700">State Manager &amp; Continuous Physical-Time Alignment (No Positional Shifts)</text>

    <line x1="280" y1="147" x2="280" y2="168" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Step 3: 49-Feature Engine -->
    <rect x="25" y="168" width="510" height="42" rx="6" fill="#0f172a" stroke="#a7f3d0" stroke-width="1.5" />
    <text x="280" y="194" text-anchor="middle" fill="#f8fafc" font-size="12" font-weight="700">49-Dimensional Multi-Scale Physical Feature Matrix Engine</text>

    <line x1="280" y1="210" x2="280" y2="231" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Step 4: 6-Tier Decision Engine -->
    <rect x="25" y="231" width="510" height="135" rx="8" fill="#0f172a" stroke="#f43f5e" stroke-width="1.5" />
    <text x="280" y="250" text-anchor="middle" fill="#fb7185" font-size="12" font-weight="800">DETERMINISTIC 6-TIER DECISION ENGINE</text>
    
    <g transform="translate(45, 260)" font-size="9.5" fill="#cbd5e1">
      <text x="0" y="14">• Tier 0: Hard Invariants &amp; Rail Limits</text>
      <text x="260" y="14">• Tier 3: 3D Mahalanobis Psychrometric</text>
      <text x="0" y="32">• Tier 1: Specialist Jump LLR &amp; Freeze</text>
      <text x="260" y="32">• Tier 4: Isolation Forest Ensemble</text>
      <text x="0" y="50">• Tier 2: Wald-Page Sequential SPRT</text>
      <text x="260" y="50">• Tier 5: Spatial Consensus Peer Veto</text>
      <text x="130" y="70" font-weight="700" fill="#f43f5e">Tier 6 Arbitration &amp; Priority Verdict Cascade</text>
    </g>

    <line x1="280" y1="366" x2="280" y2="385" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)" />

    <!-- Health & SHAP Split -->
    <rect x="25" y="385" width="240" height="35" rx="5" fill="#0f172a" stroke="#10b981" stroke-width="1" />
    <text x="145" y="407" text-anchor="middle" fill="#6ee7b7" font-size="10" font-weight="700">SENSOR HEALTH &amp; RECOVERY</text>

    <rect x="295" y="385" width="240" height="35" rx="5" fill="#0f172a" stroke="#c084fc" stroke-width="1" />
    <text x="415" y="407" text-anchor="middle" fill="#e9d5ff" font-size="10" font-weight="700">SHAP EXPLAINABILITY / X-RAY</text>

    <path d="M 145 420 L 145 432 L 280 432 L 280 438" fill="none" stroke="#38bdf8" stroke-width="1.5" />
    <path d="M 415 420 L 415 432 L 280 432" fill="none" stroke="#38bdf8" stroke-width="1.5" />

    <!-- Final Verdict Box -->
    <rect x="25" y="432" width="510" height="32" rx="6" fill="url(#verdictGrad)" filter="url(#shadow)" />
    <text x="280" y="453" text-anchor="middle" fill="#ffffff" font-size="11" font-weight="800">FINAL VERDICT: NORMAL | FAULT | AMBIGUOUS (+ Severity + SHAP)</text>
  </g>

  <!-- FLOW LINES FROM CORE TO PERSISTENCE & DASHBOARD -->
  <path d="M 800 565 L 800 585 L 1310 585 L 1310 95" fill="none" stroke="#38bdf8" stroke-width="2" />
  <path d="M 800 565 L 800 585 L 1100 585 L 1100 95" fill="none" stroke="#38bdf8" stroke-width="2" />

  <!-- SECTION 3: PERSISTENCE LAYER -->
  <g transform="translate(1100, 95)">
    <rect x="0" y="0" width="220" height="470" rx="12" fill="#1e293b" stroke="#0284c7" stroke-width="1.5" />
    <text x="110" y="26" text-anchor="middle" fill="#38bdf8" font-size="12" font-weight="700" letter-spacing="0.5">3. PERSISTENCE</text>
    
    <!-- TimescaleDB Cylinder Graphic -->
    <g transform="translate(30, 45)">
      <path d="M 0 15 A 80 15 0 0 0 160 15 L 160 80 A 80 15 0 0 1 0 80 Z" fill="url(#dbGrad)" />
      <ellipse cx="80" cy="15" rx="80" ry="15" fill="#38bdf8" stroke="#0284c7" stroke-width="1.5" />
      <text x="80" y="18" text-anchor="middle" fill="#0f172a" font-size="11" font-weight="800">TimescaleDB</text>
      <text x="80" y="55" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">PRIMARY STORE</text>
    </g>

    <g transform="translate(20, 150)" font-size="9.5" fill="#cbd5e1">
      <text x="0" y="15">• Raw Sensor Telemetry</text>
      <text x="0" y="32">• System Quality Verdicts</text>
      <text x="0" y="49">• Sensor Health &amp; Events</text>
      <text x="0" y="66">• Historical Baseline Data</text>
      <text x="0" y="83">• SHAP Attribution Vectors</text>
    </g>

    <rect x="15" y="260" width="190" height="195" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1" />
    <text x="110" y="280" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="700">LOCAL CSV &amp; FAILOVER</text>
    <text x="110" y="300" text-anchor="middle" fill="#64748b" font-size="8.5">• Runtime StationBuffer Deque</text>
    <text x="110" y="316" text-anchor="middle" fill="#64748b" font-size="8.5">• 512-Slot Causal History</text>
    <text x="110" y="332" text-anchor="middle" fill="#64748b" font-size="8.5">• Offline State Quarantine</text>
    <text x="110" y="348" text-anchor="middle" fill="#64748b" font-size="8.5">• Backup Audit Logging</text>
  </g>

  <!-- SECTION 4: OPERATOR / APPLICATION LAYER -->
  <g transform="translate(1340, 95)">
    <rect x="0" y="0" width="220" height="470" rx="12" fill="#1e293b" stroke="#84cc16" stroke-width="1.5" />
    <text x="110" y="26" text-anchor="middle" fill="#a3e635" font-size="12" font-weight="700" letter-spacing="0.5">4. OPERATOR DASHBOARD</text>
    
    <rect x="15" y="45" width="190" height="50" rx="6" fill="url(#appGrad)" />
    <text x="110" y="66" text-anchor="middle" fill="#ffffff" font-size="11" font-weight="800">VERCEL HOSTED UI</text>
    <text x="110" y="82" text-anchor="middle" fill="#d9f99d" font-size="9">SkyGuard Operations Suite</text>

    <g transform="translate(20, 115)" font-size="9.5" fill="#cbd5e1">
      <text x="0" y="15">• Real-Time Live Monitoring</text>
      <text x="0" y="32">• Anomaly Alert Stream</text>
      <text x="0" y="49">• Interactive Time Charts</text>
      <text x="0" y="66">• Anomaly Map Markers</text>
      <text x="0" y="83">• Station Health Index</text>
      <text x="0" y="100">• SHAP Diagnostic X-Ray</text>
      <text x="0" y="117">• Maintenance Dispatch</text>
      <text x="0" y="134">• WMO Benchmark Reports</text>
    </g>

    <rect x="15" y="270" width="190" height="185" rx="6" fill="#0f172a" stroke="#4d7c0f" stroke-width="1" />
    <text x="110" y="292" text-anchor="middle" fill="#bef264" font-size="10" font-weight="700">API &amp; STREAM GATEWAY</text>
    <text x="110" y="315" text-anchor="middle" fill="#a3e635" font-size="9 font-weight="700">REST API</text>
    <text x="110" y="330" text-anchor="middle" fill="#94a3b8" font-size="8.5">Endpoints for NWP &amp; ERP</text>
    <text x="110" y="355" text-anchor="middle" fill="#a3e635" font-size="9 font-weight="700">WEBSOCKET SERVER</text>
    <text x="110" y="370" text-anchor="middle" fill="#94a3b8" font-size="8.5">Real-Time Streaming Push</text>
  </g>

  <!-- SECTION 5: MODE ISOLATION FOOTER BANNER -->
  <g transform="translate(50, 580)">
    <rect x="0" y="0" width="1510" height="280" rx="12" fill="#1e293b" stroke="#64748b" stroke-width="1.5" />
    <text x="755" y="26" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="800" letter-spacing="1">5. STRICT OPERATIONAL MODE ISOLATION</text>
    
    <!-- Live Path Box -->
    <rect x="30" y="45" width="700" height="210" rx="8" fill="#0f172a" stroke="#3b82f6" stroke-width="1.5" />
    <rect x="30" y="45" width="700" height="32" rx="8" fill="#1e3a8a" />
    <text x="380" y="66" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="800">LIVE OPERATIONAL PATH</text>
    
    <g transform="translate(50, 95)" font-size="10.5" fill="#cbd5e1">
      <text x="0" y="20">• Live AWS Telemetry Ingestion from Physical Weather Sensors</text>
      <text x="0" y="42">• Real-Time StationBuffer History &amp; Continuous Diurnal Baseline Alignment</text>
      <text x="0" y="64">• Live Operational Event Logging to TimescaleDB Primary Store</text>
      <text x="0" y="86">• Real-Time WebSocket Alerts to Vercel Operations Dashboard</text>
      <text x="0" y="108">• Live Causal Health Score Decay &amp; Automated Technician Dispatch</text>
      <text x="0" y="130" font-weight="700" fill="#60a5fa">Operational Guarantee: Zero cross-talk or contamination with replay state</text>
    </g>

    <!-- Replay / Benchmark Path Box -->
    <rect x="780" y="45" width="700" height="210" rx="8" fill="#0f172a" stroke="#10b981" stroke-width="1.5" />
    <rect x="780" y="45" width="700" height="32" rx="8" fill="#065f46" />
    <text x="1130" y="66" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="800">REPLAY &amp; BENCHMARK EVALUATION PATH</text>

    <g transform="translate(800, 95)" font-size="10.5" fill="#cbd5e1">
      <text x="0" y="20">• Historical Open-Meteo Baseline Replay (60,480 Physical Readings)</text>
      <text x="0" y="42">• Controlled Synthetic Anomaly Injection Across 7 Fault Modes</text>
      <text x="0" y="64">• Isolated Replay State Buffers &amp; Chronological Evaluation Loop</text>
      <text x="0" y="86">• Bipartite Overlap Matching &amp; Episodic WMO Contract Scoring</text>
      <text x="0" y="108">• Authoritative 7-Seed Diagnostic Benchmark &amp; Scorecard Generation</text>
      <text x="0" y="130" font-weight="700" fill="#34d399">Benchmark Guarantee: 100% deterministic reproducibility across host CPUs</text>
    </g>
  </g>
</svg>
"""

svg_path = os.path.join(ASSETS_DIR, "doc2_fig1_architecture.svg")
with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg_content)

print(f"Successfully generated 16:9 publication-grade SVG architecture diagram: {svg_path}")
