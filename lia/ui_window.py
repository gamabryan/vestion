"""Janela da central (pywebview / WebView2) e as chamadas Python → interface."""
import json
import threading
from pathlib import Path
from typing import Callable

import webview

from lia.permissions import ActionCard

UI_DIR = Path(__file__).with_name("ui")
THEMES = ("cyan", "red")


def load_theme(prefs: Path) -> str:
    """Tema de cor escolhido no botão do topo (ciano se nunca escolheu ou o arquivo estragou)."""
    try:
        theme = json.loads(Path(prefs).read_text(encoding="utf-8")).get("tema")
    except (OSError, ValueError, AttributeError):
        return "cyan"
    return theme if theme in THEMES else "cyan"


def save_theme(prefs: Path, theme: str) -> None:
    if theme not in THEMES:
        return
    prefs = Path(prefs)
    prefs.parent.mkdir(parents=True, exist_ok=True)
    prefs.write_text(json.dumps({"tema": theme}), encoding="utf-8")


class _JsApi:
    """Exposto ao JavaScript como pywebview.api."""

    def __init__(self, on_confirm: Callable[[str, bool], None], on_hide: Callable[[], None] = lambda: None,
                 on_reminder_done: Callable[[str], None] = lambda rid: None,
                 on_reminder_snooze: Callable[[str], None] = lambda rid: None,
                 on_theme: Callable[[str], None] = lambda theme: None):
        self._on_confirm = on_confirm
        self._on_hide = on_hide
        self._on_reminder_done = on_reminder_done
        self._on_reminder_snooze = on_reminder_snooze
        self._on_theme = on_theme

    def set_theme(self, theme: str) -> None:
        """Botão de cor no topo da central."""
        self._on_theme(str(theme))

    def confirm(self, req_id: str, approved: bool) -> None:
        self._on_confirm(str(req_id), bool(approved))

    def hide(self) -> None:
        """Esc na central: esconde (o Vestion continua no ícone perto do relógio)."""
        self._on_hide()

    def reminder_done(self, rid: str) -> None:
        self._on_reminder_done(str(rid))

    def reminder_snooze(self, rid: str) -> None:
        self._on_reminder_snooze(str(rid))


class CentralWindow:
    def __init__(self, on_confirm: Callable[[str, bool], None]):
        self._loaded = threading.Event()
        self._quitting = False
        self._hidden = False
        self._minimized = False
        # O app liga estes depois de criar o armazenamento de lembretes.
        self.on_reminder_done: Callable[[str], None] = lambda rid: None
        self.on_reminder_snooze: Callable[[str], None] = lambda rid: None
        # Tema de cor: o app define o inicial e onde guardar a escolha.
        self.theme = "cyan"
        self.on_theme: Callable[[str], None] = lambda theme: None
        api = _JsApi(on_confirm, on_hide=self.hide,
                     on_reminder_done=lambda rid: self.on_reminder_done(rid),
                     on_reminder_snooze=lambda rid: self.on_reminder_snooze(rid),
                     on_theme=self._set_theme)
        self.window = webview.create_window(
            "Vestion", url=str(UI_DIR / "index.html"), js_api=api,
            width=1280, height=800, min_size=(900, 620), background_color="#03070d",
            fullscreen=True)  # tela cheia total; Esc esconde, segurar Tab traz de volta
        self.window.events.loaded += self._loaded.set
        self.window.events.loaded += lambda: threading.Thread(
            target=lambda: self._js("setTheme", self.theme), daemon=True).start()
        self.window.events.closing += self._on_closing
        self.window.events.minimized += self._on_minimized
        self.window.events.restored += self._on_restored
        self.window.events.maximized += self._on_restored

    def _set_theme(self, theme: str) -> None:
        if theme in THEMES:
            self.theme = theme
            self.on_theme(theme)

    def _on_minimized(self):
        self._minimized = True

    def _on_restored(self):
        self._minimized = False

    def _on_closing(self):
        if self._quitting:
            return True
        self.hide()  # fechar só esconde; "Sair" na bandeja encerra
        return False

    def _js(self, fn: str, *args) -> None:
        if not self._loaded.wait(15):
            return
        call = f"window.lia && window.lia.{fn}({', '.join(json.dumps(a, ensure_ascii=False) for a in args)})"
        try:
            self.window.evaluate_js(call)
        except Exception:
            pass  # janela fechando

    def show(self) -> None:
        # Só mexe na janela se ela estiver escondida ou minimizada: "restore" tiraria do maximizado.
        if self._hidden:
            self.window.show()
            self._hidden = False
        if self._minimized:
            self.window.restore()
            self._minimized = False

    def hide(self) -> None:
        self.window.hide()
        self._hidden = True

    def destroy(self) -> None:
        self._quitting = True
        self.window.destroy()

    def set_state(self, state: str) -> None:
        self._js("setState", state)

    def caption(self, text: str, who: str = "lia") -> None:
        self._js("setCaption", text, who)

    def show_confirm(self, req_id: str, card: ActionCard) -> None:
        self._js("showConfirm", req_id, card.title, card.detail)

    def hide_confirm(self, req_id: str) -> None:
        self._js("hideConfirm", req_id)

    def update_panel(self, name: str, data: dict) -> None:
        self._js("updatePanel", name, data)

    def show_reminder(self, rid: str, text: str) -> None:
        self._js("showReminder", rid, text)

    def hide_reminder(self, rid: str) -> None:
        self._js("hideReminder", rid)

    def speak(self, envelope: list[float], frame_ms: int) -> None:
        self._js("speak", envelope, frame_ms)


def _demo(win: CentralWindow):
    import time
    from lia.system_stats import snapshot
    win._loaded.wait()
    win.caption("Vestion, o que eu tenho hoje?", "user")
    for state in ("listening", "thinking", "speaking", "idle"):
        win.set_state(state)
        win.caption(f"Estado de demonstração: {state}.")
        win.update_panel("sistema", snapshot(3, False, 14))
        time.sleep(2.5)
    win.show_confirm("demo", ActionCard("Criar ou substituir arquivo",
                                        r"C:\Users\PC\Desktop\lista.txt", ""))
    time.sleep(4)
    win.hide_confirm("demo")
    win.update_panel("sistema", snapshot(4, True, 100))
    win.set_state("idle")
    win.caption("Fim da demonstração.")


if __name__ == "__main__":
    import sys
    win = CentralWindow(lambda rid, ok: print("confirm", rid, ok))
    if "--demo" in sys.argv:
        webview.start(_demo, win)
    else:
        webview.start()
