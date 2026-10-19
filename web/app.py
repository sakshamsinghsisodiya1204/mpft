"""Dashboard: serves status/*.json written by sender and receiver. Run: python -m mpft dashboard"""
import json
import os
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mpft.status import status_dir

HERE = os.path.dirname(os.path.abspath(__file__))
STALE_AFTER_S = 5  # no update for this long = process ended or died
app = FastAPI(title="MPFT dashboard")


@app.get("/api/status")
def status():
    sessions = []
    try:
        names = os.listdir(status_dir())
    except FileNotFoundError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(status_dir(), name)) as f:
                s = json.load(f)
        except (OSError, ValueError):
            continue  # file replaced while reading, or junk: skip this round
        s["stale"] = time.time() - s.get("updated_at", 0) > STALE_AFTER_S
        sessions.append(s)
    return sorted(sessions, key=lambda s: s.get("updated_at", 0), reverse=True)


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
