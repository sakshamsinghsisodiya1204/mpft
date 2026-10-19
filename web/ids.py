"""Receiver ID = base32("host:peer_port") in groups of 4. Decodes locally, no server needed."""
import base64
import ipaddress
import re
import socket
import subprocess


def encode_id(hosts, port):
    """hosts: one address or a list (Tailscale + LAN). Stored as "h1,h2:port"."""
    hosts = [hosts] if isinstance(hosts, str) else hosts
    raw = base64.b32encode(f"{','.join(hosts)}:{port}".encode()).decode().rstrip("=")
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def decode_id(text):
    """Return (first host, port); see decode_hosts."""
    hosts, port = decode_hosts(text)
    return hosts[0], port


def decode_hosts(text):
    """Return ([hosts], port); raise ValueError with a plain message if the ID is not valid."""
    s = re.sub(r"[\s-]", "", text or "").upper()
    try:
        host, port = base64.b32decode(s + "=" * (-len(s) % 8)).decode().rsplit(":", 1)
        port, hosts = int(port), host.split(",")
        for h in hosts:
            ipaddress.ip_address(h)
    except Exception:
        raise ValueError("Receiver ID is not valid. Copy it again from the receiver's Receive page.") from None
    if not 0 < port < 65536:
        raise ValueError("Receiver ID is not valid. Copy it again from the receiver's Receive page.")
    return hosts, port


def is_tailscale(ip):
    return ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")  # Tailscale CGNAT range


def _tailscale_ip():
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for ip in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out):
        if is_tailscale(ip):
            return ip
    return None


def _lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is sent; picks the outbound interface
            return s.getsockname()[0]
    except OSError:
        return None


def detect_hosts():
    """Every usable address, Tailscale first then LAN; 127.0.0.1 only when there is neither."""
    found = [ip for ip in (_tailscale_ip(), _lan_ip()) if ip and not ip.startswith("127.")]
    return list(dict.fromkeys(found)) or ["127.0.0.1"]


def detect_host():
    return detect_hosts()[0]


def filter_hosts(hosts, mode):
    """Advanced option: mode is auto, tailscale or lan."""
    if mode == "tailscale":
        return [h for h in hosts if is_tailscale(h)]
    if mode == "lan":
        return [h for h in hosts if not is_tailscale(h)]
    return list(hosts)
