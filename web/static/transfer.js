// Transfer view: a reducer turns the SSE events of one session into a state object, panels render it.
MP.newState = (sid) => ({ sid, role: null, phase: "starting", message: "", total: 0, done: 0, retx: 0, nacks: 0, bytes: 0,
  paths: {}, series: {}, bucket: { sec: 0, bytes: {} }, log: [], trace: [], lastNack: -1, ended: false, success: null,
  verify: { ok: 0, bad: 0, expected: null, computed: null, result: null }, dirty: new Set(), t0: null, tEnd: null });

MP.pathOf = (s, id) => (s.paths[id] ||= { id, state: "up", local: "", remote: "", bytes: 0, chunks: 0, n: 0, mean: 0, m2: 0, retries: 0, nacks: 0 });
MP.chunkLen = (s, i) => Math.min(s.cs, s.size - i * s.cs);

MP.reduce = function (s, e) {
  if (s.role === "receiver") MP.bucketReceiver(s, e.t); // close finished seconds before counting this event
  const say = (text) => s.log.push({ t: e.t, text });
  const mark = (i) => s.dirty.add(i);
  const chunkDone = (i, pid, nbytes) => {
    if (s.cell[i] === 2) return;
    s.cell[i] = 2; s.cpath[i] = pid; s.done++; s.bytes += nbytes; mark(i);
    const p = MP.pathOf(s, pid); p.bytes += nbytes; p.chunks++;
    s.bucket.bytes[pid] = (s.bucket.bytes[pid] || 0) + nbytes;
  };
  switch (e.kind) {
    case "send_state": s.phase = e.state; s.message = e.message; say(e.state + (e.message ? ": " + e.message : "")); break;
    case "session_started":
      Object.assign(s, { role: e.role, name: e.file_name, size: e.file_size, sha: e.file_sha256, cs: e.chunk_size, total: e.total_chunks, t0: e.t,
        cell: new Uint8Array(e.total_chunks), retxFlag: new Uint8Array(e.total_chunks), cpath: new Int16Array(e.total_chunks).fill(-1),
        attempts: new Uint8Array(e.total_chunks), phase: e.role === "sender" ? "transferring" : "receiving" });
      s.bucket.sec = Math.floor(e.t);
      say("session started, " + e.total_chunks + " chunks"); break;
    case "manifest_sent": say("manifest sent"); break;
    case "manifest_received": say("manifest received" + (e.held ? ", " + e.held + " chunks already held" : "")); break;
    case "path_up": { const p = MP.pathOf(s, e.path); p.state = "up"; p.local = e.local || p.local; p.remote = e.remote || p.remote; say("path " + e.path + " up"); break; }
    case "path_down": if (!s.ended && e.path != null && MP.pathOf(s, e.path).state !== "down") { const p = MP.pathOf(s, e.path); p.state = "down"; say("path " + e.path + " down" + (p.retries ? ", " + p.retries + " chunk retries" : "")); } break;
    case "chunk_state":
      if (e.state === "inflight") { if (s.cell[e.index] !== 2) { s.cell[e.index] = 1; s.cpath[e.index] = e.path; } s.attempts[e.index] = e.attempt; mark(e.index); }
      else if (e.state === "done") { chunkDone(e.index, e.path, e.bytes); const p = MP.pathOf(s, e.path); p.n++; const d = e.rtt_ms - p.mean; p.mean += d / p.n; p.m2 += d * (e.rtt_ms - p.mean); s.verify.ok = s.done; }
      else if (e.state === "retransmitted") { s.retxFlag[e.index] = 1; s.retx++; if (s.cell[e.index] !== 2) s.cell[e.index] = 0; mark(e.index); }
      break;
    case "nack": s.nacks++; s.verify.bad++; s.lastNack = e.index; MP.pathOf(s, e.path).nacks++; say("chunk " + e.index + " hash mismatch at receiver, retransmitting"); break;
    case "requeue": MP.pathOf(s, e.path ?? 0).retries++; if (e.index !== s.lastNack) say("chunk " + e.index + " requeued (attempt " + e.attempt + ")"); break;
    case "hash_chunk_ok": chunkDone(e.index, e.path, MP.chunkLen(s, e.index)); s.verify.ok = s.done; break;
    case "hash_chunk_bad": s.verify.bad++; s.retx++; s.retxFlag[e.index] = 1; mark(e.index); say("chunk " + e.index + " hash mismatch, sender will retransmit"); break;
    case "hash_file_verified": case "hash_file_mismatch":
      s.verify.expected = e.expected; s.verify.computed = e.computed; s.verify.result = e.kind === "hash_file_verified" ? "verified" : "mismatch";
      say(e.kind === "hash_file_verified" ? "whole-file SHA-256 verified" : "whole-file SHA-256 mismatch"); break;
    case "throughput_tick": (s.series[e.path] ||= []).push([e.t - s.t0, e.mbit]); break;
    case "message": s.trace.push(e); if (s.trace.length > 50) s.trace.shift(); break;
    case "emulator_path_killed": say("emulator killed the path on port " + e.port); break;
    case "session_done":
      s.ended = true; s.success = e.success; s.tEnd = e.t; s.phase = e.success ? "done" : "failed"; if (e.error) s.message = e.error;
      if (s.role === "sender") { s.verify.result = e.success ? "verified by receiver (DONE)" : s.verify.result; s.verify.expected = s.sha; }
      say(e.success ? "transfer complete" : "transfer failed" + (e.error ? ": " + e.error : "")); break;
  }
};

// The receiver emits no throughput ticks, so derive them: bytes per whole second of event time.
MP.bucketReceiver = function (s, now) {
  while (Math.floor(now) > s.bucket.sec) {
    for (const id of Object.keys(s.paths)) (s.series[id] ||= []).push([s.bucket.sec + 1 - s.t0, (s.bucket.bytes[id] || 0) * 8 / 1e6]);
    s.bucket.bytes = {}; s.bucket.sec++;
  }
};

MP.views.transfer = function (root, sid) {
  if (!sid) return MP.transferList(root);
  const s = MP.newState(+sid), meta = { loaded: false };
  const P = [MP.panels.header, MP.panels.progress, MP.panels.chunkmap, MP.panels.paths, MP.panels.chart, MP.panels.verify,
    MP.panels.network, MP.panels.logs, MP.panels.wireshark].map((f) => f(s, meta));
  root.append(MP.h("h1", {}, "Transfer"), ...P.map((p) => p.el));
  let queued = false;
  const draw = () => { queued = false; P.forEach((p) => p.update(s, meta)); s.dirty.clear(); };
  const schedule = () => { if (!queued) { queued = true; setTimeout(draw, 60); } };
  const loadMeta = () => MP.api("/api/session/" + sid).then((m) => { Object.assign(meta, m, { loaded: true }); schedule(); }).catch(() => {});
  for (const e of MP.events.bySession[sid] || []) MP.reduce(s, e);
  loadMeta(); draw();
  const off = MP.on((e) => {
    if (e.session !== s.sid && e.kind !== "emulator_path_killed") return;
    MP.reduce(s, e);
    if (e.kind === "send_state" || e.kind === "session_started" || e.kind === "emulator_path_killed") loadMeta();
    schedule();
  });
  const timer = setInterval(() => { if (!s.ended) { if (s.role === "receiver") MP.bucketReceiver(s, Date.now() / 1000); schedule(); } }, 1000);
  return () => { off(); clearInterval(timer); };
};

MP.transferList = function (root) {
  const ids = Object.keys(MP.events.bySession).filter((k) => MP.events.bySession[k].some((e) => e.kind === "session_started" || e.kind === "send_state"));
  root.append(MP.h("h1", {}, "Transfers"), ids.length ? MP.h("ul", {}, ids.reverse().map((k) =>
    MP.h("li", {}, MP.h("a", { href: "#/transfer/" + k }, "Session " + k)))) : MP.h("p", { class: "muted" }, "No transfers in this browser session. Send or accept a file first."));
};
