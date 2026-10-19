// Replay: re-runs the persisted two-sided event log of a past transfer through the same reducer and panels.
MP.views.replay = function (root, sid) {
  const meta = { loaded: true, replay: true, role: "receiver" };
  const evs = [], ctl = MP.h("div", { class: "filters" }), msg = MP.h("p", { class: "err", role: "alert" });
  let s = MP.newState(+sid), pos = 0, speed = 1, playing = false, timer = null, vt = 0, ui = null, t0 = 0;
  const range = MP.h("input", { type: "range", min: 0, max: 1000, value: 0, "aria-label": "Scrub", style: "flex:1;min-width:160px" });
  const play = MP.h("button", { type: "button", class: "primary" }, "Play"), clock = MP.h("span", { class: "mono" }, "0.0 / 0.0 s");
  const sp = MP.h("select", { "aria-label": "Speed" }, [1, 4, 16].map((v) => MP.h("option", { value: v }, v + "x")));
  const dur = () => (evs.length ? evs[evs.length - 1].t - t0 : 0);
  const seek = (target) => { // virtual time in seconds since the first event; going back re-reduces from the start
    if (target < vt) { s = MP.newState(+sid); pos = 0; }
    vt = target;
    while (pos < evs.length && evs[pos].t - t0 <= vt) MP.reduce(s, evs[pos++]);
    if (pos >= evs.length && !s.ended) s.ended = true;
    s.dirty = new Set(Array.from({ length: s.total || 0 }, (_, i) => i));
    ui.draw(s); clock.textContent = vt.toFixed(1) + " / " + dur().toFixed(1) + " s"; range.value = dur() ? (1000 * vt) / dur() : 0;
  };
  const tick = () => { if (!playing) return; seek(Math.min(dur(), vt + 0.1 * speed)); if (vt >= dur()) stop(); };
  const stop = () => { playing = false; play.textContent = "Play"; };
  play.onclick = () => { if (playing) return stop(); if (vt >= dur()) seek(0); playing = true; play.textContent = "Pause"; };
  sp.onchange = () => (speed = +sp.value);
  range.oninput = () => { stop(); seek((range.value / 1000) * dur()); };
  ctl.append(play, sp, range, clock, MP.h("a", { href: "/api/session/" + sid + "/events?download=1", download: "mpft-session-" + sid + ".json" }, "Export events (JSON)"));
  root.append(MP.h("h1", {}, "Replay " + sid), msg);
  ui = MP.buildTransfer(root, s, meta, [MP.h("div", { class: "panel" }, ctl)]);
  Promise.all([MP.api("/api/session/" + sid + "/events"), MP.api("/api/session/" + sid).catch(() => ({}))]).then(([list, m]) => {
    Object.assign(meta, m, { replay: true }); evs.push(...list); t0 = evs.length ? evs[0].t : 0; seek(dur());
  }).catch((e) => (msg.textContent = e.message));
  timer = setInterval(tick, 100);
  return () => clearInterval(timer);
};
