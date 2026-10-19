"""Automated experiments. Receiver and emulator run in-process; results go to results/*.csv.
Usage: python experiments/run_experiments.py [--size-mb 50] [--only baseline,failure]"""
import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpft.emulator import start_emulator  # noqa: E402
from mpft.receiver import start_receiver  # noqa: E402
from mpft.sender import run_transfer  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIELDS = ["scenario", "label", "total_time_s", "goodput_mbit", "retransmitted_chunks", "rtt_mean_ms",
          "rtt_jitter_ms", "recovery_time_s", "success", "bytes_per_path", "resumed_chunks"]
BASE_PORT, CHUNK = 19400, 256 * 1024
PATH_RATE, PATH_DELAY = 40, 10  # default emulated path: 40 Mbit/s, 10 ms one-way


def save(name, rows, fields=FIELDS):
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, f"{name}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote results/{name}.csv ({len(rows)} rows)", flush=True)


def transfer(src, paths, chunk=CHUNK, corrupt=0.0):
    """One transfer through emulated paths (list of config dicts without ports). Returns result dict."""
    out = tempfile.mkdtemp(prefix="mpft-out-")
    rx = start_receiver("127.0.0.1:0", out)
    cfg = [{"listen_port": BASE_PORT + i, "to": f"127.0.0.1:{rx.port}", **p} for i, p in enumerate(paths)]
    emu = start_emulator(cfg)
    try:
        r = run_transfer(src, [f"127.0.0.1:{c['listen_port']}" for c in cfg], chunk, corrupt)
    finally:
        emu.stop()
        rx.stop()
    return r


def row(scenario, label, r):
    r = dict(r, scenario=scenario, label=label, bytes_per_path=json.dumps(r["bytes_per_path"]))
    print(f"  {scenario}/{label}: {r['total_time_s']:.2f}s {r['goodput_mbit']:.1f} Mbit/s ok={r['success']}", flush=True)
    return r


def path(rate=PATH_RATE, delay=PATH_DELAY, **kw):
    return {"rate_mbit": rate, "delay_ms": delay, **kw}


def exp_baseline(src):
    return save("baseline", [row("baseline", n, transfer(src, [path()] * n)) for n in (1, 2, 4, 8)])


def exp_asymmetric(src):
    paths = [path(80, 5), path(20, 20), path(5, 60)]
    save("asymmetric", [row("asymmetric", "80/20/5 Mbit", transfer(src, paths))])


def exp_delay(src):
    rows = []
    for d in (0, 25, 50, 100, 200):
        r = transfer(src, [path(), path(delay=d, jitter_ms=d / 4)])
        rows.append(row("delay", str(d), r))
    save("delay", rows)


def exp_failure(src):
    base = row("failure", "no failure", transfer(src, [path()] * 3))
    r = transfer(src, [path(), path(), path(drop_after_s=1.5)])
    with open(os.path.join(RESULTS, "failure_events.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "path_id", "bytes"])
        w.writerows(r["events"])
    rows = [base, dict(row("failure", "path 2 dies at 1.5s", r), fail_time_s=r["fail_time_s"])]
    save("failure", rows, FIELDS + ["fail_time_s"])


def exp_corruption(src):
    rows = [row("corruption", f"{int(c * 100)}%", transfer(src, [path()] * 4, corrupt=c)) for c in (0, 0.01, 0.05)]
    save("corruption", rows)


def exp_chunksize(src):
    rows = [row("chunksize", f"{c // 1024}KiB", transfer(src, [path()] * 4, chunk=c))
            for c in (64 << 10, 256 << 10, 1 << 20, 4 << 20)]
    save("chunksize", rows)


def exp_resume(src):
    """Kill the sender process at ~40% progress, then run it again against the same part file."""
    out = tempfile.mkdtemp(prefix="mpft-out-")
    rx = start_receiver("127.0.0.1:0", out)
    emu = start_emulator([{"listen_port": BASE_PORT + i, "to": f"127.0.0.1:{rx.port}", **path()} for i in range(2)])
    cmd = [sys.executable, "-m", "mpft", "send", src, "--to", f"127.0.0.1:{BASE_PORT},127.0.0.1:{BASE_PORT + 1}",
           "--chunk-size", str(CHUNK)]
    root = os.path.dirname(RESULTS)
    try:
        t0 = time.time()
        p = subprocess.Popen(cmd, cwd=root, stdout=subprocess.DEVNULL)
        total = os.path.getsize(src) // CHUNK
        while not any(len(s.held) >= 0.4 * total for s in list(rx.sessions.values())) and p.poll() is None:
            time.sleep(0.05)
        p.send_signal(signal.SIGKILL)
        p.wait()
        interrupted_at = time.time() - t0
        held = max(len(s.held) for s in rx.sessions.values())
        print(f"  interrupted after {interrupted_at:.2f}s with {held}/{total} chunks held", flush=True)
        csv_path = os.path.join(out, "resume_run.csv")
        t1 = time.time()
        res = subprocess.run(cmd + ["--csv", csv_path], cwd=root, capture_output=True, text=True)
        resume_time = time.time() - t1
        ok = res.returncode == 0
    finally:
        emu.stop()
        rx.stop()
    full = row("resume", "uninterrupted", transfer(src, [path()] * 2))
    rows = [full,
            {"scenario": "resume", "label": "killed at 40%", "total_time_s": interrupted_at, "success": False,
             "resumed_chunks": 0},
            {"scenario": "resume", "label": "resumed run", "total_time_s": resume_time, "success": ok,
             "resumed_chunks": held}]
    print(f"  resumed run: {resume_time:.2f}s ok={ok} skipped={held} chunks", flush=True)
    save("resume", rows)


EXPERIMENTS = {"baseline": exp_baseline, "asymmetric": exp_asymmetric, "delay": exp_delay,
               "failure": exp_failure, "corruption": exp_corruption, "chunksize": exp_chunksize,
               "resume": exp_resume}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size-mb", type=float, default=50)
    ap.add_argument("--only", default=",".join(EXPERIMENTS))
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="mpft-src-")
    src = os.path.join(tmp, "testfile.bin")
    with open(src, "wb") as f:
        for _ in range(int(a.size_mb)):
            f.write(os.urandom(1 << 20))
    for name in a.only.split(","):
        print(f"== {name}", flush=True)
        EXPERIMENTS[name](src)


if __name__ == "__main__":
    main()
