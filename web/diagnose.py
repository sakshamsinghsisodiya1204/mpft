"""Connection diagnostics: probe a receiver address and say why it failed in plain words."""
import time

import httpx


def explain(exc, host):
    if isinstance(exc, httpx.ConnectTimeout):
        return ("No answer (timeout). The Mac may be asleep or on another network, a firewall may be dropping packets, "
                "or the WiFi has client isolation on. Try a phone hotspot or another network.")
    if isinstance(exc, httpx.ConnectError):
        text = str(exc).lower()
        if "refused" in text:
            return f"Connection refused by {host}. The address is reachable but the MPFT app is not listening on that port: check the ID and that the receiver app is running."
        if "no route" in text or "unreachable" in text:
            return f"No route to {host}. The two machines are on different networks."
        return f"Could not connect to {host} ({exc}). Check the ID, the network and that the receiver app is running."
    if isinstance(exc, httpx.ReadTimeout):
        return "Connected, but the peer did not answer. Is it really an MPFT app?"
    return f"Failed: {type(exc).__name__}. Check the ID."


def probe(host, port, timeout=5):
    """One address: {host, ok, ms, name, hosts, reason}."""
    t0 = time.time()
    try:
        r = httpx.get(f"http://{host}:{port}/health", timeout=timeout)
        ms = round((time.time() - t0) * 1000)
        if r.status_code != 200 or "name" not in r.json():
            return {"host": host, "ok": False, "reason": "Something answered, but it is not an MPFT peer."}
        info = {}
        try:
            info = httpx.get(f"http://{host}:{port}/addresses", timeout=timeout).json()
        except (httpx.HTTPError, ValueError):
            pass
        return {"host": host, "ok": True, "ms": ms, "name": r.json()["name"], "hosts": info.get("hosts", [])}
    except (httpx.HTTPError, ValueError) as e:
        return {"host": host, "ok": False, "reason": explain(e, host)}
