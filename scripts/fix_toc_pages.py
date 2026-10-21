"""Rewrites the page numbers in the report's contents/figure/table lists from the exported PDF (Pages has no auto-update)."""
import re, sys
import docx, pypdf

docx_path, pdf_path = sys.argv[1:3]
pages = [re.sub(r"\s+", " ", p.extract_text() or "") for p in pypdf.PdfReader(pdf_path).pages]
d = docx.Document(docx_path)
start = next(i for i, t in enumerate(pages) if "1 Introduction and Project Objectives" in t and "Table of Contents" not in t and "List of" not in t)
changed = 0
for p in d.paragraphs:
    if p.style.name not in ("TOC 1", "TOC 2") or "\t" not in p.text:
        continue
    label = re.sub(r"\s+", " ", p.text.split("\t")[0]).strip()
    key = re.sub(r"^(Figure|Table) (\S+) ", r"\1 \2 ", label)
    hit = next((i for i in range(start, len(pages)) if key in pages[i]), None)
    if hit is None:
        print("not found:", label); continue
    old = p.runs[0].text.split("\t")[-1]
    if old != str(hit + 1):
        p.runs[0].text = label.replace("  ", "  ") + "\t" + str(hit + 1); changed += 1
d.save(docx_path)
print("updated", changed)
