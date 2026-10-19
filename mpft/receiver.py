"""Receiver: accepts path connections, verifies chunks, reassembles into file.part, renames when verified."""
import hashlib
import json
import logging
import os
import socket
import threading

from .protocol import (ACK, CHUNK, DONE, ERROR, HELLO, MANIFEST, MANIFEST_ACK, NACK, ProtocolError,
                       chunk_len, parse_addr, recv_msg, send_json, send_msg, sha256_hex, tune)
from . import events as ev
from .status import StatusWriter

log = logging.getLogger("mpft.receiver")


class Session:
    def __init__(self, session_id, manifest, out_dir):
        self.id, self.m = session_id, manifest
        self.total, self.size, self.cs = manifest["total_chunks"], manifest["size"], manifest["chunk_size"]
        os.makedirs(out_dir, exist_ok=True)
        name = os.path.basename(manifest["name"])  # basename: no path traversal
        self.final = os.path.join(out_dir, name if name not in ("", ".", "..") else "file")
        self.part = self.final + ".part"
        fresh = not os.path.exists(self.part)
        self.fd = os.open(self.part, os.O_RDWR | os.O_CREAT)
        if os.fstat(self.fd).st_size != self.size:
            os.ftruncate(self.fd, 0)
            os.ftruncate(self.fd, self.size)
            fresh = True
        # Resume: trust only chunks whose bytes on disk match the manifest hash.
        self.held = set() if fresh else self._scan()
        self.lock = threading.Lock()
        self.path_bytes, self.duplicates, self.nacks = {}, 0, 0
        self.hash_status, self.finished = "pending", False
        self.writer = None

    def _scan(self):
        held = set()
        for i in range(self.total):
            data = os.pread(self.fd, chunk_len(self.size, self.cs, i), i * self.cs)
            if sha256_hex(data) == self.m["chunk_sha256"][i]:
                held.add(i)
        return held

    def finalize(self):
        """Verify whole-file SHA-256, then atomically rename. Caller holds self.lock."""
        if self.finished:
            return True
        h = hashlib.sha256()
        for off in range(0, self.size, 1 << 20):
            h.update(os.pread(self.fd, min(1 << 20, self.size - off), off))
        ev.emit("hash_file_verified" if h.hexdigest() == self.m["file_sha256"] else "hash_file_mismatch",
                role="receiver", session=self.id, expected=self.m["file_sha256"], computed=h.hexdigest())
        if h.hexdigest() != self.m["file_sha256"]:
            self.hash_status = "mismatch"
            return False
        os.replace(self.part, self.final)
        self.hash_status, self.finished = "verified", True
        log.info("session %d complete: %s verified", self.id, self.final)
        return True

    def snapshot(self):
        with self.lock:
            return {"file_name": self.m["name"], "file_size": self.size, "file_sha256": self.m["file_sha256"],
                    "total_chunks": self.total,
                    "chunks_done": len(self.held), "retransmissions": self.duplicates + self.nacks,
                    "hash_status": self.hash_status,
                    "per_path": [{"path_id": p, "bytes": b, "state": "up"}
                                 for p, b in sorted(self.path_bytes.items())]}


class ReceiverHandle:
    def __init__(self, listen, out_dir):
        self.out_dir, self.sessions = out_dir, {}
        self.lock, self.conns, self.next_path = threading.Lock(), set(), {}
        self.stopping = threading.Event()
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(parse_addr(listen))
        self.server.listen(32)
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self.stopping.set()
        self.server.close()
        with self.lock:
            for c in list(self.conns):
                c.close()
            for s in self.sessions.values():
                if s.writer:
                    s.writer.stop()

    def _accept_loop(self):
        while not self.stopping.is_set():
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with self.lock:
                self.conns.add(conn)
            threading.Thread(target=self._serve, args=(tune(conn),), daemon=True).start()

    def _open_session(self, sid, payload):
        manifest = json.loads(payload)
        with self.lock:
            sess = self.sessions.get(sid)
            if sess is None:
                sess = self.sessions[sid] = Session(sid, manifest, self.out_dir)
                sess.writer = StatusWriter("receiver", sid, sess.snapshot).start()
                ev.emit("session_started", role="receiver", session=sid, file_name=manifest["name"],
                        file_size=sess.size, file_sha256=manifest["file_sha256"], chunk_size=sess.cs,
                        total_chunks=sess.total)
                with sess.lock:
                    if len(sess.held) == sess.total:
                        sess.finalize()
        return sess

    def _serve(self, conn):
        try:
            mtype, sid, _, _ = recv_msg(conn)
            if mtype != HELLO:
                raise ProtocolError("expected HELLO")
            with self.lock:
                path_id = self.next_path[sid] = self.next_path.get(sid, -1) + 1
            log.info("session %d: path %d connected", sid, path_id)
            ev.emit("path_up", role="receiver", session=sid, path=path_id, remote="%s:%d" % conn.getpeername()[:2],
                    local="%s:%d" % conn.getsockname()[:2])
            ev.message("receiver", sid, HELLO, 0, 0, path_id, "in")
            while True:
                mtype, sid, idx, payload = recv_msg(conn)
                sess = self.sessions.get(sid)
                if mtype != CHUNK:
                    ev.message("receiver", sid, mtype, idx, len(payload), path_id, "in")
                if mtype == MANIFEST:
                    sess = self._open_session(sid, payload)
                    ev.emit("manifest_received", role="receiver", session=sid, total_chunks=sess.total, held=len(sess.held))
                    send_json(conn, MANIFEST_ACK, sid, sorted(sess.held))
                elif sess is None:
                    send_msg(conn, ERROR, sid, 0, b"no manifest")
                elif mtype == CHUNK:
                    send_msg(conn, self._store(sess, path_id, idx, payload), sid, idx)
                elif mtype == DONE:
                    with sess.lock:
                        ok = len(sess.held) == sess.total and sess.finalize()
                    send_msg(conn, DONE if ok else ERROR, sid, 0, b"" if ok else b"incomplete or hash mismatch")
                    ev.emit("session_done", role="receiver", session=sid, success=ok)
        except (ConnectionError, OSError, ProtocolError) as e:
            log.info("connection closed: %s", e)
            ev.emit("path_down", role="receiver", session=locals().get("sid"), path=locals().get("path_id"))
        finally:
            conn.close()
            with self.lock:
                self.conns.discard(conn)

    def _store(self, sess, path_id, idx, data):
        if idx >= sess.total or len(data) != chunk_len(sess.size, sess.cs, idx) \
                or sha256_hex(data) != sess.m["chunk_sha256"][idx]:
            with sess.lock:
                sess.nacks += 1
            log.warning("session %d chunk %d failed verification -> NACK", sess.id, idx)
            ev.emit("hash_chunk_bad", role="receiver", session=sess.id, index=idx, path=path_id,
                    sha=sess.m["chunk_sha256"][idx][:12] if idx < sess.total else "")
            ev.message("receiver", sess.id, NACK, idx, 0, path_id, "out")
            return NACK
        ev.emit("hash_chunk_ok", role="receiver", session=sess.id, index=idx, path=path_id, sha=sess.m["chunk_sha256"][idx][:12])
        ev.message("receiver", sess.id, CHUNK, idx, len(data), path_id, "in")
        ev.message("receiver", sess.id, ACK, idx, 0, path_id, "out")
        with sess.lock:
            if idx in sess.held:  # duplicate (retransmit after lost ACK): re-ACK, don't rewrite
                sess.duplicates += 1
            else:
                os.pwrite(sess.fd, data, idx * sess.cs)
                sess.held.add(idx)
                sess.path_bytes[path_id] = sess.path_bytes.get(path_id, 0) + len(data)
                if len(sess.held) == sess.total:
                    sess.finalize()
        return ACK


def start_receiver(listen, out_dir):
    return ReceiverHandle(listen, out_dir)
