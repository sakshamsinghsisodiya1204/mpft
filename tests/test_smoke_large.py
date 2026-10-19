"""Two-device style checks: everything bound to a real (non-loopback) address, and an optional 1 GB smoke run."""
import os
import time

import pytest

from conftest import make_file
from test_web_flow import auto_decide, free_port, wait
from web.ids import _lan_ip
from web.node import Node
from web.peer import make_peer_app
from web.sendjob import SendJob
from web.serve import start_in_thread

LAN = _lan_ip()


def node_on(tmp_path, name, host):
    port = free_port()
    n = Node(name, port, str(tmp_path / name), host, state_dir=str(tmp_path / f"st-{name}"))
    n.server = start_in_thread(make_peer_app(n), "0.0.0.0", port)
    return n


@pytest.mark.skipif(not LAN or LAN.startswith("127."), reason="no LAN address on this machine")
def test_transfer_over_the_lan_address_not_loopback(tmp_path):
    alice, bob = node_on(tmp_path, "alice", LAN), node_on(tmp_path, "bob", LAN)
    src = make_file(tmp_path / "l.bin", 4 * 1024 * 1024)
    auto_decide(bob)
    job = SendJob(alice, src, "id", bob.id, paths=3).start()
    assert wait(job) == "done"
    assert job.targets and all(t.startswith(LAN + ":") for t in job.targets)  # data plane used the LAN address
    assert open(os.path.join(bob.out_dir, "l.bin"), "rb").read() == open(src, "rb").read()


@pytest.mark.skipif(not os.environ.get("MPFT_SMOKE_MB"), reason="set MPFT_SMOKE_MB=1024 for the large-file smoke test")
def test_large_file_smoke(tmp_path):
    size = int(os.environ["MPFT_SMOKE_MB"]) * 1024 * 1024
    src = str(tmp_path / "large.bin")
    with open(src, "wb") as f:  # sparse zeros with a few random blocks: no big test data on disk
        f.truncate(size)
        for off in range(0, size, size // 16):
            f.seek(off)
            f.write(os.urandom(1 << 20))
    alice, bob = node_on(tmp_path, "alice", "127.0.0.1"), node_on(tmp_path, "bob", "127.0.0.1")
    auto_decide(bob)
    t0 = time.time()
    job = SendJob(alice, src, "id", bob.id, paths=4).start()
    assert wait(job, t=900) == "done", job.message
    print(f"\n{size >> 20} MB in {time.time() - t0:.1f}s, goodput {job.result['goodput_mbit']:.0f} Mbit/s")
    assert os.path.getsize(os.path.join(bob.out_dir, "large.bin")) == size
