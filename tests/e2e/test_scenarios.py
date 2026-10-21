import os

from .harness import NODES, make_file, send_file

ALICE = f"http://127.0.0.1:{NODES['alice'][0]}"
BOB = f"http://127.0.0.1:{NODES['bob'][0]}"
SHOTS = os.environ.get("MPFT_SHOTS") == "1"


def shot(page, name):
    if SHOTS:
        os.makedirs("docs/screenshots", exist_ok=True)
        page.screenshot(path=f"docs/screenshots/{name}.png", full_page=True)


def run(world, name, mb, profile, paths=3):
    f = make_file(str(world.tmp / name), mb << 20, seed=7)
    sid = send_file(world.pages["alice"], f, world.bob_id, world.nodes.info("bob")["code"], profile=profile, paths=paths)
    world.pages["alice"].wait_for_function("document.querySelector('#hero.ok, #hero.bad')", timeout=120000)
    return sid


def test_sender_and_receiver_see_different_pages(world):
    a, b = world.pages["alice"], world.pages["bob"]
    a.goto(ALICE + f"/#/transfer/{world.sid}")
    b.goto(BOB + f"/#/transfer/{world.sid}")
    a.wait_for_selector("#hero.sender.ok", timeout=15000)
    b.wait_for_selector("#hero.receiver.ok", timeout=15000)
    a.wait_for_function("document.getElementById('page-title').textContent.startsWith('Sending')")
    b.wait_for_function("document.getElementById('page-title').textContent.startsWith('Receiving')")
    assert "Delivered" in a.inner_text("#hero") and "Saved and verified" in b.inner_text("#hero")
    assert a.inner_text("#page-title").startswith("Sending") and b.inner_text("#page-title").startswith("Receiving")
    assert a.locator("#session-download").count() == 0 and b.locator("#session-download").count() == 1
    shot(a, "scn-sender-success"), shot(b, "scn-receiver-success")
    first = lambda p: p.evaluate("[...document.querySelectorAll('.grid12 > .panel')].sort((x, y) => x.style.order - y.style.order).slice(0, 2).map(e => e.className.includes('strip-panel') ? 'strip' : e.querySelector('h2').textContent)")
    assert first(a)[1] != first(b)[1]  # receiver leads with verification, sender with progress summary


def test_short_transfer_uses_millisecond_axis_with_real_curve(world):
    sid = run(world, "tiny.bin", 2, "none", paths=2)
    a = world.pages["alice"]
    a.wait_for_selector("#graph-throughput[data-state=ready]")
    a.wait_for_timeout(600)
    xs = a.evaluate("[...document.querySelectorAll('#graph-throughput text.tick')].map(t => +t.getAttribute('x'))")
    assert max(xs) < 400, xs  # tick labels stay inside the plot
    shot(a, "scn-short-transfer")
    assert "(ms)" in a.text_content("#graph-throughput"), sid
    assert int(a.evaluate("document.querySelector('#graph-throughput polyline.series').dataset.n")) >= 5


def test_clean_wan_scenario_succeeds_and_total_failure_fails(world):
    run(world, "wan.bin", 4, "wan", paths=3)
    assert world.pages["alice"].locator("#hero.ok").count() == 1
    shot(world.pages["alice"], "scn-wan-sender")
    sid = run(world, "doomed2.bin", 8, "total_failure", paths=3)
    a, b = world.pages["alice"], world.pages["bob"]
    assert "Not delivered" in a.inner_text("#hero")
    shot(a, "scn-failure-sender")
    b.goto(BOB + "/#/receive")
    b.wait_for_function("document.querySelector('#received-files tbody tr td') && document.body.innerText.includes('doomed2.bin')", timeout=60000)
    assert "not saved" in b.inner_text("#received-files").lower()
    b.goto(BOB + f"/#/transfer/{sid}")
    b.wait_for_selector("#hero.receiver.bad", timeout=15000)
    assert "Nothing was saved" in b.inner_text("#hero")
    shot(b, "scn-failure-receiver")
    a.goto(ALICE + "/#/send")
    shot(a, "scn-send-scenarios")
