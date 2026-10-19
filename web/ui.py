"""UI server (127.0.0.1 only): pages, JSON API for the local browser, SSE event stream, downloads."""
import csv
import io
import os
import shutil
import tempfile
import time
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mpft.emulator import BLOCK

from .diagnose import probe
from .feed import Feed
from .ids import decode_hosts, filter_hosts, is_tailscale
from .netprofiles import PROFILES
from .node import safe_name
from .sendjob import SendJob

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FIELDS = ["time", "direction", "name", "size", "sha256", "peer", "session", "paths", "result", "seconds",
                  "goodput_mbit", "retransmits", "incidents"]


class SendReq(BaseModel):
    upload_id: str
    kind: str = Field(pattern="^(id|code)$")
    value: str = Field(min_length=1, max_length=200)
    paths: int = Field(default=4, ge=1, le=8)
    chunk_size: int = Field(default=1 << 20, ge=4096, le=16 << 20)
    profile: str = "none"
    code: str | None = Field(default=None, max_length=20)
    addr_mode: str = Field(default="auto", pattern="^(auto|tailscale|lan)$")


def make_ui_app(node, ui_port=8000):
    app = FastAPI(title=f"MPFT web ({node.name})", docs_url=None, redoc_url=None, openapi_url=None)
    feed, uploads = Feed(node), {}
    app.state.node, app.state.feed = node, feed

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        """Block DNS rebinding (Host check) and cross-site writes (Origin check): this server controls the machine."""
        host = request.headers.get("host", "").rsplit(":", 1)[0]
        origin = request.headers.get("origin")
        if host not in ("127.0.0.1", "localhost", "testserver") or (
                origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost", "testserver")):
            return JSONResponse({"detail": "Local access only."}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(os.path.join(HERE, "static", "index.html"))

    @app.get("/api/info")
    def info():
        return {"name": node.name, "id": node.id, "code": node.code, "code_expires": node.codes.expires_at(node.code),
                "hosts": node.hosts, "rendezvous": node.rendezvous, "rv_status": node.rv_status, "host": node.host,
                "peer_port": node.peer_port, "max_size": node.max_size, "profiles": PROFILES}

    @app.post("/api/test-connection")
    def test_connection(body: dict):
        """body: {kind: id|code, value, addr_mode}. Probes every address of the receiver."""
        kind, value = body.get("kind", "id"), str(body.get("value", ""))
        try:
            if kind == "code":
                if not node.rendezvous:
                    raise ValueError("A code needs a rendezvous URL (Settings). Use the Receiver ID instead.")
                import httpx
                r = httpx.get(f"{node.rendezvous}/resolve/{value.strip().upper()}", timeout=5)
                if r.status_code != 200:
                    raise ValueError(r.json().get("detail", "Code not found or expired."))
                value = r.json()["id"]
            hosts, port = decode_hosts(value)
        except ValueError as e:
            return {"ok": False, "error": str(e), "results": []}
        hosts = filter_hosts(hosts, body.get("addr_mode", "auto"))
        if not hosts:
            return {"ok": False, "error": "This ID has no address of the chosen type.", "results": []}
        results = [probe(h, port) for h in hosts]
        return {"ok": any(r["ok"] for r in results), "port": port, "results": results}

    @app.post("/api/code/new")
    def code_new():
        node.new_code()
        return info()

    @app.post("/api/settings")
    def settings(body: dict):
        node.set_rendezvous(str(body.get("rendezvous", ""))[:200])
        return info()

    @app.post("/api/upload")
    async def upload(request: Request, name: str = "file"):
        """Raw body upload, streamed to a temp file (never held in RAM)."""
        for old in [k for k, v in uploads.items() if time.time() - v["t"] > 3600]:
            shutil.rmtree(uploads.pop(old)["dir"], ignore_errors=True)
        d, size = tempfile.mkdtemp(prefix="mpft-up-"), 0
        path = os.path.join(d, safe_name(name))
        with open(path, "wb") as f:
            async for part in request.stream():
                size += len(part)
                if size > node.max_size:
                    f.close()
                    shutil.rmtree(d, ignore_errors=True)
                    raise HTTPException(413, f"File is larger than the limit of {node.max_size} bytes.")
                f.write(part)
        uid = uuid.uuid4().hex
        uploads[uid] = {"dir": d, "path": path, "t": time.time()}
        return {"upload_id": uid, "name": os.path.basename(path), "size": size}

    @app.post("/api/send")
    def send(r: SendReq):
        up = uploads.pop(r.upload_id, None)
        if up is None:
            raise HTTPException(404, "Upload not found. Choose the file again.")
        if r.profile not in PROFILES:
            raise HTTPException(400, "Unknown network profile.")
        job = SendJob(node, up["path"], r.kind, r.value, r.paths, r.chunk_size, r.profile, up["dir"], r.addr_mode, r.code).start()
        return {"session": job.sid}

    @app.get("/api/session/{sid}")
    def session(sid: int):
        """Context the live view cannot get from events: peer, capture ports, emulator paths."""
        job = node.jobs.get(sid)
        if job:
            return {"role": "sender", "me": node.name, "peer": job.peer, "peer_name": job.peer_name, "peer_hosts": job.peer_hosts, "profile": job.profile, "state": job.state,
                    "capture_ports": job.capture_ports(), "loopback": job.is_loopback(),
                    "net": job.emulator.state() if job.emulator else []}
        offer = next((o for o in node.offers.values() if o["session_id"] == sid), None)
        if offer is None:
            raise HTTPException(404, "Unknown session.")
        port = (offer.get("reply") or {}).get("port")
        return {"role": "receiver", "me": node.name, "sender": offer["sender"], "peer": offer["client"],
                "capture_ports": [port] if port else [], "loopback": offer["client"] in ("127.0.0.1", "::1"),
                "file": next((x for x in node.index.items if x["session"] == sid), None)}

    @app.get("/api/session/{sid}/events")
    def session_events(sid: int, download: int = 0):
        """Merged two-sided log from disk, for replaying a past transfer. ?download=1 saves it as JSON."""
        mine = "sender" if sid in node.jobs else "receiver"
        if sid not in node.seen and not os.path.exists(node.log._path(sid)):
            raise HTTPException(404, "Unknown session.")
        evs = [{**e, "mine": e["side"] == mine} for e in node.log.events(sid)]
        if download:
            return JSONResponse(evs, headers={"Content-Disposition": f'attachment; filename="mpft-session-{sid}.json"'})
        return evs

    def emulator_of(sid):
        job = node.jobs.get(sid)
        if not job or not job.emulator:
            raise HTTPException(404, "This transfer has no emulated network. Choose a network condition when sending.")
        return job

    @app.post("/api/session/{sid}/net/kill/{n}")
    def net_kill(sid: int, n: int):
        job = emulator_of(sid)
        if not 0 <= n < len(job.emulator.paths):
            raise HTTPException(400, "No such path.")
        job.emulator.kill(n)
        return job.emulator.state()

    @app.post("/api/session/{sid}/net/restore/{n}")
    def net_restore(sid: int, n: int):
        job = emulator_of(sid)
        if not 0 <= n < len(job.emulator.paths):
            raise HTTPException(400, "No such path.")
        job.emulator.restore(n)
        return job.emulator.state()

    @app.post("/api/session/{sid}/net/delay/{n}")
    def net_delay(sid: int, n: int, body: dict):
        job = emulator_of(sid)
        try:
            ms = float(body.get("delay_ms"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Delay must be a number of milliseconds.")
        if not 0 <= n < len(job.emulator.paths) or not 0 <= ms <= 5000:
            raise HTTPException(400, "Choose an existing path and a delay from 0 to 5000 ms.")
        job.emulator.set_delay(n, ms)
        return job.emulator.state()

    @app.post("/api/session/{sid}/net/corrupt")
    def net_corrupt(sid: int, body: dict):
        """body.percent = share of chunks to damage; the emulator works per 16 KiB block, so convert."""
        job = emulator_of(sid)
        try:
            pct = float(body.get("percent", 0))
        except (TypeError, ValueError):
            raise HTTPException(400, "Corruption must be a number from 0 to 100.")
        if not 0 <= pct <= 100:
            raise HTTPException(400, "Corruption must be a number from 0 to 100.")
        blocks = max(1, job.chunk_size // BLOCK)
        job.emulator.set_corrupt(1 - (1 - pct / 100) ** (1 / blocks))
        return {"percent": pct}

    @app.get("/api/offers")
    def offers():
        return [node.public_offer(o) for o in node.offers.values() if o["state"] == "pending"]

    @app.post("/api/offers/{oid}/{action}")
    def decide(oid: str, action: str):
        if action not in ("accept", "decline"):
            raise HTTPException(404)
        try:
            node.decide(oid, action == "accept")
        except KeyError as e:
            raise HTTPException(409, str(e.args[0]))
        return {"ok": True}

    @app.get("/api/files")
    def files():
        return node.index.items

    @app.get("/api/files/{file_id}/download")
    def download(file_id: str):
        entry, path = node.index.downloadable(file_id)
        if not path:
            raise HTTPException(404, "File not found, or it was never verified.")
        return FileResponse(path, filename=entry["name"])  # Content-Disposition: attachment; Range handled by Starlette

    @app.delete("/api/files/{file_id}")
    def delete_file(file_id: str):
        if not node.index.remove(file_id):
            raise HTTPException(404, "File not found.")
        return {"ok": True}

    def enriched():
        """History rows plus paths/incidents counted from the session log (the receiver's row is written before the sender's last events arrive)."""
        out = []
        for h in node.history:
            row = dict(h)
            sid = h.get("session")
            if sid is not None and (sid in node.seen or os.path.exists(node.log._path(sid))):
                evs = node.log.events(sid)
                row["paths"] = len({e["path"] for e in evs if e["kind"] == "path_up" and e["side"] == "sender"}) or None
                row["incidents"] = sum(1 for e in evs if e["side"] == "sender" and e["kind"] in ("path_down", "nack"))
            out.append(row)
        return out

    @app.get("/api/history")
    def history():
        return enriched()

    @app.get("/api/diagnostics")
    def diagnostics():
        """Addresses of this Mac, a reachability self-test of our own peer port, and where files go."""
        results = [probe(h, node.peer_port, timeout=3) for h in node.hosts]
        return {"name": node.name, "hosts": [{"ip": h, "kind": "tailscale" if is_tailscale(h) else "lan"} for h in node.hosts],
                "peer_port": node.peer_port, "data_port": node.data_port, "max_size": node.max_size, "out_dir": node.out_dir,
                "state_dir": os.path.abspath(node.state_dir), "self_test": results, "rendezvous": node.rendezvous}

    @app.get("/api/history.csv")
    def history_csv():
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(enriched())
        return Response(out.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="mpft-history.csv"'})

    @app.get("/api/events")
    def events(request: Request, after: int = 0):
        last = int(request.headers.get("last-event-id", after) or 0)
        return StreamingResponse(feed.stream(last), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
    return app
