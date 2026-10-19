"""Peer API on 0.0.0.0: only GET /health and POST /offer. Everything else lives on the local UI server."""
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field


class Offer(BaseModel):
    sender: str = Field(max_length=80)
    file_name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=1 << 50)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: int = Field(ge=0, lt=1 << 32)
    paths: int = Field(ge=1, le=8)
    chunk_size: int = Field(ge=4096, le=64 * 1024 * 1024)
    code: str | None = Field(default=None, max_length=20)


def make_peer_app(node):
    app = FastAPI(title="MPFT peer", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        return {"ok": True, "name": node.name}

    @app.post("/offer")
    def offer(o: Offer, request: Request):  # sync handler: runs in a worker thread while it waits for Accept
        return node.handle_offer(o.model_dump(), request.client.host if request.client else "?")

    return app
