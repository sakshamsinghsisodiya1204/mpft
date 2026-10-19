// Panels of the live Transfer view. Each factory returns {el, update(state, meta)}.
MP.panels = {};
const H = MP.h;
const hex8 = (n) => n.toString(16).padStart(8, "0");
const panel = (title, ...kids) => H("section", { class: "panel" }, H("h2", {}, title), ...kids);
const lastRate = (s, id) => { const a = s.series[id]; return a && a.length ? a[a.length - 1][1] : 0; };
const elapsed = (s) => (s.t0 ? (s.tEnd || Date.now() / 1000) - s.t0 : 0);
MP.panel = panel;
MP.pathLabel = (id) => H("span", { class: "mono", style: "color:" + MP.PATH_COLORS[id % 8] }, "path " + id);

MP.panels.header = () => {
  const f = {}; const rows = ["File", "Size", "SHA-256", "Session", "Direction", "Addresses", "State", "Viewing as"];
  const tbl = H("table", { class: "kv" }, H("tbody", {}, rows.map((r) => H("tr", {}, H("th", {}, r), f[r] = H("td", { class: /SHA|Session|Addresses|Size/.test(r) ? "hash mono" : "" })))));
  return { el: panel("Session", H("div", { class: "table-wrap" }, tbl)), update(s, m) {
    f.File.textContent = s.name || "-"; f.Size.textContent = s.size != null ? MP.bytes(s.size) + " (" + s.size + " B)" : "-";
    f["SHA-256"].textContent = s.sha || "-"; f.Session.textContent = s.sid + " (0x" + hex8(s.sid) + ")";
    const me = m.me || "me", peer = m.peer_name || m.sender || "peer";
    f.Direction.textContent = m.role === "receiver" ? peer + " -> " + me : me + " -> " + peer;
    f.Addresses.textContent = m.role === "receiver" ? "sender " + (m.peer || "?") + " -> this Mac" : "this Mac -> " + (m.peer || "?");
    f.State.textContent = s.phase + (s.message && !s.ended ? " (" + s.message + ")" : "") + (s.ended && s.message ? ": " + s.message : "");
    f.State.className = s.phase === "failed" ? "err" : "";
    f["Viewing as"].textContent = m.replay ? "replay of the merged sender+receiver log" : (m.role || s.role || "?") + " on " + me + "; both sides' events are merged";
  } };
};

// Header strip: what is being transferred, its state and speed, and (receiver side) the Download button for the finished file.
const STATE_KIND = { done: "ok", failed: "bad", transferring: "info", receiving: "info" };
MP.panels.strip = () => {
  const cell = (label, cls) => { const b = H("b", { class: cls === "m" ? "m" : "" }, "-"); return [H("div", { class: "cell" + (cls === "grow" ? " grow" : "") }, H("small", {}, label), b), b]; };
  const [cf, vf] = cell("File", "grow"), [cs, vs] = cell("Size", "m"), [cst] = cell("State"), [ce, ve] = cell("Elapsed", "m"), [ct, vt] = cell("ETA", "m"), [cg, vg] = cell("Goodput", "m");
  const act = H("div", { class: "cell", id: "file-action" }); let shown = "";
  const strip = H("div", { class: "strip" }, cf, cs, cst, ce, ct, cg, act);
  return { el: H("section", { class: "panel strip-panel", "aria-label": "Transfer summary" }, strip), update(s, m) {
    vf.textContent = s.name || "waiting for the first event"; vs.textContent = s.size != null ? MP.bytes(s.size) : "-";
    const kind = STATE_KIND[s.phase] || (/ing$/.test(s.phase) ? "warn" : ""), label = s.phase + (s.message && !s.ended ? ": " + s.message : "");
    if (cst.dataset.k !== label + kind) { cst.dataset.k = label + kind; cst.querySelector("b").replaceChildren(MP.badge(kind, label)); MP.topState(s.phase, kind); }
    const el = elapsed(s), avg = el > 1 ? (s.bytes * 8) / 1e6 / el : 0;
    ve.textContent = MP.secs(el); vg.textContent = (s.ended ? avg : Object.keys(s.paths).reduce((a, id) => a + lastRate(s, id), 0)).toFixed(1) + " Mbit/s";
    vt.textContent = s.ended || avg <= 0 ? "-" : MP.secs(((s.size - s.bytes) * 8) / 1e6 / avg);
    const fl = m.file, key = m.role + (fl ? fl.id + fl.status : "") + s.ended; // rebuild only on change, or hover and clicks are lost
    if (shown === key) return; shown = key;
    if (m.role !== "receiver") act.replaceChildren();
    else if (fl && fl.status === "ok") act.replaceChildren(H("small", {}, "Received file"), H("a", { class: "btn primary", id: "session-download", href: "/api/files/" + fl.id + "/download", download: fl.name }, "Download"));
    else if (fl) act.replaceChildren(H("small", {}, "Not saved"), H("span", { class: "err", id: "session-failed" }, fl.error || "Transfer failed. Nothing was saved."));
    else act.replaceChildren();
  } };
};

MP.panels.progress = () => {
  const bar = H("div", { class: "bar", role: "progressbar", "aria-label": "Transfer progress" }, H("div"));
  const st = H("div", { class: "stats" }); const v = {};
  for (const k of ["Chunks", "Bytes", "Goodput now", "Goodput mean", "Elapsed", "ETA"]) st.append(H("span", {}, k + " ", v[k] = H("b")));
  return { el: panel("Progress", bar, st), update(s) {
    const pct = s.total ? (100 * s.done) / s.total : 0;
    bar.firstChild.style.width = pct + "%"; bar.setAttribute("aria-valuenow", Math.round(pct));
    const now = Object.keys(s.paths).reduce((a, id) => a + lastRate(s, id), 0), el = elapsed(s), avg = el > 1 ? (s.bytes * 8) / 1e6 / el : 0;
    v.Chunks.textContent = s.done + "/" + s.total; v.Bytes.textContent = MP.bytes(s.bytes);
    v["Goodput now"].textContent = s.ended ? "-" : now.toFixed(1) + " Mbit/s"; v["Goodput mean"].textContent = avg.toFixed(1) + " Mbit/s";
    v.Elapsed.textContent = MP.secs(el);
    v.ETA.textContent = s.ended ? "-" : avg > 0 ? MP.secs(((s.size - s.bytes) * 8) / 1e6 / avg) : "-";
  } };
};

MP.panels.paths = () => {
  const body = H("div"); return { el: panel("Paths", body), update(s) {
    const ids = Object.keys(s.paths).sort((a, b) => a - b);
    body.replaceChildren(ids.length ? MP.table(["Path", "Local -> remote", "State", "Bytes", "Chunks", "Mbit/s", "In flight", "RTT ms", "Jitter ms", "Retries", "Last event"],
      ids.map((id) => { const p = s.paths[id]; return [MP.pathLabel(+id), (p.local || "?") + " -> " + (p.remote || "?"), MP.badge(p.state === "down" ? "bad" : "ok", p.state), MP.bytes(p.bytes), p.chunks,
        lastRate(s, id).toFixed(1), s.inflight[id] || 0, p.n ? p.mean.toFixed(1) : "-", p.n > 1 ? Math.sqrt(p.m2 / (p.n - 1)).toFixed(1) : "-", p.retries, p.last]; }), [3, 4, 5, 6, 7, 8, 9]) : MP.empty("No paths yet", "Paths appear when the transfer starts."));
  } };
};

MP.panels.incidents = () => {
  const body = H("div"); let sig = "";
  return { el: panel("Incidents", body), update(s) {
    const g = JSON.stringify(s.incidents.map((i) => [i.requeued, i.chunks.size, i.restoredAt, i.recoveredAt, i.backoffs.length]));
    if (g === sig) return; sig = g;
    const t = (x) => (x ? "+" + (x - s.t0).toFixed(1) + " s" : "-");
    body.replaceChildren(s.incidents.length ? H("ol", { class: "timeline", id: "incident-list" }, s.incidents.map((i, n) => H("li", { class: i.recoveredAt ? "ok" : i.chunks.size ? "" : "warn" },
      H("time", {}, t(i.at)), H("strong", {}, i.kind === "path" ? "path " + i.path + " down" : "chunk " + i.cause.split(" ")[1] + " rejected"), " ",
      i.recoveredAt ? MP.badge("ok", "recovered after " + (i.recoveredAt - i.at).toFixed(2) + " s") : i.chunks.size ? MP.badge("bad", "open") : MP.badge("warn", "waiting"),
      H("div", { class: "muted" }, MP.explain(i) + (i.requeued ? " Requeued " + i.requeued + "." : "") + (i.backoffs.length ? " Backoff " + i.backoffs.map((b) => b.delay.toFixed(1) + " s").join(", ") + "." : ""))))) : MP.empty("No failures so far", "Path failures and rejected chunks appear here as they happen."));
  } };
};

MP.panels.verify = () => {
  const v = {}, rows = ["Chunks verified", "Chunks rejected", "Rejected indexes", "Expected SHA-256", "Computed SHA-256", "Result"];
  const tbl = H("table", { class: "kv" }, H("tbody", {}, rows.map((r) => H("tr", {}, H("th", {}, r), v[r] = H("td", { class: /SHA|ndex|verified|rejected/.test(r) ? "hash mono" : "" })))));
  return { el: panel("Verification", H("div", { class: "table-wrap" }, tbl)), update(s) {
    v["Chunks verified"].textContent = s.verify.ok + " / " + s.total; v["Chunks rejected"].textContent = s.verify.bad;
    v["Rejected indexes"].textContent = s.badIdx.length ? [...new Set(s.badIdx)].slice(0, 40).join(", ") + (new Set(s.badIdx).size > 40 ? " ..." : "") : "-";
    v["Expected SHA-256"].textContent = s.verify.expected || s.sha || "-"; v["Computed SHA-256"].textContent = s.verify.computed || (s.role === "sender" ? "computed by the receiver" : "-");
    const r = s.verify.result; v.Result.textContent = r === "mismatch" ? "Hash mismatch" : r ? "Hash verified" : s.ended ? "Not verified" : "Pending";
    v.Result.className = r === "mismatch" || (s.ended && !r) ? "err" : "";
  } };
};

MP.panels.trace = () => {
  const body = H("div"), types = H("select", { "aria-label": "Message type" }, ["all", "control only", "CHUNK", "ACK", "NACK", "HELLO", "MANIFEST", "DONE", "ERROR"].map((t) => H("option", { value: t }, t)));
  let S0 = null; types.addEventListener("change", () => S0 && api.update(S0));
  const api = { el: panel("Protocol trace (last 100; CHUNK and ACK sampled)", H("div", { class: "filters" }, H("label", {}, "Show "), types), body), update(s) {
    S0 = s;
    const f = types.value, ctrl = ["HELLO", "MANIFEST", "MANIFEST_ACK", "NACK", "ERROR", "DONE"];
    const rows = s.trace.filter((m) => f === "all" || (f === "control only" ? ctrl.includes(m.type) : m.type === f)).slice().reverse();
    body.replaceChildren(rows.length ? MP.table(["Time", "Side", "Dir", "Type", "Chunk", "Bytes", "Path"], rows.map((m) =>
      [MP.clock(m.t), m.side || m.role, m.direction === "out" ? "send" : "recv", m.type, ["CHUNK", "ACK", "NACK"].includes(m.type) ? m.index : "-", m.length, m.path ?? "-"]), [4, 5, 6], "tall") : MP.empty("No messages yet", "Chunk and ACK messages are sampled."));
  } }; return api;
};

MP.panels.logs = () => {
  const log = H("div", { class: "log", tabindex: "0", role: "log", "aria-label": "Event log" }), side = H("select", { "aria-label": "Side filter" }, ["Both", "Sender", "Receiver"].map((t) => H("option", { value: t.toLowerCase() }, t)));
  let n = 0, cur = "both", S1 = null;
  side.addEventListener("change", () => S1 && api.update(S1));
  const api = { el: panel("Event log", H("div", { class: "filters" }, H("label", {}, "Side "), side), log), update(s) {
    S1 = s;
    if (n > s.log.length || cur !== side.value) { log.replaceChildren(); n = 0; cur = side.value; }
    const stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
    for (; n < s.log.length; n++) { const l = s.log[n]; if (cur === "both" || l.side === cur) log.append(H("div", {}, MP.clock(l.t) + (l.side ? "  [" + l.side + "]  " : "  ") + l.text)); }
    if (stick) log.scrollTop = log.scrollHeight;
  } }; return api;
};

MP.panels.wireshark = () => {
  const body = H("div"); return { el: panel("Wireshark", body), update(s, m) {
    const ports = m.capture_ports || [];
    if (!ports.length) { body.replaceChildren(H("p", { class: "muted" }, "Capture ports are known once the transfer has started.")); return; }
    const cap = "tcp port " + ports.join(" or tcp port ");
    const cmd = "sudo tcpdump -i " + (m.loopback ? "lo0" : "any") + " -w mpft-" + s.sid + ".pcap '" + cap + "'";
    body.replaceChildren(H("p", {}, "Start before the transfer for a full capture:"), H("pre", {}, cmd), MP.copyButton("Copy command", () => cmd),
      H("p", {}, "Display filter: ", H("code", {}, ports.map((p) => "tcp.port == " + p).join(" || ")), "   chunks only: ", H("code", {}, "mpft.type == 4")),
      H("p", { class: "muted" }, "Load the current wireshark/mpft.lua first (Wireshark > Help > About > Folders > Personal Lua Plugins, then Analyze > Reload Lua Plugins). The dissector recognises MPFT by its header on any port."));
  } };
};

MP.panels.network = () => {
  const body = H("div"), msg = H("p", { class: "err", role: "alert" }), pct = H("input", { type: "number", id: "corrupt", min: 0, max: 100, step: 1, value: 0, style: "width:5em" });
  const call = (url, data) => MP.post(url, data).then(() => (msg.textContent = "")).catch((e) => (msg.textContent = e.message));
  let last = "";
  const el = H("section", { class: "panel", hidden: true }, H("h2", {}, "Network conditions (emulator)"), body,
    H("div", { class: "row" }, H("label", { for: "corrupt", style: "margin:0" }, "Corrupt % of chunks"), pct,
      H("button", { type: "button", id: "set-corrupt", onclick: () => call("/api/session/" + el.dataset.sid + "/net/corrupt", { percent: +pct.value }) }, "Set")), msg,
    H("p", { class: "muted" }, "Proxies sit between sender and receiver. Corruption hits bytes in flight; the receiver's chunk hash catches it and the sender retransmits."));
  return { el, update(s, m) {
    el.hidden = !(m.net && m.net.length); if (el.hidden) return; el.dataset.sid = s.sid;
    const sig = JSON.stringify([m.net, s.ended]); if (sig === last) return; last = sig; // rebuilding buttons on every redraw would eat clicks
    body.replaceChildren(MP.table(["Path", "Port", "Delay ms", "Jitter ms", "Rate Mbit/s", "State", "Live actions"], m.net.map((p) => [p.path, p.listen_port, p.delay_ms || 0, p.jitter_ms || 0, p.rate_mbit || "unlimited",
      p.dead ? "killed" : "up", H("span", { class: "row" },
        H("button", { type: "button", class: "kill", disabled: p.dead || s.ended, onclick: () => call("/api/session/" + s.sid + "/net/kill/" + p.path) }, "Kill"),
        H("button", { type: "button", class: "restore", disabled: !p.dead || s.ended, onclick: () => call("/api/session/" + s.sid + "/net/restore/" + p.path) }, "Restore"),
        H("input", { type: "number", min: 0, max: 5000, step: 10, value: p.delay_ms || 0, style: "width:5em", "aria-label": "Delay ms for path " + p.path, disabled: p.dead || s.ended,
          onchange: (ev) => call("/api/session/" + s.sid + "/net/delay/" + p.path, { delay_ms: +ev.target.value }) }))]), [0, 1, 2, 3, 4]));
  } };
};
