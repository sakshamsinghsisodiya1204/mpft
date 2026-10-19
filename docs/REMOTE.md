# Running between two Macs on different networks (Tailscale)

Status: written from documentation, **not yet tested by the author**. Do a real two-Mac run before the demo.

Tailscale gives each Mac a private `100.x.y.z` address that works across different WiFi networks, with
encryption (WireGuard) and NAT traversal built in. MPFT itself is unencrypted, so Tailscale also protects the data.

## 1. Install (both Macs)
```bash
brew install --cask tailscale     # or install from the Mac App Store
```
Open the app and sign in. **Both Macs must be in the same tailnet** (same account, or share one device with the
other's account from the Tailscale admin page). Then:
```bash
tailscale ip -4        # prints this Mac's 100.x.y.z; if the command is missing use
                       # /Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4
tailscale status       # the other Mac should be listed
tailscale ping 100.x.y.z    # shows whether the path is direct or via a relay (DERP)
```

## 2. Receiver Mac
```bash
python -m mpft receive --listen 0.0.0.0:9000 --out downloads
```
macOS shows "Do you want the application Python to accept incoming network connections?" Click **Allow**.
If you missed it: System Settings > Network > Firewall > Options, allow Python.

## 3. Sender Mac
```bash
python -m mpft send bigfile.bin --to 100.x.y.z:9000 --paths 4
```
`--paths 4` opens 4 TCP connections to the same address. For genuinely different routes, use two
interfaces and `--bind`: for example connect the sender to WiFi and a phone hotspot, then
`--to 100.x.y.z:9000,100.x.y.z:9000 --bind <wifi-ip>` is one path; run with the other bind for the second
(see limitations below: `--bind` applies to all paths of one command).

## 4. Fallback: phone hotspot
If Tailscale is blocked, put both Macs on one phone's Personal Hotspot and use LAN addresses:
```bash
ipconfig getifaddr en0                  # receiver's LAN IP
python -m mpft receive --listen 0.0.0.0:9000 --out downloads
python -m mpft send bigfile.bin --to <receiver-lan-ip>:9000 --paths 4
```

## 5. Honest notes
- **College WiFi often has client isolation**: devices on the same SSID cannot talk to each other, so plain LAN
  addresses fail even though both are "on the same WiFi". Tailscale usually works through it because it makes
  outbound connections and falls back to a relay.
- **CGNAT / carrier networks** (many phone hotspots, some home ISPs) block inbound connections. Tailscale
  still works by hole punching or relaying; a relayed link is slower and adds latency, so throughput numbers
  from it are not comparable with the loopback experiments.
- `tailscale ping` reporting "via DERP" means relayed; "direct" means peer-to-peer.
- All paths in one `send` go to the same Tailscale address, so they share one physical route. They still
  demonstrate parallel connections, but real multipath gain needs separate routes.
- Windows/other firewalls on the receiver must allow inbound TCP on the chosen port.
- Never commit received files or pcaps.
