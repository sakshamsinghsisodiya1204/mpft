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
    got = cb.get("/api/files").json()
    assert got[0]["name"] == "x.bin" and got[0]["status"] == "ok"
    assert cb.get(f"/api/files/{got[0]['id']}/download").content == open(src, "rb").read()
    assert "x.bin" in ca.get("/api/history.csv").text


def test_downloads_block_traversal_and_unknown_names(tmp_path):
    alice, bob, ca, cb = two_uis(tmp_path)
    (tmp_path / "secret.txt").write_text("s")
    for url in ("/api/files/..%2Fsecret.txt/download", "/api/files/../secret.txt/download", "/api/files/secret.txt/download", "/download/secret.txt"):
        assert cb.get(url).status_code in (404, 405)
    # a crafted index entry with a traversal name still cannot leave the downloads dir
    e = bob.index.add("../secret.txt", 1, "0" * 64, 1.0, "x", 1, True)
    assert cb.get(f"/api/files/{e['id']}/download").status_code == 404  # basename only: bob/secret.txt does not exist


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


def test_range_download_delete_and_verified_flag(tmp_path):
    alice, bob, ca, cb = two_uis(tmp_path)
    data = bytes(range(256)) * 400
    (tmp_path / "bob" / "r.bin").write_bytes(data)
    e = bob.index.add("r.bin", len(data), "0" * 64, 1.0, "alice", 1, True)
    r = cb.get(f"/api/files/{e['id']}/download", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206 and r.content == data[100:200]
    assert "attachment" in cb.get(f"/api/files/{e['id']}/download").headers["content-disposition"]
    assert cb.get("/api/files").json()[0]["verified"] is True
    assert cb.delete("/api/files/nope").status_code == 404
    assert cb.delete(f"/api/files/{e['id']}").status_code == 200
    assert not (tmp_path / "bob" / "r.bin").exists() and cb.get("/api/files").json() == []


def test_index_survives_restart_and_failed_has_no_download(tmp_path):
    from web.received import ReceivedIndex
    (tmp_path / "f.bin").write_bytes(b"abc")
    idx = ReceivedIndex(str(tmp_path))
    ok = idx.add("f.bin", 3, "0" * 64, 1.0, "a", 1, True)
    bad = idx.add("g.bin", 3, "0" * 64, 2.0, "a", 2, False, "no")
    again = ReceivedIndex(str(tmp_path))
    assert [x["id"] for x in again.items] == [ok["id"], bad["id"]]
    assert again.downloadable(ok["id"])[1] and again.downloadable(bad["id"])[1] is None
    (tmp_path / "f.bin").unlink()
    assert [x["id"] for x in ReceivedIndex(str(tmp_path)).items] == [bad["id"]]


def test_test_connection_reports_reachable_and_specific_failures(tmp_path):
    from web.ids import encode_id
    from test_web_flow import free_port
    alice, bob, ca, cb = two_uis(tmp_path)
    ok = ca.post("/api/test-connection", json={"kind": "id", "value": bob.id}).json()
    assert ok["ok"] and ok["results"][0]["name"] == "bob"
    dead = ca.post("/api/test-connection", json={"kind": "id", "value": encode_id("127.0.0.1", free_port())}).json()
    assert not dead["ok"] and "refused" in dead["results"][0]["reason"]
    bad = ca.post("/api/test-connection", json={"kind": "id", "value": "NOPE"}).json()
    assert not bad["ok"] and "not valid" in bad["error"]
