"""Sender: one worker thread per path pulls chunk indexes from a shared queue (work stealing)."""
import hashlib
import json
import logging
import os
import queue
import random
import socket
import statistics
import threading
import time

from .protocol import (ACK, CHUNK, DONE, ERROR, HELLO, MANIFEST, MANIFEST_ACK, NACK, ProtocolError,
                       chunk_len, parse_addr, recv_msg, send_json, send_msg, sha256_hex, tune)
from .status import StatusWriter

log = logging.getLogger("mpft.sender")
MAX_RETRIES = 5
MAX_PATH_FAILS = 6


def build_manifest(file_path, chunk_size):
    """One streaming pass: per-chunk hashes and whole-file hash, never the whole file in RAM."""
    size = os.path.getsize(file_path)
    whole, chunks = hashlib.sha256(), []
    with open(file_path, "rb") as f:
        while data := f.read(chunk_size):
            whole.update(data)
            chunks.append(sha256_hex(data))
    return {"name": os.path.basename(file_path), "size": size, "chunk_size": chunk_size,
            "total_chunks": len(chunks), "file_sha256": whole.hexdigest(), "chunk_sha256": chunks}


class Sender:
    def __init__(self, file_path, targets, chunk_size, corrupt_rate, bind=None, chunk_timeout=5.0):
        self.path, self.targets, self.corrupt_rate = file_path, targets, corrupt_rate
        self.bind, self.timeout = bind, chunk_timeout
        self.m = build_manifest(file_path, chunk_size)
        self.cs, self.sid = chunk_size, random.getrandbits(32)
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
            mtype, _, _, payload = recv_msg(sock)
            if mtype != MANIFEST_ACK:
                raise ProtocolError("expected MANIFEST_ACK")
            held = set(json.loads(payload))
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
                    self.stop.wait(min(0.1 * 2 ** fails, 2.0))
                sock = self.connect(pid)
                if sock is None:
                    break
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
                self.fail_path(pid, idx)
                sock.close()
                sock = None
        if sock is not None and not self.error:
            self.socks[pid] = sock
        else:
            self.path_state[pid] = "down"
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
        try:
            send_msg(sock, CHUNK, self.sid, idx, data)
            mtype, _, ridx, _ = recv_msg(sock)
        except (OSError, ProtocolError):  # timeout, reset or garbage: treat the path as failed
            return False
        if mtype == ACK and ridx == idx:
            self.on_ack(pid, idx, len(data), (time.perf_counter() - start) * 1000)
        elif mtype == NACK:
            self.requeue(idx)
        else:
            return False
        return True

    def on_ack(self, pid, idx, nbytes, rtt_ms):
        with self.lock:
            now = time.time() - self.t0
            self.acked.add(idx)
            self.path_bytes[pid] += nbytes
            self.rtts.append(rtt_ms)
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
        self.requeue(idx)

    def requeue(self, idx):
        """NACK, timeout or dead socket: retry up to MAX_RETRIES with exponential backoff."""
        with self.lock:
            self.retransmits += 1
            n = self.attempts[idx] = self.attempts.get(idx, 0) + 1
        if n > MAX_RETRIES:
            self.error = f"chunk {idx} failed {MAX_RETRIES} retries"
            self.stop.set()
            return
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
                mtype, _, _, payload = recv_msg(s)
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
        self.t0 = time.time()
        writer = StatusWriter("sender", self.sid, self.snapshot).start()
        threads = [threading.Thread(target=self.worker, args=(i,), daemon=True) for i in range(len(self.targets))]
        for t in threads:
            t.start()
        while not self.stop.is_set() and any(t.is_alive() for t in threads):
            time.sleep(0.02)
        self.stop.set()
        for t in threads:
            t.join()
        ok = self.error is None and self.ready.is_set() and len(self.acked) == self.to_send and self.finish()
        elapsed = time.time() - self.t0
        self.done = ok
        writer.stop()
        for s in self.socks.values():
            s.close()
        os.close(self.fd)
        sent = sum(self.path_bytes.values())
        return {"total_time_s": elapsed, "goodput_mbit": sent * 8 / 1e6 / elapsed if elapsed else 0.0,
                "bytes_per_path": dict(self.path_bytes), "retransmitted_chunks": self.retransmits,
                "rtt_mean_ms": statistics.fmean(self.rtts) if self.rtts else 0.0,
                "rtt_jitter_ms": statistics.stdev(self.rtts) if len(self.rtts) > 1 else 0.0,
                "recovery_time_s": self.recovery if self.recovery is not None else 0.0,
                "success": ok, "error": self.error, "resumed_chunks": self.resumed,
                "fail_time_s": self.t_fail, "events": self.events}


def run_transfer(file_path, targets, chunk_size=1048576, corrupt_rate=0.0, bind=None, chunk_timeout=5.0):
    return Sender(file_path, targets, chunk_size, corrupt_rate, bind, chunk_timeout).run()
