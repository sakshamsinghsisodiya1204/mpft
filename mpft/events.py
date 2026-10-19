"""Thread-safe event bus. Sender, receiver and emulator emit; the web layer subscribes.

With no subscribers emit() returns immediately, so the plain CLI pays nothing.
"""
import threading
import time

from .protocol import TYPE_NAMES

_subs, _lock = [], threading.Lock()
_counts = {}
BULK = ("CHUNK", "ACK")  # one per chunk: sampled so the UI trace does not flood
SAMPLE_FIRST, SAMPLE_EVERY = 5, 16


def subscribe(fn):
    """Call fn(event_dict) for every event, in the emitting thread. Returns an unsubscribe function."""
    with _lock:
        _subs.append(fn)

    def unsubscribe():
        with _lock:
            if fn in _subs:
                _subs.remove(fn)
    return unsubscribe


def emit(kind, **data):
    if not _subs:
        return
    ev = {"t": time.time(), "kind": kind, **data}
    for fn in list(_subs):
        try:
            fn(ev)
        except Exception:  # a broken subscriber must never break a transfer
            pass


def message(role, session, mtype, index, length, path, direction):
    """Protocol message trace. Control messages always; CHUNK/ACK only the first few, then every Nth."""
    if not _subs:
        return
    name = TYPE_NAMES[mtype]
    if name in BULK:
        with _lock:
            n = _counts[(session, role, name)] = _counts.get((session, role, name), 0) + 1
        if n > SAMPLE_FIRST and n % SAMPLE_EVERY:
            return
    emit("message", role=role, session=session, type=name, index=index, length=length,
         path=path, direction=direction)
