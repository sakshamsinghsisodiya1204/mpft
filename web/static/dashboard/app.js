const $ = (tag, text, cls) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
};

function pathTable(paths) {
  const max = Math.max(1, ...paths.map(p => p.throughput_mbit));
  const table = $("table");
  const head = $("tr");
  ["Path", "State", "Bytes", "Mbit/s", ""].forEach(h => head.append($("th", h)));
  table.append(head);
  paths.forEach(p => {
    const row = $("tr");
    row.append($("td", p.path_id), $("td", p.state, p.state === "down" ? "down" : ""),
      $("td", p.bytes.toLocaleString(), "num"), $("td", p.throughput_mbit.toFixed(1), "num"));
    const bar = $("div"), cell = $("td"), track = $("div", undefined, "bar");
    bar.style.width = (100 * p.throughput_mbit / max) + "%";
    track.append(bar);
    cell.append(track);
    row.append(cell);
    table.append(row);
  });
  return table;
}

function render(sessions) {
  const root = document.getElementById("sessions");
  root.replaceChildren();
  document.getElementById("note").textContent = sessions.length ? "" : "No transfers found in status/.";
  sessions.forEach(s => {
    const sec = $("section", undefined, s.stale ? "stale" : "");
    sec.append($("h2", `${s.role} ${s.file_name}`));
    const age = Math.max(0, Date.now() / 1000 - s.updated_at);
    sec.append($("div", `session ${s.session_id}, ${s.stale ? "ended " + age.toFixed(0) + " s ago" : "active"}`, "meta"));
    const pct = s.total_chunks ? (100 * s.chunks_done / s.total_chunks).toFixed(0) : 100;
    const info = $("div", `chunks ${s.chunks_done}/${s.total_chunks} (${pct}%), retransmissions ${s.retransmissions}, hash `);
    info.append($("span", s.hash_status, s.hash_status));
    sec.append(info, pathTable(s.per_path || []));
    if (s.file_sha256) sec.append($("div", "sha256 " + s.file_sha256, "hash"));
    root.append(sec);
  });
}

async function poll() {
  try {
    render(await (await fetch("/api/status")).json());
  } catch (e) {
    document.getElementById("note").textContent = "Dashboard server unreachable.";
  }
}
poll();
setInterval(poll, 1000);
