"""Painéis de Agenda e Gmail: atualizados direto pela API do Google, sem passar pelo Claude."""
import logging
import threading
import time
from datetime import datetime
from typing import Callable

from lia.google.calendar import hhmm

NOT_CONNECTED_TEXT = "Conecte sua conta Google pelo ícone perto do relógio."
MAX_TEXT = 60
log = logging.getLogger(__name__)


def agenda_panel(events: list[dict]) -> dict:
    return {"title": "AGENDA · HOJE", "items": [{"tag": hhmm(e), "text": e["titulo"]} for e in events]}


def gmail_panel(unread: list[dict], count: int) -> dict:
    items = []
    for m in unread:
        text = f"{m['de']} — {m['assunto']}"
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT - 1] + "…"
        items.append({"tag": "★" if m.get("importante") else "", "text": text})
    return {"title": f"GMAIL · {count} NÃO LIDOS", "items": items}


def not_connected_panel(title: str) -> dict:
    return {"title": title, "items": [{"tag": "", "text": NOT_CONNECTED_TEXT}]}


class PanelUpdater:
    def __init__(self, window, get_clients: Callable[[], tuple | None], every_s: int = 120):
        self.window = window
        self.get_clients = get_clients
        self.every_s = every_s
        self._failing = False

    def refresh_once(self) -> None:
        try:
            clients = self.get_clients()
            if clients is None:
                self.window.update_panel("agenda", not_connected_panel("AGENDA · HOJE"))
                self.window.update_panel("gmail", not_connected_panel("GMAIL"))
                return
            gmail, calendar = clients
            agenda = agenda_panel(calendar.today(datetime.now().astimezone()))
            mail = gmail_panel(gmail.unread(5), gmail.unread_count())
        except Exception as e:
            if not self._failing:  # um aviso por sequência de falhas; os painéis mantêm o último dado
                log.warning("não consegui atualizar os painéis do Google: %s", e)
            self._failing = True
            return
        self._failing = False
        self.window.update_panel("agenda", agenda)
        self.window.update_panel("gmail", mail)

    def start(self) -> None:
        def loop():
            while True:
                self.refresh_once()
                time.sleep(self.every_s)
        threading.Thread(target=loop, daemon=True).start()
