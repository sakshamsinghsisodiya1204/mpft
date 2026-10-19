MP.views.history = function (root) {
  const body = MP.h("div"), err = MP.h("p", { class: "err", role: "alert" });
  MP.api("/api/history").then((rows) => {
    body.replaceChildren(rows.length ? MP.table(["Time", "Direction", "File", "Size", "Peer", "Result", "Seconds", "Mbit/s", "Retransmits", "SHA-256"],
      rows.slice().reverse().map((r) => [MP.when(r.time), r.direction, r.session != null ? MP.h("a", { href: "#/transfer/" + r.session, title: "Replay this transfer" }, r.name) : r.name, MP.bytes(r.size), r.peer, r.result, r.seconds ?? "-", r.goodput_mbit ?? "-", r.retransmits ?? "-",
        MP.h("span", { class: "hash mono" }, (r.sha256 || "").slice(0, 16)) ]), [3, 6, 7, 8]) : MP.h("p", { class: "muted" }, "No transfers yet."));
  }).catch((e) => (err.textContent = e.message));
  root.append(MP.h("h1", {}, "History"), MP.h("p", {}, MP.h("a", { href: "/api/history.csv", download: "mpft-history.csv" }, "Export as CSV")), err, body);
};
