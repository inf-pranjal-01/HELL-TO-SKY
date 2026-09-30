import os
from fpdf import FPDF
import markdown
import re

def clean_text(text):
    text = text.replace("°C", " deg C")
    text = text.replace("—", "-")
    text = text.replace("•", "-")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("±", "+/-")
    text = text.replace("μ", "u")
    text = text.replace("Σ", "Sigma")
    # Remove italics inside table to avoid fpdf2 crash
    text = text.replace("*which*", "which")
    return text

def create_pdf(md_file_path, output_pdf_path):
    with open(md_file_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    md_text = clean_text(md_text)
    
    if "Document_2" in md_file_path:
        md_text += "\n\n## System Flowchart\n"
        md_text += "```\n"
        md_text += "[ Data Ingestion (Temp, Pressure, RH) ]\n"
        md_text += "                |\n"
        md_text += "                v\n"
        md_text += "[ StateManager: Freeze T-1 Trusted State ]\n"
        md_text += "                |\n"
        md_text += "                v\n"
        md_text += "  +-----------------------------------+\n"
        md_text += "  |       6-TIER DETECTION ENGINE     |\n"
        md_text += "  |                                   |\n"
        md_text += "  |  Tier 0: Hardware Rails & Limits  |\n"
        md_text += "  |  Tier 1: Spike & Frozen Checks    |\n"
        md_text += "  |  Tier 2: CUSUM Drift Detection    |\n"
        md_text += "  |  Tier 3: 3D Mahalanobis Distance  |\n"
        md_text += "  |  Tier 4: Isolation Forest (ML)    |\n"
        md_text += "  |  Tier 5: Ambiguous / Normal       |\n"
        md_text += "  +-----------------------------------+\n"
        md_text += "                |\n"
        md_text += "                v\n"
        md_text += "[ SHAP Explainability Engine (If ML Used) ]\n"
        md_text += "                |\n"
        md_text += "                v\n"
        md_text += "[ Verdict: Normal or Quarantined Anomaly ]\n"
        md_text += "```\n"

    html = markdown.markdown(md_text, extensions=['tables'])
    html = html.replace("<pre><code>", "<pre>").replace("</code></pre>", "</pre>")
    
    # fpdf2 workaround: remove any <em> or <strong> inside <td>
    html = re.sub(r'<td>(.*?)</td>', lambda m: '<td>' + m.group(1).replace('<em>', '').replace('</em>', '').replace('<strong>', '').replace('</strong>', '') + '</td>', html, flags=re.DOTALL)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.write_html(html)
    pdf.output(output_pdf_path)

if __name__ == "__main__":
    base_dir = "./"
    docs = [
        ("Document_1_Impact_Dossier.md", "Document_1_Impact_Dossier.pdf"),
        ("Document_2_Tech_Methodology.md", "Document_2_Tech_Methodology.pdf"),
        ("Document_3_Performance_Casebook.md", "Document_3_Performance_Casebook.pdf")
    ]
    for md_name, pdf_name in docs:
        create_pdf(os.path.join(base_dir, md_name), os.path.join(base_dir, pdf_name))
        print(f"Created {pdf_name}")
