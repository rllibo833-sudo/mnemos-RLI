"""Loopback-only live HTML graph viewer backed by the local SQLite database."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .graph import render_graph
from .store import MemoryStore


class _LiveGraphServer(HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_live_graph(store: MemoryStore, output: str | Path, port: int = 8765) -> int:
    """Serve a self-refreshing graph on loopback only; never expose the database to LAN."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be an integer from 1 to 65535.")
    target = Path(output).expanduser().resolve()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path not in ("/", "/index.html"):
                self.send_error(404)
                return
            try:
                render_graph(store.list_all(), store.links(), target, refresh_seconds=10)
                body = target.read_bytes()
            except (OSError, ValueError) as exc:
                self.send_error(500, str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        server = _LiveGraphServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise ValueError(f"Cannot start local graph viewer on 127.0.0.1:{port}: {exc}") from exc
    print(f"Mnemos live graph: http://127.0.0.1:{port}/")
    print(f"Local graph snapshot: {target}")
    print("Offline and loopback-only. Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nMnemos live graph stopped.")
    finally:
        server.server_close()
    return 0
