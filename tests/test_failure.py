import hashlib
import socket
import threading

from conftest import make_file
from mpft import protocol as P
from mpft.receiver import start_receiver
from mpft.protocol import build_manifest
from mpft.sender import run_transfer


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class FlakyProxy:
    """Forwards to the receiver; after `die_after` bytes it dies (mode kill) or goes silent (mode hole)."""
    def __init__(self, target_port, die_after=0, mode="kill"):
        self.target, self.die_after, self.mode = target_port, die_after, mode
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.port, self.conns, self.sent = self.srv.getsockname()[1], [], 0
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            up = socket.create_connection(("127.0.0.1", self.target))
            self.conns += [c, up]
            threading.Thread(target=self.pipe, args=(c, up, True), daemon=True).start()
            threading.Thread(target=self.pipe, args=(up, c, False), daemon=True).start()

    def pipe(self, a, b, counted):
        try:
            while data := a.recv(65536):
                if counted:
                    self.sent += len(data)
                    if self.die_after and self.sent > self.die_after:
                        self.kill() if self.mode == "kill" else None
                        if self.mode == "hole":
                            continue  # swallow: peer never answers
                b.sendall(data)
        except OSError:
            pass

    def kill(self):
        self.srv.close()
        for c in self.conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()


def test_path_killed_mid_transfer_chunks_requeued(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 8 << 20)
    proxy = FlakyProxy(receiver.port, die_after=1 << 20)
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}", f"127.0.0.1:{proxy.port}"], 256 * 1024)
    assert r["success"] and sha(receiver.out / "f.bin") == sha(src)
    assert r["fail_time_s"] is not None and r["retransmitted_chunks"] >= 1


def test_silent_path_times_out_and_other_path_finishes(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 4 << 20)
    proxy = FlakyProxy(receiver.port, die_after=300_000, mode="hole")
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}", f"127.0.0.1:{proxy.port}"], 256 * 1024,
                     chunk_timeout=0.4)
    assert r["success"] and sha(receiver.out / "f.bin") == sha(src)


def test_corrupted_chunks_are_retransmitted(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 4 << 20)
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}"] * 2, 64 * 1024, corrupt_rate=0.1)
    assert r["success"] and r["retransmitted_chunks"] > 0
    assert sha(receiver.out / "f.bin") == sha(src)


def test_gives_up_after_max_retries(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 256 * 1024)
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}"], 64 * 1024, corrupt_rate=1.0)
    assert not r["success"] and "retries" in r["error"]


def test_resume_after_interruption(tmp_path):
    src = make_file(tmp_path / "f.bin", 2 << 20)
    out = str(tmp_path / "out")
    cs, m = 64 * 1024, build_manifest(src, 64 * 1024)
    rx = start_receiver("127.0.0.1:0", out)
    s = socket.create_connection(("127.0.0.1", rx.port))
    P.send_msg(s, P.HELLO, 5)
    P.send_json(s, P.MANIFEST, 5, m)
    P.recv_msg(s)
    with open(src, "rb") as f:
        for i in range(0, m["total_chunks"], 2):  # send every other chunk, then "crash"
            f.seek(i * cs)
            P.send_msg(s, P.CHUNK, 5, i, f.read(cs))
            P.recv_msg(s)
    rx.stop()
    rx = start_receiver("127.0.0.1:0", out)
    try:
        r = run_transfer(src, [f"127.0.0.1:{rx.port}"] * 2, cs)
        assert r["success"] and r["resumed_chunks"] == m["total_chunks"] // 2
        assert sum(r["bytes_per_path"].values()) == (2 << 20) // 2
        assert sha(tmp_path / "out" / "f.bin") == sha(src)
    finally:
        rx.stop()


def test_resume_ignores_damaged_part_chunk(tmp_path):
    src = make_file(tmp_path / "f.bin", 1 << 20)
    out = tmp_path / "out"
    rx = start_receiver("127.0.0.1:0", str(out))
    cs = 64 * 1024
    run_transfer(src, [f"127.0.0.1:{rx.port}"], cs)
    rx.stop()
    data = bytearray(open(src, "rb").read())
    data[0] ^= 1  # part file whose first chunk is damaged
    (out / "f.bin").unlink()
    (out / "f.bin.part").write_bytes(bytes(data))
    rx = start_receiver("127.0.0.1:0", str(out))
    try:
        r = run_transfer(src, [f"127.0.0.1:{rx.port}"], cs)
        assert r["success"] and r["resumed_chunks"] == 15
        assert sha(out / "f.bin") == sha(src)
    finally:
        rx.stop()
