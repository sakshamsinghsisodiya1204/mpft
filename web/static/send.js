MP.views.send = function (root) {
  let file = null, busy = false;
  const info = MP.api("/api/info");
  const name = MP.h("span", { class: "muted" }, "No file chosen");
  const input = MP.h("input", { type: "file", id: "file" });
  const drop = MP.h("div", { class: "drop" }, MP.h("label", { for: "file", style: "margin:0" }, "File"),
    MP.h("p", { class: "muted" }, "Drop a file here or choose one."), input, MP.h("p", {}, name));
  const pick = (f) => { file = f; name.textContent = f ? f.name + " (" + MP.bytes(f.size) + ")" : "No file chosen"; };
  input.addEventListener("change", () => pick(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); });

  const kind = (v, label, on) => MP.h("label", {}, MP.h("input", { type: "radio", name: "kind", value: v, checked: on }), " " + label);
  const target = MP.h("input", { type: "text", id: "target", autocomplete: "off", spellcheck: "false", class: "mono" });
  const pcode = MP.h("input", { type: "text", id: "pcode", autocomplete: "off", spellcheck: "false", maxlength: 12, class: "mono", style: "max-width:12em" });
  const paths = MP.h("input", { type: "number", id: "paths", min: 1, max: 8, value: 4 });
  const chunk = MP.h("select", { id: "chunk" }, [["64 KiB", 65536], ["256 KiB", 262144], ["1 MiB", 1048576], ["4 MiB", 4194304]]
    .map(([t, v]) => MP.h("option", { value: v, selected: v === 1048576 }, t)));
  const profile = MP.h("select", { id: "profile" });
  info.then((i) => i.profiles.forEach((p) => profile.append(MP.h("option", { value: p },
    { none: "None", asymmetric: "Asymmetric", lossy: "Lossy", path_failure: "Path failure mid-transfer" }[p]))));
  const addr = MP.h("select", { id: "addr" }, [["auto", "Automatic (all addresses in the ID)"], ["tailscale", "Tailscale only"], ["lan", "LAN only"]]
    .map(([v, t]) => MP.h("option", { value: v }, t)));
  const msg = MP.h("p", { role: "alert", class: "err" });
  const prog = MP.h("progress", { max: 100, value: 0, hidden: true });
  const btn = MP.h("button", { type: "submit", class: "primary" }, "Send");
  const result = MP.h("div"), test = MP.h("button", { type: "button", id: "test-conn" }, "Test connection");
  test.onclick = async () => {
    result.replaceChildren(MP.h("p", { class: "muted" }, "Testing..."));
    try {
      const r = await MP.post("/api/test-connection", { kind: form.kind.value, value: target.value.trim(), addr_mode: addr.value, code: form.kind.value === "id" ? pcode.value.trim() || null : null });
      result.replaceChildren(r.error ? MP.h("p", { class: "err" }, r.error) : MP.table(["Address", "Result", "ms", "Detail"], r.results.map((x) =>
        [x.host + ":" + r.port, x.ok ? "reachable" : "unreachable", x.ok ? x.ms : "-", x.ok ? "peer " + x.name : x.reason]), [2]));
    } catch (e) { result.replaceChildren(MP.h("p", { class: "err" }, e.message)); }
  };
  const hint = () => (target.placeholder = form.kind.value === "id" ? "ABCD-EFGH-JKLM-..." : "6-character code");

  const form = MP.h("form", {}, drop,
    MP.h("label", {}, "Send to"),
    MP.h("div", { class: "opts" }, kind("id", "Receiver ID", true), kind("code", "Code", false)),
    MP.h("div", { class: "row", style: "margin-top:8px" }, target, test), result,
    MP.h("label", { for: "pcode" }, "Pairing code (optional, skips the Accept click)"), pcode,
    MP.h("details", {}, MP.h("summary", {}, "Advanced"),
      MP.h("label", { for: "paths" }, "Paths (1 to 8)"), paths,
      MP.h("label", { for: "chunk" }, "Chunk size"), chunk,
      MP.h("label", { for: "addr" }, "Receiver address"), addr,
      MP.h("label", { for: "profile" }, "Network conditions"), profile),
    MP.h("p", {}, btn), prog, msg);
  form.addEventListener("change", hint);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "";
    if (busy) return;
    if (!file) { msg.textContent = "Choose a file first."; return; }
    if (!target.value.trim()) { msg.textContent = "Enter the receiver's ID or code."; return; }
    busy = true; btn.disabled = true; prog.hidden = false;
    try {
      const up = await MP.upload(file, (p) => (prog.value = p));
      const r = await MP.post("/api/send", { upload_id: up.upload_id, kind: form.kind.value, value: target.value.trim(),
        paths: +paths.value, chunk_size: +chunk.value, profile: profile.value, addr_mode: addr.value, code: form.kind.value === "id" ? pcode.value.trim() || null : null });
      location.hash = "#/transfer/" + r.session;
    } catch (err) { msg.textContent = err.message; }
    busy = false; btn.disabled = false; prog.hidden = true;
  });
  hint();
  root.append(MP.h("h1", {}, "Send a file"), form);
};

// XHR instead of fetch so the browser reports upload progress; the body streams from disk.
MP.upload = (file, onProgress) => new Promise((resolve, reject) => {
  const x = new XMLHttpRequest();
  x.open("POST", "/api/upload?name=" + encodeURIComponent(file.name));
  x.upload.onprogress = (e) => e.lengthComputable && onProgress((100 * e.loaded) / e.total);
  x.onload = () => {
    let b = {};
    try { b = JSON.parse(x.responseText); } catch (e) { /* keep empty */ }
    x.status === 200 ? resolve(b) : reject(new Error(typeof b.detail === "string" ? b.detail : "Upload failed (" + x.status + ")."));
  };
  x.onerror = () => reject(new Error("Upload failed. Is the local server still running?"));
  x.send(file);
});
