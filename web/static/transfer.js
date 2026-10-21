// Transfer state: a reducer turns the merged sender+receiver events of one session into a state object that panels render.
MP.PATH_COLORS = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => "var(--p" + i + ")"); // CSS variables, so light and dark themes recolour them
MP.PATH_DASH = ["", "6 3", "2 2", "8 3 2 3", "1 3", "10 4", "4 2 1 2", "12 3"];
MP.newState = (sid) => ({ sid, role: null, phase: "starting", message: "", total: 0, done: 0, retx: 0, nacks: 0, bytes: 0,
  hasSender: false, sawTicks: false, okRecv: 0, badRecv: 0, badIdx: [], paths: {}, series: {}, bucket: { sec: 0, bytes: {} }, log: [], trace: [], doneLog: [],
  lastNack: -1, ended: false, success: null, verify: { ok: 0, bad: 0, expected: null, computed: null, result: null }, dirty: new Set(),
  t0: null, tEnd: null, cum: [], retxSeries: [], inflight: {}, inflightSeries: {}, rttSeries: {}, incidents: [], marks: [], addrs: null });

MP.pathOf = (s, id) => (s.paths[id] ||= { id, state: "up", local: "", remote: "", bytes: 0, chunks: 0, n: 0, mean: 0, m2: 0, retries: 0, nacks: 0, last: "" });
MP.chunkLen = (s, i) => Math.min(s.cs, s.size - i * s.cs);
// Keep at most one sample per minDt seconds (the last value wins), so graphs stay small on long transfers.
MP.sample = (arr, t, v, minDt = 0.25) => { const l = arr[arr.length - 1]; if (l && t - l[0] < minDt) l[1] = v; else arr.push([t, v]); };

MP.reduce = function (s, e) {
  if (s.role === "receiver") MP.bucketReceiver(s, e.t); // close finished seconds before counting this event
  const side = e.side || e.role;
  // Path ids differ per side (the receiver numbers every connection), so with a sender present only its events drive paths and completion.
  const recvOnly = e.role === "receiver" && s.hasSender;
  const early = ["send_state", "session_started", "emulator_path_killed", "emulator_path_restored", "offer_sent", "offer_received", "offer_accepted", "offer_declined"];
  if (s.cell === undefined && !early.includes(e.kind)) return;
  const rel = s.t0 == null ? 0 : e.t - s.t0;
  const say = (text) => s.log.push({ t: e.t, text, side });
  const mark = (i) => s.dirty.add(i);
  const pnote = (id, text) => { const p = MP.pathOf(s, id); p.last = text + " @" + rel.toFixed(1) + "s"; };
  const flag = (label) => s.marks.push({ t: rel, label });
  const setInflight = (pid, d) => { s.inflight[pid] = Math.max(0, (s.inflight[pid] || 0) + d); MP.sample((s.inflightSeries[pid] ||= []), rel, s.inflight[pid], 0.2); };
  const openInc = (pid) => s.incidents.find((x) => x.kind === "path" && x.path === pid && !x.recoveredAt);
  const closeIfDone = (inc) => { if (!inc.chunks.size && !inc.recoveredAt && (inc.kind === "chunk" || inc.requeued > 0 || inc.restoredAt)) { inc.recoveredAt = e.t; flag("recovered"); } };
  const chunkDone = (i, pid, nbytes) => {
    if (s.cell[i] === 2) return;
    s.cell[i] = 2; s.cpath[i] = pid; s.done++; s.bytes += nbytes; s.tAck[i] = e.t; mark(i);
    const p = MP.pathOf(s, pid); p.bytes += nbytes; p.chunks++;
    s.bucket.bytes[pid] = (s.bucket.bytes[pid] || 0) + nbytes;
    MP.sample(s.cum, rel, s.done); s.doneLog.push([rel, pid, nbytes]);
    for (const inc of s.incidents) if (inc.chunks.delete(i)) { inc.absorbed[pid] = (inc.absorbed[pid] || 0) + 1; closeIfDone(inc); }
  };
  switch (e.kind) {
    case "send_state": s.phase = e.state; s.message = e.message; say(e.state + (e.message ? ": " + e.message : "")); break;
    case "offer_sent": say("offer sent to " + e.peer); break;
    case "offer_received": say("offer received"); break;
    case "offer_accepted": say("offer accepted"); break;
    case "offer_declined": say("offer declined" + (e.reason ? ": " + e.reason : "")); break;
    case "session_started":
      if (e.role === "sender") s.hasSender = true;
      if (e.mine !== false) s.role = e.role; else s.role ||= e.role === "sender" ? "receiver" : "sender";
      if (s.cell === undefined) {
        const n = e.total_chunks;
        Object.assign(s, { name: e.file_name, size: e.file_size, sha: e.file_sha256, cs: e.chunk_size, total: n, t0: e.t,
          cell: new Uint8Array(n), retxFlag: new Uint8Array(n), cpath: new Int16Array(n).fill(-1), attempts: new Uint8Array(n),
          tFirst: new Float64Array(n).fill(NaN), tAck: new Float64Array(n).fill(NaN), rtt: new Float32Array(n).fill(NaN),
          vOk: new Uint8Array(n), vBad: new Uint8Array(n), csha: new Array(n).fill(""), phase: e.role === "sender" ? "transferring" : "receiving" });
        s.bucket.sec = Math.floor(e.t); s.cum.push([0, 0]); s.retxSeries.push([0, 0]);
      } else if (e.role === "sender") s.phase = "transferring";
      s.t0 = Math.min(s.t0, e.t);
      say("session started, " + e.total_chunks + " chunks"); break;
    case "manifest_sent": say("manifest sent"); break;
    case "manifest_received": say("manifest received" + (e.held ? ", " + e.held + " chunks already held" : "")); break;
    case "path_up": {
      if (recvOnly) { say("path connected from " + e.remote); break; }
      const p = MP.pathOf(s, e.path), inc = openInc(e.path);
      p.state = "up"; p.local = e.local || p.local; p.remote = e.remote || p.remote; pnote(e.path, "up"); say("path " + e.path + " up");
      if (inc && !inc.restoredAt) { inc.restoredAt = e.t; closeIfDone(inc); }
      break; }
    case "path_restored": say("path " + e.path + " reconnected"); { const inc = openInc(e.path); if (inc && !inc.restoredAt) { inc.restoredAt = e.t; closeIfDone(inc); } } break;
    case "path_down":
      if (recvOnly) { say("connection closed"); break; }
      if (!s.ended && e.path != null && MP.pathOf(s, e.path).state !== "down") {
        const p = MP.pathOf(s, e.path); p.state = "down"; pnote(e.path, "down" + (e.reason ? " (" + e.reason + ")" : "")); flag("path " + e.path + " down");
        say("path " + e.path + " down" + (e.reason ? " (" + e.reason + ")" : "") + (p.retries ? ", " + p.retries + " chunk retries" : ""));
        if (!openInc(e.path)) s.incidents.push({ kind: "path", path: e.path, at: e.t, cause: e.reason || "connection lost", chunks: new Set(), requeued: 0, backoffs: [], absorbed: {}, restoredAt: null, recoveredAt: null });
      } break;
    case "timeout": say("chunk " + e.index + " timed out on path " + e.path + " after " + e.after_s + " s"); break;
    case "backoff": { const inc = openInc(e.path); if (inc) inc.backoffs.push({ t: e.t, delay: e.delay }); say("path " + e.path + " reconnect in " + e.delay.toFixed(1) + " s (failure " + e.fails + ")"); break; }
    case "chunk_state":
      if (e.state === "inflight") {
        if (s.cell[e.index] !== 2) { s.cell[e.index] = 1; s.cpath[e.index] = e.path; } s.attempts[e.index] = e.attempt;
        if (Number.isNaN(s.tFirst[e.index])) s.tFirst[e.index] = e.t; setInflight(e.path, 1); mark(e.index);
      } else if (e.state === "done") {
        s.hasSender = true; s.rtt[e.index] = e.rtt_ms; chunkDone(e.index, e.path, e.bytes); setInflight(e.path, -1);
        const p = MP.pathOf(s, e.path); p.n++; const d = e.rtt_ms - p.mean; p.mean += d / p.n; p.m2 += d * (e.rtt_ms - p.mean); s.verify.ok = Math.max(s.done, s.okRecv);
      } else if (e.state === "retransmitted") {
        s.retxFlag[e.index] = 1; s.retx++; if (s.cell[e.index] !== 2) s.cell[e.index] = 0; setInflight(e.path, -1); mark(e.index); MP.sample(s.retxSeries, rel, s.retx);
      } else if (e.state === "failed") { s.cell[e.index] = 3; setInflight(e.path, -1); mark(e.index); say("chunk " + e.index + " failed after the retry limit"); }
      break;
    case "nack":
      s.nacks++; s.verify.bad = Math.max(s.badRecv, s.nacks); s.lastNack = e.index; MP.pathOf(s, e.path).nacks++;
      s.incidents.push({ kind: "chunk", path: e.path, at: e.t, cause: "chunk " + e.index + " hash mismatch", chunks: new Set([e.index]), requeued: 1, backoffs: [], absorbed: {}, restoredAt: e.t, recoveredAt: null });
      say("chunk " + e.index + " hash mismatch at receiver, retransmitting"); break;
    case "requeue": {
      MP.pathOf(s, e.path ?? 0).retries++;
      const inc = e.reason !== "nack" && openInc(e.path);
      if (inc) { inc.chunks.add(e.index); inc.requeued++; const m = s.marks.findLast((x) => x.label.startsWith("requeued") && x.inc === inc); if (m) m.label = "requeued " + inc.requeued; else s.marks.push({ t: rel, label: "requeued 1", inc }); }
      if (e.index !== s.lastNack) say("chunk " + e.index + " requeued (attempt " + e.attempt + ", " + (e.reason || "failure") + ")"); break; }
    case "hash_chunk_ok":
      s.vOk[e.index]++; s.csha[e.index] = e.sha || s.csha[e.index];
      if (recvOnly) { s.okRecv++; mark(e.index); } else chunkDone(e.index, e.path, MP.chunkLen(s, e.index));
      s.verify.ok = Math.max(s.done, s.okRecv); break;
    case "hash_chunk_bad":
      s.vBad[e.index]++; s.badRecv++; s.badIdx.push(e.index); s.csha[e.index] = e.sha || s.csha[e.index]; s.verify.bad = Math.max(s.badRecv, s.nacks);
      if (!s.hasSender) s.retx++; s.retxFlag[e.index] = 1; mark(e.index); say("chunk " + e.index + " hash mismatch, sender will retransmit"); break;
    case "hash_file_verified": case "hash_file_mismatch":
      s.verify.expected = e.expected; s.verify.computed = e.computed; s.verify.result = e.kind === "hash_file_verified" ? "verified" : "mismatch";
      say(e.kind === "hash_file_verified" ? "whole-file SHA-256 verified" : "whole-file SHA-256 mismatch"); break;
    case "throughput_tick": if (!s.sawTicks) { s.sawTicks = true; s.series = {}; } (s.series[e.path] ||= []).push([e.t - s.t0, e.mbit]); break;
    case "rtt_sample": (s.rttSeries[e.path] ||= []).push([rel, e.mean_ms, e.min_ms, e.max_ms]); break;
    case "message": s.trace.push(e); if (s.trace.length > 100) s.trace.shift(); break;
    case "emulator_path_killed": say("emulator killed the path on port " + e.port); break;
    case "emulator_path_restored": say("emulator restored the path on port " + e.port); break;
    case "session_done":
      s.success = s.ended ? s.success && e.success : e.success; s.ended = true; s.tEnd = s.tEnd ? Math.max(s.tEnd, e.t) : e.t;
      s.phase = s.success ? "done" : "failed"; if (e.error) s.message = e.error;
      if (e.role === "sender") { s.verify.result = e.success ? s.verify.result || "verified by receiver (DONE)" : s.verify.result; s.verify.expected = s.sha; }
      say(e.success ? "transfer complete" : "transfer failed" + (e.error ? ": " + e.error : "")); break;
  }
};

// The receiver emits no throughput ticks, so derive them when no sender events exist: bytes per whole second of event time.
MP.bucketReceiver = function (s, now) {
  if (s.sawTicks || s.hasSender) return;
  while (Math.floor(now) > s.bucket.sec) {
    for (const id of Object.keys(s.paths)) (s.series[id] ||= []).push([s.bucket.sec + 1 - s.t0, (s.bucket.bytes[id] || 0) * 8 / 1e6]);
    s.bucket.bytes = {}; s.bucket.sec++;
  }
};

// One sentence per incident: what the protocol did.
MP.explain = function (inc) {
  const by = Object.entries(inc.absorbed).sort((a, b) => b[1] - a[1]).map(([p, n]) => "path " + p + " (" + n + ")").join(", ");
  if (inc.kind === "chunk") return inc.cause + ": the receiver rejected it, the sender requeued it" + (by ? " and " + by + " delivered it." : ".");
  return "Path " + inc.path + " " + (inc.cause === "timeout" ? "stopped answering" : "failed (" + inc.cause + ")") + "; " + inc.requeued + " in-flight chunk" + (inc.requeued === 1 ? "" : "s") +
    " returned to the queue" + (by ? "; " + by + " delivered them" : "") + (inc.restoredAt ? "; the path reconnected after " + MP.secs((inc.restoredAt - inc.at)) : inc.backoffs.length ? "; reconnect attempts failed" : "") + ".";
};

// Build all panels for a state object; draw(s) refreshes them. Shared by the live view and Replay.
MP.buildTransfer = function (root, s, meta, extra = []) {
  // [name, panel factory, grid columns of 12]; the order differs by role: the sender watches delivery, the receiver watches verification.
  const layout = [["hero", MP.panels.hero, 12], ["strip", MP.panels.strip, 12], ["progress", MP.panels.progress, 12], ["chunkmap", MP.panels.chunkmap, 12], ["graphs", MP.panels.graphs, 12],
    ["paths", MP.panels.paths, 12], ["incidents", MP.panels.incidents, 6], ["verify", MP.panels.verify, 6], ["chunktable", MP.panels.chunktable, 12], ["header", MP.panels.header, 6],
    ["network", MP.panels.network, 6], ["trace", MP.panels.trace, 6], ["logs", MP.panels.logs, 6], ["wireshark", MP.panels.wireshark, 12]];
  const ORDER = {
    sender: ["hero", "strip", "progress", "chunkmap", "graphs", "paths", "network", "incidents", "verify", "chunktable", "header", "trace", "logs", "wireshark"],
    receiver: ["hero", "verify", "strip", "progress", "chunkmap", "incidents", "graphs", "paths", "chunktable", "header", "logs", "trace", "wireshark", "network"] };
  const P = layout.map(([, f]) => f(s, meta));
  P.forEach((p, i) => p.el.classList.add("s" + layout[i][2]));
  root.append(...extra, MP.h("div", { class: "grid12" }, ...P.map((p) => p.el)));
  return { draw: (st) => {
    const role = meta.role || st.role || "sender", ord = ORDER[role] || ORDER.sender;
    root.dataset.role = role;
    P.forEach((p, i) => { p.el.style.order = ord.indexOf(layout[i][0]); p.update(st, meta); }); st.dirty.clear(); } };
};

MP.views.transfer = function (root, sid) {
  if (!sid) return MP.transferList(root);
  const s = MP.newState(+sid), meta = { loaded: false };
  root.append(MP.h("h1", {}, "Transfer " + sid));
  const ui = MP.buildTransfer(root, s, meta);
  let queued = false;
  const draw = () => {
    queued = false; ui.draw(s);
    const role = meta.role || s.role, t = document.getElementById("page-title"); // the page title says which side you are on
    if (role && t) { t.textContent = (role === "sender" ? "Sending" : "Receiving") + (s.name ? " " + s.name : " (session " + sid + ")"); document.title = t.textContent + " - MPFT"; }
  };
  const schedule = () => { if (!queued) { queued = true; setTimeout(draw, 60); } };
  const loadMeta = () => MP.api("/api/session/" + sid).then((m) => { Object.assign(meta, m, { loaded: true }); schedule(); }).catch(() => {});
  const seen = new Set(); // the live feed and the persisted log overlap: apply each (side, sseq) once
  const apply = (e) => { const k = e.sseq != null && e.side + ":" + e.sseq; if (k) { if (seen.has(k)) return; seen.add(k); } MP.reduce(s, e); };
  const known = MP.events.bySession[sid];
  for (const e of known || []) apply(e);
  // Not in this browser's live feed (e.g. after a restart): replay the persisted two-sided log
  if (!known) MP.api("/api/session/" + sid + "/events").then((evs) => { evs.forEach(apply); s.dirty = new Set(); draw(); }).catch(() => {});
  loadMeta(); draw();
  const off = MP.on((e) => {
    if (e.kind === "file_received" && e.file && e.file.session === s.sid) loadMeta();
    if (e.session !== s.sid) return;
    apply(e);
    if (["send_state", "session_started", "emulator_path_killed", "emulator_path_restored"].includes(e.kind)) loadMeta();
    schedule();
  });
  const timer = setInterval(() => { if (!s.ended) { if (s.role === "receiver") MP.bucketReceiver(s, Date.now() / 1000); schedule(); } }, 1000);
  return () => { off(); clearInterval(timer); };
};

MP.transferList = function (root) {
  const ids = Object.keys(MP.events.bySession).filter((k) => MP.events.bySession[k].some((e) => e.kind === "session_started" || e.kind === "send_state"));
  root.append(MP.h("h1", {}, "Transfers"), ids.length ? MP.h("ul", {}, ids.reverse().map((k) =>
    MP.h("li", {}, MP.h("a", { href: "#/transfer/" + k }, "Session " + k)))) : MP.h("p", { class: "muted" }, "No transfers yet. Send a file to begin."));
};
