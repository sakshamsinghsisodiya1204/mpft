// Six hand-written SVG graphs on a shared time axis. Paths: fixed colour + dash pattern + direct label at the line end.
const NS = "http://www.w3.org/2000/svg", W = 600, HT = 170, L = 40, R = 548, T = 12, B = 146;
const sv = (tag, a, text) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (text != null) e.textContent = text; return e; };

// series: [{id, label, pts: [[t, v, lo, hi]], color, dash, step}]; marks: [{t, label}]
MP.chart = function (svg, series, marks, tmax, unit) {
  const all = series.flatMap((x) => x.pts.flatMap((p) => [p[1], p[3] ?? 0]));
  const ymax = Math.max(1, ...all) * 1.1, X = (t) => L + ((R - L) * t) / tmax, Y = (v) => B - ((B - T) * v) / ymax, k = [];
  k.push(sv("line", { x1: L, y1: B, x2: R, y2: B, stroke: "#cfcdc4" }), sv("line", { x1: L, y1: T, x2: L, y2: B, stroke: "#cfcdc4" }),
    sv("text", { x: L - 4, y: T + 8, "text-anchor": "end" }, ymax >= 10 ? ymax.toFixed(0) : ymax.toFixed(1)), sv("text", { x: L - 4, y: B, "text-anchor": "end" }, "0"),
    sv("text", { x: R, y: B + 12, "text-anchor": "end" }, tmax.toFixed(0) + " s"), sv("text", { x: L, y: HT - 4 }, unit));
  marks.forEach((m, n) => { const x = X(m.t); k.push(sv("line", { x1: x, y1: T, x2: x, y2: B, stroke: m.label === "recovered" ? "#1b1b1a" : "#a02622", "stroke-dasharray": "3 3", "stroke-width": 1 }),
    sv("text", { x: Math.min(x + 2, R - 40), y: T + 8 + (n % 3) * 9, fill: "#1b1b1a" }, m.label)); });
  series.forEach((x) => {
    if (!x.pts.length) return;
    if (x.pts[0].length > 2) k.push(sv("polygon", { fill: x.color, opacity: 0.15, points: [...x.pts.map((p) => X(p[0]) + "," + Y(p[3])), ...x.pts.slice().reverse().map((p) => X(p[0]) + "," + Y(p[2]))].join(" ") }));
    const pts = x.step ? x.pts.flatMap((p, i) => (i ? [X(p[0]) + "," + Y(x.pts[i - 1][1]), X(p[0]) + "," + Y(p[1])] : [X(p[0]) + "," + Y(p[1])])) : x.pts.map((p) => X(p[0]) + "," + Y(p[1]));
    k.push(sv("polyline", { fill: "none", stroke: x.color, "stroke-width": 1.5, "stroke-dasharray": x.dash, points: pts.join(" ") }));
    const last = x.pts[x.pts.length - 1]; k.push(sv("text", { x: Math.min(X(last[0]) + 3, W - 44), y: Y(last[1]) + 3, fill: x.color, style: "fill:" + x.color }, x.label));
  });
  svg.replaceChildren(...k);
};

MP.panels.graphs = () => {
  const defs = [["a", "Throughput per path and total", "Mbit/s"], ["b", "Chunks done over time", "chunks"], ["c", "In-flight chunks per path", "chunks"], ["d", "RTT per path (band = min to max per second)", "ms"], ["e", "Cumulative retransmissions", "chunks"]];
  const svgs = {}, box = MP.h("div"), share = MP.h("div");
  for (const [id, title, unit] of defs) { const svg = sv("svg", { viewBox: `0 0 ${W} ${HT}`, class: "chart", role: "img", "aria-label": title }); svgs[id] = svg; box.append(MP.h("h2", {}, title), svg); }
  box.append(MP.h("h2", {}, "Byte share per path"), share);
  const pathSeries = (map, fn) => Object.keys(map).sort((a, b) => a - b).map((id) => ({ id, label: "p" + id, pts: fn ? fn(map[id]) : map[id], color: MP.PATH_COLORS[id % 8], dash: MP.PATH_DASH[id % 8] }));
  return { el: MP.panel("Graphs", box), update(s) {
    const ser = s.series, total = {}; for (const id in ser) for (const [t, v] of ser[id]) total[Math.round(t)] = (total[Math.round(t)] || 0) + v;
    const tot = Object.entries(total).sort((a, b) => a[0] - b[0]).map(([t, v]) => [+t, v]);
    const tmax = Math.max(5, (s.tEnd || Date.now() / 1000) - (s.t0 || Date.now() / 1000), ...[ser, s.rttSeries].flatMap((m) => Object.values(m).map((a) => (a.length ? a[a.length - 1][0] : 0))));
    const m = s.marks;
    MP.chart(svgs.a, [...pathSeries(ser), { id: "t", label: "total", pts: tot, color: "#1b1b1a", dash: "" }], m, tmax, "Mbit/s per path and total");
    MP.chart(svgs.b, [{ id: "d", label: "done", pts: s.cum, color: "#1f5f5b", dash: "" }], m, tmax, "chunks done");
    MP.chart(svgs.c, pathSeries(s.inflightSeries).map((x) => ({ ...x, step: true })), m, tmax, "chunks in flight");
    MP.chart(svgs.d, pathSeries(s.rttSeries, (a) => a.map((p) => [p[0], p[1], p[2], p[3]])), m, tmax, "round trip, ms");
    MP.chart(svgs.e, [{ id: "r", label: "retx", pts: s.retxSeries, color: "#a02622", dash: "" }].map((x) => ({ ...x, step: true })), m, tmax, "retransmitted chunks");
    const ids = Object.keys(s.paths).sort((a, b) => a - b), sum = ids.reduce((a, i) => a + s.paths[i].bytes, 0) || 1;
    share.replaceChildren(MP.table(["Path", "Share", "Bytes", "%"], ids.map((i) => { const b = s.paths[i].bytes;
      return [MP.pathLabel(+i), MP.h("div", { class: "bar", style: "min-width:120px" }, MP.h("div", { style: "width:" + (100 * b) / sum + "%;background:" + MP.PATH_COLORS[i % 8] })), MP.bytes(b), (100 * b / sum).toFixed(1)]; }), [2, 3]));
  } };
};
