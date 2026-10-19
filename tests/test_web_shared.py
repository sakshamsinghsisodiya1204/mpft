"""Shared two-sided view: dual-address IDs, /addresses, /events relay, clock offset, jsonl persistence, data ports."""
import json
import os

import httpx
import pytest

from conftest import make_file
from test_web_flow import auto_decide, free_port, make_node, wait
from web.ids import decode_hosts, encode_id, filter_hosts
from web.sendjob import SendJob


def test_multi_host_id_and_modes():
    rid = encode_id(["100.64.1.2", "192.168.1.5"], 8001)
    assert decode_hosts(rid) == (["100.64.1.2", "192.168.1.5"], 8001)
    assert filter_hosts(["100.64.1.2", "192.168.1.5"], "tailscale") == ["100.64.1.2"]
    assert filter_hosts(["100.64.1.2", "192.168.1.5"], "lan") == ["192.168.1.5"]
    with pytest.raises(ValueError):
        decode_hosts(encode_id("not-an-ip", 8001))


def test_both_sides_hold_the_merged_log(tmp_path):
    alice, bob = make_node(tmp_path, "alice"), make_node(tmp_path, "bob", data_port=free_port())
    src = make_file(tmp_path / "s.bin", 3 * 1024 * 1024)
    auto_decide(bob)
    job = SendJob(alice, src, "id", bob.id, paths=2).start()
    assert wait(job) == "done"
    # a, b: (side, kind) pairs each node ended up with
    a = {(e["side"], e["kind"]) for e in alice.log.events(job.sid)}
    b = {(e["side"], e["kind"]) for e in bob.log.events(job.sid)}
    for both in (a, b):
        assert {("sender", "session_done"), ("receiver", "session_done"), ("receiver", "hash_file_verified"),
                ("sender", "chunk_state"), ("receiver", "hash_chunk_ok"), ("sender", "send_state")} <= both
    assert sorted(e["sseq"] for e in bob.log.events(job.sid) if e["side"] == "sender") == \
        sorted(e["sseq"] for e in alice.log.events(job.sid) if e["side"] == "sender")
    assert bob.tokens[job.sid]
    path = os.path.join(bob.state_dir, "sessions", f"{job.sid}.jsonl")
    assert len(open(path).read().splitlines()) == len(bob.log.events(job.sid))
    from web.sessionlog import SessionLog
    assert len(SessionLog(os.path.dirname(path)).events(job.sid)) == len(bob.log.events(job.sid))  # replay after restart


def test_clock_offset_is_applied(tmp_path):
    bob = make_node(tmp_path, "bob")
    bob.seen.add(7)
    bob.tokens[7] = "tok"
    ev = [{"kind": "x", "sseq": 1, "t": 1000.0}]
    url = f"http://127.0.0.1:{bob.peer_port}/events/7"
    r = httpx.post(url, headers={"X-Session-Token": "tok"}, json={"events": ev, "offset": 5.0})
    assert r.status_code == 200 and r.json()["ack"] == 1
    got = bob.log.events(7)[0]
    assert got["t"] == 1005.0 and got["t_raw"] == 1000.0 and got["side"] == "sender"  # receiver clock is 5 s ahead


def test_events_endpoint_rejects_bad_token_and_cannot_forge_receiver_side(tmp_path):
    bob = make_node(tmp_path, "bob")
    bob.tokens[9] = "good"
    url = f"http://127.0.0.1:{bob.peer_port}/events/9"
    assert httpx.post(url, json={"events": []}).status_code == 403
    assert httpx.post(url, headers={"X-Session-Token": "bad"}, json={"events": []}).status_code == 403
    forged = [{"kind": "x", "sseq": 1, "t": 1.0, "side": "receiver"}, {"kind": 5, "sseq": 2, "t": 1.0}]
    httpx.post(url, headers={"X-Session-Token": "good"}, json={"events": forged})
    assert [(e["side"], e["kind"]) for e in bob.log.events(9)] == [("sender", "x")]


def test_addresses_endpoint(tmp_path):
    bob = make_node(tmp_path, "bob")
    r = httpx.get(f"http://127.0.0.1:{bob.peer_port}/addresses").json()
    assert r["hosts"] == [{"ip": "127.0.0.1", "kind": "lan"}] and r["name"] == "bob"


def test_emulator_restore_and_delay():
    from mpft.emulator import start_emulator
    echo = free_port()
    emu = start_emulator([{"listen_port": 0, "to": f"127.0.0.1:{echo}", "drop_after_s": 0}])
    p = emu.paths[0]
    emu.set_delay(0, 40)
    assert p.cfg["delay_ms"] == 40
    emu.kill(0)
    assert p.dead
    emu.restore(0)
    assert not p.dead and emu.state()[0]["dead"] is False
    emu.stop()
