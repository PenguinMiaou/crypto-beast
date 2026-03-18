#!/usr/bin/env python3
"""Convert 策略详解.md to a beautifully styled HTML file for PDF export."""

import markdown
import os

MD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "策略详解.md")
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "策略详解.html")

with open(MD_FILE, "r", encoding="utf-8") as f:
    md_content = f.read()

# Convert markdown to HTML
html_body = markdown.markdown(
    md_content,
    extensions=["tables", "fenced_code", "toc", "codehilite"],
)

# Full HTML with premium styling
html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Beast v1.0 — 完整策略流程详解</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface-2: #232734;
    --border: #2e3345;
    --text: #e4e7ef;
    --text-dim: #8b90a0;
    --accent: #6c5ce7;
    --accent-light: #a29bfe;
    --green: #00cec9;
    --red: #ff6b6b;
    --orange: #fdcb6e;
    --blue: #74b9ff;
  }}

  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}

  body {{
    font-family: 'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.8;
    font-size: 14px;
    padding: 0;
  }}

  .container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 50px;
  }}

  /* Title */
  h1 {{
    font-size: 28px;
    font-weight: 700;
    color: #fff;
    text-align: center;
    padding: 30px 0;
    margin-bottom: 30px;
    background: linear-gradient(135deg, var(--accent), var(--blue));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    border-bottom: 2px solid var(--accent);
  }}

  h2 {{
    font-size: 20px;
    font-weight: 600;
    color: var(--accent-light);
    margin-top: 40px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}

  h3 {{
    font-size: 16px;
    font-weight: 600;
    color: var(--green);
    margin-top: 24px;
    margin-bottom: 12px;
  }}

  p {{
    margin-bottom: 12px;
    color: var(--text);
  }}

  strong {{
    color: var(--orange);
    font-weight: 600;
  }}

  /* Table of Contents */
  ol {{
    padding-left: 24px;
    margin-bottom: 16px;
  }}

  ol li {{
    margin-bottom: 4px;
  }}

  ul {{
    padding-left: 24px;
    margin-bottom: 16px;
  }}

  li {{
    margin-bottom: 4px;
  }}

  a {{
    color: var(--blue);
    text-decoration: none;
  }}

  /* Tables */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 13px;
    background: var(--surface);
    border-radius: 8px;
    overflow: hidden;
  }}

  thead {{
    background: linear-gradient(135deg, var(--accent), #5f27cd);
  }}

  thead th {{
    color: #fff;
    font-weight: 600;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
  }}

  tbody td {{
    padding: 8px 14px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
  }}

  tbody tr:last-child td {{
    border-bottom: none;
  }}

  tbody tr:nth-child(even) {{
    background: var(--surface-2);
  }}

  /* Code blocks */
  pre {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    overflow-x: auto;
    margin: 16px 0;
    font-size: 13px;
    line-height: 1.6;
  }}

  code {{
    font-family: 'JetBrains Mono', 'Menlo', monospace;
    font-size: 13px;
    color: var(--green);
  }}

  pre code {{
    color: var(--text);
    background: none;
    padding: 0;
  }}

  /* Inline code */
  p code, li code, td code {{
    background: var(--surface-2);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
  }}

  /* Horizontal rule */
  hr {{
    border: none;
    height: 1px;
    background: linear-gradient(to right, transparent, var(--accent), transparent);
    margin: 32px 0;
  }}

  /* Print styles */
  @media print {{
    body {{
      background: #fff;
      color: #1a1a2e;
      font-size: 11pt;
      padding: 0;
    }}

    .container {{
      max-width: 100%;
      padding: 0;
    }}

    h1 {{
      background: none;
      -webkit-text-fill-color: #1a1a2e;
      color: #1a1a2e;
      font-size: 22pt;
      border-bottom: 3px solid #6c5ce7;
    }}

    h2 {{
      color: #6c5ce7;
      font-size: 16pt;
      border-bottom: 1px solid #ddd;
      page-break-after: avoid;
    }}

    h3 {{
      color: #00896f;
      font-size: 13pt;
      page-break-after: avoid;
    }}

    strong {{
      color: #c0392b;
    }}

    table {{
      background: #fff;
      border: 1px solid #ddd;
    }}

    thead {{
      background: #6c5ce7;
    }}

    thead th {{
      color: #fff;
    }}

    tbody td {{
      color: #333;
      border-bottom: 1px solid #eee;
    }}

    tbody tr:nth-child(even) {{
      background: #f8f9fa;
    }}

    pre {{
      background: #f5f5f5;
      border: 1px solid #ddd;
      page-break-inside: avoid;
    }}

    code {{
      color: #00896f;
    }}

    pre code {{
      color: #333;
    }}

    hr {{
      background: #ddd;
    }}

    a {{
      color: #6c5ce7;
    }}
  }}

  /* Page break hints for print */
  h2 {{
    page-break-before: auto;
  }}

  table, pre {{
    page-break-inside: avoid;
  }}
</style>
</head>
<body>
<div class="container">
{html_body}
</div>
</body>
</html>
"""

with open(HTML_FILE, "w", encoding="utf-8") as f:
    f.write(html_doc)

print(f"✅ HTML file generated: {HTML_FILE}")
print(f"   File size: {os.path.getsize(HTML_FILE):,} bytes")
