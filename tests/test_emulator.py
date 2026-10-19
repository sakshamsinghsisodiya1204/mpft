import hashlib

from conftest import make_file
from mpft.emulator import start_emulator
from mpft.sender import run_transfer


def cfg(port, to, **kw):
    return {"listen_port": port, "to": f"127.0.0.1:{to}", **kw}


def test_fast_path_carries_more_than_slow_path(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 6 << 20)
    emu = start_emulator([cfg(19301, receiver.port, delay_ms=1),
                          cfg(19302, receiver.port, delay_ms=20, rate_mbit=8)])
    try:
        r = run_transfer(src, ["127.0.0.1:19301", "127.0.0.1:19302"], 256 * 1024)
    finally:
        emu.stop()
    assert r["success"]
    fast, slow = r["bytes_per_path"][0], r["bytes_per_path"][1]
    assert fast > 2 * slow
    assert hashlib.sha256(open(receiver.out / "f.bin", "rb").read()).digest() == \
        hashlib.sha256(open(src, "rb").read()).digest()


def test_rate_limit_slows_transfer(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 1 << 20)
    emu = start_emulator([cfg(19303, receiver.port, rate_mbit=8)])  # 1 MiB at 8 Mbit/s >= ~1 s
    try:
        r = run_transfer(src, ["127.0.0.1:19303"], 256 * 1024)
    finally:
        emu.stop()
    assert r["success"] and r["total_time_s"] > 0.8


def test_path_drop_after_seconds_and_survivor_finishes(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 6 << 20)
    emu = start_emulator([cfg(19304, receiver.port, delay_ms=1, rate_mbit=40),
                          cfg(19305, receiver.port, rate_mbit=16, drop_after_s=0.3)])
    try:
        r = run_transfer(src, ["127.0.0.1:19304", "127.0.0.1:19305"], 256 * 1024)
    finally:
        emu.stop()
    assert r["success"] and emu.paths[1].dead
    assert r["fail_time_s"] is not None


def test_emulator_corruption_is_survived(tmp_path, receiver):
    src = make_file(tmp_path / "f.bin", 2 << 20)
    emu = start_emulator([cfg(19306, receiver.port, corrupt_rate=0.02),
                          cfg(19307, receiver.port, corrupt_rate=0.02)])
    try:
        r = run_transfer(src, ["127.0.0.1:19306", "127.0.0.1:19307"], 64 * 1024)
    finally:
        emu.stop()
    assert r["success"]
