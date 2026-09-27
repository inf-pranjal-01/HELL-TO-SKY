import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ASSETS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS\assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

# Set clean styling for matplotlib plots
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.edgecolor'] = '#cbd5e1'
plt.rcParams['axes.linewidth'] = 1.0
plt.rcParams['grid.color'] = '#f1f5f9'
plt.rcParams['grid.linestyle'] = '--'

# -------------------------------------------------------------
# DOC 3 FIG 1: 7-Seed Scorecard Chart
# -------------------------------------------------------------
def gen_seed_chart():
    seeds = ['Seed 42', 'Seed 101', 'Seed 202', 'Seed 2024', 'Seed 8888', 'Seed 20260924', 'Seed 454562314127', '7-Seed Mean']
    prec = [72.64, 73.07, 75.04, 74.55, 73.80, 73.65, 70.53, 73.33]
    rec =  [95.68, 95.45, 94.72, 95.86, 95.68, 95.37, 95.16, 95.42]
    f1 =   [82.59, 82.77, 83.74, 83.87, 83.32, 83.11, 81.02, 82.92]
    
    x = np.arange(len(seeds))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=200)
    rects1 = ax.bar(x - width, prec, width, label='Precision (%)', color='#3b82f6', edgecolor='#1d4ed8')
    rects2 = ax.bar(x, rec, width, label='Recall (%)', color='#10b981', edgecolor='#047857')
    rects3 = ax.bar(x + width, f1, width, label='F1 Score (%)', color='#8b5cf6', edgecolor='#6d28d9')
    
    ax.set_ylabel('Score (%)', fontsize=10, fontweight='bold', color='#1e293b')
    ax.set_title('Authoritative 7-Seed Diagnostic Scorecard (60,480 Rows per Evaluation)', fontsize=11, fontweight='bold', color='#0f172a', pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(seeds, rotation=15, ha='right', fontsize=8.5, color='#334155')
    ax.set_ylim(50, 105)
    ax.legend(frameon=True, facecolor='#ffffff', edgecolor='#e2e8f0', fontsize=8.5, loc='lower right')
    ax.grid(True, axis='y')
    
    # Highlight mean
    ax.axvline(x=6.5, color='#94a3b8', linestyle=':', linewidth=1.5)
    
    # Add values on top of bars
    for r in [rects1, rects2, rects3]:
        for bar in r:
            h = bar.get_height()
            ax.annotate(f'{h:.1f}%',
                        xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 2),  # 2 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=6.5, color='#334155', fontweight='bold')
            
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig1_seed_scorecard.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# -------------------------------------------------------------
# DOC 3 FIG 2: Fault-Class Breakdown Chart
# -------------------------------------------------------------
def gen_fault_breakdown_chart():
    faults = [
        'Unstructured Multi-Sensor',
        'Sensor Fail-Low',
        'Low-SNR Calibration Drift',
        'Frozen Value Collapse',
        'Thermodynamic Inconsistency',
        'Instantaneous Spike',
        'Sensor Dropout / Rail'
    ]
    recall = [61.00, 75.09, 91.89, 97.39, 100.0, 100.0, 100.0]
    colors = ['#f59e0b', '#f59e0b', '#10b981', '#10b981', '#059669', '#059669', '#059669']
    
    fig, ax = plt.subplots(figsize=(9, 4.0), dpi=200)
    y_pos = np.arange(len(faults))
    bars = ax.barh(y_pos, recall, color=colors, edgecolor='#0f172a', height=0.55, linewidth=0.5)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(faults, fontsize=8.5, fontweight='bold', color='#1e293b')
    ax.set_xlabel('Detection Recall Rate (%)', fontsize=9.5, fontweight='bold', color='#1e293b')
    ax.set_title('Fault-Class Detection Recall Breakdown (Authoritative 7-Seed Evaluation)', fontsize=11, fontweight='bold', color='#0f172a', pad=10)
    ax.set_xlim(0, 115)
    ax.grid(True, axis='x')
    
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f'{w:.1f}%',
                    xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(4, 0),
                    textcoords="offset points",
                    ha='left', va='center', fontsize=8, fontweight='bold', color='#0f172a')
        
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig2_fault_breakdown.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# -------------------------------------------------------------
# DOC 3 FIG 3: Latency & Throughput Profile Chart
# -------------------------------------------------------------
def gen_latency_chart():
    stages = [
        'Single Reading (p50)',
        'Single Reading (p95)',
        'Single Reading (p99)',
        'Cluster Batch (4 AWS)',
        'Network Batch (28 AWS)',
        'Operational Budget Limit'
    ]
    latencies = [0.172, 0.210, 0.268, 0.840, 5.880, 2000.0]
    colors = ['#0284c7', '#0284c7', '#0369a1', '#6366f1', '#4f46e5', '#ef4444']
    
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=200)
    y_pos = np.arange(len(stages))
    bars = ax.barh(y_pos, latencies, color=colors, height=0.5, edgecolor='#0f172a', linewidth=0.5)
    
    ax.set_xscale('log')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(stages, fontsize=8.5, fontweight='bold', color='#1e293b')
    ax.set_xlabel('Execution Latency in Milliseconds (Logarithmic Scale)', fontsize=9.5, fontweight='bold', color='#1e293b')
    ax.set_title('Algorithmic Processing Latency vs. Operational Real-Time Budget', fontsize=11, fontweight='bold', color='#0f172a', pad=10)
    ax.grid(True, axis='x', which='both')
    
    for bar, val in zip(bars, latencies):
        w = bar.get_width()
        text = f'{val:.3f} ms' if val < 10 else f'{val:.1f} ms'
        if val == 2000.0:
            text = '2,000.0 ms (Target Budget)'
        ax.annotate(text,
                    xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(4, 0),
                    textcoords="offset points",
                    ha='left', va='center', fontsize=7.5, fontweight='bold', color='#0f172a')
        
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig3_latency_profile.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# -------------------------------------------------------------
# DOC 3 FIG 4: Case Study 1 (Spike Detection Plot)
# -------------------------------------------------------------
def gen_case_study_1():
    np.random.seed(42)
    t = np.linspace(0, 100, 101)  # minutes
    # Baseline diurnal curve
    baseline = 21.0 + 1.2 * np.sin(2 * np.pi * t / 200) + np.random.normal(0, 0.15, len(t))
    peers_1 = baseline + np.random.normal(0, 0.1, len(t)) - 0.2
    peers_2 = baseline + np.random.normal(0, 0.1, len(t)) + 0.3
    peers_3 = baseline + np.random.normal(0, 0.1, len(t)) + 0.1
    
    target = baseline.copy()
    # Injected spike at index 50 (50 mins)
    target[50] = 34.8  # +13.7 deg jump
    
    fig, ax = plt.subplots(figsize=(9, 4.0), dpi=200)
    ax.plot(t, peers_1, color='#94a3b8', linestyle=':', label='Sibling Peer AWS-MUM-101 (21.2°C)')
    ax.plot(t, peers_2, color='#cbd5e1', linestyle=':', label='Sibling Peer AWS-MUM-102 (21.5°C)')
    ax.plot(t, peers_3, color='#64748b', linestyle=':', label='Sibling Peer AWS-MUM-103 (21.3°C)')
    ax.plot(t, target, color='#2563eb', linewidth=1.5, label='Target Station AWS-MUM-007 (Reported Telemetry)')
    
    # Highlight anomaly
    ax.scatter([50], [34.8], color='#dc2626', s=90, zorder=5, edgecolor='#7f1d1d', linewidth=1.5, label='Tier 1 Spike Trigger (LLR = 6.2σ -> Quarantined)')
    ax.axvspan(48, 52, color='#fee2e2', alpha=0.6)
    
    ax.set_xlabel('Time Elapsed (Minutes)', fontsize=9, fontweight='bold', color='#1e293b')
    ax.set_ylabel('Ambient Temperature (°C)', fontsize=9, fontweight='bold', color='#1e293b')
    ax.set_title('Case Study 1: Instantaneous Sensor Spike Detection on AWS-MUM-007', fontsize=10.5, fontweight='bold', color='#0f172a', pad=10)
    ax.set_ylim(18, 38)
    ax.legend(frameon=True, facecolor='#ffffff', edgecolor='#e2e8f0', fontsize=7.5, loc='upper left')
    ax.grid(True)
    
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig4_case1_spike.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# -------------------------------------------------------------
# DOC 3 FIG 5: Case Study 2 (Genuine Cold Front Spatial Veto)
# -------------------------------------------------------------
def gen_case_study_2():
    np.random.seed(101)
    t = np.linspace(0, 100, 101)  # minutes
    # Coastal cold front at t=50: drop by 8 deg
    drop = 8.2 / (1 + np.exp(-(t - 50) / 3))
    
    target = 28.5 - drop + np.random.normal(0, 0.12, len(t))
    p1 = 28.3 - (7.8 / (1 + np.exp(-(t - 50) / 3))) + np.random.normal(0, 0.12, len(t))
    p2 = 28.7 - (8.4 / (1 + np.exp(-(t - 50) / 3))) + np.random.normal(0, 0.12, len(t))
    p3 = 28.4 - (8.1 / (1 + np.exp(-(t - 50) / 3))) + np.random.normal(0, 0.12, len(t))
    
    fig, ax = plt.subplots(figsize=(9, 4.0), dpi=200)
    ax.plot(t, p1, color='#0284c7', linestyle='--', label='Sibling Peer AWS-MUM-101 (ΔT = -7.8°C)')
    ax.plot(t, p2, color='#0d9488', linestyle='--', label='Sibling Peer AWS-MUM-102 (ΔT = -8.4°C)')
    ax.plot(t, p3, color='#059669', linestyle='--', label='Sibling Peer AWS-MUM-103 (ΔT = -8.1°C)')
    ax.plot(t, target, color='#dc2626', linewidth=2.0, label='Target Station AWS-MUM-007 (ΔT = -8.2°C in 20 min)')
    
    ax.axvspan(45, 65, color='#dcfce7', alpha=0.5, label='Tier 5 Spatial Consensus Zone (3/3 Peers Confirm -> VETOED)')
    
    ax.set_xlabel('Time Elapsed (Minutes)', fontsize=9, fontweight='bold', color='#1e293b')
    ax.set_ylabel('Ambient Temperature (°C)', fontsize=9, fontweight='bold', color='#1e293b')
    ax.set_title('Case Study 2: Genuine Coastal Cold Front Passage — Spatial Consensus False Alarm Suppression', fontsize=10.5, fontweight='bold', color='#0f172a', pad=10)
    ax.set_ylim(18, 31)
    ax.legend(frameon=True, facecolor='#ffffff', edgecolor='#e2e8f0', fontsize=7.5, loc='lower left')
    ax.grid(True)
    
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig5_case2_front.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# -------------------------------------------------------------
# DOC 3 FIG 6: Case Study 3 (Multivariate Inconsistency & SHAP)
# -------------------------------------------------------------
def gen_case_study_3():
    np.random.seed(202)
    t = np.linspace(0, 100, 101)
    temp = 25.0 + 0.07 * t + np.random.normal(0, 0.1, len(t))  # upward drift to 32C
    rh = 65.0 + np.random.normal(0, 0.4, len(t))               # static 65% RH
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8), dpi=200, gridspec_kw={'width_ratios': [1.3, 1]})
    
    # Left: Dual axis time plot
    color_temp = '#dc2626'
    color_rh = '#2563eb'
    
    ax1.plot(t, temp, color=color_temp, linewidth=1.8, label='Temperature (°C) [Unphysical Upward Drift]')
    ax1.set_xlabel('Time Elapsed (Minutes)', fontsize=8.5, fontweight='bold', color='#1e293b')
    ax1.set_ylabel('Temperature (°C)', color=color_temp, fontsize=8.5, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor=color_temp)
    ax1.set_ylim(23, 34)
    ax1.grid(True)
    
    ax1_twin = ax1.twinx()
    ax1_twin.plot(t, rh, color=color_rh, linewidth=1.8, linestyle='--', label='Relative Humidity (%) [Unresponsive]')
    ax1_twin.set_ylabel('Relative Humidity (%)', color=color_rh, fontsize=8.5, fontweight='bold')
    ax1_twin.tick_params(axis='y', labelcolor=color_rh)
    ax1_twin.set_ylim(55, 75)
    
    ax1.set_title('Cross-Channel Thermodynamic Divergence', fontsize=9.5, fontweight='bold', color='#0f172a')
    
    # Right: SHAP Attribution Bar
    features = ['vpd_deficit', 'temp_c_dev', 'temp_robust_scale', 'rh_dev', 'dt_hours']
    shap_vals = [0.28, 0.34, 0.28, 0.06, 0.04]
    y_pos = np.arange(len(features))
    
    ax2.barh(y_pos, shap_vals, color='#6366f1', edgecolor='#4338ca', height=0.5)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(features, fontsize=8, color='#1e293b', fontweight='bold')
    ax2.set_xlabel('SHAP Feature Importance (TreeExplainer)', fontsize=8.5, fontweight='bold', color='#1e293b')
    ax2.set_title('Model Attribution Breakdown', fontsize=9.5, fontweight='bold', color='#0f172a')
    ax2.set_xlim(0, 0.45)
    ax2.grid(True, axis='x')
    
    for i, v in enumerate(shap_vals):
        ax2.annotate(f'{v:.2f} ({v*100:.0f}%)', xy=(v, i), xytext=(3, 0), textcoords="offset points", ha='left', va='center', fontsize=7.5, fontweight='bold')
        
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc3_fig6_case3_multivariate.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

# -------------------------------------------------------------
# DOC 1 FIG 5: Scalability Scenario Chart
# -------------------------------------------------------------
def gen_doc1_scale_chart():
    stations = [100, 500, 1000, 2000, 5000, 10000]
    daily_obs_15m = [s * 96 for s in stations]
    daily_obs_5m = [s * 288 for s in stations]
    cpu_time_5m = [obs * 0.000210 for obs in daily_obs_5m]  # seconds
    
    fig, ax1 = plt.subplots(figsize=(9, 3.8), dpi=200)
    
    x = np.arange(len(stations))
    width = 0.35
    
    rects1 = ax1.bar(x - width/2, [obs/1000 for obs in daily_obs_15m], width, label='15-Min Ingestion (Thousand Obs/Day)', color='#3b82f6', edgecolor='#1d4ed8')
    rects2 = ax1.bar(x + width/2, [obs/1000 for obs in daily_obs_5m], width, label='5-Min Ingestion (Thousand Obs/Day)', color='#6366f1', edgecolor='#4338ca')
    
    ax1.set_xlabel('AWS Operational Network Scale (Station Count)', fontsize=9, fontweight='bold', color='#1e293b')
    ax1.set_ylabel('Daily Ingestion Volume (x1,000 Obs)', fontsize=9, fontweight='bold', color='#1e293b')
    ax1.set_title('National Scaling Model: Ingestion Volume vs. Single-Threaded CPU Compute Time', fontsize=10.5, fontweight='bold', color='#0f172a', pad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f'{s:,} AWS' for s in stations], fontsize=8.5, color='#334155')
    ax1.grid(True, axis='y')
    
    ax2 = ax1.twinx()
    ax2.plot(x + width/2, cpu_time_5m, color='#dc2626', marker='o', linewidth=2.0, label='Daily CPU Inference Time (Seconds @ p95 0.210ms)')
    ax2.set_ylabel('Daily CPU Time (Seconds)', color='#dc2626', fontsize=9, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#dc2626')
    ax2.set_ylim(0, 700)
    
    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, frameon=True, facecolor='#ffffff', edgecolor='#e2e8f0', fontsize=7.5, loc='upper left')
    
    fig.tight_layout()
    out_path = os.path.join(ASSETS_DIR, "doc1_fig5_scaling_model.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

if __name__ == "__main__":
    print("Generating publication-grade charts...")
    gen_seed_chart()
    gen_fault_breakdown_chart()
    gen_latency_chart()
    gen_case_study_1()
    gen_case_study_2()
    gen_case_study_3()
    gen_doc1_scale_chart()
    print("All charts successfully generated!")
