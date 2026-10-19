"""One-time codes (6 chars, no confusable letters, 10 minute expiry) and a failed-attempt rate limiter."""
import secrets
import threading
import time

ALPHABET = "ABCDEFGHJKMNPQRTUVWXY346789"  # no I L O S Z 0 1 2 5
CODE_LEN, TTL_S = 6, 600


def new_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def normalize(code):
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


class CodeBook:
    def __init__(self, ttl=TTL_S, clock=time.time, cap=1000):
        self.ttl, self.clock, self.cap = ttl, clock, cap
        self.items, self.lock = {}, threading.Lock()

    def _purge(self):
        now = self.clock()
        for c in [c for c, (_, exp) in self.items.items() if exp <= now]:
            del self.items[c]

    def add(self, code, value):
        with self.lock:
            self._purge()
            if len(self.items) >= self.cap:
                raise OverflowError("too many active codes")
            self.items[code] = (value, self.clock() + self.ttl)

    def get(self, code):
        with self.lock:
            self._purge()
            hit = self.items.get(code)
            return hit[0] if hit else None

    def use(self, code):
        """Single use: return the value and delete the code, or None if unknown or expired."""
        with self.lock:
            self._purge()
            hit = self.items.pop(code, None)
            return hit[0] if hit else None

    def remove(self, code):
        with self.lock:
            self.items.pop(code, None)

    def expires_at(self, code):
        with self.lock:
            hit = self.items.get(code)
            return hit[1] if hit else None


class RateLimiter:
    """Allow `limit` failures per `window` seconds per client; further tries are refused until it passes."""

    def __init__(self, limit=5, window=60.0, clock=time.time):
        self.limit, self.window, self.clock = limit, window, clock
        self.fails, self.lock = {}, threading.Lock()

    def blocked(self, who):
        with self.lock:
            now = self.clock()
            recent = [t for t in self.fails.get(who, []) if now - t < self.window]
            self.fails[who] = recent
            return len(recent) >= self.limit

    def fail(self, who):
        with self.lock:
            self.fails.setdefault(who, []).append(self.clock())
