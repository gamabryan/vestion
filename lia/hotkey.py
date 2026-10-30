"""Tecla para chamar o Vestion: segurar uma tecla (padrão: Tab) ou uma combinação."""
import threading
from typing import Callable

import keyboard

MODIFIERS = ("alt", "ctrl", "shift", "windows", "left windows", "right windows")


class HoldDetector:
    """Dispara o callback quando a tecla fica pressionada por `seconds`, sem modificadores.

    Um toque rápido não dispara, então a tecla continua funcionando normalmente nos programas.
    """

    def __init__(self, seconds: float, callback: Callable[[], None]):
        self.seconds = seconds
        self.callback = callback
        self._down = False
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def press(self, modifiers: bool) -> None:
        with self._lock:
            if self._down:  # repetição automática do teclado enquanto segura
                return
            self._down = True
            if modifiers:
                return  # Alt+Tab, Ctrl+Tab...: nunca é o Vestion
            self._timer = threading.Timer(self.seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def release(self) -> None:
        with self._lock:
            self._down = False
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def _fire(self) -> None:
        with self._lock:
            if not self._down:
                return
            self._timer = None
        threading.Thread(target=self.callback, daemon=True).start()


def register_hotkey(hotkey: str, callback: Callable[[], None], hold_s: float = 0.0) -> Callable[[], None]:
    """Registra o atalho e devolve a função que o remove.

    Com `hold_s` > 0, `hotkey` é uma tecla só que precisa ser segurada; senão, uma combinação.
    """
    if hold_s > 0:
        detector = HoldDetector(hold_s, callback)

        def on_event(event):
            if event.event_type == keyboard.KEY_DOWN:
                detector.press(any(keyboard.is_pressed(m) for m in MODIFIERS))
            else:
                detector.release()

        handle = keyboard.hook_key(hotkey, on_event, suppress=False)
        return lambda: keyboard.unhook(handle)

    handle = keyboard.add_hotkey(hotkey, lambda: threading.Thread(target=callback, daemon=True).start(),
                                 suppress=False)
    return lambda: keyboard.remove_hotkey(handle)
