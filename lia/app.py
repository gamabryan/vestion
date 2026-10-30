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
from lia.sentences import SentenceBuffer, for_speech
from lia.system_stats import snapshot

ROOT = Path(__file__).resolve().parent.parent
API_KEY_WARNING = "Aviso: chave de API removida para não gerar cobrança."
GREETING = "Oi, estou pronta."
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
        self._jobs: queue.Queue[str] = queue.Queue()
        self._listen_lock = threading.Lock()
        self._running = True
        speaker.on_start = lambda: window.set_state("speaking")
        speaker.on_end = lambda: window.set_state("idle")
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
        self.window.set_state("idle")
        self._say(GREETING)

    def quit(self) -> None:
        self._running = False
        self.bridge.cancel_all()
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
        self.speaker.stop()
        self.window.show()
        if not self._listen_lock.acquire(timeout=1.5):
            return  # já está ouvindo
        try:
            self.window.set_state("listening")
            try:
                text = self.listener.listen_once()
            except MicUnavailable:
                self._say(NO_MIC)
                self.window.set_state("idle")
                return
        finally:
            self._listen_lock.release()
        if text:
            self.window.caption(text, "user")
        if text and self.bridge.has_pending() and self.bridge.voice_answer(text):
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
        self.window.set_state("thinking")
        if self.brain.needs_new_session(datetime.now()):
            self.brain.new_session()
        buf = SentenceBuffer()
        full = ""
        for ev in self.brain.ask(text):
            if ev.kind == "text":
                full += ev.text
                self.window.caption(for_speech(full), "lia")
                for sentence in buf.feed(ev.text):
                    self.speaker.say(for_speech(sentence))
            elif ev.kind == "done":
                for sentence in buf.flush():
                    self.speaker.say(for_speech(sentence))
            elif ev.kind == "error":
                for sentence in buf.flush():
                    self.speaker.say(for_speech(sentence))
                self._say(friendly_error(ev.text))
        if not self.speaker.speaking:
            self.window.set_state("idle")

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
    from lia.bridge_server import start_bridge
    from lia.config import load_config
    from lia.hotkey import register_hotkey
    from lia.mcp_config import write_mcp_config
    from lia.permissions import ALLOWED_TOOLS
    from lia.tray import start_tray
    from lia.ui_window import CentralWindow

    logging.basicConfig(filename=ROOT / "lia.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(ROOT / "config.toml")
    holder: dict = {}
    bridge = ConfirmBridge(cfg.confirm_timeout_s,
                           lambda rid, card: holder["app"].on_confirm_show(rid, card),
                           lambda rid: holder["app"].on_confirm_hide(rid))
    port, token = start_bridge(bridge)
    mcp_cfg = write_mcp_config(cfg.workspace / ".lia" / "mcp.json", port, token)
    window = CentralWindow(on_confirm=bridge.resolve)
    brain = Brain(cfg, mcp_cfg, lambda: holder["app"].on_api_key_removed(), ALLOWED_TOOLS)
    app = LiaApp(cfg, brain, Listener(cfg), Speaker(cfg), window, bridge)
    holder["app"] = app

    unhook = register_hotkey(cfg.hotkey, app.on_hotkey)
    tray = start_tray(on_open=window.show, on_quit=app.quit)
    app.on_quit += [unhook, tray.stop]

    webview.start(app.start)
    os._exit(0)  # encerra threads de áudio e o hook de teclado junto com a janela


if __name__ == "__main__":
    main()
