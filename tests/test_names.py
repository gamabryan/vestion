"""O Whisper erra o nome "Vestion"; corrigimos as variações no começo da frase (erros reais medidos)."""
import pytest

from lia.audio import stt
from lia.confirm import parse_voice_approval
from lia.names import canonical_name


@pytest.mark.parametrize("heard, fixed", [
    ("Vestiam, abre o crome para mim.", "Vestion, abre o crome para mim."),
    ("Vestil, que horas são?", "Vestion, que horas são?"),
    ("Vessão, abre o crome para mim.", "Vestion, abre o crome para mim."),
    ("Vis-tion! Abra o Chrome para mim!", "Vestion! Abra o Chrome para mim!"),
    ("Viste um. Que horas são?", "Vestion. Que horas são?"),
    ("Ei, vestiam. Pesquisa o tempo amanhã.", "Ei, Vestion. Pesquisa o tempo amanhã."),
    ("Vestion, que horas são?", "Vestion, que horas são?"),
])
def test_misheard_name_is_fixed(heard, fixed):
    assert canonical_name(heard) == fixed


@pytest.mark.parametrize("text", ["Veja só que legal.", "Vestido azul, por favor.", "Não pode.",
                                  "Que horas são?", "Investe em ações?", "Vou sair agora."])
def test_other_phrases_untouched(text):
    assert canonical_name(text) == text


def test_approval_with_misheard_name():
    assert parse_voice_approval("Vestil, pode mandar.")
    assert not parse_voice_approval("Não pode.")
    assert not parse_voice_approval("Vestil, não pode.")


def test_whisper_gets_name_hint():
    assert "Vestion" in stt.WHISPER_HINTS["initial_prompt"]
    assert stt.WHISPER_HINTS["hotwords"] == "Vestion"


@pytest.mark.parametrize("heard, fixed", [
    ("Investiam. Pesquisa o tempo amanhã.", "Ei, Vestion. Pesquisa o tempo amanhã."),
    ("Envestiom, abre o Chrome.", "Ei, Vestion, abre o Chrome."),
])
def test_hey_name_glued_together_is_fixed(heard, fixed):
    assert canonical_name(heard) == fixed


@pytest.mark.parametrize("text", ["Investimento em ações rende quanto?", "Investe tudo.", "Investiram ontem na bolsa.",
                                  "Envie o arquivo.", "Investido."])
def test_real_in_words_untouched(text):
    assert canonical_name(text) == text
