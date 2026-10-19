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

from .feed import Feed
from .netprofiles import PROFILES
from .node import safe_name
from .sendjob import SendJob

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FIELDS = ["time", "direction", "name", "size", "sha256", "peer", "session", "result", "seconds",
                  "goodput_mbit", "retransmits"]


class SendReq(BaseModel):
    upload_id: str
    kind: str = Field(pattern="^(id|code)$")
    value: str = Field(min_length=1, max_length=200)
    paths: int = Field(default=4, ge=1, le=8)
    chunk_size: int = Field(default=1 << 20, ge=4096, le=16 << 20)
    profile: str = "none"


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
                "rendezvous": node.rendezvous, "rv_status": node.rv_status, "host": node.host,
                "peer_port": node.peer_port, "max_size": node.max_size, "profiles": PROFILES}

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
        job = SendJob(node, up["path"], r.kind, r.value, r.paths, r.chunk_size, r.profile, up["dir"]).start()
        return {"session": job.sid}

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

    @app.get("/api/received")
    def received():
        return node.received

    @app.get("/download/{name}")
    def download(name: str):
        path = node.download_path(name)
        real = os.path.realpath(path) if path else None
        if not real or not real.startswith(node.out_dir + os.sep) or not os.path.isfile(real):
            raise HTTPException(404, "File not found.")
        return FileResponse(real, filename=name)

    @app.get("/api/history")
    def history():
        return node.history

    @app.get("/api/history.csv")
    def history_csv():
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(node.history)
        return Response(out.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="mpft-history.csv"'})

    @app.get("/api/events")
    def events(request: Request, after: int = 0):
        last = int(request.headers.get("last-event-id", after) or 0)
        return StreamingResponse(feed.stream(last), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
    return app
