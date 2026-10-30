"""Ouvir o usuário: grava do microfone até ele parar de falar e transcreve localmente (Whisper)."""
import threading
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd

from lia.config import Config

SAMPLE_RATE = 16000
BLOCK = 512                      # 32 ms, tamanho de janela do Silero VAD
SILENCE_END_S = 0.8              # fim da fala
WAIT_SPEECH_S = 6.0              # desiste se ninguém falar
PRE_ROLL_BLOCKS = 10             # ~300 ms antes da fala, para não cortar o começo
SPEECH_PROB = 0.5
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class MicUnavailable(Exception):
    pass


def pick_whisper_model(setting: str, cuda: bool) -> str:
    if setting != "auto":
        return setting
    return "medium" if cuda else "small"


def _has_cuda() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Listener:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.muted = False
        self._model = None
        self._vad = None
        self._load_lock = threading.Lock()

    def preload(self) -> None:
        """Carrega os modelos em segundo plano para a primeira fala não demorar."""
        threading.Thread(target=self._ensure_models, daemon=True).start()

    def _ensure_models(self):
        with self._load_lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                from faster_whisper.vad import get_vad_model
                cuda = _has_cuda()
                name = pick_whisper_model(self.cfg.whisper_model, cuda)
                self._model = WhisperModel(name, device="cuda" if cuda else "cpu",
                                           compute_type="float16" if cuda else "int8",
                                           download_root=str(MODELS_DIR))
                self._vad = get_vad_model()
        return self._model, self._vad

    def _check_mic(self):
        try:
            devices = sd.query_devices()
        except Exception as e:
            raise MicUnavailable(str(e)) from e
        if not any(d.get("max_input_channels", 0) > 0 for d in devices):
            raise MicUnavailable("nenhum dispositivo de entrada")

    def _record(self, vad, max_seconds: float) -> np.ndarray | None:
        pre_roll: deque = deque(maxlen=PRE_ROLL_BLOCKS)
        speech: list[np.ndarray] = []
        silent_blocks = 0
        waited = 0
        end_blocks = int(SILENCE_END_S * SAMPLE_RATE / BLOCK)
        wait_blocks = int(WAIT_SPEECH_S * SAMPLE_RATE / BLOCK)
        max_blocks = int(max_seconds * SAMPLE_RATE / BLOCK)
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                blocksize=BLOCK) as stream:
                while True:
                    if self.muted:
                        return None
                    block, _ = stream.read(BLOCK)
                    block = block[:, 0].copy()
                    prob = float(vad(block)[0])
                    if not speech:
                        pre_roll.append(block)
                        if prob >= SPEECH_PROB:
                            speech.extend(pre_roll)
                        else:
                            waited += 1
                            if waited >= wait_blocks:
                                return None
                        continue
                    speech.append(block)
                    silent_blocks = silent_blocks + 1 if prob < SPEECH_PROB else 0
                    if silent_blocks >= end_blocks or len(speech) >= max_blocks:
                        break
        except sd.PortAudioError as e:
            raise MicUnavailable(str(e)) from e
        return np.concatenate(speech)

    def listen_once(self, max_seconds: float = 20) -> str:
        if self.muted:
            return ""
        self._check_mic()
        model, vad = self._ensure_models()
        audio = self._record(vad, max_seconds)
        if audio is None:
            return ""
        segments, _ = model.transcribe(audio, language="pt", beam_size=5, vad_filter=False)
        return " ".join(s.text.strip() for s in segments).strip()


if __name__ == "__main__":
    print("Fale algo...")
    print(Listener(Config()).listen_once())
