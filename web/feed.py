"""Event feed for the browser: keeps this node's events in a ring buffer so a page reload can replay them."""
import json
import threading
from collections import deque



class Feed:
    """Ring buffer of everything the Node hub emits (local and relayed events), so a page reload can replay it."""
    def __init__(self, node, size=100_000):
        self.node, self.buf, self.seq = node, deque(maxlen=size), 0
        self.cond = threading.Condition()
        node.add_listener(self.on_event)

    def on_event(self, e):
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
