"""Run a FastAPI app in a background thread (peer server next to the UI server, and in tests)."""
import threading
import time

import uvicorn


def start_in_thread(app, host, port):
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError(f"server on {host}:{port} did not start (port in use?)")
