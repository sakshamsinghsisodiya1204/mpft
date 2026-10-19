"""Two real `mpft web` instances (alice, bob) plus headless Chromium pages that record console errors, failed requests and SSE."""
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODES = {"alice": (8000, 8001, 9000), "bob": (8010, 8011, 9010)}

# Wraps EventSource so every SSE message is also kept in window.__sse.
SSE_HOOK = """
(() => { const E = window.EventSource; window.__sse = [];
  window.EventSource = function (u, o) { const es = new E(u, o);
    es.addEventListener('message', (m) => { try { window.__sse.push(JSON.parse(m.data)); } catch (e) { window.__sse.push({bad: m.data}); } });
    return es; }; window.EventSource.prototype = E.prototype; })();
"""


def make_file(path, size, seed=7):
    import random
    rnd = random.Random(seed)
    with open(path, "wb") as f:
        for _ in range(size >> 20):
            f.write(rnd.randbytes(1 << 20))
        f.write(rnd.randbytes(size & ((1 << 20) - 1)))
    return path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Nodes:
    """Starts both instances in one process group; cwd is a temp dir so .mpft-state/ stays out of the repo."""

    def __init__(self, tmp):
        self.tmp, self.procs, self.out = str(tmp), [], {}
        for ui, peer, data in NODES.values():
            for port in (ui, peer):
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        raise RuntimeError(f"port {port} already in use (stale mpft web process?)")
        for name, (ui, peer, data) in NODES.items():
            out = os.path.join(self.tmp, name + "-dl")
            self.out[name] = out
            cmd = [sys.executable, "-m", "mpft", "web", "--name", name, "--ui-port", str(ui), "--peer-port", str(peer),
                   "--data-port", str(data), "--out", out]
            env = dict(os.environ, PYTHONPATH=ROOT, MPFT_STATUS_DIR=os.path.join(self.tmp, "status"))
            self.procs.append(subprocess.Popen(cmd, cwd=self.tmp, env=env, start_new_session=True,
                                               stdout=open(os.path.join(self.tmp, name + ".log"), "w"), stderr=subprocess.STDOUT))
        for name, (ui, _, _) in NODES.items():
            self.wait(ui)

    def wait(self, port, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=1).read()
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError(f"port {port} never came up; see logs in {self.tmp}")

    def info(self, name):
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{NODES[name][0]}/api/info"))

    def state(self, name):
        return os.path.join(self.tmp, ".mpft-state", name)

    def stop(self):
        for p in self.procs:  # each instance leads its own process group
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


class Recorder:
    """Per-page log of console errors, page exceptions, failed/4xx/5xx requests."""

    def __init__(self, page, label):
        self.label, self.page = label, page
        self.console_errors, self.failed = [], []
        page.add_init_script(SSE_HOOK)
        page.on("console", lambda m: m.type == "error" and self.console_errors.append(m.text))
        page.on("pageerror", lambda e: self.console_errors.append("pageerror: " + str(e)))
        page.on("requestfailed", lambda r: self.failed.append(f"{r.method} {r.url} {r.failure}"))
        page.on("response", lambda r: r.status >= 400 and self.failed.append(f"{r.status} {r.url}"))

    def sse(self):
        return self.page.evaluate("window.__sse || []")


def send_file(page, file_path, bob_id, bob_code, profile="path_failure", paths=2):
    """Drive the Send form on alice's page."""
    page.goto(page.url.split("#")[0] + "#/send")
    page.set_input_files("#file", file_path)
    page.fill("#target", bob_id)
    page.fill("#pcode", bob_code)
    page.evaluate("document.querySelector('details') && (document.querySelector('details').open = true)")
    page.fill("#paths", str(paths))
    page.select_option("#profile", profile)
    page.click("button[type=submit]")
    page.wait_for_function("location.hash.startsWith('#/transfer/')", timeout=60000)
    return page.evaluate("location.hash").rsplit("/", 1)[1]
