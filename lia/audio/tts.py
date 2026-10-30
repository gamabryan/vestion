"""A voz da Lia: voz neural gratuita da Microsoft (edge-tts) e, sem internet, Piper offline."""
import asyncio
import logging
import queue
import threading
from pathlib import Path
from typing import Callable

import miniaudio
import numpy as np
import sounddevice as sd

from lia.config import Config

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
log = logging.getLogger(__name__)


def synth_edge(text: str, voice: str) -> tuple[np.ndarray, int]:
    import edge_tts

    async def run() -> bytes:
        data = bytearray()
        async for chunk in edge_tts.Communicate(text, voice).stream():
            if chunk["type"] == "audio":
                data.extend(chunk["data"])
        return bytes(data)

    mp3 = asyncio.run(run())
    if not mp3:
        raise OSError("edge-tts não devolveu áudio")
    decoded = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1)
    return np.asarray(decoded.samples, dtype=np.float32), decoded.sample_rate


_piper_voices: dict = {}


def synth_piper(text: str, voice: str) -> tuple[np.ndarray, int]:
    from piper import PiperVoice
    if voice not in _piper_voices:
        model = MODELS_DIR / f"{voice}.onnx"
        if not model.exists():
            from piper.download_voices import download_voice
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            download_voice(voice, MODELS_DIR)
        _piper_voices[voice] = PiperVoice.load(model)
    pv = _piper_voices[voice]
    pcm = b"".join(c.audio_int16_bytes for c in pv.synthesize(text))
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    return audio, pv.config.sample_rate


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.speaking = False
        self.on_start: Callable[[], None] = lambda: None
        self.on_end: Callable[[], None] = lambda: None
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._edge_ok = True
        threading.Thread(target=self._worker, daemon=True).start()

    def say(self, text: str) -> None:
        if text.strip():
            self._queue.put(text)

    def stop(self) -> None:
        self._stop.set()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        sd.stop()

    def wait_idle(self, timeout: float = 120) -> None:
        """Bloqueia até terminar de falar tudo o que está na fila."""
        import time
        end = time.monotonic() + timeout
        while (self.speaking or not self._queue.empty()) and time.monotonic() < end:
            time.sleep(0.05)

    def _synth(self, text: str) -> tuple[np.ndarray, int]:
        if self._edge_ok:
            try:
                return synth_edge(text, self.cfg.voice)
            except Exception as e:
                self._edge_ok = False
                log.warning("edge-tts falhou (%s); usando Piper até reiniciar", e)
        return synth_piper(text, self.cfg.piper_voice)

    def _play(self, audio: np.ndarray, sr: int) -> None:
        sd.play(audio, sr)
        stream = sd.get_stream()
        while stream.active and not self._stop.is_set():
            sd.sleep(50)
        if self._stop.is_set():
            sd.stop()

    def _worker(self):
        while True:
            text = self._queue.get()
            self._stop.clear()
            if not self.speaking:
                self.speaking = True
                self.on_start()
            try:
                audio, sr = self._synth(text)
                if not self._stop.is_set():
                    self._play(audio, sr)
            except Exception:
                log.exception("não consegui falar")
            if self._queue.empty() or self._stop.is_set():
                self.speaking = False
                self.on_end()


if __name__ == "__main__":
    import sys
    s = Speaker(Config())
    s.say(" ".join(sys.argv[1:]) or "Olá, eu sou a Lia.")
    import time
    time.sleep(0.2)
    s.wait_idle()
