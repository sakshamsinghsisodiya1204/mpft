// Small helpers shared by all views. Everything goes through textContent, never innerHTML with data.
const MP = { views: {} };

MP.h = function (tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
};

MP.bytes = function (n) {
  if (n < 1024) return n + " B";
  const u = ["KiB", "MiB", "GiB", "TiB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return n.toFixed(n < 10 ? 2 : 1) + " " + u[i];
};
MP.secs = function (s) {
  if (s == null || !isFinite(s)) return "-";
  s = Math.round(s);
  return s >= 60 ? Math.floor(s / 60) + "m " + (s % 60) + "s" : s + "s";
};
MP.clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });
MP.when = (t) => new Date(t * 1000).toLocaleString([], { hour12: false });

MP.api = async function (path, opts) {
  let r;
  try { r = await fetch(path, opts); } catch (e) { throw new Error("Cannot reach the local server. Is `python -m mpft web` still running?"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Request failed (" + r.status + ").");
  return body;
};
MP.post = (path, data) => MP.api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });

MP.copy = async function (text, btn) {
  try { await navigator.clipboard.writeText(text); btn.textContent = "Copied"; }
  catch (e) { btn.textContent = "Select and copy"; }
  setTimeout(() => (btn.textContent = btn.dataset.label), 1500);
};
MP.copyButton = (label, getText) => {
  const b = MP.h("button", { type: "button", "data-label": label }, label);
  b.addEventListener("click", () => MP.copy(getText(), b));
  return b;
};
MP.table = function (heads, rows, numCols = []) {
  return MP.h("div", { class: "table-wrap" }, MP.h("table", {},
    MP.h("thead", {}, MP.h("tr", {}, heads.map((t, i) => MP.h("th", { class: numCols.includes(i) ? "num" : "" }, t)))),
    MP.h("tbody", {}, rows.map((r) => MP.h("tr", {}, r.map((c, i) => MP.h("td", { class: numCols.includes(i) ? "num" : "" }, c)))))));
};
