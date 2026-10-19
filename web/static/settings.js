// Settings / Diagnostics: this Mac's addresses, reachability self-test, limits, folders.
MP.views.settings = function (root) {
  const body = MP.h("div", { class: "stack" }), err = MP.h("p", { class: "err", role: "alert" });
  const run = () => MP.api("/api/diagnostics").then((d) => {
    body.replaceChildren(
      MP.panel("Addresses of this Mac",
      MP.table(["Address", "Kind", "Own peer port reachable", "Detail"], d.self_test.map((r, i) => [r.host, d.hosts[i].kind, r.ok ? "yes (" + r.ms + " ms)" : "no", r.ok ? "" : r.reason]), []),
      d.hosts.some((h) => h.kind === "tailscale") ? null : MP.h("p", { class: "note" }, "No Tailscale address found. Across different WiFi networks both Macs need Tailscale (it also encrypts the traffic); on one network the LAN address works.")),
      MP.panel("Ports and limits", MP.table(["Setting", "Value"], [["Peer API port (0.0.0.0)", d.peer_port], ["Data ports", d.data_port ? d.data_port + " to " + (d.data_port + 99) : "any free port"], ["Max file size", MP.bytes(d.max_size)],
        ["Download folder", d.out_dir], ["State folder (history, sessions/*.jsonl)", d.state_dir], ["Rendezvous", d.rendezvous || "not set"]], [], "kv")),
      MP.panel("macOS firewall", MP.h("p", {}, "The first time the app listens, macOS asks whether Python may accept incoming connections: choose Allow. If it was denied: System Settings > Network > Firewall > Options, allow the Python binary of this project's .venv. A fixed data port range (--data-port) makes manual firewall rules easy."),
      MP.h("p", { class: "note" }, "There is no built-in encryption. Chunks and events cross the network as plain TCP and HTTP. Use Tailscale (WireGuard) between the Macs.")));
  }).catch((e) => (err.textContent = e.message));
  root.append(MP.h("h1", {}, "Settings"), err, MP.h("div", { class: "row", style: "margin-bottom:16px" }, MP.h("button", { type: "button", onclick: run }, "Run self-test")), body);
  run();
};
