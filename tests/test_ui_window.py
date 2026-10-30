"""A janela só deve aparecer/restaurar quando estiver escondida ou minimizada."""
import threading

from lia.ui_window import CentralWindow


class FakeWebviewWindow:
    def __init__(self):
        self.calls = []

    def show(self):
        self.calls.append("show")

    def hide(self):
        self.calls.append("hide")

    def restore(self):
        self.calls.append("restore")


def make():
    win = CentralWindow.__new__(CentralWindow)
    win.window = FakeWebviewWindow()
    win._loaded = threading.Event()
    win._quitting = False
    win._hidden = False
    win._minimized = False
    return win


def test_show_when_visible_and_maximized_does_nothing():
    win = make()
    win.show()
    assert win.window.calls == []


def test_show_after_hide_shows_without_restore():
    win = make()
    win.hide()
    win.show()
    assert win.window.calls == ["hide", "show"]


def test_show_when_minimized_restores_once():
    win = make()
    win._on_minimized()
    win.show()
    assert win.window.calls == ["restore"]
    win.show()
    assert win.window.calls == ["restore"]


def test_closing_hides_and_next_show_brings_it_back():
    win = make()
    assert win._on_closing() is False
    win.show()
    assert win.window.calls == ["hide", "show"]


def test_window_opens_fullscreen(monkeypatch):
    from lia import ui_window

    created = {}

    class FakeEvents:
        def __getattr__(self, name):
            class Hook:
                def __iadd__(self, fn):
                    return self
            return Hook()

    class FakeWin:
        events = FakeEvents()

    def fake_create_window(*args, **kwargs):
        created.update(kwargs)
        return FakeWin()

    monkeypatch.setattr(ui_window.webview, "create_window", fake_create_window)
    CentralWindow(lambda rid, ok: None)
    assert created.get("fullscreen") is True


def test_esc_from_page_hides_window():
    from lia.ui_window import _JsApi
    win = make()
    api = _JsApi(lambda rid, ok: None, on_hide=win.hide)
    api.hide()
    assert win.window.calls == ["hide"]
    win.show()
    assert win.window.calls == ["hide", "show"]


def test_reminders_are_voice_only_no_manual_add():
    from lia.ui_window import UI_DIR, _JsApi
    api = _JsApi(lambda rid, ok: None)
    assert not hasattr(api, "reminder_add")
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    js = (UI_DIR / "app.js").read_text(encoding="utf-8")
    assert "reminder-form" not in html and "novo lembrete" not in html
    assert "reminder_add" not in js and "check" not in js.split("function fillRows")[1].split("}\n\n")[0]


def test_alert_buttons_still_answer_reminder():
    from lia.ui_window import _JsApi
    calls = []
    api = _JsApi(lambda rid, ok: None, on_reminder_done=lambda rid: calls.append(("done", rid)),
                 on_reminder_snooze=lambda rid: calls.append(("snooze", rid)))
    api.reminder_done("ab12")
    api.reminder_snooze("cd34")
    assert calls == [("done", "ab12"), ("snooze", "cd34")]
