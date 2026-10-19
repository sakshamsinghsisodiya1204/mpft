import os
import socket
import threading
import time

import httpx
import pytest

from conftest import make_file
from web.ids import decode_id, encode_id
from web.node import Node, safe_name
from web.peer import make_peer_app
from web.rendezvous import make_rendezvous_app
from web.sendjob import SendJob
from web.serve import start_in_thread


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def rv():
    port = free_port()
    srv = start_in_thread(make_rendezvous_app(), "127.0.0.1", port)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True


def make_node(tmp_path, name, rv=None, **kw):
    port = free_port()
    n = Node(name, port, str(tmp_path / name), "127.0.0.1", rv, state_dir=str(tmp_path / f"st-{name}"), **kw)
    n.server = start_in_thread(make_peer_app(n), "127.0.0.1", port)
    return n


def wait(job, states=("done", "failed"), t=30):
    end = time.time() + t
    while job.state not in states and time.time() < end:
        time.sleep(0.05)
    return job.state


def auto_decide(node, accept=True):
    def loop():
        for _ in range(200):
            for oid, o in list(node.offers.items()):
                if o["state"] == "pending":
                    return node.decide(oid, accept)
            time.sleep(0.05)
    threading.Thread(target=loop, daemon=True).start()


def test_id_round_trip():
    for host, port in [("100.101.102.103", 8001), ("127.0.0.1", 65535), ("192.168.1.20", 1)]:
        rid = encode_id(host, port)
        assert decode_id(rid.lower().replace("-", " ")) == (host, port)
    with pytest.raises(ValueError):
        decode_id("not an id!")


def test_safe_name():
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("..") == "file" and safe_name("a b\x00c.txt") == "a b_c.txt"


def test_id_offer_accept_transfers_10mb(tmp_path, rv):
    alice, bob = make_node(tmp_path, "alice", rv), make_node(tmp_path, "bob", rv)
    src = make_file(tmp_path / "data.bin", 10 * 1024 * 1024)
    auto_decide(bob)
    job = SendJob(alice, src, "id", bob.id, paths=3).start()
    assert wait(job) == "done", job.message
    assert (tmp_path / "bob" / "data.bin").stat().st_size == 10 * 1024 * 1024
    assert bob.received[0]["name"] == "data.bin" and not (tmp_path / "bob" / ".incoming" / "x").exists()
    # same name again: never overwrites
    auto_decide(bob)
    assert wait(SendJob(alice, src, "id", bob.id, paths=2).start()) == "done"
    assert sorted(r["name"] for r in bob.received) == ["data (1).bin", "data.bin"]
    assert alice.history[-1]["direction"] == "send" and bob.history[-1]["direction"] == "receive"


def test_code_auto_accepts_once_and_wrong_code_rejected(tmp_path, rv):
    alice, bob = make_node(tmp_path, "alice", rv), make_node(tmp_path, "bob", rv)
    assert bob.rv_status == "registered"
    src = make_file(tmp_path / "c.bin", 2 * 1024 * 1024)
    code = bob.code
    assert wait(SendJob(alice, src, "code", code, paths=2).start()) == "done"  # no Accept click
    bad = SendJob(alice, src, "code", code)  # used: rendezvous entry was deleted
    assert wait(bad.start()) == "failed" and "not found" in bad.message.lower()
    wrong = SendJob(alice, src, "id", bob.id)
    r = httpx.post(f"http://127.0.0.1:{bob.peer_port}/offer", json={
        "sender": "x", "file_name": "a", "size": 1, "sha256": "0" * 64, "session_id": 1, "paths": 1,
        "chunk_size": 4096, "code": "AAAAAA"}).json()
    assert r["status"] == "rejected"
    assert wrong.state == "starting"


def test_expired_code_rejected_and_rate_limited(tmp_path):
    bob = make_node(tmp_path, "bob")
    bob.codes.clock = lambda: time.time() + 700  # past the 10 minute expiry
    o = {"sender": "x", "file_name": "a", "size": 1, "sha256": "0" * 64, "session_id": 1, "paths": 1,
         "chunk_size": 4096, "code": bob.code}
    assert bob.handle_offer(dict(o), "1.2.3.4")["status"] == "rejected"
    for _ in range(5):
        bob.handle_offer({**o, "code": "WRONG1"}, "1.2.3.4")
    assert "Too many" in bob.handle_offer(dict(o), "1.2.3.4")["reason"]


def test_decline_and_size_limit(tmp_path, rv):
    alice = make_node(tmp_path, "alice", rv)
    bob = make_node(tmp_path, "bob", rv, max_size=1000)
    src = make_file(tmp_path / "d.bin", 5000)
    big = SendJob(alice, src, "id", bob.id)
    assert wait(big.start()) == "failed" and "larger" in big.message
    bob.max_size = 10 ** 9
    auto_decide(bob, accept=False)
    job = SendJob(alice, src, "id", bob.id)
    assert wait(job.start()) == "failed" and "declined" in job.message.lower()
    assert not bob.received
