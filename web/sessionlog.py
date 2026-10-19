"""Per-session merged event log. Each side numbers its own events (sseq); remote events are stored with
their timestamp shifted into the local clock. Every event is appended to <dir>/<session>.jsonl for replay."""
import json
import os
import threading

MAX_EVENT_BYTES = 4096
SIDE_ORDER = {"sender": 0, "receiver": 1}


class SessionLog:
    def __init__(self, directory):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.lock = threading.Lock()
        self.sessions = {}  # sid -> {"events": [...], "seq": {"sender": n, "receiver": n}}

    def _get(self, sid):
        s = self.sessions.get(sid)
        if s is None:
            s = self.sessions[sid] = {"events": [], "seq": {"sender": 0, "receiver": 0}}
            try:
                with open(self._path(sid)) as f:
                    for line in f:
                        if line.strip():
                            e = json.loads(line)
                            s["events"].append(e)
                            s["seq"][e["side"]] = max(s["seq"][e["side"]], e["sseq"])
            except (OSError, ValueError, KeyError):
                pass
        return s

    def _path(self, sid):
        return os.path.join(self.dir, f"{int(sid)}.jsonl")

    def _store(self, sid, s, e):
        s["events"].append(e)
        with open(self._path(sid), "a") as f:
            f.write(json.dumps(e, default=str) + "\n")

    def add_local(self, sid, side, e):
        with self.lock:
            s = self._get(sid)
            s["seq"][side] += 1
            e = {**e, "session": sid, "side": side, "sseq": s["seq"][side]}
            self._store(sid, s, e)
            return e

    def add_remote(self, sid, side, events, offset=0.0):
        """Keep events with sseq beyond what we hold, in order. offset = remote clock minus local clock."""
        new = []
        with self.lock:
            s = self._get(sid)
            for e in sorted(events, key=lambda x: x["sseq"]):
                if e["sseq"] <= s["seq"][side]:
                    continue
                e = {**e, "session": sid, "side": side, "t_raw": e["t"], "t": e["t"] - offset}
                s["seq"][side] = e["sseq"]
                self._store(sid, s, e)
                new.append(e)
        return new

    def seq(self, sid, side):
        with self.lock:
            return self._get(sid)["seq"][side]

    def since(self, sid, side, n, limit=500):
        with self.lock:
            return [e for e in self._get(sid)["events"] if e["side"] == side and e["sseq"] > n][:limit]

    def events(self, sid):
        """Merged order: offset-corrected time first, then side, then that side's own sequence."""
        with self.lock:
            return sorted(self._get(sid)["events"], key=lambda e: (e["t"], SIDE_ORDER[e["side"]], e["sseq"]))


def clean_events(raw, side):
    """Validate events received from the peer: bounded size, plain JSON, required fields."""
    out = []
    for e in raw[:2000]:
        if not isinstance(e, dict) or not isinstance(e.get("kind"), str) or not isinstance(e.get("sseq"), int) \
                or not isinstance(e.get("t"), (int, float)) or len(json.dumps(e, default=str)) > MAX_EVENT_BYTES:
            continue
        out.append({k: v for k, v in e.items() if k not in ("side", "mine", "t_raw")} | {"side": side})
    return out
