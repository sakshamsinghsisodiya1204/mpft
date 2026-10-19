import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_transfer_reducer_with_scripted_events():
    r = subprocess.run(["node", "tests/js/reducer_test.js"], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr
