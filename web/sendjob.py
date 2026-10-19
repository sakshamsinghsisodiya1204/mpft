"""Sender side of the web layer: resolve target, make the offer, then run the real MPFT transfer."""
import hashlib
import os
import random
import shutil
import threading
import time

import httpx

from mpft import events as ev
from mpft.sender import run_transfer

from .ids import decode_id
from .netprofiles import start_profile
from .node import safe_name


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


class SendJob:
    def __init__(self, node, path, kind, value, paths=4, chunk_size=1 << 20, profile="none", cleanup_dir=None):
        self.node, self.path, self.kind, self.value = node, path, kind, value
        self.paths, self.chunk_size, self.profile, self.cleanup_dir = paths, chunk_size, profile, cleanup_dir
        self.sid = random.getrandbits(32)
        self.state, self.message, self.emulator, self.result = "starting", "", None, None
        self.peer, self.peer_name, self.targets = None, None, []
        node.jobs[self.sid] = self
        node.seen.add(self.sid)

    def set_state(self, state, message=""):
        self.state, self.message = state, message
        ev.emit("send_state", node=self.node.name, session=self.sid, state=state, message=message)

    def capture_ports(self):
        """Ports the sender connects to: the receiver's transfer port, or the emulator proxies in front of it."""
        return sorted({int(t.rsplit(":", 1)[1]) for t in self.targets})

    def is_loopback(self):
        return all(t.startswith("127.") for t in self.targets)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()
        return self

    def resolve(self):
        """Return (receiver_id, code or None)."""
        if self.kind == "id":
            return self.value, None
        if not self.node.rendezvous:
            raise RuntimeError("No rendezvous URL is set. Add one in Settings, or send by Receiver ID.")
        r = httpx.get(f"{self.node.rendezvous}/resolve/{self.value.strip().upper()}", timeout=5)
        if r.status_code != 200:
            raise RuntimeError(r.json().get("detail", f"Rendezvous returned {r.status_code}."))
        return r.json()["id"], self.value

    def run(self):
        t0, ok, err, res = time.time(), False, None, {}
        size = os.path.getsize(self.path)
        try:
            self.set_state("resolving", "Looking up receiver")
            rid, code = self.resolve()
            host, port = decode_id(rid)
            self.peer = f"{host}:{port}"
            self.peer_name = httpx.get(f"http://{host}:{port}/health", timeout=5).json().get("name")  # also checks reachability
            self.set_state("hashing", "Computing SHA-256")
            offer = {"sender": self.node.name, "file_name": safe_name(os.path.basename(self.path)), "size": size,
                     "sha256": file_sha256(self.path), "session_id": self.sid, "paths": self.paths,
                     "chunk_size": self.chunk_size, "code": code}
            self.set_state("offered", "Waiting for the receiver to accept" if not code else "Offer sent")
            r = httpx.post(f"http://{host}:{port}/offer", json=offer, timeout=150).json()
            if r.get("status") != "accepted":
                raise RuntimeError(r.get("reason") or r.get("detail") or "Receiver did not accept.")
            targets, self.emulator = start_profile(self.profile, host, r["port"], self.paths, self.chunk_size)
            self.targets = targets
            self.set_state("transferring", f"{self.paths} path(s)")
            res = run_transfer(self.path, targets, self.chunk_size, session_id=self.sid)
            ok, err = res["success"], res.get("error")
        except httpx.HTTPError as e:
            err = f"Could not reach the receiver ({type(e).__name__}). Check the ID, that the receiver app is running and the network."
        except (RuntimeError, ValueError) as e:
            err = str(e)
        finally:
            if self.emulator:
                self.emulator.stop()
            if self.cleanup_dir:
                shutil.rmtree(self.cleanup_dir, ignore_errors=True)
        self.result = res
        self.node.add_history({"direction": "send", "name": os.path.basename(self.path), "size": size,
                               "sha256": offer["sha256"] if "offer" in locals() else "", "time": time.time(),
                               "peer": self.kind + ":" + str(self.value)[:20], "session": self.sid,
                               "result": "ok" if ok else f"failed: {err}", "seconds": round(time.time() - t0, 2),
                               "goodput_mbit": round(res.get("goodput_mbit", 0), 2),
                               "retransmits": res.get("retransmitted_chunks", 0)})
        self.set_state("done" if ok else "failed", err or "")
