"""Tecla de atalho global para chamar a Lia."""
import threading
from typing import Callable

import keyboard


def register_hotkey(hotkey: str, callback: Callable[[], None]) -> Callable[[], None]:
    """Registra o atalho; o callback roda numa thread própria. Devolve a função que remove o atalho."""
    handle = keyboard.add_hotkey(hotkey, lambda: threading.Thread(target=callback, daemon=True).start(),
                                 suppress=False)
    return lambda: keyboard.remove_hotkey(handle)
