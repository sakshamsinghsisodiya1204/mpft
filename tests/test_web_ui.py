import time

from fastapi.testclient import TestClient

from conftest import make_file
from test_web_flow import auto_decide, make_node, wait  # noqa: F401  (fixtures + helpers)
from web.ui import make_ui_app


def two_uis(tmp_path):
    alice, bob = make_node(tmp_path, "alice"), make_node(tmp_path, "bob")
    return alice, bob, TestClient(make_ui_app(alice)), TestClient(make_ui_app(bob))


def test_upload_send_accept_download_and_feed(tmp_path):
    alice, bob, ca, cb = two_uis(tmp_path)
    src = make_file(tmp_path / "x.bin", 3 * 1024 * 1024)
    up = ca.post("/api/upload?name=../x.bin", content=open(src, "rb").read()).json()
    assert up["name"] == "x.bin" and up["size"] == 3 * 1024 * 1024
    sid = ca.post("/api/send", json={"upload_id": up["upload_id"], "kind": "id", "value": bob.id, "paths": 2}).json()["session"]
    for _ in range(100):  # receiver clicks Accept
        offers = cb.get("/api/offers").json()
        if offers:
            break
        time.sleep(0.05)
    assert offers[0]["file_name"] == "x.bin"
    assert cb.post(f"/api/offers/{offers[0]['id']}/accept").status_code == 200
    assert wait(alice.jobs[sid]) == "done"
    time.sleep(0.3)
    got = cb.get("/api/received").json()
    assert got[0]["name"] == "x.bin"
    assert cb.get("/download/x.bin").content == open(src, "rb").read()
    assert "x.bin" in ca.get("/api/history.csv").text


def test_downloads_block_traversal_and_unknown_names(tmp_path):
    alice, bob, ca, cb = two_uis(tmp_path)
    (tmp_path / "secret.txt").write_text("s")
    for url in ("/download/..%2Fsecret.txt", "/download/../secret.txt", "/download/secret.txt"):
        assert cb.get(url).status_code in (404, 405)


def test_rejects_foreign_host_and_origin(tmp_path):
    alice, bob, ca, cb = two_uis(tmp_path)
    assert ca.get("/api/info", headers={"host": "evil.example"}).status_code == 403
    assert ca.post("/api/code/new", headers={"origin": "http://evil.example"}).status_code == 403
    assert ca.get("/api/info").json()["name"] == "alice"


def test_feed_replays_session_events(tmp_path):
    alice, bob, ca, cb = two_uis(tmp_path)
    feed = ca.app.state.feed
    src = make_file(tmp_path / "y.bin", 2 * 1024 * 1024)
    auto_decide(bob)
    from web.sendjob import SendJob
    job = SendJob(alice, src, "id", bob.id, paths=2).start()
    assert wait(job) == "done"
    import json
    kinds = {json.loads(d)["kind"] for _, d in feed.buf}
    assert {"send_state", "session_started", "chunk_state", "session_done", "message"} <= kinds
    frame = next(feed.stream(0))
    assert frame.startswith("id: 1\ndata: ")
