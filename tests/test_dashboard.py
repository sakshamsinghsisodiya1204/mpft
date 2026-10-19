import json
import time

from fastapi.testclient import TestClient

from conftest import make_file
from mpft.sender import run_transfer
from web.app import app


def test_dashboard_lists_sender_and_receiver_sessions(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 1 << 20)
    run_transfer(src, [f"127.0.0.1:{receiver.port}"] * 2, 256 * 1024)
    client = TestClient(app)
    data = client.get("/api/status").json()
    assert {s["role"] for s in data} == {"sender", "receiver"}
    s = [x for x in data if x["role"] == "sender"][0]
    assert s["chunks_done"] == s["total_chunks"] == 4 and s["hash_status"] == "verified"
    assert len(s["file_sha256"]) == 64 and len(s["per_path"]) == 2
    assert client.get("/").status_code == 200 and client.get("/static/app.js").status_code == 200


def test_stale_and_garbage_files(tmp_path, monkeypatch):
    d = tmp_path / "st"
    d.mkdir()
    monkeypatch.setenv("MPFT_STATUS_DIR", str(d))
    (d / "bad.json").write_text("{not json")
    (d / "old.json").write_text(json.dumps({"updated_at": time.time() - 60}))
    data = TestClient(app).get("/api/status").json()
    assert len(data) == 1 and data[0]["stale"] is True
