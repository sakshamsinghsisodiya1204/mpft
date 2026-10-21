// Role-aware banner: the same session reads differently for the side that sends and the side that receives.
const HH = MP.h;
MP.panels.hero = () => {
  const el = HH("section", { class: "panel hero", id: "hero", "aria-label": "Transfer outcome" });
  let shown = "";
  return { el, update(s, m) {
    const role = m.role || s.role || "sender", el_ = s.t0 ? (s.tEnd || Date.now() / 1000) - s.t0 : 0, avg = el_ > 0 ? (s.bytes * 8) / 1e6 / el_ : 0;
    const peer = (role === "sender" ? m.peer_name : m.sender) || "the other side", fl = m.file;
    const sc = (MP.scenarios && MP.scenarios[m.profile] && MP.scenarios[m.profile].label) || null;
    const key = JSON.stringify([role, s.phase, s.ended, s.success, s.name, peer, fl && fl.id, fl && fl.status, s.retx, s.message, Math.round(el_ * 10)]);
    if (key === shown) return; shown = key;
    el.classList.remove("sender", "receiver", "ok", "bad"); el.classList.add(role); if (s.ended) el.classList.add(s.success ? "ok" : "bad");
    const facts = [["Time", MP.secs(el_)], ["Goodput", avg.toFixed(1) + " Mbit/s"], ["Paths used", Object.values(s.paths).filter((p) => p.bytes).length + " of " + Object.keys(s.paths).length],
      ["Retransmitted chunks", String(s.retx)]];
    if (role === "sender" && sc) facts.push(["Scenario", sc]);
    let head, body, acts = [];
    if (role === "sender") {
      head = "Sending";
      if (!s.ended) body = ["Sending " + (s.name || "file") + " to " + peer, s.message || "Chunks are being pulled from one shared queue by every path."];
      else if (s.success) { body = ["Delivered to " + peer, "The receiver confirmed the whole-file SHA-256 and acknowledged completion (DONE)."]; acts = [HH("a", { class: "btn primary", href: "#/send" }, "Send another file")]; }
      else { body = ["Not delivered", s.message || "The transfer failed; the receiver kept no partial file as a finished download."]; acts = [HH("a", { class: "btn primary", href: "#/send" }, "Try again")]; }
    } else {
      head = "Receiving";
      if (!s.ended) body = ["Receiving " + (s.name || "file") + " from " + peer, "Each chunk is checked against its SHA-256 before it is written; damaged chunks are rejected."];
      else if (s.success && fl && fl.status === "ok") { body = ["Saved and verified", "Whole-file SHA-256 matched the sender's manifest. The file is ready."];
        acts = [HH("a", { class: "btn primary", id: "session-download", href: "/api/files/" + fl.id + "/download", download: fl.name }, "Download " + fl.name)]; }
      else if (s.success) body = ["Saved and verified", "Finalising the file..."];
      else { body = ["Nothing was saved", (fl && fl.error) || s.message || "The transfer failed before every chunk arrived."]; acts = [HH("span", { class: "err", id: "session-failed" }, "No file to download")]; }
    }
    el.replaceChildren(HH("h2", {}, head + (s.name ? " " + s.name : "")),
      HH("div", { class: "hero-body" }, HH("div", {}, HH("p", { class: "hero-title" }, body[0]), HH("p", { class: "muted" }, body[1])), HH("div", { class: "row" }, ...acts)),
      HH("dl", { class: "facts" }, facts.map(([k, v]) => HH("div", {}, HH("dt", {}, k), HH("dd", {}, v)))));
  } };
};
