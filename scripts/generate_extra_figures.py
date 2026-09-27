import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ASSETS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS\assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.edgecolor'] = '#cbd5e1'
plt.rcParams['axes.linewidth'] = 1.0
plt.rcParams['grid.color'] = '#f1f5f9'
plt.rcParams['grid.linestyle'] = '--'

# DOC 3 FIG 7: Case Study 4 (Frozen Sensor / Variance Collapse)
def gen_case_study_4():
    np.random.seed(303)
    t = np.linspace(0, 100, 101) # minutes
    # Sibling diurnal pressure tidal oscillation (range ~2.8 hPa)
    tide = 1012.0 + 1.4 * np.sin(2 * np.pi * t / 60)
    p1 = tide + np.random.normal(0, 0.08, len(t))
    p2 = tide + np.random.normal(0, 0.08, len(t)) + 0.3
    p3 = tide + np.random.normal(0, 0.08, len(t)) - 0.2
    
    target = tide.copy()
    # Injected frozen value from t=30 to t=85: flatline at 1012.40 hPa
    frozen_val = 1012.40
    target[30:86] = frozen_val
    
    fig, ax = plt.subplots(figsize=(9, 4.0), dpi=200)
    ax.plot(t, p1, color='#0284c7', linestyle='--', label='Sibling Peer AWS-KOL-101 (Active Diurnal Tide)')
    ax.plot(t, p2, color='#0d9488', linestyle='--', label='Sibling Peer AWS-KOL-102 (Active Diurnal Tide)')
    ax.plot(t, p3, color='#059669', linestyle='--', label='Sibling Peer AWS-KOL-103 (Active Diurnal Tide)')
    ax.plot(t, target, color='#dc2626', linewidth=2.0, label='Target Station AWS-KOL-015 (Pressure Lockup @ 1012.40 hPa)')
    
    # Highlight frozen interval
    ax.axvspan(30, 85, color='#fee2e2', alpha=0.6, label='Tier 1 Frozen Value Collapse (Var(P) = 0.000 -> Quarantined)')
    
    ax.set_xlabel('Time Elapsed (Minutes)', fontsize=9, fontweight='bold', color='#1e293b')
    ax.set_ylabel('Atmospheric Pressure (hPa)', fontsize=9, fontweight='bold', color='#1e293b')
    ax.set_title('Case Study 4: Variance Collapse (Frozen Sensor Lockup) on AWS-KOL-015', fontsize=10.5, fontweight='bold', color='#0f172a', pad=10)
    ax.set_ylim(1009.5, 1015.0)
    ax.legend(frameon=True, facecolor='#ffffff', edgecolor='#e2e8f0', fontsize=7.5, loc='lower left')
    ax.grid(True)
    
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig7_case4_frozen.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# DOC 1 FIG 3: Research to SkyGuard Mapping SVG Diagram
def gen_doc1_fig3():
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 200" width="100%" height="200">
  <rect width="100%" height="100%" fill="#ffffff" rx="8" />
  <text x="450" y="20" fill="#0f172a" font-family="Inter, sans-serif" font-size="11" font-weight="bold" text-anchor="middle">RESEARCH FOUNDATIONS TO SKYGUARD IMPLEMENTATION MAPPING</text>

  <g transform="translate(15, 35)">
    <!-- 5 Mapping Rows -->
    <g transform="translate(0, 0)">
      <rect width="260" height="26" rx="4" fill="#eff6ff" stroke="#bfdbfe"/>
      <text x="10" y="17" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="8" font-weight="bold">1. WMO-No. 8 Level I-III Standards [R01]</text>
      <line x1="265" y1="13" x2="335" y2="13" stroke="#64748b" stroke-width="1.5"/>
      <rect x="340" y="0" width="530" height="26" rx="4" fill="#f8fafc" stroke="#cbd5e1"/>
      <text x="350" y="17" fill="#0f172a" font-family="Inter, sans-serif" font-size="8">Physical plausibility limits, step tests &amp; 3-peer spatial consensus veto (Tier 0, 1, 5)</text>
    </g>

    <g transform="translate(0, 32)">
      <rect width="260" height="26" rx="4" fill="#eff6ff" stroke="#bfdbfe"/>
      <text x="10" y="17" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="8" font-weight="bold">2. Sequential SPRT / CUSUM (Page 1954) [M02]</text>
      <line x1="265" y1="13" x2="335" y2="13" stroke="#64748b" stroke-width="1.5"/>
      <rect x="340" y="0" width="530" height="26" rx="4" fill="#f8fafc" stroke="#cbd5e1"/>
      <text x="350" y="17" fill="#0f172a" font-family="Inter, sans-serif" font-size="8">Pre-whitened innovation residual accumulation for low-SNR sensor calibration drift (Tier 2)</text>
    </g>

    <g transform="translate(0, 64)">
      <rect width="260" height="26" rx="4" fill="#eff6ff" stroke="#bfdbfe"/>
      <text x="10" y="17" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="8" font-weight="bold">3. Clausius-Clapeyron Psychrometrics [M04]</text>
      <line x1="265" y1="13" x2="335" y2="13" stroke="#64748b" stroke-width="1.5"/>
      <rect x="340" y="0" width="530" height="26" rx="4" fill="#f8fafc" stroke="#cbd5e1"/>
      <text x="350" y="17" fill="#0f172a" font-family="Inter, sans-serif" font-size="8">Vapor Pressure Deficit (VPD) boundary tracking &amp; dewpoint depression consistency (Tier 0, 3)</text>
    </g>

    <g transform="translate(0, 96)">
      <rect width="260" height="26" rx="4" fill="#eff6ff" stroke="#bfdbfe"/>
      <text x="10" y="17" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="8" font-weight="bold">4. 3D Mahalanobis Distance (1936) [M05]</text>
      <line x1="265" y1="13" x2="335" y2="13" stroke="#64748b" stroke-width="1.5"/>
      <rect x="340" y="0" width="530" height="26" rx="4" fill="#f8fafc" stroke="#cbd5e1"/>
      <text x="350" y="17" fill="#0f172a" font-family="Inter, sans-serif" font-size="8">Joint cross-channel covariance distance D² across T, P, RH (threshold: p &lt; 10⁻³) (Tier 3)</text>
    </g>

    <g transform="translate(0, 128)">
      <rect width="260" height="26" rx="4" fill="#eff6ff" stroke="#bfdbfe"/>
      <text x="10" y="17" fill="#1e3a8a" font-family="Inter, sans-serif" font-size="8" font-weight="bold">5. Isolation Forest &amp; SHAP (2008, 2017) [M01,M03]</text>
      <line x1="265" y1="13" x2="335" y2="13" stroke="#64748b" stroke-width="1.5"/>
      <rect x="340" y="0" width="530" height="26" rx="4" fill="#f8fafc" stroke="#cbd5e1"/>
      <text x="350" y="17" fill="#0f172a" font-family="Inter, sans-serif" font-size="8">49-D continuous feature space isolation &amp; TreeExplainer local feature attribution (Tier 4)</text>
    </g>
  </g>
</svg>"""
    out_path = os.path.join(ASSETS_DIR, "doc1_fig3_research_mapping.svg")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated: {out_path}")

if __name__ == "__main__":
    gen_case_study_4()
    gen_doc1_fig3()
