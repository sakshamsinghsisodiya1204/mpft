// Chunk map (canvas, scales past 20,000 chunks by grouping) and the sortable chunk table.
const HC = MP.h;
let CELL = 9;
const MAX_CELLS = 6000; // px per cell incl. gap; above MAX_CELLS chunks, several chunks share a cell
const NAMES = ["pending", "in flight", "done", "failed"];

MP.panels.chunkmap = (s0, meta) => {
  const cv = HC("canvas", { class: "chunkmap", tabindex: "0", role: "img", "aria-label": "Chunk map" }), tip = HC("p", { class: "muted mono" }, "Hover a cell for details, click to select.");
  const legend = HC("p", { class: "legend" }, ...[["", "pending"], ["f", "in flight (hatched)"], ["d", "done"], ["r", "retransmitted (outline)"], ["x", "failed (crossed)"]].map(([c, t]) => HC("span", {}, HC("i", { class: c }), t)));
  let S = null, k = 1, cols = 1;
  const hatch = document.createElement("canvas"); hatch.width = hatch.height = 4;
  const paintHatch = (bg, fg) => { const hx = hatch.getContext("2d"); hx.fillStyle = bg; hx.fillRect(0, 0, 4, 4); hx.strokeStyle = fg; hx.beginPath(); hx.moveTo(0, 4); hx.lineTo(4, 0); hx.stroke(); };
  const group = (c) => { const lo = c * k, hi = Math.min(lo + k, S.total); let d = 0, fl = 0, rx = 0, fa = 0; for (let i = lo; i < hi; i++) { const v = S.cell[i]; if (v === 2) d++; else if (v === 1) fl++; else if (v === 3) fa++; if (S.retxFlag[i]) rx = 1; } return { d, fl, rx, fa, n: hi - lo }; };
  const cellAt = (ev) => { const r = cv.getBoundingClientRect(), x = Math.floor(((ev.clientX - r.left) * cv.width) / r.width / CELL), y = Math.floor(((ev.clientY - r.top) * cv.height) / r.height / CELL); return y * cols + x; };
  cv.addEventListener("mousemove", (ev) => {
    const c = cellAt(ev); if (!S || c < 0 || c * k >= S.total) return; const i = c * k;
    if (k > 1) { const g = group(c); tip.textContent = "Chunks " + i + " to " + (i + g.n - 1) + ": " + g.d + " done, " + g.fl + " in flight, " + g.fa + " failed"; return; }
    const off = i * S.cs, rtt = S.rtt[i];
    tip.textContent = "Chunk " + i + ": " + NAMES[S.cell[i]] + ", offset " + off + ", size " + MP.chunkLen(S, i) + ", path " + (S.cpath[i] < 0 ? "-" : S.cpath[i]) + ", attempts " + S.attempts[i] + ", rtt " + (Number.isNaN(rtt) ? "-" : rtt.toFixed(1) + " ms");
  });
  cv.addEventListener("click", (ev) => { const c = cellAt(ev); if (S && c >= 0 && c * k < S.total) { S.selected = c * k; meta.onSelect && meta.onSelect(c * k); } });
  const draw = (s) => {
    S = s; if (!s.total) return;
    const w = Math.max(cv.parentNode.clientWidth - 34, 120); // panel padding (2 x 16 px) and canvas border k = Math.max(1, Math.ceil(s.total / MAX_CELLS)); CELL = s.total <= 64 ? 24 : s.total <= 400 ? 14 : 9; // few chunks get big cells
    cols = Math.max(1, Math.floor(w / CELL)); const n = Math.ceil(s.total / k), rows = Math.ceil(n / cols);
    if (cv.width !== cols * CELL || cv.height !== rows * CELL) { cv.width = cols * CELL; cv.height = rows * CELL; }
    const C = { done: MP.css("--accent"), bg: MP.css("--surface"), line: MP.css("--border-strong"), retx: MP.css("--text"), err: MP.css("--err"), p: [0, 1, 2, 3, 4, 5, 6, 7].map((i) => MP.css("--p" + i)) };
    paintHatch(C.bg, C.done); // pending / done / in-flight colours come from the theme
    const g = cv.getContext("2d"), pat = g.createPattern(hatch, "repeat"); g.clearRect(0, 0, cv.width, cv.height);
    for (let c = 0; c < n; c++) {
      const x = (c % cols) * CELL, y = Math.floor(c / cols) * CELL, q = group(c);
      g.fillStyle = q.d === q.n ? C.done : q.d + q.fl ? pat : C.bg; g.fillRect(x, y, CELL - 1, CELL - 1);
      g.strokeStyle = C.line; g.lineWidth = 1; if (q.d !== q.n) g.strokeRect(x + .5, y + .5, CELL - 2, CELL - 2);
      if (q.rx) { g.strokeStyle = C.retx; g.lineWidth = 1.5; g.strokeRect(x + 1, y + 1, CELL - 3, CELL - 3); }
      if (q.fa) { g.strokeStyle = C.err; g.beginPath(); g.moveTo(x, y); g.lineTo(x + CELL - 1, y + CELL - 1); g.moveTo(x + CELL - 1, y); g.lineTo(x, y + CELL - 1); g.stroke(); }
      if (k === 1 && s.cpath[c] >= 0) { g.fillStyle = C.p[s.cpath[c] % 8]; g.fillRect(x, y + CELL - 3, CELL - 1, 2); } // path colour tick on the bottom edge
    }
  };
  return { el: MP.panel("Chunk map", legend, cv, tip), update(s) { if (s.dirty.size || S !== s || cv.dataset.n !== String(s.total)) { cv.dataset.n = s.total; draw(s); } } };
};

MP.panels.chunktable = (s0, meta) => {
  const body = HC("div"), st = HC("select", { "aria-label": "State filter" }, ["any state", ...NAMES].map((t, i) => HC("option", { value: i - 1 }, t)));
  const pf = HC("select", { "aria-label": "Path filter" }), multi = HC("input", { type: "checkbox", id: "multi" }), goto = HC("input", { type: "number", min: 0, placeholder: "index", style: "width:6em", "aria-label": "Go to chunk index" });
  const cols = [["Index", (s, i) => i], ["Offset", (s, i) => i * s.cs], ["Size", (s, i) => MP.chunkLen(s, i)], ["SHA-256", (s, i) => s.csha[i]], ["Path", (s, i) => s.cpath[i]], ["Attempts", (s, i) => s.attempts[i]],
    ["First sent", (s, i) => s.tFirst[i]], ["Acked", (s, i) => s.tAck[i]], ["RTT ms", (s, i) => s.rtt[i]], ["Verification", (s, i) => s.vBad[i] * 10 + s.vOk[i]]];
  let sort = 0, dir = 1, S = null, limit = 100;
  const redraw = () => S && draw(S);
  const draw = (s) => {
    S = s; if (!s.total) { body.replaceChildren(HC("p", { class: "muted" }, "No chunks yet.")); return; }
    if (pf.options.length !== Object.keys(s.paths).length + 1) pf.replaceChildren(HC("option", { value: -1 }, "any path"), ...Object.keys(s.paths).map((p) => HC("option", { value: p }, "path " + p)));
    let idx = []; const want = +st.value, wp = +pf.value;
    for (let i = 0; i < s.total; i++) { if (want >= 0 && s.cell[i] !== want) continue; if (wp >= 0 && s.cpath[i] !== wp) continue; if (multi.checked && s.attempts[i] < 2) continue; idx.push(i); }
    if (goto.value !== "") { const g = +goto.value; idx = idx.filter((i) => i >= g); }
    const f = cols[sort][1]; if (sort || dir < 0) idx.sort((a, b) => { const x = f(s, a), y = f(s, b); return (x > y ? 1 : x < y ? -1 : a - b) * dir; });
    const t = (x) => (Number.isNaN(x) ? "-" : "+" + (x - s.t0).toFixed(2));
    const rows = idx.slice(0, limit).map((i) => { const tr = HC("tr", { class: s.selected === i ? "sel" : "" }, [i, i * s.cs, MP.chunkLen(s, i), s.csha[i] || "-", s.cpath[i] < 0 ? "-" : s.cpath[i], s.attempts[i], t(s.tFirst[i]), t(s.tAck[i]),
      Number.isNaN(s.rtt[i]) ? "-" : s.rtt[i].toFixed(1), s.vBad[i] ? "rejected x" + s.vBad[i] + (s.vOk[i] ? ", then ok" : "") : s.vOk[i] ? "ok" : "-"].map((c, j) => HC("td", { class: j !== 3 && j !== 9 ? "num" : "mono" }, c))); return tr; });
    const head = HC("tr", {}, cols.map(([n], j) => HC("th", { class: "sort" + (j !== 3 && j !== 9 ? " num" : ""), tabindex: "0", onkeydown: (ev) => ev.key === "Enter" && ev.target.click(), "aria-sort": sort === j ? (dir > 0 ? "ascending" : "descending") : "none",
      onclick: () => { dir = sort === j ? -dir : 1; sort = j; redraw(); } }, n + (sort === j ? (dir > 0 ? " ^" : " v") : ""))));
    body.replaceChildren(HC("div", { class: "table-wrap tall" }, HC("table", {}, HC("thead", {}, head), HC("tbody", {}, rows))),
      HC("p", { class: "muted" }, idx.length + " chunks match" + (idx.length > limit ? ", showing " + limit + " " : ""), idx.length > limit ? HC("button", { type: "button", onclick: () => { limit += 400; redraw(); } }, "Show more") : null));
  };
  [st, pf, multi, goto].forEach((e) => e.addEventListener("change", redraw)); goto.addEventListener("input", redraw);
  meta.onSelect = (i) => { goto.value = i; redraw(); };
  let last = 0;
  return { el: MP.panel("Chunks", HC("div", { class: "filters" }, st, pf, HC("label", {}, multi, " attempts > 1"), HC("label", {}, "from ", goto)), body),
    update(s) { S = s; if (Date.now() - last > 700 || s.dirty.size === 0) { last = Date.now(); draw(s); } } };
};
