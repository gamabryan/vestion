"""Corrige o nome "Vestion" quando o Whisper o entende errado no começo da frase."""
import difflib
import re
import unicodedata

NAME = "Vestion"
_KEY = "vestion"
# Palavras reais parecidas com o nome, que nunca devem virar "Vestion".
REAL_WORDS = {"vestido", "vestida", "vestidos", "vestidas", "vestir", "vestiu", "veste", "vestem", "vestindo",
              "vestiario", "vestibular", "vestigio", "visto", "vista", "vistos", "vistas", "visao", "vision"}
# Erros de duas palavras vistos nas medições.
TWO_WORD_VARIANTS = {"visteum", "vestium", "vestieu"}
MIN_SIMILARITY = 0.6

_START = re.compile(r"^(\s*(?:ei|oi|ola|olá)[,!.]?\s+)?([^\W\d_][\w\-]*)(\s+[^\W\d_]+)?", re.IGNORECASE)


def _key(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in word if c.isalpha() and not unicodedata.combining(c))


def _is_name(word: str) -> bool:
    key = _key(word)
    if not key or key in REAL_WORDS or key[0] not in "vw":
        return False
    return difflib.SequenceMatcher(None, key, _KEY).ratio() >= MIN_SIMILARITY


def canonical_name(text: str) -> str:
    m = _START.match(text)
    if not m:
        return text
    prefix, first, second = m.group(1) or "", m.group(2), m.group(3)
    if _is_name(first):
        return prefix + NAME + text[m.end(2):]
    # "Ei Vestion" grudado numa palavra só ("Investiam.", "Envestiom,"): só com pontuação logo depois,
    # para não mexer em frases como "Investiram ontem".
    rest = text[m.end(2):]
    if not prefix and _key(first)[:2] in ("in", "en", "ei") and rest[:1] in (",", ".", "!", "?") \
            and _is_name(_key(first)[2:]):
        return "Ei, " + NAME + rest
    if second and _key(first + second) in TWO_WORD_VARIANTS:
        return prefix + NAME + text[m.end(3):]
    return text
