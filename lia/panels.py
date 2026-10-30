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


MAX_REMINDERS = 8


def reminders_panel(groups: dict[str, list[dict]], now: datetime) -> dict:
    """Atrasados (laranja), hoje (hora), próximos (data e hora) e tarefas sem hora."""
    def when(r, fmt):
        return datetime.fromisoformat(r["quando"]).astimezone().strftime(fmt)

    today = now.astimezone().strftime("%d/%m")
    items = [{"id": r["id"], "tag": when(r, "%H:%M") if when(r, "%d/%m") == today else when(r, "%d/%m"),
              "text": r["texto"], "kind": "late"} for r in groups["atrasados"]]
    items += [{"id": r["id"], "tag": when(r, "%H:%M"), "text": r["texto"], "kind": "today"} for r in groups["hoje"]]
    items += [{"id": r["id"], "tag": when(r, "%d/%m %H:%M"), "text": r["texto"], "kind": "next"} for r in groups["proximos"]]
    items += [{"id": r["id"], "tag": "", "text": r["texto"], "kind": "task"} for r in groups["sem_hora"]]
    total = len(items)
    return {"title": f"LEMBRETES · {total}", "items": items[:MAX_REMINDERS]}


def not_connected_panel(title: str) -> dict:
    return {"title": title, "items": [{"tag": "", "text": NOT_CONNECTED_TEXT}]}


class PanelUpdater:
    def __init__(self, window, get_clients: Callable[[], tuple | None], every_s: int = 120, reminders=None):
        self.window = window
        self.get_clients = get_clients
        self.every_s = every_s
        self.reminders = reminders
        self._failing = False

    def refresh_reminders(self) -> None:
        """Só o painel de lembretes (local, rápido): usado após cada mudança e pelo vigia de horários."""
        if self.reminders is not None:
            now = datetime.now().astimezone()
            self.window.update_panel("lembretes", reminders_panel(self.reminders.groups(now), now))

    def refresh_once(self) -> None:
        self.refresh_reminders()
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
