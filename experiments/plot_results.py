"""Turn results/*.csv into plain PNG graphs in results/."""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")


def load(name):
    with open(os.path.join(RESULTS, f"{name}.csv")) as f:
        return list(csv.DictReader(f))


def finish(fig, ax, name, title, xlabel, ylabel):
    ax.set(title=title, xlabel=xlabel, ylabel=ylabel)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, name), dpi=130)
    plt.close(fig)
    print("wrote", name)


def line(rows, x, y, name, title, xlabel, ylabel):
    fig, ax = plt.subplots(figsize=(6, 4))
    xs = [float(r[x]) for r in rows]
    ys = [float(r[y]) for r in rows]
    ax.plot(xs, ys, marker="o")
    for a, b in zip(xs, ys):
        ax.annotate(f"{b:.1f}", (a, b), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
    finish(fig, ax, name, title, xlabel, ylabel)


def throughput_vs_paths():
    rows = load("baseline")
    line([dict(r, n=r["label"]) for r in rows], "n", "goodput_mbit", "throughput_vs_paths.png",
         "Goodput vs number of paths (each path 40 Mbit/s, 10 ms)", "Number of paths", "Goodput (Mbit/s)")


def time_vs_delay():
    rows = load("delay")
    line([dict(r, d=r["label"]) for r in rows], "d", "total_time_s", "time_vs_delay.png",
         "Transfer time as one of two paths gets slower", "One-way delay on path 2 (ms)", "Total time (s)")


def path_byte_share():
    r = load("asymmetric")[0]
    per = {int(k): v for k, v in json.loads(r["bytes_per_path"]).items()}
    total = sum(per.values())
    names = ["path 0\n80 Mbit, 5 ms", "path 1\n20 Mbit, 20 ms", "path 2\n5 Mbit, 60 ms"]
    fig, ax = plt.subplots(figsize=(6, 4))
    shares = [100 * per.get(i, 0) / total for i in range(3)]
    ax.bar(names, shares, color="#555555")
    for i, s in enumerate(shares):
        ax.annotate(f"{s:.1f}%", (i, s), textcoords="offset points", xytext=(0, 4), ha="center")
    finish(fig, ax, "path_byte_share.png", "Share of bytes carried per path (work stealing)", "Path", "Share of file bytes (%)")


def recovery_timeline():
    with open(os.path.join(RESULTS, "failure_events.csv")) as f:
        ev = list(csv.DictReader(f))
    fail = float(load("failure")[1]["fail_time_s"])
    fig, ax = plt.subplots(figsize=(7, 4))
    bin_s = 0.5
    end = max(float(e["t_s"]) for e in ev)
    nbins = int(end / bin_s) + 1
    total = [0.0] * nbins
    for pid in sorted({int(e["path_id"]) for e in ev}):
        rate = [0.0] * nbins
        for e in ev:
            if int(e["path_id"]) == pid:
                rate[int(float(e["t_s"]) / bin_s)] += int(e["bytes"]) * 8 / 1e6 / bin_s
        total = [a + b for a, b in zip(total, rate)]
        ax.plot([(i + 0.5) * bin_s for i in range(nbins)], rate, marker=".", label=f"path {pid}")
    ax.plot([(i + 0.5) * bin_s for i in range(nbins)], total, "k--", label="total")
    ax.axvline(fail, color="red", linestyle=":", label="path 2 failure")
    ax.legend()
    finish(fig, ax, "recovery_timeline.png", "Per-path throughput around a path failure (0.5 s bins)",
           "Time since start (s)", "Throughput (Mbit/s)")


def retransmissions_vs_corruption():
    rows = load("corruption")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar([r["label"] for r in rows], [int(r["retransmitted_chunks"]) for r in rows], color="#555555")
    for i, r in enumerate(rows):
        ax.annotate(r["retransmitted_chunks"], (i, int(r["retransmitted_chunks"])), textcoords="offset points",
                    xytext=(0, 4), ha="center")
    finish(fig, ax, "retransmissions_vs_corruption.png", "Retransmitted chunks vs chunk corruption rate",
           "Probability a sent chunk is corrupted", "Retransmitted chunks (count)")


def chunk_size():
    rows = load("chunksize")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([r["label"] for r in rows], [float(r["goodput_mbit"]) for r in rows], marker="o")
    finish(fig, ax, "chunk_size_vs_goodput.png", "Goodput vs chunk size (4 paths)", "Chunk size", "Goodput (Mbit/s)")


if __name__ == "__main__":
    for fn in (throughput_vs_paths, time_vs_delay, path_byte_share, recovery_timeline,
               retransmissions_vs_corruption, chunk_size):
        fn()
