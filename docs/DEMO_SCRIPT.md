# Demo Script (5 minutes)

Prepare before the demo (not counted): venv active (`source .venv/bin/activate`), a test file, four terminals,
Wireshark open on **Loopback: lo0** with `mpft.lua` installed, a pre-captured screenshot set as backup.

```bash
mkdir -p /tmp/demo && head -c 60000000 /dev/urandom > /tmp/demo/video.bin   # 60 MB
cat > /tmp/demo/topo.json <<'J'
[{"listen_port":9201,"to":"127.0.0.1:9000","delay_ms":5, "rate_mbit":40},
 {"listen_port":9202,"to":"127.0.0.1:9000","delay_ms":20,"rate_mbit":20},
 {"listen_port":9203,"to":"127.0.0.1:9000","delay_ms":20,"rate_mbit":20,"drop_after_s":6}]
J
```

## 0:00 - 1:00 Problem and topology
Say: one TCP connection uses one route, stalls when it breaks, and a corrupted or half-sent file is wasted.
MPFT splits the file into chunks, sends them over several TCP paths, verifies SHA-256, and resumes.
Show `docs/TOPOLOGY.md` ASCII diagram: sender, 3 emulated paths (fast, medium, one that dies at 6 s), receiver.

## 1:00 - 4:00 Live transfer with a path killed
Terminal 1 (receiver):
```bash
python -m mpft receive --listen 127.0.0.1:9000 --out /tmp/demo/out
```
Terminal 2 (emulator, 3 paths, third dies 6 s after its first connection):
```bash
python -m mpft emulate --config /tmp/demo/topo.json
```
Terminal 3 (dashboard; open http://127.0.0.1:8080):
```bash
python -m mpft dashboard
```
Terminal 4 (sender, start Wireshark capture first):
```bash
python -m mpft -v send /tmp/demo/video.bin --to 127.0.0.1:9201,127.0.0.1:9202,127.0.0.1:9203 --chunk-size 256k
```
Point at: three bars on the dashboard, faster path carries more, at about 6 s the third path turns `down`, bars of
the others stay up, log line "path 2 failed ... requeueing", transfer still ends with `OK`.
Then prove integrity:
```bash
shasum -a 256 /tmp/demo/video.bin /tmp/demo/out/video.bin
```
Optional corruption run (shows NACK in the receiver log):
```bash
python -m mpft send /tmp/demo/video.bin --to 127.0.0.1:9201 --paths 2 --corrupt-rate 0.05
```
Note: the emulator's third path is already dead after the first run; restart the emulator (Ctrl-C, run again)
before repeating.

## 4:00 - 5:00 Wireshark, then results
Wireshark (about 30 s): filter `mpft.type == 2` (decoded MANIFEST JSON), `mpft.type == 4` (CHUNK header fields),
`tcp.flags.syn == 1` (one handshake per path), Statistics > Conversations (bytes per path).
Results (about 30 s): open `results/throughput_vs_paths.png` (goodput doubles with paths) and
`results/recovery_timeline.png` (one path stops, others carry on, recovery 0.15 s).

## Rehearsal checklist
- [ ] Time each section with a stopwatch; cut the corruption run first if over time
- [ ] Ports 9000, 9201-9203, 8080 are free (`lsof -i :9201`)
- [ ] Backup: screenshots of dashboard and Wireshark if the live demo fails
