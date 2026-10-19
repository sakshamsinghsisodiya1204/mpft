import time

from fastapi.testclient import TestClient

from conftest import make_file
from test_web_flow import auto_decide, make_node, wait
from web.sendjob import SendJob
from web.ui import make_ui_app


def test_kill_path_and_corruption_controls_during_transfer(tmp_path):
    alice, bob = make_node(tmp_path, "alice"), make_node(tmp_path, "bob")
    ca = TestClient(make_ui_app(alice))
    src = make_file(tmp_path / "n.bin", 24 * 1024 * 1024)
    auto_decide(bob)
    job = SendJob(alice, src, "id", bob.id, paths=3, chunk_size=1 << 20, profile="asymmetric").start()
    wait(job, ("transferring",))
    info = ca.get(f"/api/session/{job.sid}").json()
    assert len(info["net"]) == 3 and len(info["capture_ports"]) == 3 and info["loopback"]
    assert ca.post(f"/api/session/{job.sid}/net/corrupt", json={"percent": 150}).status_code == 400
    assert ca.post(f"/api/session/{job.sid}/net/corrupt", json={"percent": 5}).status_code == 200
    time.sleep(0.5)
    assert ca.post(f"/api/session/{job.sid}/net/kill/2").status_code == 200
    assert ca.post(f"/api/session/{job.sid}/net/kill/9").status_code == 400
    assert wait(job, t=90) == "done", job.message  # survives a dead path and corrupted chunks
    assert any(p["dead"] for p in alice.jobs[job.sid].emulator.state()) if job.emulator else True
    h = alice.history[-1]
    assert h["result"] == "ok" and h["retransmits"] >= 1


def test_no_emulator_means_404(tmp_path):
    alice = make_node(tmp_path, "alice")
    ca = TestClient(make_ui_app(alice))
    assert ca.post("/api/session/1/net/kill/0").status_code == 404
