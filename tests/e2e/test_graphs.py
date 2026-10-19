import math
import re

GRAPHS = ["throughput", "chunks", "inflight", "rtt", "retx", "share"]
JS = """(g) => { const svg = document.querySelector('#graph-' + g); const b = svg.getBoundingClientRect();
  return { w: b.width, h: b.height, state: svg.dataset.state, text: svg.textContent,
    series: [...svg.querySelectorAll('polyline.series')].map(p => ({path: p.dataset.path, n: +p.dataset.n, pts: p.getAttribute('points')})),
    bars: svg.querySelectorAll('rect.sharebar').length, marks: [...svg.querySelectorAll('line.mark')].map(l => l.dataset.label),
    nan: svg.innerHTML.includes('NaN') || svg.innerHTML.includes('undefined') }; }"""


def check(page, world):
    base = page.url.split("#")[0]
    page.goto(base + "#/receive")  # force a fresh view build for the session
    page.goto(base + f"#/transfer/{world.sid}")
    page.wait_for_selector("#graph-throughput[data-state=ready]", timeout=10000)
    page.wait_for_timeout(600)
    for g in GRAPHS:
        d = page.evaluate(JS, g)
        assert d["w"] > 200 and d["h"] > 60, (g, d["w"], d["h"])
        assert d["state"] == "ready", (g, d["state"], d["text"])
        assert not d["nan"], g
        for s in d["series"]:
            assert not re.search(r"NaN|undefined", s["pts"]), g
            assert s["n"] >= 2 or g == "retx", (g, s["path"], s["n"])
        if g == "share":
            assert d["bars"] == 2, d
        elif g in ("throughput", "inflight", "rtt"):
            assert {s["path"] for s in d["series"] if s["path"] != ""} == {"0", "1"}, (g, d["series"])
        if g in ("throughput", "chunks", "inflight", "rtt", "retx"):
            labels = " ".join(d["marks"])
            assert "path 1 down" in labels and "requeued" in labels and "recovered" in labels, (g, d["marks"])


def test_graphs_alice_live_view(world):
    check(world.pages["alice"], world)


def test_graphs_bob_receiver_sees_sender_events(world):
    check(world.pages["bob"], world)


def test_graphs_after_fresh_load_replay(world):
    p = world.pages["bob"]
    p.reload()
    check(p, world)
    p.locator(".graphs").screenshot(path="docs/screenshots/graphs-bob.png")


def test_no_console_errors(world):
    for n in ("alice", "bob"):
        assert world.rec[n].console_errors == [], world.rec[n].console_errors
        assert world.rec[n].failed == [], world.rec[n].failed


def test_graphs_open_mid_transfer_and_update_live(world):
    from .harness import NODES, Recorder, send_file
    sid = send_file(world.pages["alice"], world.orig, world.bob_id, world.nodes.info("bob")["code"], profile="asymmetric", paths=2)
    late = world.browser.new_page(viewport={"width": 1440, "height": 900})
    rec = Recorder(late, "late")
    late.goto(f"http://127.0.0.1:{NODES['bob'][0]}/#/transfer/{sid}")
    late.wait_for_selector("#graph-chunks[data-state=ready]", timeout=30000)
    n1 = late.evaluate("document.querySelector('#graph-chunks polyline').dataset.n")
    late.wait_for_timeout(3000)
    n2 = late.evaluate("document.querySelector('#graph-chunks polyline').dataset.n")
    assert int(n2) > int(n1), (n1, n2)  # graph redraws as events arrive
    late.wait_for_function("window.__sse.some(e => String(e.session) === '%s' && e.kind === 'session_done')" % sid, timeout=120000)
    late.wait_for_timeout(800)
    assert rec.console_errors == []
    late.close()
