import hashlib
import socket

from conftest import make_file
from mpft import protocol as P
from mpft.protocol import build_manifest
from mpft.sender import run_transfer


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_20mb_loopback_transfer_matches_sha256(tmp_path, receiver):
    src = make_file(tmp_path / "big.bin", 20 * 1024 * 1024)
    r = run_transfer(src, [f"127.0.0.1:{receiver.port}"] * 4)
    assert r["success"]
    assert sha(receiver.out / "big.bin") == sha(src)
    assert not (receiver.out / "big.bin.part").exists()
    assert sum(r["bytes_per_path"].values()) == 20 * 1024 * 1024


def connect_session(receiver, src, chunk_size=1024):
    m = build_manifest(src, chunk_size)
    s = socket.create_connection(("127.0.0.1", receiver.port), timeout=2)
    P.send_msg(s, P.HELLO, 9)
    P.send_json(s, P.MANIFEST, 9, m)
    assert P.recv_msg(s)[0] == P.MANIFEST_ACK
    return s, m


def chunk(src, i, size=1024):
    with open(src, "rb") as f:
        f.seek(i * size)
        return f.read(size)


def test_corrupted_chunk_gets_nack(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 4096)
    s, _ = connect_session(receiver, src)
    bad = bytearray(chunk(src, 1))
    bad[0] ^= 1
    P.send_msg(s, P.CHUNK, 9, 1, bytes(bad))
    assert P.recv_msg(s)[0] == P.NACK
    P.send_msg(s, P.CHUNK, 9, 1, chunk(src, 1))
    assert P.recv_msg(s)[0] == P.ACK


def test_duplicate_and_out_of_order_chunks(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 4096)
    s, _ = connect_session(receiver, src)
    for i in (3, 0, 3, 2, 1, 0):  # out of order, with duplicates
        P.send_msg(s, P.CHUNK, 9, i, chunk(src, i))
        assert P.recv_msg(s)[0] == P.ACK
    P.send_msg(s, P.DONE, 9)
    assert P.recv_msg(s)[0] == P.DONE
    assert sha(receiver.out / "f.bin") == sha(src)
