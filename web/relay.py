"""Sender-side event relay: batches this side's events to the receiver's POST /events/{sid} and merges the
receiver's events from the reply, so both people watch the same dashboard."""
import threading
import time

import httpx

TICK_S = 0.5


class Relay:
    def __init__(self, node, sid, base, token, offset):
        self.node, self.sid, self.base, self.token, self.offset = node, sid, base, token, offset
        self.acked, self.stop_flag = 0, threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def flush(self):
        batch = self.node.log.since(self.sid, "sender", self.acked)
        have = self.node.log.seq(self.sid, "receiver")
        try:
            r = httpx.post(f"{self.base}/events/{self.sid}", headers={"X-Session-Token": self.token}, timeout=5,
                           json={"events": batch, "have": have, "offset": self.offset})
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError):
            return False  # keep the batch; the next tick resends it
        self.acked = max(self.acked, body.get("ack", 0))
        self.node.ingest(self.sid, "receiver", body.get("events", []), self.offset)
        return True

    def _run(self):
        while not self.stop_flag.wait(TICK_S):
            self.flush()

    def finish(self):
        """Stop the loop, then flush until nothing is left (the final events include session_done)."""
        self.stop_flag.set()
        self.thread.join(2)
        for _ in range(4):
            self.flush()
            if not self.node.log.since(self.sid, "sender", self.acked):
                break
            time.sleep(0.3)
