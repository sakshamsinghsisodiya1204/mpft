import os
import shutil
import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from .harness import NODES, Nodes, Recorder, make_file, send_file


class World:
    pass


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    w = World()
    w.tmp, w.nodes = tmp, Nodes(tmp)
    w.orig = make_file(str(tmp / "payload.bin"), 30 << 20)
    with sync_playwright() as pw:
        w.browser = pw.chromium.launch()
        ctx = {n: w.browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True) for n in NODES}
        w.pages = {n: ctx[n].new_page() for n in NODES}
        w.rec = {n: Recorder(w.pages[n], n) for n in NODES}
        for n, (ui, _, _) in NODES.items():
            w.pages[n].goto(f"http://127.0.0.1:{ui}/#/receive" if n == "bob" else f"http://127.0.0.1:{ui}/#/send")
        bob = w.nodes.info("bob")
        w.bob_id, w.bob_code = bob["id"], bob["code"]
        send_file(w.pages["alice"], w.orig, w.bob_id, w.bob_code)
        w.pages["alice"].wait_for_url("**#/transfer/*", timeout=60000)
        w.sid = w.pages["alice"].url.rsplit("/", 1)[1]
        # wait until the transfer is over on alice's side (session_done event)
        w.pages["alice"].wait_for_function("window.__sse.some(e => e.kind === 'session_done' || e.kind === 'done')", timeout=120000)
        w.pages["alice"].wait_for_timeout(2500)
        w.pages["bob"].goto(f"http://127.0.0.1:{NODES['bob'][0]}/#/transfer/{w.sid}")
        w.pages["bob"].wait_for_timeout(2500)
        yield w
        w.browser.close()
    w.nodes.stop()
