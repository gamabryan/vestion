"""Corta o texto que chega do Claude em frases, para a Lia começar a falar antes da resposta acabar."""
import re

ABBREVIATIONS = {"sr", "sra", "srta", "dr", "dra", "prof", "profa", "eng", "av", "etc", "nº", "n", "obs"}
_BOUNDARY = re.compile(r"([.!?…]+)(\s+)|\n+")


class SentenceBuffer:
    def __init__(self):
        self._buf = ""

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        out = []
        start = 0
        for m in _BOUNDARY.finditer(self._buf):
            if m.group(1) == ".":
                words = self._buf[start:m.start()].split()
                if words and words[-1].lower().strip("(") in ABBREVIATIONS:
                    continue
            end = m.end(1) if m.group(1) else m.start()
            sentence = self._buf[start:end].strip()
            if sentence:
                out.append(sentence)
            start = m.end()
        self._buf = self._buf[start:]
        return out

    def flush(self) -> list[str]:
        rest, self._buf = self._buf.strip(), ""
        return [rest] if rest else []


def for_speech(text: str) -> str:
    """Tira a formatação markdown para não ser lida em voz alta."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*(#+|[-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`#>|~]", "", text)
    return " ".join(text.split())
