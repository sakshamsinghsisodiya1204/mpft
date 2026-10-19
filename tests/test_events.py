import json
import random
import urllib.request

from conftest import make_file
from mpft import events
from mpft.emulator import start_emulator
from mpft.emu_control import start_control
from mpft.sender import run_transfer


def collect():
    got = []
    return got, events.subscribe(got.append)


def test_events_emitted_in_order_during_loopback_transfer(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 3 * 1024 * 1024)
    got, unsub = collect()
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}"] * 2, chunk_size=1024 * 1024, session_id=4242)
    unsub()
    assert r["success"]
    ks = [(e["role"], e["kind"]) for e in got if e.get("session") == 4242 and "role" in e]
    first = lambda k: ks.index(k)
    assert first(("sender", "session_started")) < first(("sender", "path_up")) < first(("sender", "manifest_sent"))
    assert first(("sender", "manifest_sent")) < first(("receiver", "manifest_received")) < first(("receiver", "hash_chunk_ok"))
    assert first(("receiver", "hash_file_verified")) < ks.index(("sender", "session_done"))
    done = [e for e in got if e["kind"] == "chunk_state" and e["state"] == "done"]
    assert sorted(e["index"] for e in done) == [0, 1, 2]
    types = {e["type"] for e in got if e["kind"] == "message"}
    assert {"HELLO", "MANIFEST", "MANIFEST_ACK", "CHUNK", "ACK", "DONE"} <= types


def test_corruption_emits_nack_requeue_and_bad_hash(tmp_path, receiver):
    random.seed(11)  # sender corruption uses the global RNG: seeded so the run is deterministic
    src = make_file(tmp_path / "f.bin", 4 * 1024 * 1024)
    got, unsub = collect()
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}"] * 2, chunk_size=256 * 1024, corrupt_rate=0.3, session_id=7)
    unsub()
    kinds = {e["kind"] for e in got}
    assert r["success"] and {"nack", "requeue", "hash_chunk_bad"} <= kinds


def test_emulator_control_port_kills_path_and_sets_corruption():
    emu = start_emulator([{"listen_port": 0, "to": "127.0.0.1:9"}])
    emu.paths[0].cfg["listen_port"] = emu.paths[0].srv.getsockname()[1]
    srv = start_control(emu, 0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    post = lambda p: json.load(urllib.request.urlopen(urllib.request.Request(base + p, method="POST")))
    assert post("/corrupt/0.25")[0]["corrupt_rate"] == 0.25
    assert post("/kill/0")[0]["dead"] is True
    assert json.load(urllib.request.urlopen(base + "/state"))[0]["dead"]
    srv.shutdown()


def test_killed_path_emits_down_reason_backoff_restored_and_rtt(tmp_path, receiver):
    import threading
    import time
    src = make_file(tmp_path / "f.bin", 24 * 1024 * 1024)
    emu = start_emulator([{"listen_port": 0, "to": f"127.0.0.1:{receiver.port}", "rate_mbit": 40} for _ in range(2)])
    ports = [p.srv.getsockname()[1] for p in emu.paths]
    for p, port in zip(emu.paths, ports):
        p.cfg["listen_port"] = port
    got, unsub = collect()

    def chaos():
        time.sleep(0.7)
        emu.kill(1)
        time.sleep(0.5)
        emu.restore(1)
    threading.Thread(target=chaos, daemon=True).start()
    r = run_transfer(src, [f"127.0.0.1:{p}" for p in ports], chunk_size=256 * 1024, session_id=99)
    unsub()
    emu.stop()
    assert r["success"]
    kinds = {e["kind"] for e in got if e.get("session") == 99 or e["kind"].startswith("emulator")}
    assert {"path_down", "emulator_path_killed", "emulator_path_restored", "rtt_sample"} <= kinds
    down = [e for e in got if e["kind"] == "path_down" and e.get("reason")]
    assert down and down[0]["path"] == 1
    inflight = [e for e in got if e["kind"] == "chunk_state" and e["state"] == "inflight"][0]
    assert inflight["size"] > 0 and "offset" in inflight
