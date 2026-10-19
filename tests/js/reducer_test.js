// Scripted fake event stream through the Transfer view reducer (run by tests/test_js_reducer.py).
const vm = require("vm"), fs = require("fs"), assert = require("assert");
const ctx = { MP: { views: {}, panels: {} }, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + "/../../web/static/transfer.js", "utf8"), ctx);
const MP = ctx.MP, s = MP.newState(7);
let t = 1000;
const ev = (kind, o = {}) => MP.reduce(s, { kind, t: (t += 0.2), session: 7, role: "sender", ...o });
ev("send_state", { state: "offered", message: "waiting" });
ev("session_started", { file_name: "f.bin", file_size: 4 << 20, file_sha256: "ab", chunk_size: 1 << 20, total_chunks: 4 });
ev("path_up", { path: 0, local: "a:1", remote: "b:2" }); ev("path_up", { path: 1, local: "a:3", remote: "b:2" });
ev("chunk_state", { index: 0, state: "inflight", path: 0, attempt: 1 });
ev("chunk_state", { index: 0, state: "done", path: 0, bytes: 1 << 20, rtt_ms: 10 });
ev("chunk_state", { index: 1, state: "inflight", path: 1, attempt: 1 });
ev("nack", { index: 1, path: 1 }); ev("requeue", { index: 1, path: 1, attempt: 1 });
ev("chunk_state", { index: 1, state: "retransmitted", path: 1, attempt: 1 });
ev("chunk_state", { index: 2, state: "inflight", path: 1, attempt: 1 });
ev("requeue", { index: 2, path: 1, attempt: 1 }); ev("chunk_state", { index: 2, state: "retransmitted", path: 1, attempt: 1 });
ev("path_down", { path: 1 });
for (const i of [1, 2, 3]) { ev("chunk_state", { index: i, state: "done", path: 0, bytes: 1 << 20, rtt_ms: 20 }); }
ev("throughput_tick", { path: 0, mbit: 12.5 });
ev("session_done", { success: true });
assert.strictEqual(s.done, 4); assert.strictEqual(s.retx, 2); assert.strictEqual(s.nacks, 1);
assert.strictEqual(s.paths[1].state, "down"); assert.strictEqual(s.paths[0].chunks, 4);
assert.strictEqual(s.paths[0].n, 4); assert.ok(Math.abs(s.paths[0].mean - 17.5) < 1e-9);
assert.deepStrictEqual([...s.cell], [2, 2, 2, 2]); assert.deepStrictEqual([...s.retxFlag], [0, 1, 1, 0]);
assert.strictEqual(s.phase, "done"); assert.strictEqual(s.verify.result, "verified by receiver (DONE)");
const texts = s.log.map((l) => l.text);
assert.ok(texts.some((x) => x.includes("chunk 1 hash mismatch at receiver, retransmitting")));
assert.ok(texts.some((x) => x.startsWith("path 1 down")));
assert.ok(!texts.some((x) => x.startsWith("chunk 1 requeued")), "requeue after NACK must not log twice");

// receiver role: throughput is derived from hash_chunk_ok bytes per second of event time
const r = MP.newState(8); t = 2000;
const rv = (kind, o = {}) => MP.reduce(r, { kind, t: (t += 0.5), session: 8, role: "receiver", ...o });
rv("session_started", { file_name: "g", file_size: 3 << 20, file_sha256: "cd", chunk_size: 1 << 20, total_chunks: 3 });
rv("path_up", { path: 0, remote: "x:1" });
for (let i = 0; i < 3; i++) rv("hash_chunk_ok", { index: i, path: 0 });
rv("hash_file_verified", { expected: "cd", computed: "cd" }); rv("session_done", { success: true });
assert.strictEqual(r.done, 3); assert.strictEqual(r.verify.result, "verified");
assert.ok(r.series[0].length >= 1 && r.series[0][0][1] > 0);

// merged two-sided stream: receiver path ids differ from sender's and must not create phantom paths or double counts
const m = MP.newState(9); t = 3000;
const mv = (role, kind, o = {}) => MP.reduce(m, { kind, t: (t += 0.1), session: 9, role, side: role, mine: role === "sender", ...o });
const info = { file_name: "h", file_size: 2 << 20, file_sha256: "ef", chunk_size: 1 << 20, total_chunks: 2 };
mv("sender", "session_started", info); mv("receiver", "session_started", info);
mv("sender", "path_up", { path: 0, local: "a:1", remote: "b:2" }); mv("receiver", "path_up", { path: 5, remote: "a:1" });
for (let i = 0; i < 2; i++) {
  mv("sender", "chunk_state", { index: i, state: "inflight", path: 0, attempt: 1 });
  mv("receiver", "hash_chunk_ok", { index: i, path: 5 });
  mv("sender", "chunk_state", { index: i, state: "done", path: 0, bytes: 1 << 20, rtt_ms: 5 });
}
mv("sender", "throughput_tick", { path: 0, mbit: 9 });
mv("receiver", "hash_file_verified", { expected: "ef", computed: "ef" });
mv("receiver", "session_done", { success: true }); mv("sender", "session_done", { success: true });
assert.deepStrictEqual(Object.keys(m.paths), ["0"]); assert.strictEqual(m.done, 2); assert.strictEqual(m.paths[0].bytes, 2 << 20);
assert.strictEqual(m.role, "sender"); assert.strictEqual(m.verify.result, "verified"); assert.strictEqual(m.phase, "done");
assert.ok(m.log.some((l) => l.side === "receiver") && m.log.some((l) => l.side === "sender"));
console.log("ok");
