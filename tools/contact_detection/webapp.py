"""Small stdlib web dashboard for the H4 contact demo."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

STATIC = Path(__file__).resolve().parent / "static"


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, content, content_type="application/json; charset=utf-8"):
            body = content.encode("utf-8") if isinstance(content, str) else content
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_text(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send(200, json.dumps(state.snapshot()))
            elif self.path == "/api/health":
                snap = state.snapshot()
                self._send(200, json.dumps({"ok": True, "connection": snap["connection"],
                                            "source": snap["source"]}))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            if self.path == "/api/recalibrate":
                self._send(200, json.dumps({"detection": state.recalibrate()}))
            else:
                self._send(404, json.dumps({"error": "not found"}))
    return Handler


def start_web(state, port: int, host: str = "127.0.0.1"):
    server = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
