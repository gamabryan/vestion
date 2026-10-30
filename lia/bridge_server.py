"""Servidor HTTP local (127.0.0.1) que recebe pedidos de confirmação do servidor MCP da Lia."""
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lia.confirm import ConfirmBridge
from lia.permissions import describe_action, needs_confirmation

log = logging.getLogger(__name__)


def start_bridge(bridge: ConfirmBridge, describe=describe_action, taint=None,
                 policy=needs_confirmation) -> tuple[int, str]:
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
                tool_name, tool_input = str(body["tool_name"]), dict(body.get("input") or {})
                card = describe(tool_name, tool_input)
            except (ValueError, KeyError, TypeError):
                self.send_error(400)
                return
            tainted = bool(taint and taint.active)
            if taint:
                taint.observe(tool_name)  # leu e-mail: daqui até o próximo pedido, saídas pedem cartão
            if policy(tool_name, tool_input, tainted=tainted):
                approved = bridge.request(card)
                log.info("confirmação %s: %s %s", "APROVADA" if approved else "RECUSADA", card.title, card.detail[:200])
            else:
                approved = True
                log.info("automático: %s %s", card.title, card.detail[:200])
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
