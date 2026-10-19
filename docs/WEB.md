# Web interface

A browser front end for sending and receiving files, with a live view of what the protocol is doing.
The data plane is unchanged: the sender app calls `mpft.sender.run_transfer`, the receiver app runs the
ordinary `mpft.receiver`, so Wireshark still sees plain MPFT.

## Architecture

```
 Browser tab (alice)                                         Browser tab (bob)
      |  HTTP + SSE  (127.0.0.1:8000)                             |  HTTP + SSE (127.0.0.1:8010)
 +----+------------------------+                            +-----+-----------------------+
 | alice: python -m mpft web   |   POST /offer (peer API)   | bob: python -m mpft web     |
 |  UI server  (127.0.0.1)     | -------------------------> |  peer server (0.0.0.0:8011) |
 |  peer server (0.0.0.0:8001) |                            |  UI server (127.0.0.1)      |
 |  sender  ---- MPFT over N TCP connections -------------> |  mpft receiver (free port)  |
 +-----------------------------+   (optionally via emulator) +-----------------------------+
            |                    code -> ID lookup                      |
            +------------> python -m mpft rendezvous :9100 <------------+
```

| Piece | File | Job |
|---|---|---|
| Event bus | `mpft/events.py` | Thread-safe; sender, receiver and emulator emit, the web layer subscribes |
| Node | `web/node.py` | Identity, one-time code, offers, received files, history |
| Peer API | `web/peer.py` | Only `GET /health` and `POST /offer`, bound to 0.0.0.0 |
| UI server | `web/ui.py`, `web/feed.py` | Pages, JSON API, SSE stream, downloads. Bound to 127.0.0.1 |
| Send job | `web/sendjob.py` | Resolve target, offer, then `run_transfer` |
| Rendezvous | `web/rendezvous.py` | Code to Receiver ID lookup |
| Profiles | `web/netprofiles.py` | Emulator paths for None, Asymmetric, Lossy, Path failure |

**Receiver ID.** `base32("host:peer_port")` shown in groups of four letters. It decodes locally, so no server is
needed. The host is the Tailscale 100.x address if there is one, else the LAN IP, else 127.0.0.1 (`--host` overrides).

**One-time code.** Six characters without confusable letters, valid 10 minutes, single use. The receiver registers
`code -> ID` with the rendezvous service; the sender resolves it. A valid code makes the receiver accept without a click.

## Offer flow

```
sender browser     sender app            rendezvous        receiver app          receiver browser
     | upload file     |                      |                  |                      |
     |---------------->| (temp dir, SHA-256)  |                  |                      |
     | Send (code?)    |                      |                  |                      |
     |---------------->| GET /resolve/CODE -->|                  |                      |
     |                 |<---- Receiver ID ----|                  |                      |
     |                 | POST /offer (name, size, sha256, session, paths, chunk size, code?)
     |                 |------------------------------------------>| code valid? accept  |
     |                 |                                           | else wait ---------->| Accept / Decline
     |                 |<-------- {accepted, port} / {declined} ---|<---------------------|
     |                 | MPFT: HELLO, MANIFEST, CHUNK/ACK x N, DONE (N paths, maybe via emulator)
     |                 |------------------------------------------>| verify, rename       |
     |<-- SSE events --|                                           |--- SSE events ------>|
```

Offers without a valid code wait up to 120 s for Accept or Decline. Received files are staged in
`<out>/.incoming/<id>/`, then renamed into `<out>/` with a numeric suffix if the name exists (never overwritten).

## Run on one Mac (two instances, two tabs)

```bash
source .venv/bin/activate
python -m mpft rendezvous --host 127.0.0.1 --port 9100                          # terminal 1
python -m mpft web --name alice --ui-port 8000 --peer-port 8001 --out ./alice-dl --host 127.0.0.1 --rendezvous http://127.0.0.1:9100   # terminal 2
python -m mpft web --name bob   --ui-port 8010 --peer-port 8011 --out ./bob-dl   --host 127.0.0.1 --rendezvous http://127.0.0.1:9100   # terminal 3
```

Open `http://127.0.0.1:8010/#/receive` (bob) and `http://127.0.0.1:8000/#/send` (alice). Copy bob's ID or code into
alice's Send page, choose a file and press Send. With an ID, press Accept on bob's page; with a code there is no click.

## Run on two Macs over Tailscale

1. Install Tailscale on both Macs and sign in to the same tailnet; note each 100.x address (`tailscale ip -4`).
2. On the Mac that will host lookups, start `python -m mpft rendezvous --port 9100`.
   **The rendezvous URL is that Mac's 100.x address:** `http://100.x.y.z:9100`.
3. On each Mac: `python -m mpft web --name NAME --ui-port 8000 --peer-port 8001 --out ./downloads --rendezvous http://100.x.y.z:9100`.
   The ID then contains the Tailscale address automatically. The URL can also be set in Receive > Settings.
4. Allow incoming connections if macOS asks (peer port 8001 and the transfer ports).
5. Sender enters the receiver's ID (or code) in the browser at `http://127.0.0.1:8000`.

Security: MPFT has no built-in encryption and the rendezvous service has no authentication. Tailscale (WireGuard)
encrypts traffic between the Macs; do not expose the peer port or the rendezvous port to the open internet.
The UI server only listens on 127.0.0.1 and rejects foreign Host or Origin headers, because it controls the machine.

## Network conditions

The Send page offers None, Asymmetric (paths progressively slower), Lossy (about 5 % of chunks damaged) and Path
failure (last path dies 3 s after it connects; use a file of 50 MB or more). The emulator proxies run inside the
sender app, in front of the receiver. The Transfer page then shows Kill path N and Set corruption (percent of
chunks; converted to the emulator's per-16 KiB-block probability). `python -m mpft emulate --control-port 9300`
exposes the same control over HTTP: `GET /state`, `POST /kill/N`, `POST /corrupt/RATE`.

## Wireshark for a web transfer

Ports are chosen per transfer, so the Transfer page prints the exact command and filter. Re-copy `wireshark/mpft.lua`
into the Wireshark plugin folder: it now also recognises MPFT by its header on any port.

```bash
sudo tcpdump -i lo0 -w mpft.pcap 'tcp port 59216 or tcp port 59217'   # as shown on the Transfer page
```

Display filters: `mpft.type == 4` (chunks), `mpft.type == 2` (manifest), `mpft.type == 6` (NACKs).

## Limits and honest notes

- The offer's size and SHA-256 are what the receiver shows; the data plane verifies against the manifest the sender sends.
- Corruption in the UI is emulated on the sender side of the emulator; real packet loss is not emulated (TCP hides it).
- The event feed keeps the last 100 000 events per process, so a page reload replays a transfer; very large transfers with tiny chunks lose their oldest events.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Could not reach the receiver" | Wrong ID, receiver app not running, or firewall. Open `http://RECEIVER:PEERPORT/health` from the sender Mac. |
| "No rendezvous URL is set" | Add it in Receive > Settings, or start with `--rendezvous`; or send by ID. |
| "Code not found or expired" | Codes live 10 minutes and work once. Press New code on the receiver. |
| "Too many wrong codes" | Five failures per minute per client are allowed; wait a minute. |
| Port already in use | A previous instance is still running: `lsof -i :8001`. |
| ID shows 127.0.0.1 across Macs | No Tailscale or LAN address found; start with `--host 100.x.y.z`. |
| Packets look like plain TCP in Wireshark | Old copy of `mpft.lua`; reload the new one. |

## Shared two-sided dashboard

- **Receiver ID** carries every address of the receiver ("h1,h2:port", base32): Tailscale 100.x and LAN when both exist. The sender probes each with `GET /health`, spreads the paths round-robin over those that answer (real multipath over two networks), and Advanced > Receiver address can force Tailscale only or LAN only. Send > Test connection shows per address reachable/unreachable with the reason.
- **Peer API** is exactly `GET /health`, `GET /addresses`, `POST /offer`, `POST /events/{session_id}`. The accept reply carries a session token; `/events` needs it in `X-Session-Token`.
- **Event forwarding**: the sender batches its events every 0.5 s to `/events/{id}`; the reply carries the receiver's new events, so both browsers show one merged log. Each event is tagged `side` and a per-side sequence `sseq`. Timestamps are shifted with an NTP-style offset measured on the offer round trip (the receiver's wait for Accept cancels out). Order: corrected time, then side, then `sseq`. `t` is epoch seconds (offset-corrected); the UI shows time since session start.
- **Events**: `session_started`, `offer_sent/received/accepted/declined`, `manifest_sent/received`, `path_up/down/restored`, `backoff`, `timeout`, `chunk_state` (pending, inflight, done, retransmitted, failed; offset, size, path, attempt), `message` (HELLO, MANIFEST, NACK, ERROR, DONE always; CHUNK/ACK sampled), `nack`, `requeue` (count, reason), `hash_chunk_ok/bad`, `hash_file_verified/mismatch`, `throughput_tick`, `rtt_sample`, `session_done`. `status/<role>-<session>.json` is unchanged.
- **Persistence**: `.mpft-state/<name>/sessions/<session>.jsonl` on each side. History > Replay re-runs a session through the same reducer (play, pause, 1x/4x/16x, scrub); History > JSON exports it.
- **Data ports**: `--data-port 9000` makes the receiver listen on the first free port in 9000..9099 (0 = any free port); use it for fixed firewall rules.
- **Resume**: received data is staged by file hash. If the receiver or network goes away the sender fails with a clear message and the `.part` file is kept; sending the same file again resumes from the chunks already held.
- **Transfer page**: session header, progress, canvas chunk map (hatched in flight, solid done, outlined retransmitted, crossed failed, path-colour tick), sortable chunk table, paths table, incidents table with a plain sentence per failure, six graphs on a shared time axis with incident markers, verification, network controls (Kill, Restore, set delay, set corruption), protocol trace, event log with side filter, Wireshark commands.

## Two-Mac runbook (Tailscale)

1. Both people install Tailscale and join the same tailnet (`tailscale ip -4` shows the 100.x address). Tailscale is what encrypts the traffic; MPFT does not.
2. Both run `python -m mpft web --name NAME --ui-port 8000 --peer-port 8001 --data-port 9000 --out ./downloads` and open `http://127.0.0.1:8000`.
3. Receiver: Receive page, press Copy ID and message it to the sender. Optionally also send the 6-character code (valid 10 minutes, once).
4. Sender: Send page, pick a file, paste the ID (and code), Test connection, Send.
5. Without a code, the receiver presses Accept. Both open the Transfer page and see the same dashboard.
6. macOS asks "accept incoming connections" the first time: Allow. If it was denied: System Settings > Network > Firewall > Options and allow the project's `.venv` Python.
7. No Tailscale, different WiFi: use a phone hotspot that both Macs join (client isolation on guest or campus WiFi blocks Mac-to-Mac traffic; hotspots usually allow it).

## Troubleshooting (addition)

| Symptom | Cause and fix |
|---|---|
| Test connection: "No answer (timeout)" | Other network, Mac asleep, firewall dropping packets, or WiFi client isolation. Use Tailscale or a hotspot. |
| "Connection refused" | Address reachable, app not listening: check the ID and that the receiver app runs on that peer port. |
| "No route to host" | Different networks without Tailscale. |
| Transfer failed, "send the same file again" | Receiver or network dropped; resend the same file and it resumes. |
| Settings > self-test says unreachable for a LAN address | macOS firewall blocks Python; allow it. |

## Honest security notes

No built-in encryption or authentication: chunks, events and offers are plain TCP and HTTP. Tailscale (WireGuard) encrypts between the Macs. Protections in the app: the UI server listens on 127.0.0.1 only and checks Host/Origin; the peer server exposes only four endpoints; `/events` needs a per-session token; codes are single-use, expire after 10 minutes and are rate-limited; names are sanitised, files never overwritten, 2 GB default limit; the receiver must press Accept unless a valid code was given.
