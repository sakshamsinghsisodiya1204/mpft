"""Network scenarios: start emulator proxies in front of the receiver's MPFT port."""
from mpft.emulator import BLOCK, start_emulator

# name -> (label, what happens, expected outcome). Order is the order shown in the Send form.
SCENARIOS = {
    "none": ("Clean network (no emulation)", "Direct connections, nothing injected.", "success"),
    "wan": ("Clean but slow (16 Mbit/s per path)", "Rate-limited, 20 ms delay: a long, smooth transfer to read the graphs.", "success"),
    "asymmetric": ("Asymmetric paths", "Paths get slower and further away; fast paths carry more.", "success"),
    "lossy": ("Lossy (5% corrupted chunks)", "Bytes are flipped in flight; the receiver NACKs and the sender retransmits.", "success"),
    "heavy_loss": ("Heavy loss (20% corrupted chunks)", "Many retransmissions; still ends with a matching file hash.", "success"),
    "path_failure": ("Path failure mid-transfer", "The last path dies for good after 3 s; the others finish the file.", "success"),
    "path_flap": ("Path flaps and recovers", "One path dies after 2 s and returns 3 s later; watch backoff and reconnect.", "success"),
    "total_failure": ("Total failure (needs a file over 2 MB)", "Every path dies after 1 s and never returns. The transfer fails and nothing is saved.", "failure"),
}
PROFILES = tuple(SCENARIOS)


def path_configs(profile, hosts, port, n, chunk_size):
    """Per-path emulator configs (listen_port 0 = pick a free port)."""
    cfgs = []
    lossy = lambda pct: 1 - (1 - pct) ** (1 / max(1, chunk_size // BLOCK))  # per-16KiB-block rate giving pct of chunks damaged
    for i in range(n):
        c = {"listen_port": 0, "to": f"{hosts[i % len(hosts)]}:{port}", "delay_ms": 0, "jitter_ms": 0, "rate_mbit": 0}
        if profile == "wan":
            c.update(delay_ms=20, jitter_ms=4, rate_mbit=16)
        elif profile == "asymmetric":  # paths get progressively slower and further away
            c.update(delay_ms=5 + 20 * i, jitter_ms=2 * i, rate_mbit=max(40 // (i + 1), 2))
        elif profile in ("lossy", "heavy_loss"):
            c.update(delay_ms=10, jitter_ms=5, rate_mbit=20, corrupt_rate=lossy(0.05 if profile == "lossy" else 0.2))
        elif profile == "path_failure":
            c.update(delay_ms=10, jitter_ms=3, rate_mbit=20)
            if i == n - 1 and n > 1:
                c["drop_after_s"] = 3  # last path dies 3 s after its first connection
        elif profile == "path_flap":
            c.update(delay_ms=10, jitter_ms=3, rate_mbit=12)
            if i == n - 1 and n > 1:
                c.update(drop_after_s=2, restore_after_s=3)
        elif profile == "total_failure":
            c.update(delay_ms=10, rate_mbit=4, drop_after_s=1)
        cfgs.append(c)
    return cfgs


def start_profile(profile, hosts, port, n, chunk_size):
    """hosts: receiver addresses; paths alternate over them. Return (targets, emulator handle or None)."""
    if profile in (None, "", "none"):
        return [f"{hosts[i % len(hosts)]}:{port}" for i in range(n)], None
    if profile not in PROFILES:
        raise ValueError(f"Unknown network profile '{profile}'.")
    emu = start_emulator(path_configs(profile, hosts, port, n, chunk_size))
    for p in emu.paths:  # report the port the OS picked
        p.cfg["listen_port"] = p.srv.getsockname()[1]
    return [f"127.0.0.1:{p.cfg['listen_port']}" for p in emu.paths], emu
