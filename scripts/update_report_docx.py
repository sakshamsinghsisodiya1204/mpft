"""Adds section 3.5 (views, scenarios, graph axis) to the submission report and swaps in current screenshots."""
import copy
from pathlib import Path
import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches
from PIL import Image

SUB, A = Path("docs/submission"), Path("docs/submission/assets")
d = docx.Document(SUB / "MPFT_Mini_Project_Report.docx")
P = d.paragraphs
if any(p.text.startswith("3.5 Sender and Receiver") for p in P):
    raise SystemExit("already updated")


def swap_image(par, png):
    """Replace the picture inside paragraph par, keeping its width and fixing the height."""
    sh = d.inline_shapes[[p._p for p in d.paragraphs if 'graphic' in p._p.xml].index(par._p)] if False else None
    blip = par._p.xpath(".//a:blip")[0]
    rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
    d.part.related_parts[rid]._blob = Path(png).read_bytes()
    w, h = Image.open(png).size
    ext = par._p.xpath(".//wp:extent")[0]
    ext.set("cy", str(int(int(ext.get("cx")) * h / w)))
    for e in par._p.xpath(".//a:ext[@cx]"):
        e.set("cy", str(int(int(e.get("cx")) * h / w)))


fig_par = {p.text.split(" ")[1]: i for i, p in enumerate(P) if p.style.name == "Caption" and p.text.startswith("Figure 3.")}
swap_image(P[fig_par["3.2"] - 1], A / "ui_transfer_top.png")
swap_image(P[fig_par["3.3"] - 1], A / "ui_transfer_paths.png")

anchor = next(p for p in P if p.text.startswith("4 Testing and Results") and p.style.name == "Heading 1")
bullet = lambda t: anchor.insert_paragraph_before(t, style="List Bullet")


def text(t, style="Normal"):
    return anchor.insert_paragraph_before(t, style=style)


def figure(png, caption, width=6.3):
    p = anchor.insert_paragraph_before("")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(png), width=Inches(width))
    c = anchor.insert_paragraph_before(caption, style="Caption")
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER


text("3.5 Sender and Receiver Views, Scenarios and Graph Axis", "Heading 2")
text("Both devices open the same session, but the page is role-aware. The title says Sending or Receiving, a coloured banner states the outcome "
     "for that side, and the panels are ordered for what each side needs. Figure 3.4 is the sender after a successful transfer: it reports delivery "
     "and offers to send another file. Figure 3.5 is the receiver for the same session: verification comes first and the Download button appears only here.")
figure(A / "scn_sender.png", "Figure 3.4 Sender view: Delivered, with the scenario and transfer figures")
figure(A / "scn_receiver.png", "Figure 3.5 Receiver view: Saved and verified, with Download")
text("Transfer scenarios. The Send form offers eight network scenarios, each run through the emulator in front of the receiver. This makes it easy to show "
     "success and failure side by side in a demonstration:")
for t in ("Clean network (no emulation) and Clean but slow (16 Mbit/s per path, 20 ms delay): smooth, long curves.",
          "Asymmetric paths: faster paths carry more chunks (work stealing).",
          "Lossy (5% of chunks corrupted) and Heavy loss (20%): NACKs, retransmissions, and a matching final SHA-256.",
          "Path failure (last path dies after 3 s) and Path flaps (one path dies at 2 s and returns 3 s later): requeue, backoff and reconnect.",
          "Total failure (every path dies after 1 s, file over 2 MB): the transfer fails, and nothing is saved or offered for download."):
    bullet(t)
text("Figure 3.6 shows the failure case on the receiving side. The banner reads Nothing was saved, the incident list shows each path going down, "
     "and no Download button is offered because no verified file exists.")
figure(A / "scn_failure.png", "Figure 3.6 Receiver view of a failed transfer (total failure scenario)")
text("Graph time axis. Transfers on loopback can finish in well under a second, which left the earlier graphs almost empty on a fixed seconds axis. "
     "Throughput is now computed in the browser from chunk completions in buckets of one twentieth of the transfer duration (one second only for transfers "
     "over 20 s), the x range equals the real duration, and transfers shorter than 2 s use a millisecond axis. Figure 3.7 shows the slow-WAN scenario, "
     "where per-path throughput, chunk completion and in-flight chunks are readable.")
figure(A / "scn_wan.png", "Figure 3.7 Slow-WAN scenario: per-path graphs on a millisecond axis")

# list of figures
lof = next(p for p in d.paragraphs if p.text.startswith("Figure 3.3  Per-path table"))
for n, t in (("3.4", "Sender view: Delivered, with the scenario and transfer figures"), ("3.5", "Receiver view: Saved and verified, with Download"),
             ("3.6", "Receiver view of a failed transfer (total failure scenario)"), ("3.7", "Slow-WAN scenario: per-path graphs on a millisecond axis")):
    new = copy.deepcopy(lof._p)
    lof._p.addnext(new)
    lof = docx.text.paragraph.Paragraph(new, lof._parent)
    for r in lof.runs[1:]:
        r._r.getparent().remove(r._r)
    lof.runs[0].text = f"Figure {n}  {t}\t"
    lof = lof
toc = next(p for p in d.paragraphs if p.text.startswith("3.4 Execution Procedure") and p.style.name == "TOC 2")
new = copy.deepcopy(toc._p)
toc._p.addnext(new)
t5 = docx.text.paragraph.Paragraph(new, toc._parent)
for r in t5.runs[1:]:
    r._r.getparent().remove(r._r)
t5.runs[0].text = "3.5 Sender and Receiver Views, Scenarios and Graph Axis\t"
d.save(SUB / "MPFT_Mini_Project_Report.docx")
print("saved")
