import os
import pytest

from mpft.receiver import start_receiver


@pytest.fixture(autouse=True)
def status_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("MPFT_STATUS_DIR", str(tmp_path / "status"))


def make_file(path, size, seed=1):
    import random
    rnd = random.Random(seed)
    with open(path, "wb") as f:
        left = size
        while left:
            n = min(left, 1 << 20)
            f.write(rnd.randbytes(n))
            left -= n
    return str(path)


@pytest.fixture
def receiver(tmp_path):
    h = start_receiver("127.0.0.1:0", str(tmp_path / "out"))
    h.out = tmp_path / "out"
    yield h
    h.stop()
