// Panels of the live Transfer view. Each factory returns {el, update(state, meta)}.
MP.panels = {};
const H = MP.h;
const hex8 = (n) => n.toString(16).padStart(8, "0");
const panel = (title, ...kids) => H("section", { class: "panel" }, H("h2", {}, title), ...kids);
const lastRate = (s, id) => { const a = s.series[id]; return a && a.length ? a[a.length - 1][1] : 0; };
const elapsed = (s) => (s.t0 ? (s.tEnd || Date.now() / 1000) - s.t0 : 0);

MP.panels.header = (s0) => {
  const f = {}; const rows = ["File", "Size", "SHA-256", "Session", "Direction", "State"];
  const tbl = H("table", {}, H("tbody", {}, rows.map((r) => H("tr", {}, H("th", {}, r), f[r] = H("td", { class: r === "SHA-256" ? "hash mono" : "" })))));
  return { el: panel("Session", H("div", { class: "table-wrap" }, tbl)), update(s, m) {
    f.File.textContent = s.name || "-"; f.Size.textContent = s.size != null ? MP.bytes(s.size) + " (" + s.size + " B)" : "-";
    f["SHA-256"].textContent = s.sha || "-"; f.Session.textContent = s.sid + " (0x" + hex8(s.sid) + ")";
    const peer = m.peer || "?";
    f.Direction.textContent = m.role === "receiver" ? (m.sender || "sender") + " -> " + (m.me || "me") : (m.me || "me") + " -> " + (m.peer_name ? m.peer_name + " (" + peer + ")" : peer);
    f.State.textContent = s.phase + (s.message && !s.ended ? " (" + s.message + ")" : "") + (s.ended && s.message ? ": " + s.message : "");
    f.State.className = s.phase === "failed" ? "err" : "";
  } };
};

MP.panels.progress = () => {
  const bar = H("div", { class: "bar", role: "progressbar", "aria-label": "Transfer progress" }, H("div"));
  const st = H("div", { class: "stats" }); const v = {};
  for (const k of ["Chunks", "Goodput now", "Goodput avg", "Elapsed", "ETA"]) st.append(H("span", {}, k + " ", v[k] = H("b")));
  return { el: panel("Progress", bar, st), update(s) {
    const pct = s.total ? (100 * s.done) / s.total : 0;
    bar.firstChild.style.width = pct + "%"; bar.setAttribute("aria-valuenow", Math.round(pct));
    const now = Object.keys(s.paths).reduce((a, id) => a + lastRate(s, id), 0), el = elapsed(s), avg = el > 1 ? (s.bytes * 8) / 1e6 / el : 0;
    v.Chunks.textContent = s.done + " / " + s.total + " (" + pct.toFixed(0) + "%)";
    v["Goodput now"].textContent = s.ended ? "-" : now.toFixed(1) + " Mbit/s"; v["Goodput avg"].textContent = avg.toFixed(1) + " Mbit/s";
    v.Elapsed.textContent = MP.secs(el);
    v.ETA.textContent = s.ended ? "-" : avg > 0 ? MP.secs(((s.size - s.bytes) * 8) / 1e6 / avg) : "-";
  } };
};

MP.panels.chunkmap = () => {
  const grid = H("div", { class: "chunkmap", role: "img", "aria-label": "Chunk map" }), tip = H("p", { class: "muted mono" }, "Hover a cell for details.");
  const legend = H("p", { class: "legend" }, ...[["", "pending"], ["inflight", "in flight"], ["done", "done"], ["retx", "retransmitted (outline)"]].map(([c, t]) => H("span", {}, H("i", { class: c }), t)));
  let cells = [], k = 1, built = 0, S = null;
  const state = (c) => { const s = S, lo = c * k, hi = Math.min(lo + k, s.total); let d = 0, fl = 0, rx = 0;
    for (let i = lo; i < hi; i++) { if (s.cell[i] === 2) d++; else if (s.cell[i] === 1) fl++; if (s.retxFlag[i]) rx = 1; }
    return (d === hi - lo ? "done" : d + fl ? "inflight" : "") + (rx ? " retx" : ""); };
  grid.addEventListener("mouseover", (e) => {
    const c = cells.indexOf(e.target); if (c < 0 || !S) return; const lo = c * k, hi = Math.min(lo + k, S.total) - 1;
    const names = ["pending", "in flight", "done"], i = lo;
    tip.textContent = k === 1 ? "Chunk " + i + ": " + names[S.cell[i]] + ", path " + (S.cpath[i] < 0 ? "-" : S.cpath[i]) + ", attempts " + S.attempts[i] + (S.retxFlag[i] ? ", retransmitted" : "")
      : "Chunks " + lo + " to " + hi + ": " + state(c).trim();
  });
  return { el: panel("Chunk map", legend, grid, tip), update(s) {
    S = s; if (!s.total) return;
    if (built !== s.total) { built = s.total; k = Math.ceil(s.total / 3000); cells = Array.from({ length: Math.ceil(s.total / k) }, () => H("i")); grid.replaceChildren(...cells); s.dirty = new Set(Array.from({ length: s.total }, (_, i) => i)); }
    for (const i of new Set([...s.dirty].map((i) => Math.floor(i / k)))) cells[i].className = state(i);
  } };
};

MP.panels.paths = () => {
  const body = H("div"); return { el: panel("Paths", body), update(s) {
    const ids = Object.keys(s.paths).sort((a, b) => a - b);
    body.replaceChildren(ids.length ? MP.table(["Path", "Local -> remote", "State", "Bytes", "Chunks", "Mbit/s", "RTT ms", "Jitter ms", "Retries"],
      ids.map((id) => { const p = s.paths[id]; return [id, (p.local || "?") + " -> " + (p.remote || "?"), p.state, MP.bytes(p.bytes), p.chunks, lastRate(s, id).toFixed(1),
        p.n ? p.mean.toFixed(1) : "-", p.n > 1 ? Math.sqrt(p.m2 / (p.n - 1)).toFixed(1) : "-", p.retries]; }), [0, 3, 4, 5, 6, 7, 8]) : H("p", { class: "muted" }, "No paths yet."));
  } };
};

MP.panels.chart = () => {
  const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), legend = H("p", { class: "legend muted" });
  svg.setAttribute("viewBox", "0 0 600 180"); svg.setAttribute("class", "chart"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Throughput per path over time");
  const styles = [["#3d6b5e", ""], ["#1b1b1a", ""], ["#66655f", ""], ["#3d6b5e", "6 3"], ["#1b1b1a", "6 3"], ["#66655f", "6 3"], ["#3d6b5e", "2 3"], ["#1b1b1a", "2 3"]];
  const el = (tag, a, text) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (text != null) e.textContent = text; return e; };
  return { el: panel("Throughput over time", svg, legend), update(s) {
    const ids = Object.keys(s.series).sort((a, b) => a - b), L = 44, R = 590, T = 10, B = 156;
    const tmax = Math.max(10, ...ids.map((i) => s.series[i].at(-1)[0])), ymax = Math.max(1, ...ids.flatMap((i) => s.series[i].map((p) => p[1]))) * 1.1;
    const X = (t) => L + ((R - L) * t) / tmax, Y = (v) => B - ((B - T) * v) / ymax, kids = [];
    kids.push(el("line", { x1: L, y1: B, x2: R, y2: B, stroke: "#cfcdc4" }), el("line", { x1: L, y1: T, x2: L, y2: B, stroke: "#cfcdc4" }),
      el("text", { x: L - 4, y: T + 8, "text-anchor": "end", "font-size": 10, fill: "#66655f" }, ymax.toFixed(0)), el("text", { x: L - 4, y: B, "text-anchor": "end", "font-size": 10, fill: "#66655f" }, "0"),
      el("text", { x: R, y: B + 14, "text-anchor": "end", "font-size": 10, fill: "#66655f" }, Math.round(tmax) + " s"), el("text", { x: L, y: 175, "font-size": 10, fill: "#66655f" }, "Mbit/s per path"));
    ids.forEach((id, n) => { const [c, d] = styles[n % 8]; kids.push(el("polyline", { fill: "none", stroke: c, "stroke-width": 1.5, "stroke-dasharray": d, points: s.series[id].map((p) => X(p[0]) + "," + Y(p[1])).join(" ") })); });
    svg.replaceChildren(...kids);
    legend.replaceChildren(...ids.map((id, n) => H("span", {}, H("i", { style: "background:" + styles[n % 8][0] }), "path " + id + (styles[n % 8][1] ? " (dashed)" : ""))));
  } };
};

MP.panels.verify = () => {
  const v = {}, rows = ["Chunks verified", "Chunks failed", "Expected SHA-256", "Computed SHA-256", "Result"];
  const tbl = H("table", {}, H("tbody", {}, rows.map((r) => H("tr", {}, H("th", {}, r), v[r] = H("td", { class: r.includes("SHA") ? "hash mono" : "" })))));
  return { el: panel("Verification", H("div", { class: "table-wrap" }, tbl)), update(s) {
    v["Chunks verified"].textContent = s.verify.ok + " / " + s.total; v["Chunks failed"].textContent = s.verify.bad;
    v["Expected SHA-256"].textContent = s.verify.expected || s.sha || "-"; v["Computed SHA-256"].textContent = s.verify.computed || (s.role === "sender" ? "computed by the receiver" : "-");
    const r = s.verify.result; v.Result.textContent = r === "mismatch" ? "Hash mismatch" : r ? "Hash verified" + (r === "verified" ? "" : ", " + r.replace("verified ", "")) : s.ended ? "Not verified" : "Pending";
    v.Result.className = r === "mismatch" || (s.ended && !r) ? "err" : "";
  } };
};

MP.panels.logs = () => {
  const log = H("div", { class: "log", tabindex: "0", role: "log", "aria-label": "Event log" }), trace = H("div");
  let n = 0;
  return { el: H("div", {}, panel("Event log", log), panel("Protocol messages (last 50, CHUNK and ACK sampled)", trace)), update(s) {
    if (n > s.log.length) { log.replaceChildren(); n = 0; }
    const stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
    for (; n < s.log.length; n++) log.append(H("div", {}, MP.clock(s.log[n].t) + (s.log[n].side ? "  [" + s.log[n].side + "]  " : "  ") + s.log[n].text));
    if (stick) log.scrollTop = log.scrollHeight;
    trace.replaceChildren(MP.table(["Time", "Side", "Dir", "Type", "Chunk", "Bytes", "Path"], s.trace.slice().reverse().map((m) =>
      [MP.clock(m.t), m.side || m.role, m.direction === "out" ? "send" : "recv", m.type, ["CHUNK", "ACK", "NACK"].includes(m.type) ? m.index : "-", m.length, m.path ?? "-"]), [4, 5, 6]));
  } };
};

MP.panels.wireshark = () => {
  const body = H("div"); return { el: panel("Wireshark", body), update(s, m) {
    const ports = m.capture_ports || [];
    if (!ports.length) { body.replaceChildren(H("p", { class: "muted" }, "Capture ports are known once the transfer has started.")); return; }
    const cap = "tcp port " + ports.join(" or tcp port ");
    const cmd = "sudo tcpdump -i " + (m.loopback ? "lo0" : "any") + " -w mpft-" + s.sid + ".pcap '" + cap + "'";
    body.replaceChildren(H("p", {}, "Start this before the transfer for a full capture:"), H("pre", {}, cmd),
      H("p", {}, "Display filter for this transfer: ", H("code", {}, ports.map((p) => "tcp.port == " + p).join(" || ")), ". Chunks only: ", H("code", {}, "mpft.type == 4"), "."),
      H("p", { class: "muted" }, "Load the current wireshark/mpft.lua first (Wireshark > Help > About > Folders > Personal Lua Plugins, then Analyze > Reload Lua Plugins). Ports are chosen per transfer; the dissector recognises MPFT by its header on any port."));
  } };
};

MP.panels.network = () => {
  const body = H("div"), msg = H("p", { class: "err", role: "alert" }), pct = H("input", { type: "number", id: "corrupt", min: 0, max: 100, step: 1, value: 0, style: "width:6em" });
  const call = (url, data) => MP.post(url, data).then(() => (msg.textContent = "")).catch((e) => (msg.textContent = e.message));
  let last = "";
  const el = H("section", { class: "panel", hidden: true }, H("h2", {}, "Network conditions"), body,
    H("div", { class: "row" }, H("label", { for: "corrupt", style: "margin:0" }, "Corrupt % of chunks"), pct,
      H("button", { type: "button", id: "set-corrupt", onclick: () => call("/api/session/" + el.dataset.sid + "/net/corrupt", { percent: +pct.value }) }, "Set corruption")), msg,
    H("p", { class: "muted" }, "Emulator proxies sit between sender and receiver. Corruption is applied to bytes in flight; the receiver's chunk hash catches it and the sender retransmits."));
  return { el, update(s, m) {
    el.hidden = !(m.net && m.net.length); if (el.hidden) return; el.dataset.sid = s.sid;
    const sig = JSON.stringify([m.net, s.ended]); if (sig === last) return; last = sig; // rebuilding buttons on every redraw would eat clicks
    body.replaceChildren(MP.table(["Path", "Listen port", "Delay ms", "Jitter ms", "Rate Mbit/s", "State", "Live actions (set delay in ms)"], m.net.map((p) => [p.path, p.listen_port, p.delay_ms || 0, p.jitter_ms || 0, p.rate_mbit || "unlimited",
      p.dead ? "killed" : "up", H("span", { class: "row" },
        H("button", { type: "button", class: "kill", disabled: p.dead || s.ended, onclick: () => call("/api/session/" + s.sid + "/net/kill/" + p.path) }, "Kill path " + p.path),
        H("button", { type: "button", class: "restore", disabled: !p.dead || s.ended, onclick: () => call("/api/session/" + s.sid + "/net/restore/" + p.path) }, "Restore"),
        H("input", { type: "number", min: 0, max: 5000, step: 10, value: p.delay_ms || 0, style: "width:5em", "aria-label": "Delay ms for path " + p.path, disabled: p.dead || s.ended,
          onchange: (ev) => call("/api/session/" + s.sid + "/net/delay/" + p.path, { delay_ms: +ev.target.value }) }))]), [0, 1, 2, 3, 4]));
  } };
};
