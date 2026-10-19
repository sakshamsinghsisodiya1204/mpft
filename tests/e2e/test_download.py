import time
from urllib.request import urlopen

from .harness import NODES, make_file, send_file, sha256_file

BOB = f"http://127.0.0.1:{NODES['bob'][0]}"


def wait_rows(page, n, timeout=60000):
    page.wait_for_function(f"document.querySelectorAll('#received-files tbody tr').length >= {n}", timeout=timeout)


def test_receive_page_download_matches_original(world):
    p = world.pages["bob"]
    p.goto(BOB + "/#/receive")
    wait_rows(p, 1)
    row = p.locator("#received-files tbody tr").first
    assert "payload.bin" in row.inner_text() and "verified" in row.inner_text()
    with p.expect_download() as d:
        row.locator("a[data-act=download]").click()
    path = world.tmp / "dl1.bin"
    d.value.save_as(str(path))
    assert d.value.suggested_filename == "payload.bin"
    assert sha256_file(str(path)) == sha256_file(world.orig)
    assert world.sha if hasattr(world, "sha") else True


def test_transfer_page_has_download_on_receiver(world):
    p = world.pages["bob"]
    p.goto(BOB + f"/#/transfer/{world.sid}")
    p.wait_for_selector("#session-download", timeout=10000)
    with p.expect_download() as d:
        p.click("#session-download")
    path = world.tmp / "dl2.bin"
    d.value.save_as(str(path))
    assert sha256_file(str(path)) == sha256_file(world.orig)
    world.pages["alice"].goto(f"http://127.0.0.1:{NODES['alice'][0]}/#/transfer/{world.sid}")
    world.pages["alice"].wait_for_selector("#view .panel", timeout=10000)
    assert world.pages["alice"].locator("#session-download").count() == 0  # sender side offers no download


def test_second_transfer_same_name_gets_suffix_and_table_refreshes_live(world):
    bob, alice = world.pages["bob"], world.pages["alice"]
    bob.goto(BOB + "/#/receive")
    wait_rows(bob, 1)
    send_file(alice, world.orig, world.bob_id, world.nodes.info("bob")["code"], profile="none")
    wait_rows(bob, 2)  # no reload: refreshed by the file_received event
    names = bob.locator("#received-files tbody tr td:first-child").all_inner_texts()
    assert sorted(names) == ["payload (1).bin", "payload.bin"], names
    import os
    assert sorted(f for f in os.listdir(world.nodes.out["bob"]) if f.endswith(".bin")) == ["payload (1).bin", "payload.bin"]
    assert sha256_file(os.path.join(world.nodes.out["bob"], "payload.bin")) == sha256_file(world.orig)


def test_failed_transfer_has_no_download_and_clear_message(world):
    bob, alice = world.pages["bob"], world.pages["alice"]
    small = make_file(str(world.tmp / "doomed.bin"), 40 << 20, seed=3)
    bob.goto(BOB + "/#/receive")
    wait_rows(bob, 1)
    n0 = bob.locator("#received-files tbody tr").count()
    sid = send_file(alice, small, world.bob_id, world.nodes.info("bob")["code"], profile="lossy", paths=1)
    assert sid != world.sid
    alice.wait_for_function("(sid) => window.__sse.some(e => String(e.session) === sid && e.kind === 'chunk_state' && e.state === 'done')", arg=sid, timeout=30000)
    r = alice.request.post(f"http://127.0.0.1:{NODES['alice'][0]}/api/session/{sid}/net/kill/0", data="{}", headers={"Content-Type": "application/json"})
    assert r.ok, (sid, r.text(), [(e['kind'], e.get('state'), e.get('message')) for e in alice.evaluate('window.__sse') if e['kind'] in ('send_state','offer_declined')][-6:])
    wait_rows(bob, n0 + 1, timeout=120000)
    row = bob.locator("#received-files tbody tr").first
    text = row.inner_text()
    assert "doomed.bin" in text and "failed" in text and "not saved" in text.lower()
    assert row.locator("a[data-act=download]").count() == 0
    bob.goto(BOB + f"/#/transfer/{sid}")
    bob.wait_for_selector("#session-failed", timeout=10000)
    assert bob.locator("#session-download").count() == 0
    assert not any(f.startswith("doomed") for f in __import__("os").listdir(world.nodes.out["bob"]))
