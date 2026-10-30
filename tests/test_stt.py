import pytest

from lia.audio import stt
from lia.audio.stt import Listener, MicUnavailable, pick_whisper_model
from lia.config import Config


def test_pick_model_auto_cuda():
    assert pick_whisper_model("auto", True) == "medium"


def test_pick_model_auto_cpu():
    assert pick_whisper_model("auto", False) == "small"


def test_pick_model_explicit():
    assert pick_whisper_model("tiny", True) == "tiny"


def test_no_input_device_raises_mic_unavailable(monkeypatch):
    monkeypatch.setattr(stt.sd, "query_devices", lambda: [{"name": "alto-falante", "max_input_channels": 0}])
    with pytest.raises(MicUnavailable):
        Listener(Config()).listen_once()


def test_muted_returns_empty():
    listener = Listener(Config())
    listener.muted = True
    assert listener.listen_once() == ""
