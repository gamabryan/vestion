import time

import numpy as np

from lia.audio import tts
from lia.audio.tts import Speaker
from lia.config import Config


def _wait(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_speaker_falls_back_to_piper_when_edge_fails(monkeypatch):
    calls = []

    def edge_fails(text, voice):
        calls.append("edge")
        raise OSError("sem internet")

    def piper_ok(text, voice):
        calls.append("piper")
        return np.zeros(100, dtype=np.float32), 22050

    monkeypatch.setattr(tts, "synth_edge", edge_fails)
    monkeypatch.setattr(tts, "synth_piper", piper_ok)
    speaker = Speaker(Config())
    monkeypatch.setattr(speaker, "_play", lambda audio, sr: None)
    speaker.say("Olá.")
    speaker.say("De novo.")
    assert _wait(lambda: calls.count("piper") == 2)
    assert calls.count("edge") == 1  # depois da primeira falha, só Piper nesta execução


def test_stop_clears_queue(monkeypatch):
    spoken = []
    monkeypatch.setattr(tts, "synth_edge", lambda text, voice: (spoken.append(text) or np.zeros(10, dtype=np.float32), 24000))
    speaker = Speaker(Config())
    monkeypatch.setattr(speaker, "_play", lambda audio, sr: time.sleep(0.2))
    for i in range(5):
        speaker.say(f"frase {i}")
    assert _wait(lambda: spoken)
    speaker.stop()
    time.sleep(0.5)
    assert len(spoken) <= 2
    assert _wait(lambda: not speaker.speaking)


def test_callbacks_fire(monkeypatch):
    events = []
    monkeypatch.setattr(tts, "synth_edge", lambda text, voice: (np.zeros(10, dtype=np.float32), 24000))
    speaker = Speaker(Config())
    monkeypatch.setattr(speaker, "_play", lambda audio, sr: None)
    speaker.on_start = lambda: events.append("start")
    speaker.on_end = lambda: events.append("end")
    speaker.say("Oi.")
    assert _wait(lambda: events == ["start", "end"])
