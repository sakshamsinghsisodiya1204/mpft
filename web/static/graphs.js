// Six SVG graphs on a shared time axis. The SVG is drawn at its real pixel width (ResizeObserver) so it never ends up 0 px
// wide when it was built in a hidden container; redraws are throttled to ~4 per second.
const NS = "http://www.w3.org/2000/svg", HT = 230, L = 46, T = 16, B = 36, MARK_COLOR = { down: "var(--err)", requeued: "var(--warn)", recovered: "var(--ok)" };
const sv = (tag, a, text) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (text != null) e.textContent = text; return e; };

// 1/2/5 x 10^n tick values covering 0..max
MP.ticks = (max, n = 4, int = false) => {
  const raw = int ? Math.max(1, max / n) : max / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map((m) => m * mag).find((v) => v >= raw);
  const out = []; for (let v = 0; v < max + step - 1e-9; v += step) out.push(+v.toFixed(6)); return { step, out, end: out[out.length - 1] }; // last tick >= max, so no data is clipped
};
// Throughput from chunk completions in buckets sized to the transfer: a per-second tick gives one point for a 0.4 s transfer.
MP.rateSeries = (s, tmax) => {
  const dt = tmax >= 20 ? 1 : Math.max(0.02, tmax / 20), n = Math.max(1, Math.ceil(tmax / dt - 1e-9)), per = {};
  for (const [t, pid, b] of s.doneLog) { const k = Math.min(n - 1, Math.floor(t / dt)); ((per[pid] ||= new Array(n).fill(0)))[k] += b; }
  return Object.fromEntries(Object.entries(per).map(([pid, a]) => [pid, [[0, a[0] * 8 / 1e6 / dt], ...a.map((b, k) => [Math.min(tmax, (k + 1) * dt), b * 8 / 1e6 / dt])]]));
};
const fmt = (v) => (Math.abs(v) >= 100 || Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1));

// series: [{label, pts: [[t, v, lo, hi]], color, dash, step, path}]; marks: [{t, label}]
MP.chart = function (svg, series, marks, tmax, yUnit) {
  const W = Math.max(280, Math.round(svg.getBoundingClientRect().width) || 640), R = W - 56, k = [];
  svg.setAttribute("viewBox", `0 0 ${W} ${HT}`); svg.setAttribute("height", HT);
  const live = series.filter((x) => x.pts.length), bad = (v) => !Number.isFinite(v);
  svg.dataset.state = live.length ? "ready" : "empty";
  if (!live.length) { svg.replaceChildren(sv("text", { x: W / 2, y: HT / 2, "text-anchor": "middle", class: "empty" }, "Waiting for data")); return; }
  const ymax0 = Math.max(0, ...live.flatMap((x) => x.pts.flatMap((p) => [p[1], p[3] ?? 0]).filter(Number.isFinite))), ymax = ymax0 < 1e-3 ? 1 : ymax0, yt = MP.ticks(ymax * 1.02, 4, /chunks/.test(yUnit)), top = yt.end;
  // Short transfers (under 2 s) get a millisecond axis, otherwise the whole curve is squeezed against the left edge.
  const ms = tmax < 2, u = ms ? 1000 : 1, xt = MP.ticks(tmax * u, Math.max(2, Math.floor((R - L) / 90)));
  const X = (t) => L + ((R - L) * t * u) / (xt.end || tmax * u), Y = (v) => HT - B - ((HT - B - T) * v) / top;
  yt.out.forEach((v) => k.push(sv("line", { x1: L, x2: R, y1: Y(v), y2: Y(v), class: "grid" }), sv("text", { x: L - 6, y: Y(v) + 3, "text-anchor": "end", class: "tick" }, fmt(v))));
  xt.out.forEach((v) => k.push(sv("line", { x1: X(v / u), x2: X(v / u), y1: HT - B, y2: HT - B + 4, class: "axis" }), sv("text", { x: X(v / u), y: HT - B + 15, "text-anchor": "middle", class: "tick" }, fmt(v))));
  k.push(sv("line", { x1: L, x2: R, y1: HT - B, y2: HT - B, class: "axis" }), sv("line", { x1: L, x2: L, y1: T, y2: HT - B, class: "axis" }),
    sv("text", { x: (L + R) / 2, y: HT - 4, "text-anchor": "middle", class: "axlabel" }, ms ? "time since start (ms)" : "time since start (s)"), sv("text", { x: L, y: 10, class: "axlabel" }, yUnit));
  const used = [];
  marks.forEach((m) => {
    if (bad(m.t)) return;
    const x = X(m.t), off = used.filter((u) => Math.abs(u - x) < 12).length * 12; used.push(x);
    const kind = m.label.split(" ")[0] === "recovered" ? "recovered" : /down$/.test(m.label) ? "down" : "requeued";
    k.push(sv("line", { x1: x, x2: x, y1: T, y2: HT - B, class: "mark", style: "stroke:" + MARK_COLOR[kind], "data-label": m.label }),
      sv("text", { transform: `translate(${x - 3 + off},${HT - B - 4}) rotate(-90)`, class: "marktext", style: "fill:" + MARK_COLOR[kind] }, m.label));
  });
  const ends = [];
  live.forEach((x) => {
    const pts = x.pts.filter((p) => !bad(p[0]) && !bad(p[1]));
    if (!pts.length) return;
    if (x.pts[0].length > 2) k.push(sv("polygon", { class: "band", style: "fill:" + x.color, points: [...pts.map((p) => X(p[0]) + "," + Y(p[3])), ...pts.slice().reverse().map((p) => X(p[0]) + "," + Y(p[2]))].join(" ") }));
    const xy = x.step ? pts.flatMap((p, i) => (i ? [[p[0], pts[i - 1][1]], [p[0], p[1]]] : [[p[0], p[1]]])) : pts.map((p) => [p[0], p[1]]);
    const line = sv("polyline", { class: "series", fill: "none", "data-path": x.path ?? "", "data-n": pts.length, points: xy.map((p) => X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)).join(" ") });
    line.style.cssText = "stroke:" + x.color + (x.dash ? ";stroke-dasharray:" + x.dash : "");
    k.push(line);
    const last = pts[pts.length - 1];
    k.push(sv("circle", { cx: X(last[0]), cy: Y(last[1]), r: 2.5, style: "fill:" + x.color }));
    ends.push({ y: Y(last[1]), x: X(last[0]), x_: x });
  });
  ends.sort((a, b) => a.y - b.y).forEach((e, i, a) => { if (i && e.y < a[i - 1].y + 11) e.y = a[i - 1].y + 11; // keep direct labels from overlapping
    k.push(sv("text", { x: Math.min(e.x + 6, R + 4), y: e.y + 3, class: "dlabel", style: "fill:" + e.x_.color }, e.x_.label)); });
  svg.replaceChildren(...k);
};

MP.panels.graphs = () => {
  const defs = [["throughput", "Throughput per path and total", "Mbit/s"], ["chunks", "Chunks done over time", "chunks"], ["inflight", "In-flight chunks per path", "chunks"],
    ["rtt", "RTT per path (band = min to max)", "ms"], ["retx", "Cumulative retransmissions", "chunks"], ["share", "Byte share per path", "% of bytes"]];
  const svgs = {}, cells = defs.map(([id, title]) => { svgs[id] = sv("svg", { class: "chart", role: "img", "aria-label": title, id: "graph-" + id }); return MP.h("div", { class: "graph", "data-graph": id }, MP.h("h3", {}, title), svgs[id]); });
  const grid = MP.h("div", { class: "graphs" }, cells);
  const pathSeries = (map, fn) => Object.keys(map).sort((a, b) => a - b).map((id) => ({ path: id, label: "path " + id, pts: fn ? fn(map[id]) : map[id], color: MP.PATH_COLORS[id % 8], dash: MP.PATH_DASH[id % 8] }));
  let last = null, timer = null, lastDraw = 0;
  const share = (svg, s) => {
    const ids = Object.keys(s.paths).sort((a, b) => a - b), sum = ids.reduce((a, i) => a + s.paths[i].bytes, 0), W = Math.max(280, Math.round(svg.getBoundingClientRect().width) || 640);
    const H2 = sum ? Math.min(HT, 30 + ids.length * 34) : HT; // bar chart needs less height than the line charts
    svg.setAttribute("viewBox", `0 0 ${W} ${H2}`); svg.setAttribute("height", H2); svg.style.height = H2 + "px"; svg.dataset.state = sum ? "ready" : "empty";
    if (!sum) { svg.replaceChildren(sv("text", { x: W / 2, y: HT / 2, "text-anchor": "middle", class: "empty" }, "Waiting for data")); return; }
    const row = 34, k = [];
    ids.forEach((i, n) => { const b = s.paths[i].bytes, w = ((W - 190) * b) / sum, y = 12 + n * row;
      k.push(sv("text", { x: 4, y: y + row / 2 + 1, class: "dlabel", style: "fill:" + MP.PATH_COLORS[i % 8] }, "path " + i),
        sv("rect", { x: 56, y, width: Math.max(w, 1), height: row - 8, class: "sharebar", "data-path": i, style: "fill:" + MP.PATH_COLORS[i % 8] }),
        sv("text", { x: 56 + w + 6, y: y + row / 2 + 1, class: "tick" }, (100 * b / sum).toFixed(1) + " %  " + MP.bytes(b))); });
    svg.replaceChildren(...k);
  };
  const draw = () => {
    const s = last; lastDraw = Date.now(); timer = null; if (!s) return;
    const tmax = Math.max(0.05, (s.tEnd || Date.now() / 1000) - (s.t0 || Date.now() / 1000), ...[s.rttSeries, s.inflightSeries, s.series].flatMap((m) => Object.values(m).map((a) => (a.length ? a[a.length - 1][0] : 0))));
    const ser = tmax < 20 && s.doneLog.length ? MP.rateSeries(s, tmax) : s.series, total = {};
    for (const id in ser) for (const [t, v] of ser[id]) total[t.toFixed(4)] = (total[t.toFixed(4)] || 0) + v;
    const tot = Object.entries(total).sort((a, b) => a[0] - b[0]).map(([t, v]) => [+t, v]);
    const m = s.marks, step = (x) => ({ ...x, step: true });
    MP.chart(svgs.throughput, [...pathSeries(ser), { label: "total", pts: tot, color: "var(--text)", dash: "" }], m, tmax, "Mbit/s");
    MP.chart(svgs.chunks, [{ label: "done", pts: s.cum, color: "var(--accent)", dash: "" }].map(step), m, tmax, "chunks done");
    MP.chart(svgs.inflight, pathSeries(s.inflightSeries).map(step), m, tmax, "chunks in flight");
    MP.chart(svgs.rtt, pathSeries(s.rttSeries), m, tmax, "round trip, ms");
    MP.chart(svgs.retx, [{ label: "retx", pts: s.retxSeries, color: "var(--err)", dash: "" }].map(step), m, tmax, "retransmitted chunks");
    share(svgs.share, s);
  };
  // Redraw when a graph gets a real size (view switch, window resize); the whole panel shares one trailing throttle.
  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(draw, 50); }) : null;
  if (ro) cells.forEach((c) => ro.observe(c));
  return { el: MP.panel("Graphs", grid), update(s) { last = s; if (timer) return; timer = setTimeout(draw, Math.max(0, 250 - (Date.now() - lastDraw))); } };
};
