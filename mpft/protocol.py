"""MPFT wire format: 20-byte header + payload. See docs/PROTOCOL.md."""
import hashlib
import json
import os
import socket
import struct
import zlib

MAGIC = b"MP"
VERSION = 1
HELLO, MANIFEST, MANIFEST_ACK, CHUNK, ACK, NACK, DONE, ERROR = range(1, 9)
TYPE_NAMES = {1: "HELLO", 2: "MANIFEST", 3: "MANIFEST_ACK", 4: "CHUNK",
              5: "ACK", 6: "NACK", 7: "DONE", 8: "ERROR"}

# magic, version, type, session_id, chunk_index, payload_len; crc32 follows
_BODY = struct.Struct(">2sBBIII")
HEADER_LEN = _BODY.size + 4  # 20
MAX_PAYLOAD = 64 * 1024 * 1024  # sanity limit so a corrupt length can't make us allocate GBs


class ProtocolError(Exception):
    """Malformed frame (bad magic, version, CRC or length). The stream is unusable afterwards."""


def pack_header(mtype, session, index, payload_len):
    body = _BODY.pack(MAGIC, VERSION, mtype, session, index, payload_len)
    return body + struct.pack(">I", zlib.crc32(body))


def unpack_header(raw):
    if len(raw) != HEADER_LEN:
        raise ProtocolError("short header")
    body, (crc,) = raw[:-4], struct.unpack(">I", raw[-4:])
    if zlib.crc32(body) != crc:
        raise ProtocolError("header CRC mismatch")
    magic, version, mtype, session, index, plen = _BODY.unpack(body)
    if magic != MAGIC or version != VERSION or mtype not in TYPE_NAMES:
        raise ProtocolError("bad magic/version/type")
    if plen > MAX_PAYLOAD:
        raise ProtocolError("payload too large")
    return mtype, session, index, plen


def send_msg(sock, mtype, session, index=0, payload=b""):
    sock.sendall(pack_header(mtype, session, index, len(payload)) + payload)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            raise ConnectionError("peer closed connection")
        buf += part
    return bytes(buf)


def recv_msg(sock):
    """Return (type, session, index, payload)."""
    mtype, session, index, plen = unpack_header(recv_exact(sock, HEADER_LEN))
    return mtype, session, index, recv_exact(sock, plen) if plen else b""


def send_json(sock, mtype, session, obj, index=0):
    send_msg(sock, mtype, session, index, json.dumps(obj).encode())


def parse_addr(text):
    host, _, port = text.rpartition(":")
    return host or "0.0.0.0", int(port)


def chunk_len(size, chunk_size, index):
    return min(chunk_size, size - index * chunk_size)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def build_manifest(file_path, chunk_size):
    """One streaming pass: per-chunk hashes and whole-file hash, never the whole file in RAM."""
    size = os.path.getsize(file_path)
    whole, chunks = hashlib.sha256(), []
    with open(file_path, "rb") as f:
        while data := f.read(chunk_size):
            whole.update(data)
            chunks.append(sha256_hex(data))
    return {"name": os.path.basename(file_path), "size": size, "chunk_size": chunk_size,
            "total_chunks": len(chunks), "file_sha256": whole.hexdigest(), "chunk_sha256": chunks}


def tune(sock):
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock
