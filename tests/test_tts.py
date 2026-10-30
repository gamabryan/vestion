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
    played = []
    monkeypatch.setattr(tts, "synth_edge", lambda text, voice: (np.full(1, len(played), dtype=np.float32), 24000))
    speaker = Speaker(Config())
    monkeypatch.setattr(speaker, "_play", lambda audio, sr: (played.append(1), time.sleep(0.2)))
    for i in range(5):
        speaker.say(f"frase {i}")
    assert _wait(lambda: played)
    speaker.stop()
    time.sleep(0.6)
    assert len(played) <= 2  # o que já estava gerado não é tocado depois do stop
    assert _wait(lambda: not speaker.speaking)
    speaker.say("nova frase")  # depois de parar, volta a falar normalmente
    assert _wait(lambda: len(played) >= 2 and not speaker.speaking)


def test_callbacks_fire(monkeypatch):
    events = []
    monkeypatch.setattr(tts, "synth_edge", lambda text, voice: (np.zeros(10, dtype=np.float32), 24000))
    speaker = Speaker(Config())
    monkeypatch.setattr(speaker, "_play", lambda audio, sr: None)
    speaker.on_start = lambda: events.append("start")
    speaker.on_end = lambda: events.append("end")
    speaker.say("Oi.")
    assert _wait(lambda: events == ["start", "end"])


def test_next_sentence_synthesized_while_current_plays(monkeypatch):
    log = []

    def slow_synth(text, voice):
        log.append(("synth_start", text, time.time()))
        time.sleep(0.3)
        return np.zeros(10, dtype=np.float32), 24000

    monkeypatch.setattr(tts, "synth_edge", slow_synth)
    speaker = Speaker(Config())

    def slow_play(audio, sr):
        log.append(("play_start", None, time.time()))
        time.sleep(0.3)
        log.append(("play_end", None, time.time()))

    monkeypatch.setattr(speaker, "_play", slow_play)
    start = time.time()
    for f in ("Um.", "Dois.", "Três."):
        speaker.say(f)
    time.sleep(0.1)
    speaker.wait_idle(5)
    total = time.time() - start
    second_synth = [t for k, txt, t in log if k == "synth_start" and txt == "Dois."][0]
    first_play_end = [t for k, _, t in log if k == "play_end"][0]
    assert second_synth < first_play_end  # gerou a próxima enquanto tocava
    assert total < 1.5  # em série seriam ~1.8 s
