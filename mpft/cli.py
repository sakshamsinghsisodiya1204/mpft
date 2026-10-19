"""Command line: python -m mpft send|receive|emulate|dashboard"""
import argparse
import csv
import logging
import os
import time


def parse_size(text):
    units = {"k": 1024, "m": 1024 ** 2}
    return int(float(text[:-1]) * units[text[-1].lower()]) if text[-1].lower() in units else int(text)


def cmd_send(a):
    from .sender import run_transfer
    targets = a.to.split(",")
    if len(targets) == 1:
        targets *= a.paths  # same address N times = N parallel connections
    r = run_transfer(a.file, targets, a.chunk_size, a.corrupt_rate, bind=a.bind)
    r.pop("events")
    print(("OK " if r["success"] else "FAILED ") + " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                                              for k, v in r.items()))
    if a.csv:
        new = not os.path.exists(a.csv)
        with open(a.csv, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=r.keys())
            if new:
                w.writeheader()
            w.writerow(r)
    return 0 if r["success"] else 1


def cmd_receive(a):
    from .receiver import start_receiver
    handle = start_receiver(a.listen, a.out)
    print(f"receiving on port {handle.port}, writing to {a.out} (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle.stop()


def cmd_emulate(a):
    from .emulator import run_emulator
    run_emulator(a.config)


def cmd_dashboard(a):
    import uvicorn
    uvicorn.run("web.app:app", host=a.host, port=a.port, log_level="warning")


def main(argv=None):
    p = argparse.ArgumentParser(prog="mpft", description="Multipath reliable file transfer")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("file")
    s.add_argument("--to", required=True, help="host:port[,host:port...] one per path")
    s.add_argument("--paths", type=int, default=1, help="connections to open when --to has one address")
    s.add_argument("--chunk-size", type=parse_size, default=1048576, help="bytes, or 64k / 1m")
    s.add_argument("--bind", help="local source IP for outgoing connections")
    s.add_argument("--csv", help="append metrics row to this CSV")
    s.add_argument("--corrupt-rate", type=float, default=0.0, help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_send)
    r = sub.add_parser("receive")
    r.add_argument("--listen", default="0.0.0.0:9000")
    r.add_argument("--out", default="downloads")
    r.set_defaults(fn=cmd_receive)
    e = sub.add_parser("emulate")
    e.add_argument("--config", required=True)
    e.set_defaults(fn=cmd_emulate)
    d = sub.add_parser("dashboard")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8080)
    d.set_defaults(fn=cmd_dashboard)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    raise SystemExit(a.fn(a) or 0)
