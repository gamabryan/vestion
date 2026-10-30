"""Pedidos de confirmação: o cartão PODE / CANCELAR e o "pode" falado."""
import re
import threading
import time
import unicodedata
import uuid
from typing import Callable

from lia.permissions import ActionCard

APPROVAL_PHRASES = {"pode", "pode mandar", "pode fazer", "confirma", "confirmo", "sim pode"}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def parse_voice_approval(text: str) -> bool:
    """Só uma frase clara de aprovação conta; qualquer outra coisa é cancelar."""
    norm = _normalize(text)
    if norm.startswith("vestion "):
        norm = norm[len("vestion "):]
    return norm in APPROVAL_PHRASES


class _Pending:
    def __init__(self):
        self.event = threading.Event()
        self.approved = False
        self.voice_deadline = 0.0


class ConfirmBridge:
    def __init__(self, timeout_s: float, show: Callable[[str, ActionCard], None],
                 hide: Callable[[str], None]):
        self.timeout_s = timeout_s
        self.show = show
        self.hide = hide
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def request(self, card: ActionCard) -> bool:
        rid = uuid.uuid4().hex
        pending = _Pending()
        with self._lock:
            self._pending[rid] = pending
        try:
            self.show(rid, card)
            pending.event.wait(self.timeout_s)
            return pending.approved
        finally:
            with self._lock:
                self._pending.pop(rid, None)
            self.hide(rid)

    def resolve(self, req_id: str, approved: bool) -> None:
        with self._lock:
            pending = self._pending.get(req_id)
        if pending and not pending.event.is_set():
            pending.approved = approved
            pending.event.set()

    def open_voice_window(self, req_id: str, seconds: int) -> None:
        with self._lock:
            pending = self._pending.get(req_id)
            if pending:
                pending.voice_deadline = time.monotonic() + seconds

    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._pending)

    def voice_answer(self, text: str, force: bool = False) -> bool:
        """Responde pela voz. `force` = o usuário apertou o atalho de propósito para responder."""
        now = time.monotonic()
        with self._lock:
            open_ids = [rid for rid, p in self._pending.items() if force or p.voice_deadline > now]
        if not open_ids:
            return False
        self.resolve(open_ids[0], parse_voice_approval(text))
        return True

    def cancel_all(self) -> None:
        with self._lock:
            ids = list(self._pending)
        for rid in ids:
            self.resolve(rid, False)
