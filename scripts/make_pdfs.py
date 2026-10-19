"""Export README.md and docs/*.md to pdf/ (plus pdf/MPFT_Report.pdf).
Uses pandoc if installed, otherwise markdown + headless Chrome/Edge. Images are embedded as data URIs."""
import base64
import glob
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_ORDER = ["README", "PROTOCOL", "ARCHITECTURE", "TOPOLOGY", "TEST_REPORT", "DEMO_SCRIPT",
                "VIVA_PREP", "CONTRIBUTIONS"]
BROWSERS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "google-chrome", "chromium", "microsoft-edge"]
CSS = """body{font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;color:#000;background:#fff;
font-size:11pt;line-height:1.45;margin:0}h1{font-size:20pt}h2{font-size:15pt;margin-top:1.4em}h3{font-size:12pt}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:9.5pt}th,td{border:1px solid #888;padding:3px 6px;
text-align:left;vertical-align:top}code{font-family:Menlo,monospace;font-size:9pt}
pre{border:1px solid #bbb;padding:6px;font-size:7.5pt;line-height:1.25;white-space:pre;overflow:hidden}
pre code{font-size:7.5pt}img{max-width:100%}section{page-break-before:always}section:first-child{page-break-before:auto}
@page{size:A4;margin:16mm}"""


def embed_images(html, base_dir):
    def repl(m):
        src = m.group(1)
        path = os.path.normpath(os.path.join(base_dir, src))
        if src.startswith(("http", "data:")) or not os.path.exists(path):
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            return f'src="data:{mime};base64,{base64.b64encode(f.read()).decode()}"'
    return re.sub(r'src="([^"]+)"', repl, html)


def md_to_html(md_path):
    with open(md_path, encoding="utf-8") as f:
        body = markdown.markdown(f.read(), extensions=["tables", "fenced_code", "sane_lists"])
    return embed_images(body, os.path.dirname(md_path))


def page(sections):
    inner = "".join(f"<section>{s}</section>" for s in sections)
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{inner}</body></html>'


def find_browser():
    for b in BROWSERS:
        if shutil.which(b) or os.path.exists(b):
            return b
    sys.exit("No Chrome/Edge found and pandoc is missing")


def html_to_pdf(html, pdf_path, tmp):
    html_path = os.path.join(tmp, "page.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    if shutil.which("pandoc"):
        subprocess.run(["pandoc", html_path, "-o", pdf_path], check=True)
        return
    subprocess.run([find_browser(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--user-data-dir={tmp}/profile", f"--print-to-pdf={pdf_path}", "file://" + html_path],
                   check=True, capture_output=True, timeout=120)


def main():
    out = os.path.join(ROOT, "pdf")
    os.makedirs(out, exist_ok=True)
    sources = {"README": os.path.join(ROOT, "README.md")}
    for p in sorted(glob.glob(os.path.join(ROOT, "docs", "*.md"))):
        sources[os.path.basename(p)[:-3]] = p
    with tempfile.TemporaryDirectory() as tmp:
        bodies = {name: md_to_html(p) for name, p in sources.items()}
        for name, body in bodies.items():
            html_to_pdf(page([body]), os.path.join(out, f"{name}.pdf"), tmp)
            print("pdf/%s.pdf" % name)
        html_to_pdf(page([bodies[n] for n in REPORT_ORDER]), os.path.join(out, "MPFT_Report.pdf"), tmp)
        print("pdf/MPFT_Report.pdf")


if __name__ == "__main__":
    main()
