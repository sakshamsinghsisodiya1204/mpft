"""Screenshot the web UI with headless Chrome: python scripts/ui_shots.py http://127.0.0.1:8000 SESSION_ID
The page keeps an SSE stream open, so Chrome is killed once the PNG exists."""
import os
import subprocess
import sys
import time

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def shot(url, out, size):
    if os.path.exists(out):
        os.remove(out)
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--timeout=6000", "--run-all-compositor-stages-before-draw",
                          f"--window-size={size}", f"--screenshot={out}", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.time() + 40
    while time.time() < end and not os.path.exists(out):
        time.sleep(0.5)
    time.sleep(1)
    p.kill()


if __name__ == "__main__":
    base, sid = sys.argv[1], sys.argv[2]
    os.makedirs("docs/screenshots", exist_ok=True)
    for name, route in [("send", "send"), ("receive", "receive"), ("transfer", f"transfer/{sid}"), ("history", "history"), ("settings", "settings"), ("about", "about")]:
        for w, h in [(1280, 1100), (390, 1000)]:
            shot(f"{base}/#/{route}", f"docs/screenshots/ui-{name}-{w}.png", f"{w},{h}")
            print(name, w, flush=True)
