import os
import subprocess
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# Output directories
DOCS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS"
ALT_DOCS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANTIGRAVITY RESEARCH DOCUMENT"
ASSETS_DIR = os.path.join(DOCS_DIR, "assets")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(ALT_DOCS_DIR, exist_ok=True)

# Set matplotlib style for professional publication graphics
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#cbd5e1'
plt.rcParams['axes.linewidth'] = 1.2

def generate_scene1_chart():
    """Generates Figure for Scene 1: Single Station Isolated View with False-Positive Alert"""
    time = [datetime(2026, 9, 29, 12, 0) + timedelta(minutes=15*i) for i in range(17)]
    
    # Synthetic clean atmospheric trajectory until t=10 (14:30)
    temp = np.array([27.2, 27.5, 27.8, 28.1, 28.3, 28.5, 28.4, 28.3, 28.2, 28.1, 34.5, 35.1, 34.8, 33.9, 32.5, 31.0, 30.2])
    pressure = np.array([1012.5, 1012.3, 1012.1, 1011.8, 1011.5, 1011.2, 1011.0, 1010.8, 1010.5, 1010.2, 1004.1, 1003.5, 1004.0, 1005.2, 1006.8, 1008.0, 1009.5])
    humidity = np.array([65.0, 64.5, 64.0, 63.5, 63.0, 62.5, 63.0, 63.8, 64.5, 65.0, 84.0, 88.5, 87.0, 82.5, 78.0, 74.5, 71.0])

    fig, ax1 = plt.subplots(figsize=(10, 4.5), dpi=300)
    
    ax2 = ax1.twinx()
    
    # Plot Temperature and Pressure
    line1 = ax1.plot(time, temp, color='#dc2626', linewidth=2.5, marker='o', markersize=4, label='Temp (°C)')
    line2 = ax2.plot(time, pressure, color='#0284c7', linewidth=2.5, marker='s', markersize=4, linestyle='--', label='Pressure (hPa)')
    
    # Event Timestamp T (14:30)
    t_event = time[10]
    
    # Highlight anomaly zone
    ax1.axvspan(time[9], time[12], color='#fecaca', alpha=0.35, label='Spike Window')
    ax1.axvline(t_event, color='#b91c1c', linestyle=':', linewidth=2)
    
    # Annotations
    ax1.annotate('SUDDEN TEMP SPIKE (+6.4°C)\nSingle-Station Verdict: ANOMALY', 
                 xy=(t_event, 34.5), xytext=(time[5], 33.5),
                 arrowprops=dict(facecolor='#b91c1c', shrink=0.08, width=2, headwidth=8),
                 fontsize=9, fontweight='bold', color='#7f1d1d',
                 bbox=dict(boxstyle='round,pad=0.5', facecolor='#fef2f2', edgecolor='#b91c1c', lw=1.5))
    
    ax1.set_xlabel('Timestamp (HH:MM)', fontsize=10, fontweight='bold', labelpad=8)
    ax1.set_ylabel('Temperature (°C)', fontsize=10, fontweight='bold', color='#dc2626')
    ax2.set_ylabel('Atmospheric Station Pressure (hPa)', fontsize=10, fontweight='bold', color='#0284c7')
    
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.grid(True, linestyle=':', alpha=0.6)
    
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', framealpha=0.9)
    
    plt.title('Station 01 (Isolated View) — Telemetry Ingestion Stream at Timestamp T = 14:30', 
              fontsize=11, fontweight='bold', pad=12, color='#0f172a')
    
    plt.tight_layout()
    chart_path = os.path.join(ASSETS_DIR, "scene1_single_station.png")
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    return chart_path

def generate_scene2_chart():
    """Generates Figure for Scene 2: Multi-Station Spatial Peer Consensus View"""
    time = [datetime(2026, 9, 29, 12, 0) + timedelta(minutes=15*i) for i in range(17)]
    
    # Station 01 (Primary)
    temp1 = np.array([27.2, 27.5, 27.8, 28.1, 28.3, 28.5, 28.4, 28.3, 28.2, 28.1, 34.5, 35.1, 34.8, 33.9, 32.5, 31.0, 30.2])
    # Station 02 (12 km North)
    temp2 = np.array([26.8, 27.1, 27.4, 27.7, 27.9, 28.1, 28.0, 27.9, 27.8, 27.7, 33.8, 34.6, 34.2, 33.4, 32.1, 30.6, 29.8])
    # Station 03 (24 km East)
    temp3 = np.array([27.5, 27.8, 28.0, 28.3, 28.5, 28.7, 28.6, 28.5, 28.4, 28.3, 34.1, 34.9, 34.5, 33.7, 32.3, 30.9, 30.0])

    fig, axes = plt.subplots(3, 1, figsize=(10, 6.5), sharex=True, dpi=300)
    
    t_event = time[10]
    
    stations = [
        ('Station 01 (Primary AWS Node)', temp1, '#dc2626', axes[0]),
        ('Station 02 (Regional Spatial Peer — 12 km North)', temp2, '#2563eb', axes[1]),
        ('Station 03 (Regional Spatial Peer — 24 km East)', temp3, '#059669', axes[2])
    ]
    
    for name, temp_data, color, ax in stations:
        ax.plot(time, temp_data, color=color, linewidth=2.2, marker='o', markersize=3.5, label=f'{name} Temp (°C)')
        ax.axvspan(time[9], time[12], color='#bbf7d0', alpha=0.45)
        ax.axvline(t_event, color='#16a34a', linestyle='--', linewidth=1.8)
        ax.set_ylabel('Temp (°C)', fontsize=8.5, fontweight='bold')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
        ax.set_title(name, fontsize=9.5, fontweight='bold', color='#1e293b', loc='left', pad=4)

    axes[0].annotate('SIMULTANEOUS ATMOSPHERIC SHIFT ACROSS ALL PEERS\nSpatial Verdict: VETOED TO NORMAL (Storm Front)', 
                     xy=(t_event, 34.5), xytext=(time[4], 32.0),
                     arrowprops=dict(facecolor='#16a34a', shrink=0.08, width=2, headwidth=8),
                     fontsize=8.5, fontweight='bold', color='#14532d',
                     bbox=dict(boxstyle='round,pad=0.5', facecolor='#f0fdf4', edgecolor='#16a34a', lw=1.5))

    axes[2].set_xlabel('Timestamp (HH:MM)', fontsize=9.5, fontweight='bold', labelpad=6)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    
    plt.suptitle('Multi-Station Regional Spatial Peer Consensus — 50 km Microclimate Cluster Verification', 
                 fontsize=11.5, fontweight='bold', y=0.98, color='#0f172a')
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    chart_path = os.path.join(ASSETS_DIR, "scene2_multi_station.png")
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    return chart_path

def build_demo_storyboard_html():
    css_styles = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
    
    @page {
        size: A4 portrait;
        margin: 14mm 14mm 14mm 14mm;
        @bottom-center {
            content: "Page " counter(page) " of " counter(pages);
            font-family: 'Inter', sans-serif;
            font-size: 8pt;
            color: #64748b;
        }
    }
    
    body {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 8.8pt;
        line-height: 1.45;
        color: #1e293b;
        background: #ffffff;
        margin: 0;
        padding: 0;
    }
    
    .header-banner {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        color: #ffffff;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 12px;
    }
    
    .header-badge {
        font-size: 7pt;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        background: rgba(255,255,255,0.2);
        padding: 2px 6px;
        border-radius: 3px;
        display: inline-block;
        margin-bottom: 4px;
    }
    
    .header-title {
        font-size: 16pt;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.3px;
    }
    
    .header-subtitle {
        font-size: 9.5pt;
        color: #93c5fd;
        font-weight: 500;
        margin-top: 2px;
    }
    
    .script-box {
        background: #f8fafc;
        border: 1.5px solid #cbd5e1;
        border-left: 4px solid #3b82f6;
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 12px;
    }
    
    .script-label {
        font-size: 8pt;
        font-weight: 800;
        color: #1e3a8a;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 4px;
    }
    
    .script-text {
        font-size: 9pt;
        color: #0f172a;
        font-style: italic;
        line-height: 1.4;
    }
    
    .figure-container {
        border: 1px solid #e2e8f0;
        background: #ffffff;
        border-radius: 6px;
        padding: 10px;
        text-align: center;
        margin-bottom: 12px;
    }
    
    .figure-container img {
        width: 100%;
        max-height: 340px;
        object-fit: contain;
        border-radius: 4px;
    }
    
    .verdict-card {
        padding: 10px 14px;
        border-radius: 6px;
        font-size: 8.5pt;
        margin-top: 8px;
    }
    
    .verdict-warn {
        background: #fef2f2;
        border: 1.5px solid #fecaca;
        border-left: 4px solid #dc2626;
        color: #7f1d1d;
    }
    
    .verdict-pass {
        background: #f0fdf4;
        border: 1.5px solid #bbf7d0;
        border-left: 4px solid #16a34a;
        color: #14532d;
    }
    
    .grid-2col {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-top: 10px;
    }
    
    .info-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 8px 12px;
    }
    
    .info-card h4 {
        margin: 0 0 4px 0;
        font-size: 8.5pt;
        color: #1e3a8a;
        font-weight: 700;
    }
    
    .page-break {
        page-break-before: always;
    }
    """
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SkyGuard AI — Demonstration Script &amp; Visual Storyboard Blueprint</title>
    <style>{css_styles}</style>
</head>
<body>

    <!-- PAGE 1: SCENE 1 (SINGLE STATION ISOLATED VIEW) -->
    <div class="header-banner">
        <div class="header-badge">Demonstration Video Script &amp; Storyboard Blueprint — Page 1 of 2</div>
        <div class="header-title">Scene 1: Isolated Single-Station Observation (The False Anomaly Trap)</div>
        <div class="header-subtitle">Demonstrates how single-station threshold detectors trigger false disaster alerts during extreme local events</div>
    </div>

    <div class="script-box">
        <div class="script-label">🎙️ Presenter Script &amp; Voiceover Narrative:</div>
        <div class="script-text">
            "Look at the live stream on screen. Here is <strong>Station 01</strong> monitoring surface Ambient Temperature, Station Pressure, and Relative Humidity. At timestamp <strong>T = 14:30</strong>, notice how the temperature reading suddenly spikes by <strong>+6.4°C</strong> in a single observation interval! In isolation, traditional single-station algorithms look at this sharp excursion and immediately flag it as a sensor failure or hardware glitch. But is it really a fault?"
        </div>
    </div>

    <div class="figure-container">
        <img src="assets/scene1_single_station.png" alt="Scene 1 Single Station Graph">
    </div>

    <div class="verdict-card verdict-warn">
        <strong style="font-size: 9.5pt;">🚨 Traditional Single-Station Detector Verdict: FAULT DETECTED (FALSE ALARM)</strong><br>
        <strong>Why it fails:</strong> Single-station algorithms evaluate observations in total isolation. Without regional context, a sharp physical temperature jump is algorithmically indistinguishable from an electrical spike or sensor latch-up.
    </div>

    <div class="grid-2col">
        <div class="info-card">
            <h4>Physical Telemetry Parameters (Station 01)</h4>
            <ul style="margin: 0; padding-left: 16px; font-size: 8pt;">
                <li><strong>Ambient Temperature (T):</strong> 28.1°C &rarr; 34.5°C at T = 14:30</li>
                <li><strong>Station Pressure (P):</strong> 1010.2 hPa &rarr; 1004.1 hPa (Barometric Dip)</li>
                <li><strong>Relative Humidity (RH):</strong> 65.0% &rarr; 84.0% (Moisture Inflow)</li>
            </ul>
        </div>
        <div class="info-card">
            <h4>Demonstrated System Limitation</h4>
            <p style="margin: 0; font-size: 8pt;">Demonstrates why simple single-point rules trigger massive operator alert fatigue during dynamic weather events, proving the absolute necessity of spatial peer consensus.</p>
        </div>
    </div>

    <!-- PAGE 2: SCENE 2 (MULTI-STATION SPATIAL CONSENSUS VIEW) -->
    <div class="page-break"></div>

    <div class="header-banner" style="background: linear-gradient(135deg, #065f46 0%, #059669 100%);">
        <div class="header-badge">Demonstration Video Script &amp; Storyboard Blueprint — Page 2 of 2</div>
        <div class="header-title">Scene 2: Zoomed-Out Multi-Station Spatial Peer Consensus View</div>
        <div class="header-subtitle">SkyGuard AI's Tier 5 Spatial Engine cross-checks regional peers to distinguish genuine weather fronts from faults</div>
    </div>

    <div class="script-box" style="border-left-color: #059669;">
        <div class="script-label" style="color: #065f46;">🎙️ Presenter Script &amp; Voiceover Narrative:</div>
        <div class="script-text">
            "Now let's zoom out on screen to get broader spatial context! We bring in two neighboring stations from the same 50 km microclimate cluster: <strong>Station 02</strong> (12 km North) and <strong>Station 03</strong> (24 km East). Notice that at the exact same timestamp <strong>T = 14:30</strong>, both Station 02 and Station 03 record the exact same rapid thermodynamic shift! Because multiple independent physical sensors agree, this is NOT a hardware fault—it is a <strong>genuine regional weather event</strong>, such as an approaching storm front or gust outflow! <strong>SkyGuard AI's Tier 5 Spatial Consensus Engine</strong> automatically cross-checks regional peers and <strong>VETOES the false alert back to NORMAL</strong>."
        </div>
    </div>

    <div class="figure-container">
        <img src="assets/scene2_multi_station.png" alt="Scene 2 Multi Station Graph">
    </div>

    <div class="verdict-card verdict-pass">
        <strong style="font-size: 9.5pt;">✅ SkyGuard AI Tier 5 Spatial Consensus Verdict: VETOED TO NORMAL (GENUINE METEOROLOGICAL FRONT)</strong><br>
        <strong>SkyGuard Resolution:</strong> Alert Vetoed | System Status: NORMAL | Spatial Consensus: 3 / 3 Cluster Stations Agree | Action: Telemetry passed clean to NWP forecast models without false maintenance dispatch.
    </div>

    <div class="grid-2col">
        <div class="info-card">
            <h4>Spatial Peer Cluster Verification (50 km Horizon)</h4>
            <ul style="margin: 0; padding-left: 16px; font-size: 8pt;">
                <li><strong>Station 01 (Primary Node):</strong> Temp spike +6.4°C (Confirmed)</li>
                <li><strong>Station 02 (12 km Peer):</strong> Temp spike +6.1°C (Directionally Aligned)</li>
                <li><strong>Station 03 (24 km Peer):</strong> Temp spike +5.8°C (Directionally Aligned)</li>
            </ul>
        </div>
        <div class="info-card">
            <h4>Core Value Proposition for SIH Judges</h4>
            <p style="margin: 0; font-size: 8pt;">SkyGuard AI does not just flag anomalies—it intelligently distinguishes between true sensor hardware failures and genuine extreme meteorological events, directly addressing the core requirement of the SIH AWS problem statement.</p>
        </div>
    </div>

</body>
</html>"""

def compile_storyboard_pdf():
    print("Generating Matplotlib Figure Assets...")
    fig1_path = generate_scene1_chart()
    fig2_path = generate_scene2_chart()
    print(f"Generated Scene 1 Figure: {fig1_path}")
    print(f"Generated Scene 2 Figure: {fig2_path}")
    
    html_content = build_demo_storyboard_html()
    
    base_filename = "SkyGuard_Document_5_Demo_Script_and_Spatial_Consensus_Storyboard"
    html_file = os.path.join(DOCS_DIR, f"{base_filename}.html")
    pdf_file = os.path.join(DOCS_DIR, f"{base_filename}.pdf")
    alt_pdf_file = os.path.join(ALT_DOCS_DIR, f"{base_filename}.pdf")
    
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    cmd = [
        EDGE_PATH,
        "--headless",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_file}",
        html_file
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    if os.path.exists(pdf_file):
        with open(pdf_file, "rb") as f_src, open(alt_pdf_file, "wb") as f_dst:
            f_dst.write(f_src.read())
            
    size = os.path.getsize(pdf_file) if os.path.exists(pdf_file) else 0
    print(f"Successfully compiled Storyboard PDF: {pdf_file} | Size: {size} bytes")
    return os.path.exists(pdf_file)

if __name__ == "__main__":
    compile_storyboard_pdf()
