"""Receiver ID = base32("host:peer_port") in groups of 4. Decodes locally, no server needed."""
import base64
import ipaddress
import re
import socket
import subprocess


def encode_id(host, port):
    raw = base64.b32encode(f"{host}:{port}".encode()).decode().rstrip("=")
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def decode_id(text):
    """Return (host, port); raise ValueError with a plain message if the ID is not valid."""
    s = re.sub(r"[\s-]", "", text or "").upper()
    try:
        host, port = base64.b32decode(s + "=" * (-len(s) % 8)).decode().rsplit(":", 1)
        port = int(port)
    except Exception:
        raise ValueError("Receiver ID is not valid. Copy it again from the receiver's Receive page.") from None
    if not host or not 0 < port < 65536:
        raise ValueError("Receiver ID is not valid. Copy it again from the receiver's Receive page.")
    return host, port


def _tailscale_ip():
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for ip in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out):
        if ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10"):  # Tailscale CGNAT range
            return ip
    return None


def detect_host():
    """Tailscale 100.x address if present, else LAN IP, else 127.0.0.1."""
    if ip := _tailscale_ip():
        return ip
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is sent; picks the outbound interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
