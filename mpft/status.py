"""Periodic status/<session_id>.json writer shared by sender and receiver (read by the dashboard)."""
import json
import os
import threading
import time


def status_dir():
    return os.environ.get("MPFT_STATUS_DIR", "status")


class StatusWriter:
    def __init__(self, role, session_id, snapshot, interval=1.0):
        """snapshot() returns the role-specific fields; per_path throughput is derived here."""
        self.role, self.session_id, self.snapshot, self.interval = role, session_id, snapshot, interval
        self.dir = status_dir()
        self.started_at = time.time()
        self._last = {}  # path_id -> (bytes, time) from the previous write
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        os.makedirs(self.dir, exist_ok=True)
        self.write()
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self.write()

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.write()

    def write(self):
        now = time.time()
        data = self.snapshot()
        for p in data.get("per_path", []):
            prev_bytes, prev_t = self._last.get(p["path_id"], (0, self.started_at))
            dt = max(now - prev_t, 1e-6)
            p["throughput_mbit"] = round((p["bytes"] - prev_bytes) * 8 / 1e6 / dt, 3)
            self._last[p["path_id"]] = (p["bytes"], now)
        data.update(role=self.role, session_id=self.session_id,
                    started_at=self.started_at, updated_at=now)
        path = os.path.join(self.dir, f"{self.role}-{self.session_id}.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # atomic so the dashboard never reads a half-written file
