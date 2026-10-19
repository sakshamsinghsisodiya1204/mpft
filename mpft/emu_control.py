"""Tiny HTTP control for a running emulator (127.0.0.1 only). GET /state, POST /kill/N, /restore/N, /delay/N/MS, /corrupt/RATE."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_control(handle, port):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.reply(200, handle.state()) if self.path == "/state" else self.reply(404, {"error": "not found"})

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            try:
                if parts[0] == "kill":
                    handle.kill(int(parts[1]))
                elif parts[0] == "restore":
                    handle.restore(int(parts[1]))
                elif parts[0] == "delay":
                    handle.set_delay(int(parts[1]), float(parts[2]))
                elif parts[0] == "corrupt":
                    handle.set_corrupt(float(parts[1]))
                else:
                    return self.reply(404, {"error": "not found"})
            except (IndexError, ValueError):
                return self.reply(400, {"error": "bad path index or rate"})
            self.reply(200, handle.state())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
