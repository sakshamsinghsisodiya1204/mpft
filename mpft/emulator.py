"""TCP proxy per emulated path: delay, jitter, rate limit, bit corruption, and path death."""
import json
import logging
import queue
import random
import socket
import threading
import time

from . import events as ev
from .protocol import parse_addr, tune

log = logging.getLogger("mpft.emulator")
BLOCK = 16 * 1024  # forwarding unit; corrupt_rate is the probability per block


class PathProxy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.target = parse_addr(cfg["to"])
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((cfg.get("listen_host", "127.0.0.1"), cfg["listen_port"]))
        self.srv.listen(32)
        self.conns, self.lock, self.dead = [], threading.Lock(), False
        self.timer = None
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while True:
            try:
                client, _ = self.srv.accept()
            except OSError:
                return
            if self.cfg.get("drop_after_s") and self.timer is None:
                self.timer = threading.Timer(self.cfg["drop_after_s"], self.kill)  # clock starts at first connection
                self.timer.daemon = True
                self.timer.start()
            try:
                upstream = socket.create_connection(self.target, timeout=3)
            except OSError:
                client.close()
                continue
            with self.lock:
                self.conns += [client, upstream]
            tune(client), tune(upstream)
            self._start_pipe(client, upstream, corrupt=True)  # sender -> receiver carries the data
            self._start_pipe(upstream, client, corrupt=False)

    def _start_pipe(self, src, dst, corrupt):
        q = queue.Queue()
        threading.Thread(target=self._reader, args=(src, q, corrupt), daemon=True).start()
        threading.Thread(target=self._writer, args=(dst, q), daemon=True).start()

    def _reader(self, src, q, corrupt):
        c, last_due = self.cfg, 0.0
        try:
            while data := src.recv(BLOCK):
                if corrupt and random.random() < c.get("corrupt_rate", 0.0):
                    b = bytearray(data)
                    b[random.randrange(len(b))] ^= 1 << random.randrange(8)
                    data = bytes(b)
                delay = c.get("delay_ms", 0) + random.uniform(-1, 1) * c.get("jitter_ms", 0)
                last_due = max(last_due, time.monotonic() + max(delay, 0) / 1000)  # never reorder bytes
                q.put((last_due, data))
        except OSError:
            pass
        q.put((0.0, None))

    def _writer(self, dst, q):
        rate = self.cfg.get("rate_mbit", 0)
        try:
            while True:
                due, data = q.get()
                if data is None:
                    dst.shutdown(socket.SHUT_WR)
                    return
                time.sleep(max(due - time.monotonic(), 0))
                dst.sendall(data)
                if rate:
                    time.sleep(len(data) * 8 / (rate * 1e6))
        except OSError:
            pass

    def kill(self):
        log.warning("path on port %s dropped", self.cfg["listen_port"])
        ev.emit("emulator_path_killed", port=self.cfg["listen_port"])
        self.dead = True
        self.stop()

    def stop(self):
        if self.timer:
            self.timer.cancel()
        self.srv.close()
        with self.lock:
            for c in self.conns:
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                c.close()


class EmulatorHandle:
    def __init__(self, paths):
        self.paths = paths

    def state(self):
        return [{"path": i, **p.cfg, "dead": p.dead} for i, p in enumerate(self.paths)]

    def kill(self, i):
        self.paths[i].kill()

    def set_corrupt(self, rate):
        for p in self.paths:
            p.cfg["corrupt_rate"] = rate  # read per block, so it applies immediately

    def stop(self):
        for p in self.paths:
            p.stop()


def start_emulator(config):
    """config: list of dicts {listen_port, to, delay_ms, jitter_ms, rate_mbit, drop_after_s, corrupt_rate}."""
    return EmulatorHandle([PathProxy(c) for c in config])


def run_emulator(config_path, control_port=None):
    with open(config_path) as f:
        config = json.load(f)
    handle = start_emulator(config)
    if control_port:
        from .emu_control import start_control
        start_control(handle, control_port)
        print(f"control: http://127.0.0.1:{control_port}/state", flush=True)
    for c in config:
        print(f"path :{c['listen_port']} -> {c['to']} delay={c.get('delay_ms', 0)}ms "
              f"jitter={c.get('jitter_ms', 0)}ms rate={c.get('rate_mbit', 0) or 'unlimited'}Mbit "
              f"drop_after={str(c['drop_after_s']) + 's' if c.get('drop_after_s') else 'never'} corrupt={c.get('corrupt_rate', 0)}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle.stop()
