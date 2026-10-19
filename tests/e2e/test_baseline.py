"""Baseline bug report: prints what is broken. Not an assertion test yet."""


def test_report(world):
    for n in ("alice", "bob"):
        r = world.rec[n]
        print(f"\n== {n}: console errors={r.console_errors} failed={r.failed}")
        ev = r.sse()
        kinds = {}
        for e in ev:
            kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
        print("sse", len(ev), kinds)
    for n in ("alice", "bob"):
        p = world.pages[n]
        print(n, p.url, p.evaluate("""() => [...document.querySelectorAll('svg.chart')].map(s => { const b = s.getBoundingClientRect(); return [s.getAttribute('aria-label'), Math.round(b.width), Math.round(b.height), s.querySelectorAll('polyline').length, s.innerHTML.includes('NaN')]; })"""))
        p.screenshot(path=str(world.tmp / f"{n}.png"), full_page=True)
    print("tmp", world.tmp)
    assert True


def test_fresh_load(world):
    p = world.pages["bob"]
    p.reload()
    p.wait_for_timeout(2500)
    print("fresh", p.evaluate("""() => [...document.querySelectorAll('svg.chart')].map(s => [s.querySelectorAll('polyline').length, s.querySelectorAll('polyline')[0]?.getAttribute('points')?.split(' ').length])"""), world.rec["bob"].console_errors)
    p.screenshot(path=str(world.tmp / "bob-fresh.png"), full_page=True)
    print("receive tab:")
    p.goto("http://127.0.0.1:8010/#/receive"); p.wait_for_timeout(800)
    print(p.inner_text("#view")[-400:])
