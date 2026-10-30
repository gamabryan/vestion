"""Orquestra a Lia: atalho → ouvir → cérebro → falar, com o cartão de confirmação no meio."""
import logging
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from lia.audio.stt import MicUnavailable
from lia.brain import BILLING_KEYS, friendly_error
from lia.config import Config
from lia.confirm import ConfirmBridge
from lia.permissions import ActionCard
from lia.reminders import parse_reminder_answer
from lia.sentences import SentenceBuffer, for_speech
from lia.system_stats import snapshot

ROOT = Path(__file__).resolve().parent.parent
API_KEY_WARNING = "Aviso: chave de API removida para não gerar cobrança."
GREETING = "Oi, estou pronto."
NO_MIC = "Não encontrei um microfone."
log = logging.getLogger(__name__)


class LiaApp:
    def __init__(self, cfg: Config, brain, listener, speaker, window, bridge: ConfirmBridge):
        self.cfg = cfg
        self.brain = brain
        self.listener = listener
        self.speaker = speaker
        self.window = window
        self.bridge = bridge
        self.on_quit: list[Callable[[], None]] = []
        self.briefing: Callable[[], str] | None = None  # resumo do dia ao abrir (agenda + Gmail)
        self.taint = None  # Taint compartilhado com a ponte (e-mails lidos neste pedido)
        self.briefing_timeout_s = 6.0
        self.after_answer: Callable[[], None] | None = None
        self.reminders = None              # ReminderStore (lembretes só no PC)
        self.on_reminders_changed: Callable[[], None] = lambda: None  # ex.: atualizar o painel
        self._open_reminder: str | None = None
        self._jobs: queue.Queue[str] = queue.Queue()
        self._listen_lock = threading.Lock()
        self._running = True
        self._generation = 0
        speaker.on_start = lambda: window.set_state("speaking")
        speaker.on_end = lambda: window.set_state("idle")
        speaker.on_play = lambda envelope, frame_ms: window.speak(envelope, frame_ms)
        threading.Thread(target=self._brain_worker, daemon=True).start()

    # ---- ciclo de vida -------------------------------------------------
    def start(self, run_background: bool = True) -> None:
        removed = [k for k in BILLING_KEYS if k in os.environ]
        for key in removed:
            del os.environ[key]
        if removed:
            self.on_api_key_removed()
        if run_background:
            if hasattr(self.listener, "preload"):
                self.listener.preload()
            threading.Thread(target=self._stats_loop, daemon=True).start()
            if self.reminders is not None:
                threading.Thread(target=self._reminder_loop, daemon=True).start()
        self.window.set_state("idle")
        self._say(self._briefing_or_greeting())

    def _briefing_or_greeting(self) -> str:
        """Resumo do dia; se o Google demorar ou falhar (sem internet), só a saudação."""
        if not self.briefing:
            return GREETING
        result: list[str] = []

        def build():
            try:
                result.append(self.briefing())
            except Exception:
                log.exception("falha ao montar o resumo do dia")

        worker = threading.Thread(target=build, daemon=True)
        worker.start()
        worker.join(self.briefing_timeout_s)
        return result[0] if result else GREETING

    def quit(self) -> None:
        self._running = False
        self.bridge.cancel_all()
        if hasattr(self.brain, "kill"):
            self.brain.kill()  # o Claude não continua trabalhando depois de "Sair"
        self.speaker.stop()
        for hook in self.on_quit:
            try:
                hook()
            except Exception:
                log.exception("erro ao encerrar")
        self.window.destroy()

    def on_api_key_removed(self) -> None:
        self.window.caption(API_KEY_WARNING, "lia")

    # ---- fala do usuário ----------------------------------------------
    def on_hotkey(self) -> None:
        log.info("atalho recebido")
        self.speaker.stop()
        self.window.show()
        self._generation += 1  # o resto da resposta anterior não deve mais ser falado
        if not self._listen_lock.acquire(timeout=1.5):
            log.info("atalho ignorado: já estava ouvindo")
            return
        try:
            self.window.set_state("listening")
            log.info("ouvindo (mudo=%s)", getattr(self.listener, "muted", None))
            try:
                text = self.listener.listen_once()
                log.info("ouvido: %r", text)
            except MicUnavailable:
                self._say(NO_MIC)
                self.window.set_state("idle")
                return
            except Exception:
                log.exception("falha ao ouvir")
                self._say(friendly_error(""))
                self.window.set_state("idle")
                return
        finally:
            self._listen_lock.release()
        if text:
            self.window.caption(text, "user")
        if text and self._open_reminder and self._answer_reminder_by_voice(text):
            return
        if text and self.bridge.has_pending() and self.bridge.voice_answer(text, force=True):
            self.window.set_state("thinking")
            return
        if not text:
            self.window.set_state("idle")
            return
        self._jobs.put(text)

    def wait_jobs(self, timeout: float = 5) -> bool:
        end = time.monotonic() + timeout
        while self._jobs.unfinished_tasks and time.monotonic() < end:
            time.sleep(0.01)
        return not self._jobs.unfinished_tasks

    def _brain_worker(self) -> None:
        while True:
            text = self._jobs.get()
            try:
                self.handle_utterance(text)
            except Exception:
                log.exception("falha ao processar pedido")
                self._say(friendly_error(""))
            finally:
                self._jobs.task_done()

    def handle_utterance(self, text: str) -> None:
        if self.taint:
            self.taint.reset()  # pedido novo do usuário: e-mails lidos antes não contam mais
        self.window.set_state("thinking")
        if self.brain.needs_new_session(datetime.now()):
            self.brain.new_session()
        generation = self._generation
        buf = SentenceBuffer()
        full = ""
        for ev in self.brain.ask(text):
            current = generation == self._generation  # atalho apertado no meio = cala o resto
            if ev.kind == "text":
                full += ev.text
                sentences = buf.feed(ev.text)
                if current:
                    self.window.caption(for_speech(full), "lia")
                    for sentence in sentences:
                        self.speaker.say(for_speech(sentence))
            elif ev.kind in ("done", "error"):
                sentences = buf.flush()
                if current:
                    for sentence in sentences:
                        self.speaker.say(for_speech(sentence))
                    if ev.kind == "error":
                        self._say(friendly_error(ev.text))
        if not self.speaker.speaking:
            self.window.set_state("idle")
        if self.after_answer:
            self.after_answer()  # ex.: atualizar os painéis na hora, se ele mexeu na agenda ou no Gmail

    def _say(self, text: str) -> None:
        self.window.caption(text, "lia")
        self.speaker.say(text)

    # ---- confirmação ---------------------------------------------------
    def on_confirm_show(self, req_id: str, card: ActionCard) -> None:
        self.window.show()
        self.window.show_confirm(req_id, card)
        self.listener.muted = True  # não ouvir a própria voz lendo o cartão
        self.window.caption(card.spoken, "lia")
        self.speaker.say(card.spoken)
        threading.Thread(target=self._voice_confirm, args=(req_id,), daemon=True).start()

    def _voice_confirm(self, req_id: str) -> None:
        time.sleep(0.1)
        self.speaker.wait_idle()
        self.listener.muted = False
        if not self.bridge.has_pending():
            return
        with self._listen_lock:
            self.bridge.open_voice_window(req_id, self.cfg.voice_confirm_window_s)
            self.window.set_state("listening")
            try:
                text = self.listener.listen_once(max_seconds=self.cfg.voice_confirm_window_s)
            except MicUnavailable:
                text = ""
        if text:
            self.window.caption(text, "user")
            self.bridge.voice_answer(text)
        self.window.set_state("thinking")

    def on_confirm_hide(self, req_id: str) -> None:
        self.window.hide_confirm(req_id)
        self.listener.muted = False

    # ---- lembretes -----------------------------------------------------
    def check_reminders(self) -> None:
        """Chamado pelo vigia: avisa (uma vez) o primeiro lembrete que chegou na hora."""
        if self.reminders is None or self._open_reminder:
            return
        due = self.reminders.due(datetime.now().astimezone())
        if not due:
            return
        item = due[0]
        self.reminders.mark_warned(item["id"])
        self._open_reminder = item["id"]
        self.window.show()
        self.window.show_reminder(item["id"], item["texto"])
        self._say(f"Lembrete: {item['texto']}.")
        threading.Thread(target=self._listen_reminder_answer, args=(item["id"],), daemon=True).start()

    def _listen_reminder_answer(self, rid: str) -> None:
        """Depois de falar o lembrete, escuta uma vez por 'feito' ou 'adia' (como no cartão)."""
        time.sleep(0.1)
        self.speaker.wait_idle()
        if self._open_reminder != rid or not self._listen_lock.acquire(timeout=0.5):
            return
        try:
            self.window.set_state("listening")
            try:
                text = self.listener.listen_once(max_seconds=self.cfg.voice_confirm_window_s)
            except Exception:
                text = ""
        finally:
            self._listen_lock.release()
        self.window.set_state("idle")
        if text:
            self._answer_reminder_by_voice(text)

    def _answer_reminder_by_voice(self, text: str) -> bool:
        answer = parse_reminder_answer(text)
        rid = self._open_reminder
        if not answer or not rid:
            return False
        if answer == "done":
            self.complete_reminder(rid)
            self._say("Marquei como feito.")
        else:
            self.snooze_reminder(rid)
            self._say("Certo, te lembro de novo em dez minutos.")
        return True

    def complete_reminder(self, rid: str) -> None:
        self.reminders.complete(rid)
        self._close_reminder(rid)

    def snooze_reminder(self, rid: str) -> None:
        self.reminders.snooze(rid, 10, datetime.now().astimezone())
        self._close_reminder(rid)

    def _close_reminder(self, rid: str) -> None:
        if self._open_reminder == rid:
            self._open_reminder = None
            self.window.hide_reminder(rid)
        self.on_reminders_changed()

    def _reminder_loop(self) -> None:
        turn = 0
        while self._running:
            try:
                if self.reminders is not None and turn % 4 == 0:  # Google Tasks a cada minuto (o que mudou pelo celular aparece aqui)
                    self.reminders.sync()
                turn += 1
                self.check_reminders()
                self.on_reminders_changed()  # atrasados mudam de cor com o tempo
            except Exception:
                log.exception("falha no vigia de lembretes")
            time.sleep(15)

    # ---- painéis -------------------------------------------------------
    def _stats_loop(self) -> None:
        while self._running:
            self.window.update_panel("sistema", snapshot(self.brain.requests_today, self.brain.limit_hit,
                                                         self.brain.usage_pct))
            time.sleep(2)


def main() -> None:
    import webview

    from lia.audio.stt import Listener
    from lia.audio.tts import Speaker
    from lia.brain import Brain
    from lia.briefing import briefing_text
    from lia.bridge_server import start_bridge
    from lia.config import load_config
    from lia.google.auth import connect_interactive, credentials_file, load_credentials
    from lia.google.calendar import CalendarClient
    from lia.google.gmail import GmailClient
    from lia.google.tasks import TasksClient
    from lia.hotkey import register_hotkey
    from lia.mcp_config import write_mcp_config
    from lia.panels import PanelUpdater
    from lia.permissions import ALLOWED_TOOLS, Taint, make_describer, make_policy
    from lia.reminders import ReminderStore
    from lia.tray import ICON_PATH, save_ico, start_tray
    from lia.ui_window import CentralWindow, load_theme, save_theme

    from lia.appid import set_process_app_id
    set_process_app_id()  # ícone próprio na barra de tarefas, em vez do Python
    icon = ICON_PATH if ICON_PATH.exists() else save_ico()

    logging.basicConfig(filename=ROOT / "lia.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Sem console (pythonw), erros em threads sumiriam: manda todos para o lia.log.
    threading.excepthook = lambda a: log.error("erro na thread %s", a.thread.name if a.thread else "?",
                                               exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    cfg = load_config(ROOT / "config.toml")
    holder: dict = {}
    bridge = ConfirmBridge(cfg.confirm_timeout_s,
                           lambda rid, card: holder["app"].on_confirm_show(rid, card),
                           lambda rid: holder["app"].on_confirm_hide(rid))
    def google_clients():
        creds = load_credentials(cfg.workspace)
        if not creds:
            return None
        return GmailClient.from_credentials(creds), CalendarClient.from_credentials(creds)

    def calendar_only():
        clients = google_clients()
        return clients[1] if clients else None

    def tasks_client():
        creds = load_credentials(cfg.workspace)
        return TasksClient.from_credentials(creds) if creds else None

    reminders = ReminderStore(cfg.workspace / "lembretes.json", remote=tasks_client)
    taint = Taint()
    port, token = start_bridge(bridge, describe=make_describer(calendar_only, reminders=reminders), taint=taint,
                               policy=make_policy(calendar_only))
    mcp_cfg = write_mcp_config(cfg.workspace / ".lia" / "mcp.json", port, token, workspace=cfg.workspace)
    window = CentralWindow(on_confirm=bridge.resolve)
    ui_prefs = cfg.workspace / ".lia" / "ui.json"
    window.theme = load_theme(ui_prefs)
    window.on_theme = lambda theme: save_theme(ui_prefs, theme)
    brain = Brain(cfg, mcp_cfg, lambda: holder["app"].on_api_key_removed(), ALLOWED_TOOLS)
    brain.is_waiting_user = bridge.has_pending
    app = LiaApp(cfg, brain, Listener(cfg), Speaker(cfg), window, bridge)
    holder["app"] = app

    panels = PanelUpdater(window, google_clients, reminders=reminders)
    app.reminders = reminders
    app.on_reminders_changed = panels.refresh_reminders
    window.on_reminder_done = app.complete_reminder
    window.on_reminder_snooze = app.snooze_reminder

    def briefing():
        now = datetime.now().astimezone()
        reminders.sync()
        groups = reminders.groups(now)
        clients = google_clients()
        if not clients:
            return briefing_text(now, None, None, groups)
        gmail, calendar = clients
        return briefing_text(now, calendar.today(now), gmail.today(now, 10), groups)

    app.briefing = briefing
    app.taint = taint
    app.after_answer = lambda: threading.Thread(target=panels.refresh_once, daemon=True).start()

    def connect_google():
        if not credentials_file(cfg.workspace).exists():
            app._say("Ainda falta o arquivo de credenciais do Google. Siga o guia de conexão no README.")
            return
        app._say("Abri o navegador. Entre na sua conta Google e autorize o Vestion.")
        if connect_interactive(cfg.workspace):
            reminders.sync()  # lembretes que estavam só no PC vão para o Google Tasks
            panels.refresh_once()
            app._say("Pronto, conectei sua conta Google.")
        else:
            app._say("Não consegui conectar a conta Google. Tente de novo pelo ícone.")

    unhook = register_hotkey(cfg.hotkey, app.on_hotkey, cfg.hotkey_hold_s)
    tray = start_tray(on_open=window.show, on_quit=app.quit,
                      on_connect_google=lambda: threading.Thread(target=connect_google, daemon=True).start())
    app.on_quit += [unhook, tray.stop]

    def on_start():
        panels.start()
        app.start()

    webview.start(on_start, icon=str(icon))
    os._exit(0)  # encerra threads de áudio e o hook de teclado junto com a janela


if __name__ == "__main__":
    main()
