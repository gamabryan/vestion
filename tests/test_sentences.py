from lia.sentences import SentenceBuffer, for_speech


def test_buffer_splits_on_period_space():
    buf = SentenceBuffer()
    assert buf.feed("Oi, tudo bem. Você tem ") == ["Oi, tudo bem."]
    assert buf.feed("três compromissos! Quer ouvir? ") == ["Você tem três compromissos!", "Quer ouvir?"]


def test_buffer_keeps_partial_until_flush():
    buf = SentenceBuffer()
    assert buf.feed("Sem ponto final") == []
    assert buf.flush() == ["Sem ponto final"]
    assert buf.flush() == []


def test_buffer_splits_on_newline():
    assert SentenceBuffer().feed("Primeira linha\nSegunda") == ["Primeira linha"]


def test_buffer_does_not_split_decimal():
    buf = SentenceBuffer()
    assert buf.feed("O valor é 3.5 reais. ") == ["O valor é 3.5 reais."]


def test_buffer_does_not_split_time():
    buf = SentenceBuffer()
    assert buf.feed("A reunião é às 15:30. ") == ["A reunião é às 15:30."]


def test_buffer_does_not_split_sr():
    buf = SentenceBuffer()
    assert buf.feed("Ligue para o Sr. Carlos e a Dra. Ana. ") == ["Ligue para o Sr. Carlos e a Dra. Ana."]


def test_for_speech_strips_markdown():
    assert for_speech("**Oi** [site](http://x)") == "Oi site"
    assert for_speech("# Título\n- `item`  _um_") == "Título item um"
