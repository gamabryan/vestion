"""Segurar o Tab chama o Vestion; um toque rápido e o Alt+Tab não."""
import time

from lia.config import Config
from lia.hotkey import HoldDetector

HOLD = 0.05


def make():
    fired = []
    return HoldDetector(HOLD, lambda: fired.append(1)), fired


def test_holding_fires_once_despite_key_repeat():
    det, fired = make()
    det.press(modifiers=False)
    for _ in range(5):  # repetição automática do teclado enquanto segura
        time.sleep(HOLD / 3)
        det.press(modifiers=False)
    time.sleep(HOLD * 3)
    det.release()
    assert fired == [1]


def test_quick_tap_does_not_fire():
    det, fired = make()
    det.press(modifiers=False)
    det.release()
    time.sleep(HOLD * 3)
    assert fired == []


def test_with_modifier_does_not_fire():
    det, fired = make()
    det.press(modifiers=True)  # Alt+Tab, Ctrl+Tab, Shift+Tab
    time.sleep(HOLD * 3)
    det.release()
    assert fired == []


def test_can_fire_again_after_release():
    det, fired = make()
    for _ in range(2):
        det.press(modifiers=False)
        time.sleep(HOLD * 3)
        det.release()
    assert fired == [1, 1]


def test_default_is_hold_tab():
    cfg = Config()
    assert cfg.hotkey == "tab"
    assert cfg.hotkey_hold_s == 0.4
