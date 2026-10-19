"""Rendezvous service: receivers register code -> Receiver ID, senders resolve it.
Run: python -m mpft rendezvous --port 9100. No auth and no encryption: use it on a trusted network (Tailscale)."""
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .codes import CodeBook, RateLimiter, normalize


class Registration(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    id: str = Field(min_length=4, max_length=200)


def make_rendezvous_app(codes=None, limiter=None):
    codes, limiter = codes or CodeBook(), limiter or RateLimiter()
    app = FastAPI(title="MPFT rendezvous")

    @app.post("/register")
    def register(r: Registration):
        try:
            codes.add(normalize(r.code), r.id)
        except OverflowError:
            raise HTTPException(503, "Too many active codes. Try again later.")
        return {"ok": True, "ttl_s": codes.ttl}

    @app.get("/resolve/{code}")
    def resolve(code: str, request: Request):
        who = request.client.host if request.client else "?"
        if limiter.blocked(who):
            raise HTTPException(429, "Too many wrong codes. Wait a minute and try again.")
        rid = codes.get(normalize(code))
        if rid is None:
            limiter.fail(who)
            raise HTTPException(404, "Code not found or expired. Ask the receiver for a new code.")
        return {"id": rid}

    @app.delete("/code/{code}")
    def delete(code: str):
        codes.remove(normalize(code))
        return {"ok": True}

    return app
