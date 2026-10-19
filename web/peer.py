"""Peer API on 0.0.0.0: only GET /health, GET /addresses, POST /offer and POST /events/{session_id}.
Everything else lives on the local UI server."""
import secrets

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .ids import is_tailscale
from .sessionlog import clean_events


class Offer(BaseModel):
    sender: str = Field(max_length=80)
    file_name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=1 << 50)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: int = Field(ge=0, lt=1 << 32)
    paths: int = Field(ge=1, le=8)
    chunk_size: int = Field(ge=4096, le=64 * 1024 * 1024)
    code: str | None = Field(default=None, max_length=20)


class EventBatch(BaseModel):
    events: list[dict] = Field(max_length=2000)
    have: int = Field(default=0, ge=0)  # highest receiver-side sseq the sender already holds
    offset: float = Field(default=0.0, ge=-1e7, le=1e7)  # receiver clock minus sender clock, measured on the offer


def make_peer_app(node):
    app = FastAPI(title="MPFT peer", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        return {"ok": True, "name": node.name}

    @app.get("/addresses")
    def addresses():
        return {"name": node.name, "peer_port": node.peer_port,
                "hosts": [{"ip": h, "kind": "tailscale" if is_tailscale(h) else "lan"} for h in node.hosts]}

    @app.post("/events/{session_id}")
    def events(session_id: int, b: EventBatch, x_session_token: str = Header(default="")):
        token = node.tokens.get(session_id)
        if not token or not secrets.compare_digest(token, x_session_token):
            raise HTTPException(403, "Bad session token.")
        node.offsets[session_id] = b.offset
        node.ingest(session_id, "sender", clean_events(b.events, "sender"), -b.offset)  # sender clock -> receiver clock
        return {"ack": node.log.seq(session_id, "sender"),
                "events": node.log.since(session_id, "receiver", b.have)}

    @app.post("/offer")
    def offer(o: Offer, request: Request):  # sync handler: runs in a worker thread while it waits for Accept
        return node.handle_offer(o.model_dump(), request.client.host if request.client else "?")

    return app
