MP.views.receive = function (root) {
  const idBox = MP.h("div", { class: "bigid", id: "my-id" });
  const codeBox = MP.h("span", { class: "code-big", id: "my-code" });
  const codeNote = MP.h("span", { class: "muted", id: "code-expiry" });
  const status = MP.h("p", {});
  const rvInput = MP.h("input", { type: "url", id: "rv", placeholder: "http://192.168.1.10:9100" });
  const rvMsg = MP.h("p", { class: "muted" });
  const offers = MP.h("div"), files = MP.h("div", { class: "files-wrap" }), err = MP.h("p", { class: "err", role: "alert" });
  let info = null, timer = null;

  const showInfo = (i) => {
    info = i;
    idBox.textContent = i.id;
    codeBox.textContent = i.code;
    status.textContent = "Listening on port " + i.peer_port + " as " + i.name + " (" + (i.hosts || [i.host]).join(" + ") + "). Max file size " + MP.bytes(i.max_size) + ".";
    rvInput.value = i.rendezvous || "";
    rvMsg.textContent = "Rendezvous: " + i.rv_status; tick();
  };
  const tick = () => {
    if (!info) return;
    const left = Math.max(0, Math.round(info.code_expires - Date.now() / 1000));
    codeNote.textContent = left ? "expires in " + MP.secs(left) : "expired, press New code"; codeNote.className = left && left < 30 ? "badge warn" : left ? "muted" : "badge bad";
  };
  const drawOffers = async () => {
    const list = await MP.api("/api/offers");
    offers.replaceChildren(list.length ? MP.h("ul", { class: "list", id: "offer-list" }, list.map((o) => MP.h("li", {},
      MP.h("div", { class: "grow" }, MP.h("strong", {}, o.file_name), MP.h("div", { class: "muted" }, MP.bytes(o.size) + " from " + o.sender),
        MP.h("div", { class: "hash mono muted" }, o.sha256.slice(0, 24) + "...")),
      MP.h("span", { class: "row" }, MP.h("button", { class: "primary", "data-act": "accept", onclick: () => decide(o, "accept") }, "Accept"),
        MP.h("button", { "data-act": "decline", onclick: () => decide(o, "decline") }, "Decline")))))
      : MP.empty("No incoming offers", "When someone sends you a file with your ID, it appears here for you to accept."));
  };
  const decide = async (o, action) => {
    err.textContent = "";
    try {
      await MP.post("/api/offers/" + o.id + "/" + action);
      if (action === "accept") location.hash = "#/transfer/" + o.session_id;
      else drawOffers();
    } catch (e) { err.textContent = e.message; drawOffers(); }
  };
  const drawFiles = async () => {
    const list = await MP.api("/api/files");
    const del = (f) => MP.h("button", { type: "button", class: "danger", "data-act": "delete", "aria-label": "Delete " + f.name, onclick: async () => {
      if (!confirm("Delete " + f.name + " from this Mac?")) return;
      await MP.api("/api/files/" + f.id, { method: "DELETE" }).catch((e) => (err.textContent = e.message)); drawFiles(); } }, "Delete");
    const row = (f) => f.status === "ok"
      ? [f.name, MP.bytes(f.size), MP.h("span", { class: "hash mono" }, f.sha256), MP.when(f.time), MP.h("span", { class: "badge ok" }, "verified"),
        MP.h("span", { class: "row" }, MP.h("a", { class: "btn", "data-act": "download", href: "/api/files/" + f.id + "/download", download: f.name }, "Download"), del(f))]
      : [f.name, MP.bytes(f.size), MP.h("span", { class: "hash mono" }, f.sha256), MP.when(f.time), MP.h("span", { class: "badge bad" }, "failed"),
        MP.h("span", { class: "row" }, MP.h("span", { class: "err" }, f.error || "Not saved."), del(f))];
    files.replaceChildren(list.length ? MP.table(["Name", "Size", "SHA-256", "Received", "Verified", ""], list.slice().reverse().map(row), [1])
      : MP.empty("No files received yet", "Verified files you accept are listed here with a Download button."));
    files.firstChild.id = "received-files";
  };
  const refresh = () => MP.api("/api/info").then(showInfo).catch((e) => (err.textContent = e.message));

  const panel = (t, ...k) => MP.h("section", { class: "panel" }, MP.h("h2", {}, t), ...k);
  root.append(MP.h("h1", {}, "Receive"),
    MP.h("div", { class: "stack" },
      panel("My Receiver ID", idBox, MP.h("div", { class: "row" }, MP.copyButton("Copy ID", () => idBox.textContent)), status),
      panel("Pairing code", MP.h("p", {}, codeBox, " ", codeNote),
        MP.h("div", { class: "row" }, MP.h("button", { onclick: () => MP.post("/api/code/new").then(showInfo) }, "New code"), MP.copyButton("Copy code", () => codeBox.textContent)),
        MP.h("p", { class: "muted" }, "A sender who enters this code is accepted without a click. Single use."), rvMsg,
        MP.h("details", {}, MP.h("summary", {}, "Settings"), MP.h("label", { for: "rv" }, "Rendezvous URL"), rvInput,
          MP.h("p", {}, MP.h("button", { onclick: () => MP.post("/api/settings", { rendezvous: rvInput.value }).then(showInfo).catch((e) => (err.textContent = e.message)) }, "Save")))),
      err, panel("Incoming offers", offers), panel("Received files", files)));
  refresh(); drawOffers(); drawFiles();
  timer = setInterval(tick, 1000);
  const off = MP.on((e) => {
    if (e.kind === "offer_received" || e.kind === "offer_resolved") drawOffers();
    if (e.kind === "file_received") drawFiles();
    if (e.kind === "code_changed") refresh();
  });
  return () => { clearInterval(timer); off(); };
};
