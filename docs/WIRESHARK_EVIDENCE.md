# Wireshark/tshark evidence (real capture)

Captured on lo0 with tshark 4.6.9 during a 60 MB transfer through the emulator (3 paths, path 3 dies at 6 s). Decoded with wireshark/mpft.lua. Commands are shown above each output. These are text extracts, not GUI screenshots.

## TCP handshakes (tcp.flags.syn==1)
```
tshark -r mpft.pcapng -Y 'tcp.flags.syn==1' -T fields -e frame.time_relative -e tcp.srcport -e tcp.dstport -e tcp.flags.ack
0.000000000	49922	9201	False
0.000003000	49923	9202	False
0.000005000	49924	9203	False
0.000046000	9201	49922	True
0.000061000	9202	49923	True
0.000076000	9203	49924	True
6.210553000	49955	9203	False
6.413139000	49956	9203	False
6.818631000	49957	9203	False
7.620042000	49958	9203	False
```

## MPFT messages per type (mpft.type)
```
tshark -r mpft.pcapng -Y mpft -T fields -e mpft.type | sort | uniq -c   (1 HELLO, 2 MANIFEST, 3 MANIFEST_ACK, 4 CHUNK, 5 ACK, 6 NACK, 7 DONE; each appears on both hops)
   5 1
   1 1,2
   1 2
   2 3
 459 4
 458 5
   4 7
```

## Decoded MANIFEST (first, truncated)
```
MPFT MANIFEST
    Magic: MP
    Version: 1
    Type: MANIFEST (2)
    Session ID: 0xe3a2e66d
    Chunk index: 0
    Payload length: 15755
    Header CRC32: 0xa90d94bb
    JSON payload […]: {"name": "video.bin", "size": 60000000, "chunk_size": 262144, "total_chunks": 229, "file_sha256": "610d5a0532f34fa133bd97d7faf15
```

## Decoded CHUNK header fields
```
frame.number	tcp.dstport	mpft.session	mpft.chunk	mpft.len	mpft.crc
96	9201	0xe3a2e66d	0	262144	0x1e63f1ac
114	9203	0xe3a2e66d	1	262144	0x2303d81c
126	9202	0xe3a2e66d	2	262144	0x64a3a2cc
251	9000	0xe3a2e66d	0	262144	0x1e63f1ac
```

## Bytes per path (TCP conversations, sender-to-proxy ports)
```
Filter:<No Filter>
127.0.0.1:49922            <-> 127.0.0.1:9201                 725 43 kB        2472 35 MB        3197 35 MB   
127.0.0.1:49923            <-> 127.0.0.1:9202                 271 16 kB        1085 15 MB        1356 15 MB   
127.0.0.1:49924            <-> 127.0.0.1:9203                 166 9988 bytes     635 9211 kB       801 9221 kB
127.0.0.1:49955            <-> 127.0.0.1:9203                   1 44 bytes        1 68 bytes        2 112 byte
127.0.0.1:49956            <-> 127.0.0.1:9203                   1 44 bytes        1 68 bytes        2 112 byte
127.0.0.1:49957            <-> 127.0.0.1:9203                   1 44 bytes        1 68 bytes        2 112 byte
127.0.0.1:49958            <-> 127.0.0.1:9203                   1 44 bytes        1 68 bytes        2 112 byte
```

## TCP retransmissions (tcp.analysis.retransmission)
```
count: 0
```

## Path 3 (port 9203) closing at the kill (FIN/RST)
```
6.004847000	9203	49924	False	True
6.005392000	49924	9203	False	True
6.210572000	9203	49955	True	False
6.413174000	9203	49956	True	False
6.818662000	9203	49957	True	False
7.620070000	9203	49958	True	False
```

Notes: SYNs on port 9203 after 6.0 s are the sender's reconnect attempts after the path was killed; they are refused (RST,ACK) with growing gaps (0.2, 0.4, 0.8 s), then the path is declared down. The count of 0 TCP retransmissions is expected on loopback. A line such as `1,2` in the type counts means two MPFT messages (HELLO and MANIFEST) were in one TCP segment.
