"""Network-condition profiles: start emulator proxies in front of the receiver's MPFT port."""
from mpft.emulator import start_emulator

PROFILES = ("none", "asymmetric", "lossy", "path_failure")


def path_configs(profile, host, port, n, chunk_size):
    """Per-path emulator configs (listen_port 0 = pick a free port)."""
    cfgs = []
    for i in range(n):
        c = {"listen_port": 0, "to": f"{host}:{port}", "delay_ms": 0, "jitter_ms": 0, "rate_mbit": 0}
        if profile == "asymmetric":  # paths get progressively slower and further away
            c.update(delay_ms=5 + 20 * i, jitter_ms=2 * i, rate_mbit=max(40 // (i + 1), 2))
        elif profile == "lossy":
            c.update(delay_ms=10, jitter_ms=5, rate_mbit=20)
            c["corrupt_rate"] = 0.02
        elif profile == "path_failure":
            c.update(delay_ms=10, jitter_ms=3, rate_mbit=20)
            if i == n - 1 and n > 1:
                c["drop_after_s"] = 3  # last path dies 3 s after its first connection
        cfgs.append(c)
    return cfgs


def start_profile(profile, host, port, n, chunk_size):
    """Return (targets, emulator handle or None)."""
    if profile in (None, "", "none"):
        return [f"{host}:{port}"] * n, None
    if profile not in PROFILES:
        raise ValueError(f"Unknown network profile '{profile}'.")
    emu = start_emulator(path_configs(profile, host, port, n, chunk_size))
    for p in emu.paths:  # report the port the OS picked
        p.cfg["listen_port"] = p.srv.getsockname()[1]
    return [f"127.0.0.1:{p.cfg['listen_port']}" for p in emu.paths], emu
