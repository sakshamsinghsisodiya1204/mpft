from .harness import NODES, Recorder, make_file, send_file

ALICE = f"http://127.0.0.1:{NODES['alice'][0]}"
BOB = f"http://127.0.0.1:{NODES['bob'][0]}"


def test_send_page_chip_dropzone_and_remove(world):
    p = world.browser.new_page(viewport={"width": 1440, "height": 900})
    p.goto(ALICE + "/#/send")
    assert p.locator("#dropzone").is_visible() and p.locator("#file-chip").is_hidden()
    p.dispatch_event("#dropzone", "dragover")
    assert "over" in p.get_attribute("#dropzone", "class")
    p.dispatch_event("#dropzone", "dragleave")
    p.set_input_files("#file", world.orig)
    assert p.inner_text("#chip-name") == "payload.bin" and p.inner_text("#chip-size") == "30.0 MiB"
    assert p.locator("#dropzone").is_hidden()
    p.click("#chip-remove")
    assert p.locator("#dropzone").is_visible() and p.locator("#file-chip").is_hidden()
    p.click("button[type=submit]")
    assert "Choose a file" in p.inner_text("#send-error")
    p.close()


def test_theme_toggle_persists(world):
    ctx = world.browser.new_context(color_scheme="light")
    p = ctx.new_page()
    p.goto(ALICE + "/#/send")
    bg_light = p.evaluate("getComputedStyle(document.body).backgroundColor")
    p.click("#theme-toggle")
    assert p.evaluate("document.documentElement.dataset.theme") == "dark"
    assert p.evaluate("getComputedStyle(document.body).backgroundColor") != bg_light
    p.reload()
    assert p.evaluate("document.documentElement.dataset.theme") == "dark"
    ctx.close()


def test_dark_follows_os_preference(world):
    ctx = world.browser.new_context(color_scheme="dark")
    p = ctx.new_page()
    p.goto(ALICE + "/#/send")
    assert p.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(20, 20, 18)"
    ctx.close()


def test_copy_button_confirms_and_keyboard_focus_ring(world):
    ctx = world.browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    p = ctx.new_page()
    p.goto(BOB + "/#/receive")
    p.wait_for_function("document.querySelector('#my-id').textContent.length > 10")
    p.click("text=Copy ID")
    p.wait_for_function("document.querySelector(\"button[data-label='Copy ID']\").textContent === 'Copied'", timeout=1200)
    assert p.evaluate("navigator.clipboard.readText()") == p.inner_text("#my-id")
    p.reload()
    p.keyboard.press("Tab")
    assert p.evaluate("document.activeElement.className") == "skip"
    for _ in range(3):
        p.keyboard.press("Tab")
    assert p.evaluate("document.activeElement.closest('nav') !== null")
    assert p.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
    p.wait_for_function("document.querySelector('#code-expiry').textContent.startsWith('expires in')", timeout=5000)
    ctx.close()


def test_mobile_layout_has_top_nav_and_no_overflow(world):
    ctx = world.browser.new_context(viewport={"width": 390, "height": 844})
    p = ctx.new_page()
    p.goto(BOB + "/#/receive")
    p.wait_for_timeout(500)
    box = p.locator(".sidebar").bounding_box()
    assert box["width"] >= 380 and box["height"] < 200  # collapsed to a top bar
    ctx.close()


def test_accept_click_flow_lands_on_transfer_with_graphs(world):
    """No pairing code: bob must click Accept. Bob's page is open on Receive during the offer."""
    bob, alice = world.pages["bob"], world.pages["alice"]
    bob.goto(BOB + "/#/receive")
    small = make_file(str(world.tmp / "accept.bin"), 20 << 20, seed=5)
    alice.goto(ALICE + "/#/send")
    alice.set_input_files("#file", small)
    alice.fill("#target", world.bob_id)
    alice.evaluate("document.querySelector('details').open = true")
    alice.select_option("#profile", "asymmetric")
    alice.fill("#paths", "2")
    alice.click("button[type=submit]")
    bob.wait_for_selector("#offer-list [data-act=accept]", timeout=30000)
    assert "accept.bin" in bob.inner_text("#offer-list")
    bob.click("#offer-list [data-act=accept]")
    bob.wait_for_function("location.hash.startsWith('#/transfer/')")
    bob.wait_for_selector("#graph-chunks[data-state=ready]", timeout=30000)
    bob.wait_for_function("document.querySelector('#session-download')", timeout=120000)
    assert world.rec["bob"].console_errors == []
