"""Sender: one worker thread per path pulls chunk indexes from a shared queue (work stealing)."""
import json
import logging
import os
import queue
import random
import socket
import threading
import time

from .protocol import (ACK, CHUNK, DONE, ERROR, HELLO, MANIFEST, MANIFEST_ACK, NACK, ProtocolError,
                       build_manifest, chunk_len, parse_addr, recv_msg, send_json, send_msg, tune)
from .metrics import build_result
from . import events as ev
from .status import StatusWriter

log = logging.getLogger("mpft.sender")
MAX_RETRIES = 5
MAX_PATH_FAILS = 6


class Sender:
    def __init__(self, file_path, targets, chunk_size, corrupt_rate, bind=None, chunk_timeout=5.0, session_id=None):
        self.path, self.targets, self.corrupt_rate = file_path, targets, corrupt_rate
        self.bind, self.timeout = bind, chunk_timeout
        self.m = build_manifest(file_path, chunk_size)
        self.cs, self.sid = chunk_size, session_id if session_id is not None else random.getrandbits(32)
        self.fd = os.open(file_path, os.O_RDONLY)
        self.q = queue.PriorityQueue()  # (0, idx) retries jump ahead of fresh (1, idx) work
        self.lock, self.manifest_lock = threading.Lock(), threading.Lock()
        self.ready, self.stop = threading.Event(), threading.Event()  # stop: finished or failed
        self.acked, self.attempts, self.retransmits = set(), {}, 0
        self.resumed, self.to_send = 0, 0
        self.path_bytes = {i: 0 for i in range(len(targets))}
        self.path_state = {i: "up" for i in range(len(targets))}
        self.socks, self.rtts, self.events = {}, [], []  # events: (t, path, bytes) per ACK
        self.t0 = self.t_fail = self.recovery = None
        self.fail_pending = set()
        self.error = None

    # ---- connection handling ----
    def connect(self, pid):
        host, port = parse_addr(self.targets[pid])
        for attempt in range(4):
            try:
                s = socket.create_connection((host, port), timeout=3,
                                             source_address=(self.bind, 0) if self.bind else None)
                tune(s).settimeout(self.timeout)
                send_msg(s, HELLO, self.sid)
                ev.emit("path_up", role="sender", session=self.sid, path=pid,
                        local="%s:%d" % s.getsockname()[:2], remote=self.targets[pid])
                ev.message("sender", self.sid, HELLO, 0, 0, pid, "out")
                return s
            except OSError:
                time.sleep(0.2 * 2 ** attempt)
        return None

    def ensure_manifest(self, sock):
        """First path to get here sends MANIFEST; the rest wait. If it dies, the next path takes over."""
        with self.manifest_lock:
            if self.ready.is_set():
                return
            send_json(sock, MANIFEST, self.sid, self.m)
            ev.emit("manifest_sent", role="sender", session=self.sid, total_chunks=self.m["total_chunks"])
            ev.message("sender", self.sid, MANIFEST, 0, 0, None, "out")
            mtype, _, _, payload = recv_msg(sock)
            if mtype != MANIFEST_ACK:
                raise ProtocolError("expected MANIFEST_ACK")
            held = set(json.loads(payload))
            ev.message("sender", self.sid, MANIFEST_ACK, 0, 0, None, "in")
            self.resumed = len(held)
            todo = [i for i in range(self.m["total_chunks"]) if i not in held]
            self.to_send = len(todo)
            for i in todo:
                self.q.put((1, i))
            if not todo:
                self.stop.set()
            self.ready.set()

    # ---- per-path worker ----
    def worker(self, pid):
        sock, fails = None, 0  # fails: consecutive failures on this path
        while not self.stop.is_set():
            if sock is None:
                if fails >= MAX_PATH_FAILS:
                    break
                if fails:  # exponential backoff before reconnecting a flaky path
                    delay = min(0.1 * 2 ** fails, 2.0)
                    ev.emit("backoff", role="sender", session=self.sid, path=pid, delay=delay, fails=fails)
                    self.stop.wait(delay)
                sock = self.connect(pid)
                if sock is None:
                    break
                if fails:
                    ev.emit("path_restored", role="sender", session=self.sid, path=pid)
                try:
                    self.ensure_manifest(sock)
                except (OSError, ProtocolError):
                    sock.close()
                    sock = None
                    continue
            try:
                _, idx = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            if self.send_chunk(sock, pid, idx):
                fails = 0
            else:
                fails += 1
                ev.emit("path_down", role="sender", session=self.sid, path=pid, reason=getattr(self, "fail_reason", "send failed"))
                self.fail_path(pid, idx)
                sock.close()
                sock = None
        if sock is not None and not self.error:
            self.socks[pid] = sock
        else:
            self.path_state[pid] = "down"
            ev.emit("path_down", role="sender", session=self.sid, path=pid)
            if sock is None and not self.stop.is_set():
                log.warning("path %d is down", pid)

    def send_chunk(self, sock, pid, idx):
        """Return False if the connection is unusable; chunk is requeued here on NACK."""
        data = os.pread(self.fd, chunk_len(self.m["size"], self.cs, idx), idx * self.cs)
        if random.random() < self.corrupt_rate:
            flipped = bytearray(data)
            flipped[random.randrange(len(flipped))] ^= 0x01
            data = bytes(flipped)
        start = time.perf_counter()
        ev.emit("chunk_state", role="sender", session=self.sid, index=idx, state="inflight", path=pid,
                attempt=self.attempts.get(idx, 0) + 1, offset=idx * self.cs, size=len(data))
        ev.message("sender", self.sid, CHUNK, idx, len(data), pid, "out")
        try:
            send_msg(sock, CHUNK, self.sid, idx, data)
            mtype, _, ridx, _ = recv_msg(sock)
        except (OSError, ProtocolError) as e:  # timeout, reset or garbage: treat the path as failed
            self.fail_reason = "timeout" if isinstance(e, TimeoutError) else type(e).__name__
            if isinstance(e, TimeoutError):
                ev.emit("timeout", role="sender", session=self.sid, index=idx, path=pid, after_s=self.timeout)
            return False
        ev.message("sender", self.sid, mtype, ridx, 0, pid, "in")
        if mtype == ACK and ridx == idx:
            self.on_ack(pid, idx, len(data), (time.perf_counter() - start) * 1000)
        elif mtype == NACK:
            ev.emit("nack", role="sender", session=self.sid, index=idx, path=pid)
            self.requeue(idx, pid)
        else:
            return False
        return True

    def on_ack(self, pid, idx, nbytes, rtt_ms):
        with self.lock:
            now = time.time() - self.t0
            self.acked.add(idx)
            ev.emit("chunk_state", role="sender", session=self.sid, index=idx, state="done", path=pid,
                    bytes=nbytes, rtt_ms=round(rtt_ms, 2))
            self.path_bytes[pid] += nbytes
            self.rtts.append(rtt_ms)
            self.tick_rtts.setdefault(pid, []).append(rtt_ms)
            self.events.append((round(now, 4), pid, nbytes))
            if idx in self.fail_pending:
                self.fail_pending.discard(idx)
                if not self.fail_pending and self.recovery is None:
                    self.recovery = now - self.t_fail
            if len(self.acked) == self.to_send:
                self.stop.set()

    def fail_path(self, pid, idx):
        with self.lock:
            if self.t_fail is None:
                self.t_fail = time.time() - self.t0
            self.fail_pending.add(idx)
        log.warning("path %d failed with chunk %d in flight; requeueing", pid, idx)
        self.requeue(idx, pid)

    def requeue(self, idx, pid=None):
        """NACK, timeout or dead socket: retry up to MAX_RETRIES with exponential backoff."""
        with self.lock:
            self.retransmits += 1
            n = self.attempts[idx] = self.attempts.get(idx, 0) + 1
        if n > MAX_RETRIES:
            self.error = f"chunk {idx} failed {MAX_RETRIES} retries"
            ev.emit("chunk_state", role="sender", session=self.sid, index=idx, state="failed", path=pid, attempt=n)
            self.stop.set()
            return
        ev.emit("requeue", role="sender", session=self.sid, index=idx, path=pid, attempt=n, count=n,
                reason=getattr(self, "fail_reason", "nack") if pid is not None and idx in self.fail_pending else "nack",
                delay=min(0.05 * 2 ** (n - 1), 1.0))
        ev.emit("chunk_state", role="sender", session=self.sid, index=idx, state="retransmitted", path=pid, attempt=n)
        timer = threading.Timer(min(0.05 * 2 ** (n - 1), 1.0), self.q.put, ((0, idx),))
        timer.daemon = True
        timer.start()

    # ---- end of transfer ----
    def finish(self):
        """DONE handshake: receiver verifies the whole file and answers DONE or ERROR."""
        socks = list(self.socks.values()) or [s for s in [self.connect(0)] if s]
        for s in socks:
            try:
                s.settimeout(60)
                send_msg(s, DONE, self.sid)
                ev.message("sender", self.sid, DONE, 0, 0, None, "out")
                mtype, _, _, payload = recv_msg(s)
                ev.message("sender", self.sid, mtype, 0, len(payload), None, "in")
                if mtype == DONE:
                    return True
                self.error = payload.decode(errors="replace") or "receiver reported ERROR"
                return False
            except (OSError, ProtocolError):
                continue
        self.error = self.error or "no connection left for DONE"
        return False

    def snapshot(self):
        with self.lock:
            return {"file_name": self.m["name"], "file_size": self.m["size"], "file_sha256": self.m["file_sha256"],
                    "total_chunks": self.m["total_chunks"], "chunks_done": self.resumed + len(self.acked),
                    "retransmissions": self.retransmits,
                    "hash_status": "verified" if self.done else "pending",
                    "per_path": [{"path_id": p, "bytes": b, "state": self.path_state[p]}
                                 for p, b in self.path_bytes.items()]}

    def run(self):
        self.done = False
        self.tick_rtts = {}
        self.t0 = time.time()
        ev.emit("session_started", role="sender", session=self.sid, file_name=self.m["name"],
                file_size=self.m["size"], file_sha256=self.m["file_sha256"], chunk_size=self.cs,
                total_chunks=self.m["total_chunks"], paths=len(self.targets))
        writer = StatusWriter("sender", self.sid, self.snapshot).start()
        threads = [threading.Thread(target=self.worker, args=(i,), daemon=True) for i in range(len(self.targets))]
        for t in threads:
            t.start()
        last_tick, last_bytes = time.time(), dict(self.path_bytes)
        while not self.stop.is_set() and any(t.is_alive() for t in threads):
            time.sleep(0.02)
            if time.time() - last_tick >= 1.0:  # per-path throughput once a second
                dt, last_tick = time.time() - last_tick, time.time()
                for p, b in dict(self.path_bytes).items():
                    ev.emit("throughput_tick", role="sender", session=self.sid, path=p,
                            mbit=round((b - last_bytes[p]) * 8 / 1e6 / dt, 3), bytes=b)
                    last_bytes[p] = b
                    r = self.tick_rtts.pop(p, [])
                    if r:
                        ev.emit("rtt_sample", role="sender", session=self.sid, path=p, mean_ms=round(sum(r) / len(r), 2),
                                min_ms=round(min(r), 2), max_ms=round(max(r), 2))
        self.stop.set()
        for t in threads:
            t.join()
        ok = self.error is None and self.ready.is_set() and len(self.acked) == self.to_send and self.finish()
        elapsed = time.time() - self.t0
        self.done = ok
        writer.stop()
        ev.emit("session_done", role="sender", session=self.sid, success=ok, error=self.error, elapsed_s=round(elapsed, 3),
                retransmits=self.retransmits, bytes_per_path=dict(self.path_bytes))
        for s in self.socks.values():
            s.close()
        os.close(self.fd)
        return build_result(self, elapsed, ok)


def run_transfer(file_path, targets, chunk_size=1048576, corrupt_rate=0.0, bind=None, chunk_timeout=5.0,
                 session_id=None):
    return Sender(file_path, targets, chunk_size, corrupt_rate, bind, chunk_timeout, session_id).run()
