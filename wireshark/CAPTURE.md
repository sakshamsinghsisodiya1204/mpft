# Capturing MPFT in Wireshark (macOS)

Dissector verified in Wireshark 4.6.9 on macOS (HELLO, MANIFEST, MANIFEST_ACK, CHUNK, ACK, DONE decode correctly).

## 1. Install
```bash
brew install --cask wireshark        # includes the ChmodBPF helper so you can capture without sudo
mkdir -p ~/.config/wireshark/plugins
cp wireshark/mpft.lua ~/.config/wireshark/plugins/    # restart Wireshark
```
Or for one session: `wireshark -X lua_script:wireshark/mpft.lua`.
The dissector claims TCP ports 9000 and 9201-9220. For other ports use *Analyze > Decode As... > TCP port > MPFT*.

## 2. Capture on loopback
Everything runs on one machine, so capture on **Loopback: lo0**. Start the capture before the transfer.
```bash
python -m mpft receive --listen 127.0.0.1:9000 --out downloads
python -m mpft emulate --config topology.example.json
python -m mpft send bigfile.bin --to 127.0.0.1:9201,127.0.0.1:9202,127.0.0.1:9203
```
You see each path twice: sender-to-proxy (ports 9201-9203) and proxy-to-receiver (port 9000).
Capture filter (before starting): `tcp port 9000 or tcp portrange 9201-9203`.

Optional command-line capture, then open the file in Wireshark (pcaps are git-ignored, do not commit):
```bash
sudo tcpdump -i lo0 -w mpft.pcap 'tcp port 9000 or tcp portrange 9201-9203'
```

## 3. Display filters
| Goal | Filter |
|---|---|
| Only MPFT frames | `mpft` |
| One path | `tcp.port == 9202` |
| TCP handshakes | `tcp.flags.syn == 1` |
| Manifest | `mpft.type == 2` |
| Chunks / ACKs / NACKs | `mpft.type == 4`, `mpft.type == 5`, `mpft.type == 6` |
| One chunk | `mpft.chunk == 10` |
| One session | `mpft.session == 0x1234abcd` (hex value from the HELLO packet) |
| TCP retransmissions | `tcp.analysis.retransmission` |
| Path failure | `tcp.flags.reset == 1 or tcp.flags.fin == 1` |

## 4. Screenshot checklist (save into docs/screenshots/)
- [ ] 3-way handshake (SYN, SYN-ACK, ACK) on each path: filter `tcp.flags.syn == 1`, 3 paths visible
- [ ] *Statistics > Conversations > TCP*: one row per path, bytes A to B differ between fast and slow path
- [ ] Filter `tcp.analysis.retransmission` (may be empty on loopback: screenshot it anyway and say so)
- [ ] *Statistics > I/O Graphs*: three series, filters `tcp.dstport==9201`, `tcp.dstport==9202`, `tcp.dstport==9203`, unit Bytes; run again with a path killed to show one series stopping
- [ ] Decoded MANIFEST packet (`mpft.type == 2`), JSON field expanded
- [ ] Decoded CHUNK packet (`mpft.type == 4`), header fields expanded (type, session, chunk, len, crc)
- [ ] ACK following a CHUNK with the same `mpft.chunk`
- [ ] RST/FIN on the killed path

## 5. Notes
- Checksum offload on loopback can show "bad checksum" warnings. Ignore, or disable *Validate the TCP checksum*.
- Large frames (up to 16 KiB on lo0) are normal: loopback MTU is 16384.
