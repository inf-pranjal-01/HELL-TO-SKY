import os
import subprocess
import markdown
import re

DOCS_DIR = r"C:\Users\PRANJAL TIWARI\Desktop\HELL TO SKY\ANITIGRAVITY RESEARCH DOCS"
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS_TEMPLATE = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

@page {
    size: A4 portrait;
    margin: 20mm 15mm 20mm 15mm;
    @bottom-right {
        content: counter(page);
    }
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.55;
    color: #1f2937;
    background-color: #ffffff;
    margin: 0;
    padding: 0;
}

.cover-container {
    padding-top: 40px;
    padding-bottom: 30px;
    border-bottom: 3px solid #1e3a8a;
    margin-bottom: 25px;
}

.doc-badge {
    display: inline-block;
    background: #1e3a8a;
    color: #ffffff;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 4px 10px;
    border-radius: 4px;
    margin-bottom: 12px;
}

.doc-title {
    font-size: 22pt;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
    margin: 0 0 8px 0;
    letter-spacing: -0.5px;
}

.doc-subtitle {
    font-size: 12pt;
    font-weight: 500;
    color: #4b5563;
    margin: 0 0 16px 0;
}

.doc-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    font-size: 8.5pt;
    color: #6b7280;
    background: #f8fafc;
    padding: 10px 14px;
    border-radius: 6px;
    border-left: 4px solid #3b82f6;
}

.doc-meta span {
    font-weight: 600;
    color: #374151;
}

h1 {
    font-size: 14pt;
    font-weight: 700;
    color: #0f172a;
    border-bottom: 1.5px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 24px;
    margin-bottom: 10px;
    page-break-after: avoid;
}

h2 {
    font-size: 12pt;
    font-weight: 600;
    color: #1e3a8a;
    margin-top: 18px;
    margin-bottom: 8px;
    page-break-after: avoid;
}

h3 {
    font-size: 10.5pt;
    font-weight: 600;
    color: #334155;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
}

p {
    margin-top: 0;
    margin-bottom: 10px;
    text-align: justify;
}

ul, ol {
    margin-top: 0;
    margin-bottom: 10px;
    padding-left: 20px;
}

li {
    margin-bottom: 4px;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin-top: 10px;
    margin-bottom: 15px;
    page-break-inside: avoid;
}

th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
    text-align: left;
    padding: 6px 8px;
    border: 1px solid #cbd5e1;
}

td {
    padding: 5px 8px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
}

tr:nth-child(even) {
    background-color: #f8fafc;
}

code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8.5pt;
    background-color: #f1f5f9;
    padding: 2px 4px;
    border-radius: 3px;
    color: #0f172a;
    border: 1px solid #e2e8f0;
}

pre {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8pt;
    background-color: #0f172a;
    color: #f8fafc;
    padding: 10px 12px;
    border-radius: 6px;
    overflow-x: auto;
    margin-top: 8px;
    margin-bottom: 12px;
    page-break-inside: avoid;
}

pre code {
    background: transparent;
    border: none;
    color: #f8fafc;
    padding: 0;
}

blockquote {
    margin: 10px 0;
    padding: 8px 14px;
    background-color: #f0fdf4;
    border-left: 4px solid #22c55e;
    color: #166534;
    font-size: 9pt;
    border-radius: 0 4px 4px 0;
}

.callout-warn {
    margin: 10px 0;
    padding: 8px 14px;
    background-color: #fef2f2;
    border-left: 4px solid #ef4444;
    color: #991b1b;
    font-size: 9pt;
    border-radius: 0 4px 4px 0;
}

.callout-info {
    margin: 10px 0;
    padding: 8px 14px;
    background-color: #eff6ff;
    border-left: 4px solid #3b82f6;
    color: #1e40af;
    font-size: 9pt;
    border-radius: 0 4px 4px 0;
}

.status-badge-demo {
    display: inline-block;
    background: #dcfce7;
    color: #166534;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
}

.status-badge-supp {
    display: inline-block;
    background: #e0e7ff;
    color: #3730a3;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
}

.status-badge-fut {
    display: inline-block;
    background: #fef3c7;
    color: #92400e;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
}

.case-study-box {
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 14px;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    page-break-inside: avoid;
}

.case-study-title {
    font-size: 11pt;
    font-weight: 700;
    color: #1e3a8a;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
}

.chain-step {
    font-size: 8.5pt;
    margin-bottom: 4px;
}
.chain-label {
    font-weight: 700;
    color: #334155;
    display: inline-block;
    width: 140px;
}

.page-break {
    page-break-before: always;
}

hr {
    border: 0;
    height: 1px;
    background: #e2e8f0;
    margin: 16px 0;
}
"""

print("Helper script ready")
