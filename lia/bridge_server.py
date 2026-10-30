"""Servidor HTTP local (127.0.0.1) que recebe pedidos de confirmação do servidor MCP da Lia."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lia.confirm import ConfirmBridge
from lia.permissions import describe_action


def start_bridge(bridge: ConfirmBridge) -> tuple[int, str]:
    token = secrets.token_hex(16)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/confirm" or not secrets.compare_digest(
                    self.headers.get("X-Lia-Token", ""), token):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                card = describe_action(str(body["tool_name"]), dict(body.get("input") or {}))
            except (ValueError, KeyError, TypeError):
                self.send_error(400)
                return
            approved = bridge.request(card)
            payload = json.dumps({"approved": approved}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1], token
