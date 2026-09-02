"""`/healthz` (alive) and `/readyz` (dependencies answer) for consumers, which have no HTTP.

Kubernetes' liveness probe hits /healthz, readiness hits /readyz. A tiny threaded server.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_probe_server(port: int, ready: Callable[[], bool]) -> ThreadingHTTPServer:
    class Probe(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server's naming
            if self.path == "/healthz":
                self._reply(200, b'{"status":"alive"}')
            elif self.path == "/readyz":
                ok = False
                try:
                    ok = bool(ready())
                except Exception:  # noqa: BLE001 — a readiness check that throws is "not ready"
                    ok = False
                self._reply(
                    200 if ok else 503, b'{"status":"ready"}' if ok else b'{"status":"not ready"}'
                )
            else:
                self._reply(404, b'{"error":"not found"}')

        def _reply(self, code: int, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:  # probes are noisy; keep stdout for JSON logs
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), Probe)
    threading.Thread(target=server.serve_forever, name="probes", daemon=True).start()
    return server
