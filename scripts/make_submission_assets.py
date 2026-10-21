"""Draws the architecture and sequence figures and crops UI screenshots for the report/PPT."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image
from pathlib import Path

OUT = Path("docs/submission/assets")
NAVY, TEAL, GREY = "#16324f", "#1b6b73", "#f1f4f6"


def box(ax, x, y, w, h, text, fc=GREY, ec=NAVY, fs=9, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color="white" if fc in (NAVY, TEAL) else "#111", weight="bold" if bold else "normal")


def arrow(ax, p, q, text="", style="->", color=NAVY, dy=0.12):
    ax.annotate("", xy=q, xytext=p, arrowprops=dict(arrowstyle=style, color=color, lw=1.4))
    if text:
        ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + dy, text, ha="center", fontsize=8, color=color)


def architecture():
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.set_xlim(0, 10); ax.set_ylim(-0.1, 5.2); ax.axis("off")
    box(ax, 0.2, 1.9, 1.6, 1.4, "File on disk\n(read by pread,\nchunk by chunk)", fc="white")
    box(ax, 2.2, 1.6, 2.0, 2.0, "SENDER\nmanifest + SHA-256\nshared chunk queue\nretry / backoff", fc=NAVY, bold=True)
    for i, y in enumerate((3.9, 2.55, 1.2)):
        box(ax, 4.8, y - 0.35, 1.9, 0.7, f"Path {i}: TCP + emulator\ndelay / rate / loss", fc="white", fs=8)
        arrow(ax, (4.2, 2.6), (4.8, y), style="->")
        arrow(ax, (6.7, y), (7.3, 2.6), style="->")
    box(ax, 7.3, 1.6, 2.5, 2.0, "RECEIVER\nverify chunk SHA-256\npwrite at offset\nverify file, rename", fc=TEAL, bold=True)
    box(ax, 7.6, 0.1, 1.6, 0.8, "Output file\n(SHA-256 verified)", fc="white")
    arrow(ax, (8.4, 1.6), (8.4, 0.9))
    arrow(ax, (1.8, 2.6), (2.2, 2.6))
    ax.text(5.75, 4.85, "Parallel TCP paths (work stealing)", ha="center", fontsize=9, color=NAVY, style="italic")
    box(ax, 2.2, 0.1, 3.6, 0.5, "status/*.json  ->  web dashboard (SSE)", fc="white", fs=8)
    ax.set_title("MPFT architecture: one file, many TCP paths, end-to-end verification", fontsize=11, color=NAVY)
    fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def slide_architecture():
    """Large-text variant for the presentation."""
    fig, ax = plt.subplots(figsize=(7.6, 3.5))
    ax.set_xlim(-0.2, 10.2); ax.set_ylim(0, 4.6); ax.axis("off")
    box(ax, 0.0, 1.5, 2.6, 1.6, "SENDER\nshared queue\nretry + backoff", fc=NAVY, fs=12, bold=True)
    for i, y in enumerate((3.65, 2.3, 0.95)):
        box(ax, 3.6, y - 0.4, 2.8, 0.8, "Path %d  (TCP)" % i, fc="white", fs=12)
        arrow(ax, (2.6, 2.3), (3.6, y)); arrow(ax, (6.4, y), (7.4, 2.3))
    box(ax, 7.4, 1.5, 2.6, 1.6, "RECEIVER\nSHA-256 check\nwrite at offset", fc=TEAL, fs=12, bold=True)
    ax.text(5.0, 4.5, "emulator: delay, jitter, rate, kill, corrupt", ha="center", fontsize=11, color=NAVY, style="italic")
    ax.text(5.0, 0.0, "ACK / NACK flow back on the same path", ha="center", fontsize=11, color=NAVY)
    fig.savefig(OUT / "architecture_slide.png", dpi=220, bbox_inches="tight"); plt.close(fig)


def sequence():
    fig, ax = plt.subplots(figsize=(9, 5.6))
    ax.set_xlim(0, 9); ax.set_ylim(0, 8.6); ax.axis("off")
    box(ax, 0.8, 7.8, 2, 0.6, "Sender", fc=NAVY, bold=True)
    box(ax, 6.2, 7.8, 2, 0.6, "Receiver", fc=TEAL, bold=True)
    for x in (1.8, 7.2):
        ax.plot([x, x], [0.3, 7.8], color="#888", ls="--", lw=1)
    steps = [("HELLO (per path)", 7.2, 1), ("MANIFEST (JSON: size, chunks, hashes)", 6.5, 1),
             ("MANIFEST_ACK (chunks already held)", 5.8, -1), ("CHUNK i  (path A)", 5.0, 1),
             ("ACK i", 4.4, -1), ("CHUNK j  (path B, corrupted)", 3.6, 1), ("NACK j", 3.0, -1),
             ("CHUNK j  (retransmit)", 2.3, 1), ("ACK j", 1.7, -1), ("DONE  ->  verify file, rename  ->  DONE", 0.9, 1)]
    for text, y, d in steps:
        a, b = (1.8, 7.2) if d == 1 else (7.2, 1.8)
        arrow(ax, (a, y), (b, y), text, color="#a33" if "NACK" in text or "corrupted" in text else NAVY)
    ax.set_title("MPFT message sequence", fontsize=11, color=NAVY)
    fig.savefig(OUT / "sequence.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def crops():
    src = Image.open("docs/screenshots/ui-transfer-light-1440.png")
    src.crop((200, 60, 1440, 1700)).save(OUT / "ui_transfer_top.png")       # banner, verification, progress, chunk map, incidents, graphs
    src.crop((200, 1700, 1440, 2060)).save(OUT / "ui_transfer_paths.png")    # per-path table
    shots = {"scn_sender": ("scn-sender-success", 1000), "scn_receiver": ("scn-receiver-success", 1000), "scn_failure": ("scn-failure-receiver", 1300),
             "scn_wan": ("scn-wan-sender", 1500)}  # sender view, receiver view, failed transfer, slow-WAN scenario
    for out, (name, bottom) in shots.items():
        Image.open(f"docs/screenshots/{name}.png").crop((200, 60, 1440, bottom)).save(OUT / f"{out}.png")
    Image.open("docs/screenshots/scn-send-scenarios.png").save(OUT / "scn_send.png")
    Image.open("docs/screenshots/ui-send-light-1440.png").save(OUT / "ui_send.png")


if __name__ == "__main__":
    architecture(); slide_architecture(); sequence(); crops()
