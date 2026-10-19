"""Renders every page at three widths in both themes. Set MPFT_SHOTS=1 to also save PNGs to docs/screenshots/ (MPFT_SHOTS_DIR overrides)."""
import os

import pytest

from .harness import NODES

SIZES = [(1440, 900), (1024, 768), (390, 844)]
PAGES = ["send", "receive", "transfer", "history", "settings", "about"]
OUT = os.environ.get("MPFT_SHOTS_DIR", "docs/screenshots")
SHOTS = os.environ.get("MPFT_SHOTS") == "1"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width,height", SIZES)
def test_pages_render_without_overflow(world, theme, width, height):
    ctx = world.browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme)
    p = ctx.new_page()
    errors = []
    p.on("console", lambda m: m.type == "error" and errors.append(m.text))
    p.on("pageerror", lambda e: errors.append(str(e)))
    base = f"http://127.0.0.1:{NODES['bob'][0]}/"
    p.goto(base)
    for page in PAGES:
        route = f"transfer/{world.sid}" if page == "transfer" else page
        p.goto(base + "#/" + route)
        p.wait_for_timeout(1200 if page == "transfer" else 400)
        over = p.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert over <= 1, f"{page} overflows horizontally by {over}px at {width}"
        if SHOTS:
            os.makedirs(OUT, exist_ok=True)
            p.screenshot(path=f"{OUT}/ui-{page}-{theme}-{width}.png", full_page=True)
    if SHOTS:  # Send page with a file chosen (chip state)
        p.goto(base + "#/send")
        p.set_input_files("#file", world.orig)
        p.screenshot(path=f"{OUT}/ui-send-file-{theme}-{width}.png", full_page=True)
    assert errors == [], errors
    ctx.close()


def test_overflow_culprits_report(world):
    """Diagnostic: names the widest elements when a page overflows at phone width."""
    ctx = world.browser.new_context(viewport={"width": 390, "height": 844})
    p = ctx.new_page()
    p.goto(f"http://127.0.0.1:{NODES['bob'][0]}/#/transfer/{world.sid}")
    p.wait_for_timeout(1200)
    bad = p.evaluate("""() => [...document.querySelectorAll('#view *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1 && ![...document.querySelectorAll('.table-wrap, .log, pre')].some(w => w !== e && w.contains(e)))
      .slice(0, 5).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right))""")
    assert bad == [], bad
    ctx.close()
