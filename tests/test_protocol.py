import socket
import pytest

from mpft import protocol as P


def pair():
    a, b = socket.socketpair()
    a.settimeout(2), b.settimeout(2)
    return a, b


def test_header_is_20_bytes_and_roundtrips():
    raw = P.pack_header(P.CHUNK, 7, 42, 100)
    assert len(raw) == 20 and raw[:2] == b"MP"
    assert P.unpack_header(raw) == (P.CHUNK, 7, 42, 100)


def test_crc_failure_detected():
    raw = bytearray(P.pack_header(P.ACK, 1, 2, 0))
    raw[9] ^= 0xFF  # corrupt session id byte
    with pytest.raises(P.ProtocolError):
        P.unpack_header(bytes(raw))


def test_bad_magic_rejected():
    raw = bytearray(P.pack_header(P.ACK, 1, 2, 0))
    raw[0] = ord("X")
    with pytest.raises(P.ProtocolError):
        P.unpack_header(bytes(raw))


def test_message_over_socket_with_payload():
    a, b = pair()
    P.send_msg(a, P.CHUNK, 5, 3, b"hello")
    assert P.recv_msg(b) == (P.CHUNK, 5, 3, b"hello")


def test_stream_split_across_recv_calls():
    a, b = pair()
    frame = P.pack_header(P.CHUNK, 1, 0, 4) + b"abcd"
    for i in range(len(frame)):
        a.sendall(frame[i:i + 1])
    assert P.recv_msg(b)[3] == b"abcd"
