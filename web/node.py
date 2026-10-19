"""One running MPFT web instance: identity, one-time code, incoming offers, received files, history."""
import json
import os
import re
import shutil
import threading
import time

import httpx

from mpft import events as ev
from mpft.receiver import start_receiver

from .codes import CodeBook, RateLimiter, new_code, normalize
from .ids import detect_host, encode_id

OFFER_WAIT_S = 120  # how long a sender's offer waits for Accept/Decline
MAX_PENDING = 10


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(str(name))).strip(" .")[:120]
    return name or "file"


class Node:
    def __init__(self, name, peer_port, out_dir, host=None, rendezvous=None, max_size=2 * 1024 ** 3, state_dir=None):
        self.name, self.peer_port, self.max_size = name, peer_port, max_size
        self.host = host or detect_host()
        self.id = encode_id(self.host, peer_port)
        self.out_dir = os.path.abspath(out_dir)
        os.makedirs(self.out_dir, exist_ok=True)
        self.state_dir = state_dir or f".mpft-state/{safe_name(name)}"
        os.makedirs(self.state_dir, exist_ok=True)
        self.rendezvous, self.rv_status = rendezvous, "not configured"
        self.codes, self.limiter = CodeBook(), RateLimiter()
        self.code = None
        self.lock = threading.Lock()
        self.offers, self.sessions, self.jobs = {}, {}, {}  # offer_id / session id -> state
        self.received, self.seen = [], set()  # seen: every session id this node took part in
        self.history = self._load_history()
        ev.subscribe(self._on_event)
        self.new_code()

    # ---- persistence ----
    def _load_history(self):
        try:
            with open(os.path.join(self.state_dir, "history.jsonl")) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def add_history(self, entry):
        with self.lock:
            self.history.append(entry)
            with open(os.path.join(self.state_dir, "history.jsonl"), "a") as f:
                f.write(json.dumps(entry) + "\n")

    # ---- one-time code ----
    def set_rendezvous(self, url):
        self.rendezvous = (url or "").rstrip("/") or None
        self.new_code()

    def _rv(self, method, path, **kw):
        if not self.rendezvous:
            self.rv_status = "not configured: codes cannot be resolved by senders"
            return
        try:
            httpx.request(method, self.rendezvous + path, timeout=3, **kw).raise_for_status()
            self.rv_status = "registered"
        except httpx.HTTPError as e:
            self.rv_status = f"rendezvous unreachable ({type(e).__name__}). Check the URL in Settings."

    def new_code(self):
        if self.code:
            self.codes.remove(self.code)
            self._rv("DELETE", f"/code/{self.code}")
        self.code = new_code()
        self.codes.add(self.code, self.id)
        self._rv("POST", "/register", json={"code": self.code, "id": self.id})
        ev.emit("code_changed", node=self.name)

    # ---- offers (called by the peer API) ----
    def handle_offer(self, o, client):
        """Return {"status": "accepted", "port": n} or {"status": "declined", "reason": ...}."""
        if o["size"] > self.max_size:
            return {"status": "declined", "reason": f"File is larger than the receiver's limit of {self.max_size} bytes."}
        code = normalize(o.get("code"))
        trusted = False
        if code:
            if self.limiter.blocked(client):
                return {"status": "rejected", "reason": "Too many wrong codes. Wait a minute and try again."}
            if self.codes.use(code) is None:
                self.limiter.fail(client)
                return {"status": "rejected", "reason": "Code is wrong, expired or already used. Ask for a new code."}
            trusted = True
            self._rv("DELETE", f"/code/{code}")
            self.new_code()
        oid = f"{o['session_id']:08x}"
        offer = {"id": oid, "sender": o["sender"][:40], "file_name": safe_name(o["file_name"]), "size": o["size"],
                 "sha256": o["sha256"], "session_id": o["session_id"], "paths": o["paths"],
                 "chunk_size": o["chunk_size"], "client": client, "t": time.time(), "state": "pending",
                 "event": threading.Event()}
        with self.lock:
            if sum(1 for x in self.offers.values() if x["state"] == "pending") >= MAX_PENDING:
                return {"status": "rejected", "reason": "Receiver has too many pending offers. Try again later."}
            self.offers[oid] = offer
        ev.emit("offer_received", node=self.name, offer=self.public_offer(offer), auto=trusted)
        if trusted:
            return self._accept(offer)
        offer["event"].wait(OFFER_WAIT_S)
        if offer["state"] == "pending":
            self._resolve(offer, "declined")
        return offer.get("reply") or {"status": "declined", "reason": "Receiver declined or did not respond."}

    @staticmethod
    def public_offer(o):
        return {k: o[k] for k in ("id", "sender", "file_name", "size", "sha256", "session_id", "state", "t")}

    def _resolve(self, offer, state):
        offer["state"] = state
        offer["event"].set()
        ev.emit("offer_resolved", node=self.name, offer=self.public_offer(offer))

    def _accept(self, offer):
        stage = os.path.join(self.out_dir, ".incoming", offer["id"])
        handle = start_receiver("0.0.0.0:0", stage)
        with self.lock:
            self.seen.add(offer["session_id"])
            self.sessions[offer["session_id"]] = {"offer": offer, "handle": handle, "stage": stage}
        threading.Timer(3600, self._cleanup, (offer["session_id"],)).start()
        offer["reply"] = {"status": "accepted", "port": handle.port}
        self._resolve(offer, "accepted")
        return offer["reply"]

    def decide(self, oid, accept):
        offer = self.offers.get(oid)
        if offer is None or offer["state"] != "pending":
            raise KeyError("Offer is no longer pending.")
        if accept:
            self._accept(offer)
        else:
            offer["reply"] = {"status": "declined", "reason": "Receiver declined."}
            self._resolve(offer, "declined")

    # ---- finishing a received file ----
    def _on_event(self, e):
        if e.get("role") != "receiver" or e["kind"] != "session_done" or e["session"] not in self.sessions:
            return
        if e["success"]:
            self._store_file(self.sessions[e["session"]])
        threading.Thread(target=self._cleanup, args=(e["session"],), daemon=True).start()

    def _store_file(self, sess):
        offer, stage = sess["offer"], sess["stage"]
        files = [f for f in os.listdir(stage) if not f.endswith(".part")]
        if not files:
            return
        base, ext = os.path.splitext(offer["file_name"])
        with self.lock:  # unique name: never overwrite an existing download
            n, dest = 0, offer["file_name"]
            while os.path.exists(os.path.join(self.out_dir, dest)):
                n += 1
                dest = f"{base} ({n}){ext}"
            os.rename(os.path.join(stage, files[0]), os.path.join(self.out_dir, dest))
        entry = {"name": dest, "size": offer["size"], "sha256": offer["sha256"], "time": time.time(),
                 "sender": offer["sender"], "session": offer["session_id"]}
        self.received.append(entry)
        self.add_history({**entry, "direction": "receive", "peer": offer["sender"], "result": "ok"})
        ev.emit("file_received", node=self.name, file=entry)

    def _cleanup(self, sid):
        with self.lock:
            sess = self.sessions.pop(sid, None)
        if sess:
            sess["handle"].stop()
            shutil.rmtree(sess["stage"], ignore_errors=True)

    def download_path(self, name):
        """Absolute path of a received file, or None. Only names we stored are served: no traversal."""
        if any(r["name"] == name for r in self.received):
            return os.path.join(self.out_dir, name)
        return None
