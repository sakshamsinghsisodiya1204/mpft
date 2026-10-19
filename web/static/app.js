// Router: plain links with hash routes. Each view is a function(root, args) that may return a cleanup function.
(function () {
  let cleanup = null;
  const main = document.getElementById("view");
  function route() {
    const [, name = "send", arg] = location.hash.split("/");
    const view = MP.views[name] || MP.views.send;
    if (cleanup) cleanup();
    main.replaceChildren();
    main.classList.toggle("wide", name === "transfer");
    document.querySelectorAll("nav a").forEach((a) => {
      if (a.getAttribute("href").split("/")[1] === name) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    cleanup = view(main, arg) || null;
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  MP.connect();
  MP.api("/api/info").then((i) => (document.getElementById("whoami").textContent = "MPFT / " + i.name)).catch(() => {});
  route();
})();
