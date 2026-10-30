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


ENVELOPE_FRAME_MS = 40


def speech_envelope(audio: np.ndarray, sr: int, frame_ms: int = ENVELOPE_FRAME_MS) -> list[float]:
    """Volume da fala ao longo do tempo (0..1 por quadro), usado para mexer a boca do rosto 3D."""
    frame = max(1, int(sr * frame_ms / 1000))
    count = -(-len(audio) // frame)
    padded = np.zeros(count * frame, dtype=np.float32)
    padded[:len(audio)] = audio
    rms = np.sqrt(np.mean(padded.reshape(count, frame) ** 2, axis=1))
    peak = float(rms.max()) if count else 0.0
    if peak < 1e-4:
        return [0.0] * count
    return [round(float(v), 3) for v in np.sqrt(np.clip(rms / peak, 0, 1))]


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
        self.on_play: Callable[[list[float], int], None] = lambda envelope, frame_ms: None
        # Duas etapas em paralelo: enquanto uma frase toca, a próxima já está sendo gerada.
        self._text_q: queue.Queue[tuple[int, str]] = queue.Queue()
        self._audio_q: queue.Queue[tuple[int, np.ndarray, int]] = queue.Queue()
        self._gen = 0             # muda a cada stop(); frases de gerações antigas são descartadas
        self._pending = 0         # frases pedidas e ainda não tocadas (ou descartadas)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._edge_ok = True
        threading.Thread(target=self._synth_worker, daemon=True).start()
        threading.Thread(target=self._play_worker, daemon=True).start()

    def say(self, text: str) -> None:
        if text.strip():
            with self._lock:
                self._pending += 1
                gen = self._gen
            self._text_q.put((gen, text))

    def stop(self) -> None:
        with self._lock:
            self._gen += 1
        self._stop.set()
        for q in (self._text_q, self._audio_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
                self._done_one()
        sd.stop()

    def wait_idle(self, timeout: float = 120) -> None:
        """Bloqueia até terminar de falar tudo o que foi pedido."""
        import time
        end = time.monotonic() + timeout
        while (self.speaking or self._pending > 0) and time.monotonic() < end:
            time.sleep(0.05)

    def _done_one(self) -> None:
        with self._lock:
            self._pending = max(0, self._pending - 1)
            finished = self._pending == 0 and self.speaking
            if finished:
                self.speaking = False
        if finished:
            self.on_end()

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

    def _synth_worker(self):
        while True:
            gen, text = self._text_q.get()
            if gen != self._gen:
                self._done_one()
                continue
            try:
                audio, sr = self._synth(text)
            except Exception:
                log.exception("não consegui gerar a fala")
                self._done_one()
                continue
            self._audio_q.put((gen, audio, sr))

    def _play_worker(self):
        while True:
            gen, audio, sr = self._audio_q.get()
            if gen == self._gen:
                self._stop.clear()
                start = False
                with self._lock:
                    if not self.speaking:
                        self.speaking = start = True
                if start:
                    self.on_start()
                try:
                    self.on_play(speech_envelope(audio, sr), ENVELOPE_FRAME_MS)
                except Exception:
                    log.exception("não consegui mandar o volume para o rosto")
                try:
                    self._play(audio, sr)
                except Exception:
                    log.exception("não consegui tocar a fala")
            self._done_one()


if __name__ == "__main__":
    import sys
    s = Speaker(Config())
    s.say(" ".join(sys.argv[1:]) or "Olá, eu sou a Lia.")
    import time
    time.sleep(0.2)
    s.wait_idle()
