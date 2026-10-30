"""Janela da central (pywebview / WebView2) e as chamadas Python → interface."""
import json
import threading
from pathlib import Path
from typing import Callable

import webview

from lia.permissions import ActionCard

UI_DIR = Path(__file__).with_name("ui")


class _JsApi:
    """Exposto ao JavaScript como pywebview.api."""

    def __init__(self, on_confirm: Callable[[str, bool], None]):
        self._on_confirm = on_confirm

    def confirm(self, req_id: str, approved: bool) -> None:
        self._on_confirm(str(req_id), bool(approved))


class CentralWindow:
    def __init__(self, on_confirm: Callable[[str, bool], None]):
        self._loaded = threading.Event()
        self._quitting = False
        self.window = webview.create_window(
            "Lia", url=str(UI_DIR / "index.html"), js_api=_JsApi(on_confirm),
            width=1280, height=800, min_size=(900, 620), background_color="#03070d")
        self.window.events.loaded += self._loaded.set
        self.window.events.closing += self._on_closing

    def _on_closing(self):
        if self._quitting:
            return True
        self.window.hide()  # fechar só esconde; "Sair" na bandeja encerra
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
        self.window.show()
        self.window.restore()

    def hide(self) -> None:
        self.window.hide()

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


def _demo(win: CentralWindow):
    import time
    from lia.system_stats import snapshot
    win._loaded.wait()
    win.caption("Lia, o que eu tenho hoje?", "user")
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
