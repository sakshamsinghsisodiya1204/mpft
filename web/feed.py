"""Event feed for the browser: keeps this node's events in a ring buffer so a page reload can replay them."""
import json
import threading
from collections import deque

from mpft import events as ev

NODE_KINDS = {"offer_received", "offer_resolved", "file_received", "code_changed", "send_state"}


class Feed:
    def __init__(self, node, size=100_000):
        self.node, self.buf, self.seq = node, deque(maxlen=size), 0
        self.cond = threading.Condition()
        ev.subscribe(self.on_event)

    def mine(self, e):
        if e["kind"] in NODE_KINDS:
            return e.get("node") == self.node.name
        if e["kind"] == "emulator_path_killed":
            return True
        sid = e.get("session")
        return sid in self.node.seen and e.get("role") in (None, "sender" if sid in self.node.jobs else "receiver")

    def on_event(self, e):
        if not self.mine(e):
            return
        with self.cond:
            self.seq += 1
            self.buf.append((self.seq, json.dumps({**e, "seq": self.seq}, default=str)))
            self.cond.notify_all()

    def stream(self, after=0):
        """Generator of SSE frames: everything after `after`, then new events as they arrive."""
        last = after
        while True:
            with self.cond:
                self.cond.wait_for(lambda: self.seq > last, 15)
                first = self.buf[0][0] if self.buf else 1
                new = list(self.buf)[max(last - first + 1, 0):] if self.seq > last else []
            if not new:
                yield ": keepalive\n\n"
                continue
            last = new[-1][0]
            yield "".join(f"id: {n}\ndata: {d}\n\n" for n, d in new)
