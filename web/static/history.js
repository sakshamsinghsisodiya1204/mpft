MP.views.history = function (root) {
  const body = MP.h("div"), err = MP.h("p", { class: "err", role: "alert" });
  MP.api("/api/history").then((rows) => {
    body.replaceChildren(rows.length ? MP.table(["Time", "Dir", "File", "Size", "Peer", "Paths", "Duration s", "Mbit/s", "Retx", "Incidents", "Result", "Open"],
      rows.slice().reverse().map((r) => [MP.when(r.time), r.direction, r.name, MP.bytes(r.size), r.peer, r.paths ?? "-", r.seconds ?? "-", r.goodput_mbit ?? "-", r.retransmits ?? "-", r.incidents ?? "-",
        MP.h("span", { class: /^failed/.test(r.result) ? "err" : "" }, r.result),
        r.session != null ? MP.h("span", { class: "row" }, MP.h("a", { href: "#/replay/" + r.session }, "Replay"), MP.h("a", { href: "/api/session/" + r.session + "/events?download=1", download: "" }, "JSON")) : "-"]), [3, 5, 6, 7, 8, 9]) : MP.h("p", { class: "muted" }, "No transfers yet."));
  }).catch((e) => (err.textContent = e.message));
  root.append(MP.h("h1", {}, "History"), MP.h("p", {}, MP.h("a", { href: "/api/history.csv", download: "mpft-history.csv" }, "Export table as CSV")), err, body);
};
