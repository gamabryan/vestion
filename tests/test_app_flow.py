import os
import threading
import time

from lia.app import API_KEY_WARNING, LiaApp
from lia.audio.stt import MicUnavailable
from lia.brain import BrainEvent
from lia.config import Config
from lia.confirm import ConfirmBridge
from lia.permissions import ActionCard


class FakeBrain:
    def __init__(self, scripts=None, delay=0.0):
        self.scripts = scripts or {}
        self.delay = delay
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.requests_today = 0
        self.limit_hit = False
        self.usage_pct = None
        self.new_sessions = 0

    def needs_new_session(self, now):
        return False

    def new_session(self):
        self.new_sessions += 1

    def ask(self, text):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(text)
        try:
            time.sleep(self.delay)
            yield from self.scripts.get(text, [BrainEvent("text", "Ok. "), BrainEvent("done")])
        finally:
            self.active -= 1


class FakeSpeaker:
    def __init__(self):
        self.said = []
        self.stops = 0
        self.speaking = False
        self.on_start = lambda: None
        self.on_end = lambda: None

    def say(self, text):
        self.said.append(text)

    def stop(self):
        self.stops += 1

    def wait_idle(self, timeout=120):
        pass


class FakeListener:
    def __init__(self, answers):
        self.answers = list(answers)
        self.muted = False

    def listen_once(self, max_seconds=20):
        ans = self.answers.pop(0) if self.answers else ""
        if isinstance(ans, Exception):
            raise ans
        return ans


class FakeWindow:
    def __init__(self):
        self.captions = []
        self.states = []
        self.confirms = []
        self.shown = 0

    def show(self):
        self.shown += 1

    def hide(self):
        pass

    def destroy(self):
        pass

    def set_state(self, s):
        self.states.append(s)

    def caption(self, text, who="lia"):
        self.captions.append((who, text))

    def show_confirm(self, rid, card):
        self.confirms.append(rid)

    def hide_confirm(self, rid):
        pass

    def update_panel(self, name, data):
        pass


def make_app(answers, brain=None):
    cfg = Config(confirm_timeout_s=2, voice_confirm_window_s=1)
    holder = {}
    bridge = ConfirmBridge(cfg.confirm_timeout_s, lambda r, c: holder["app"].on_confirm_show(r, c),
                           lambda r: holder["app"].on_confirm_hide(r))
    app = LiaApp(cfg, brain or FakeBrain(), FakeListener(answers), FakeSpeaker(), FakeWindow(), bridge)
    holder["app"] = app
    return app


def wait_until(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_utterance_streams_sentences_to_speaker():
    brain = FakeBrain({"que horas são": [BrainEvent("text", "São **três** horas. Quer "),
                                         BrainEvent("text", "mais algo?"), BrainEvent("done")]})
    app = make_app(["que horas são"], brain)
    app.on_hotkey()
    assert app.wait_jobs()
    assert app.speaker.said == ["São três horas.", "Quer mais algo?"]
    assert ("user", "que horas são") in app.window.captions


def test_hotkey_while_speaking_stops_speech_and_queues():
    brain = FakeBrain(delay=0.2)
    app = make_app(["primeiro", "segundo"], brain)
    app.on_hotkey()
    app.on_hotkey()
    assert app.wait_jobs()
    assert brain.calls == ["primeiro", "segundo"]
    assert brain.max_active == 1
    assert app.speaker.stops >= 2


def test_voice_answer_consumed_when_card_pending():
    brain = FakeBrain()
    app = make_app([], brain)
    result = []
    t = threading.Thread(target=lambda: result.append(app.bridge.request(ActionCard("T", "D", "T. Posso?"))))
    t.start()
    assert wait_until(lambda: app.window.confirms)
    # a janela de voz abre depois de a Lia ler o cartão; a escuta automática não ouviu nada
    assert wait_until(lambda: any(p.voice_deadline for p in app.bridge._pending.values()))
    app.listener.answers = ["pode"]
    app.on_hotkey()
    t.join(3)
    assert result == [True]
    assert brain.calls == []
    assert "T. Posso?" in app.speaker.said


def test_empty_utterance_does_not_call_brain():
    brain = FakeBrain()
    app = make_app([""], brain)
    app.on_hotkey()
    assert app.wait_jobs()
    assert brain.calls == []
    assert app.window.states[-1] == "idle"


def test_brain_error_spoken_friendly():
    brain = FakeBrain({"oi": [BrainEvent("error", "getaddrinfo ENOTFOUND api.anthropic.com")]})
    app = make_app(["oi"], brain)
    app.on_hotkey()
    assert app.wait_jobs()
    assert app.speaker.said[-1] == "Estou sem conexão agora."


def test_mic_unavailable_spoken():
    app = make_app([MicUnavailable("sem mic")])
    app.on_hotkey()
    assert app.speaker.said[-1] == "Não encontrei um microfone."
    assert app.window.states[-1] == "idle"


def test_quit_denies_pending_confirmation():
    app = make_app([])
    result = []
    t = threading.Thread(target=lambda: result.append(app.bridge.request(ActionCard("T", "D", "T. Posso?"))))
    t.start()
    assert wait_until(lambda: app.window.confirms)
    app.quit()
    t.join(3)
    assert result == [False]


def test_api_key_warning_caption(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    app = make_app([])
    app.start(run_background=False)
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert ("lia", API_KEY_WARNING) in app.window.captions
    assert "Oi, estou pronto." in app.speaker.said


# 6. Atalho no meio da resposta: frases antigas não são mais faladas
def test_hotkey_drops_rest_of_previous_answer():
    gate = threading.Event()

    class SlowBrain(FakeBrain):
        def ask(self, text):
            self.calls.append(text)
            if text == "primeiro":
                yield BrainEvent("text", "Frase um. ")
                gate.wait(3)
                yield BrainEvent("text", "Frase velha. ")
                yield BrainEvent("done")
            else:
                yield BrainEvent("text", "Resposta nova. ")
                yield BrainEvent("done")

    app = make_app(["primeiro", "segundo"], SlowBrain())
    app.on_hotkey()
    assert wait_until(lambda: "Frase um." in app.speaker.said)
    threading.Thread(target=lambda: (time.sleep(0.2), gate.set())).start()
    app.on_hotkey()
    assert app.wait_jobs()
    assert "Frase velha." not in app.speaker.said
    assert "Resposta nova." in app.speaker.said


# Promovido: "pode" pelo atalho enquanto o cartão ainda é lido
def test_hotkey_answer_counts_even_before_voice_window():
    app = make_app([])
    app.speaker.wait_idle = lambda timeout=120: time.sleep(5)  # ainda lendo o cartão
    result = []
    t = threading.Thread(target=lambda: result.append(app.bridge.request(ActionCard("T", "D", "T. Posso?"))))
    t.start()
    assert wait_until(lambda: app.window.confirms)
    app.listener.answers = ["pode"]
    app.on_hotkey()
    t.join(3)
    assert result == [True]
    assert app.brain.calls == []


# Promovido: erro inesperado ao ouvir não deixa a central travada em "ouvindo"
def test_unexpected_listen_error_resets_state():
    app = make_app([RuntimeError("falha ao baixar modelo")])
    app.on_hotkey()
    assert app.window.states[-1] == "idle"
    assert app.speaker.said[-1] == "Tive um problema e não consegui fazer isso."


# 8. Sair encerra o Claude em andamento
def test_quit_kills_brain():
    brain = FakeBrain()
    killed = []
    brain.kill = lambda: killed.append(True)
    app = make_app([], brain)
    app.quit()
    assert killed == [True]


def test_speaker_envelope_reaches_face():
    app = make_app([])
    spoken = []
    app.window.speak = lambda env, ms: spoken.append((env, ms))
    app.speaker.on_play([0.1, 0.9], 40)
    assert spoken == [([0.1, 0.9], 40)]
