// Router: plain links with hash routes. Each view is a function(root, args) that may return a cleanup function.
(function () {
  let cleanup = null;
  const main = document.getElementById("view"), title = document.getElementById("page-title"), root = document.documentElement;
  // theme: no attribute = follow the OS; the toggle stores an explicit choice
  try { const t = localStorage.getItem("mpft-theme"); if (t) root.dataset.theme = t; } catch (e) { /* storage blocked: follow the OS */ }
  const dark = () => (root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = dark() ? "light" : "dark"; root.dataset.theme = next;
    try { localStorage.setItem("mpft-theme", next); } catch (e) { /* ignore */ }
    route(); // canvases read colours when drawn, so rebuild the view
  });
  function route() {
    const [, name = "send", arg] = location.hash.split("/");
    const view = MP.views[name] || MP.views.send;
    if (cleanup) cleanup();
    main.replaceChildren();
    MP.topState("", "");
    main.classList.toggle("narrow", ["send", "receive", "about", "settings"].includes(name));
    document.querySelectorAll(".sidebar nav a").forEach((a) => {
      if (a.getAttribute("href").split("/")[1] === name) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    cleanup = view(main, arg) || null;
    const h = main.querySelector("h1"); // views write their own title; it lives in the top bar
    if (h) { title.textContent = h.textContent; document.title = h.textContent + " - MPFT"; h.remove(); }
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  MP.connect();
  MP.api("/api/info").then((i) => {
    document.getElementById("whoami").textContent = "MPFT / " + i.name;
    const short = document.getElementById("my-id-short"); short.textContent = i.id.length > 18 ? i.id.slice(0, 10) + "..." + i.id.slice(-6) : i.id; short.title = i.id;
  }).catch(() => {});
  route();
})();
