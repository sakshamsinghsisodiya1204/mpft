// One EventSource for the page. Raw events are kept per session; views subscribe to what they need.
MP.events = { bySession: {}, listeners: [], all: [] };

MP.on = function (fn) {
  MP.events.listeners.push(fn);
  return () => (MP.events.listeners = MP.events.listeners.filter((f) => f !== fn));
};

MP.connect = function () {
  const es = new EventSource("/api/events");
  es.onmessage = (m) => {
    const e = JSON.parse(m.data);
    if (e.session != null) (MP.events.bySession[e.session] ||= []).push(e);
    MP.events.all.push(e);
    if (MP.events.all.length > 2000) MP.events.all.splice(0, 500);
    for (const fn of MP.events.listeners.slice()) fn(e);
  };
  const conn = (ok) => { const c = document.getElementById("conn"); if (c) { c.className = "badge " + (ok ? "ok" : "warn"); c.textContent = ok ? "Connected" : "Reconnecting"; } };
  es.onopen = () => conn(true);
  es.onerror = () => conn(false); // EventSource reconnects by itself and resends Last-Event-ID
};
