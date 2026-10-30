import json
from datetime import datetime, timedelta

import pytest

from lia import mcp_server
from lia.mcp_config import write_mcp_config
from lia.permissions import describe_action, make_describer, needs_confirmation

NOT_CONNECTED = mcp_server.NOT_CONNECTED
LOCAL = datetime.now().astimezone().tzinfo


class FakeGmail:
    def __init__(self):
        self.sent = []

    def unread(self, n=5):
        return [{"id": "1", "de": "Ana", "assunto": "Oi", "trecho": "x", "importante": True}]

    def send(self, to, subject, body, reply_to_id=None):
        self.sent.append((to, subject, body, reply_to_id))
        return "m1"


class FakeCalendar:
    def __init__(self):
        self.created = []

    def events_between(self, start, end):
        return [{"id": "e1", "titulo": "Dentista", "inicio": datetime(2026, 10, 30, 10, tzinfo=LOCAL),
                 "fim": datetime(2026, 10, 30, 11, tzinfo=LOCAL), "dia_todo": False, "local": "", "convidados": 0}]

    def create(self, titulo, inicio, fim, convidados=None, local=""):
        self.created.append((titulo, inicio, fim, convidados))
        return "e2"

    def get(self, event_id):
        return {"id": event_id, "titulo": "Reunião real", "inicio": datetime(2026, 10, 30, 15, tzinfo=LOCAL),
                "fim": datetime(2026, 10, 30, 16, tzinfo=LOCAL), "dia_todo": False, "local": "", "convidados": 2}


@pytest.fixture
def connected(monkeypatch):
    g, c = FakeGmail(), FakeCalendar()
    monkeypatch.setattr(mcp_server, "_gmail", lambda: g)
    monkeypatch.setattr(mcp_server, "_calendar", lambda: c)
    return g, c


def test_tools_not_connected_message(monkeypatch):
    monkeypatch.setattr(mcp_server, "_gmail", lambda: None)
    monkeypatch.setattr(mcp_server, "_calendar", lambda: None)
    assert mcp_server.gmail_nao_lidos() == NOT_CONNECTED
    assert mcp_server.agenda_listar("2026-10-30T00:00", "2026-10-31T00:00") == NOT_CONNECTED
    assert "Conectar Google" in NOT_CONNECTED


def test_gmail_enviar_calls_send(connected):
    g, _ = connected
    assert "enviado" in mcp_server.gmail_enviar("ana@x.com", "Oi", "Tudo bem?").lower()
    assert g.sent == [("ana@x.com", "Oi", "Tudo bem?", None)]


def test_agenda_listar_returns_json(connected):
    items = json.loads(mcp_server.agenda_listar("2026-10-30T00:00", "2026-10-31T00:00"))
    assert items[0]["titulo"] == "Dentista" and items[0]["inicio"].startswith("2026-10-30T10:00")


def test_agenda_criar_parses_naive_times_as_local(connected):
    _, c = connected
    mcp_server.agenda_criar("Dentista", "2026-10-30T10:00", "2026-10-30T11:00")
    titulo, inicio, fim, convidados = c.created[0]
    assert inicio == datetime(2026, 10, 30, 10, tzinfo=LOCAL) and fim - inicio == timedelta(hours=1)


def test_mcp_config_passes_workspace(tmp_path):
    path = write_mcp_config(tmp_path / "mcp.json", 1, "t", workspace=tmp_path / "ws")
    env = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["lia"]["env"]
    assert env["LIA_WORKSPACE"] == str(tmp_path / "ws")


# Política: só o importante pede o cartão
@pytest.mark.parametrize("tool", ["gmail_nao_lidos", "gmail_buscar", "gmail_ler", "gmail_rascunho",
                                  "agenda_listar", "agenda_mover"])
def test_reads_draft_move_auto(tool):
    assert not needs_confirmation(f"mcp__lia__{tool}", {"id": "1"})


@pytest.mark.parametrize("tool", ["gmail_enviar", "agenda_cancelar"])
def test_send_and_cancel_ask(tool):
    assert needs_confirmation(f"mcp__lia__{tool}", {"id": "1", "para": "a@b.com"})


def test_create_with_guests_asks_without_guests_auto():
    assert needs_confirmation("mcp__lia__agenda_criar", {"titulo": "x", "convidados": ["a@b.com"]})
    assert not needs_confirmation("mcp__lia__agenda_criar", {"titulo": "x", "convidados": []})
    assert not needs_confirmation("mcp__lia__agenda_criar", {"titulo": "x"})


def test_email_card_shows_everything_but_speech_is_short():
    card = describe_action("mcp__lia__gmail_enviar", {"para": "ana.souza@empresa.com", "assunto": "Proposta", "texto": "Segue."})
    assert card.title == "Enviar e-mail"
    assert "ana.souza@empresa.com" in card.detail and "Proposta" in card.detail and "Segue." in card.detail
    assert card.spoken == "Posso enviar o e-mail que está na tela?"


def test_cancel_card_shows_real_event_not_claude_text():
    describe = make_describer(lambda: FakeCalendar())
    card = describe("mcp__lia__agenda_cancelar", {"id": "e7", "titulo": "Almoço inventado"})
    assert card.title == "Cancelar compromisso"
    assert card.detail == "Reunião real — 30/10 15:00"
    assert card.spoken == "Posso cancelar o compromisso que está na tela?"


def test_cancel_card_when_lookup_fails():
    def broken():
        raise OSError("sem internet")
    card = make_describer(broken)("mcp__lia__agenda_cancelar", {"id": "e7"})
    assert card.detail == "Compromisso id e7 (não consegui confirmar no Google)"


def test_create_with_guests_card():
    card = describe_action("mcp__lia__agenda_criar", {"titulo": "Reunião", "inicio": "2026-10-30T15:00",
                                                      "fim": "2026-10-30T16:00", "convidados": ["ana@x.com"]})
    assert card.title == "Criar compromisso e enviar convites"
    assert "ana@x.com" in card.detail and "Reunião" in card.detail
    assert card.spoken == "Posso criar o compromisso e mandar os convites?"


def test_moving_event_with_guests_asks_without_guests_runs():
    from lia.permissions import make_policy

    class Cal:
        def __init__(self, guests):
            self.guests = guests

        def get(self, event_id):
            return {"id": event_id, "titulo": "x", "inicio": datetime(2026, 10, 30, 10, tzinfo=LOCAL),
                    "fim": datetime(2026, 10, 30, 11, tzinfo=LOCAL), "dia_todo": False, "local": "", "convidados": self.guests}

    mover = ("mcp__lia__agenda_mover", {"id": "e1", "inicio": "2026-10-30T14:00", "fim": "2026-10-30T15:00"})
    assert make_policy(lambda: Cal(2))(*mover) is True
    assert make_policy(lambda: Cal(0))(*mover) is False


def test_moving_event_asks_when_lookup_fails():
    from lia.permissions import make_policy

    def broken():
        raise OSError("sem internet")
    assert make_policy(broken)("mcp__lia__agenda_mover", {"id": "e1"}) is True


def test_policy_wrapper_keeps_normal_rules():
    from lia.permissions import make_policy
    policy = make_policy(lambda: None)
    assert policy("Bash", {"command": "dir"}) is False
    assert policy("Bash", {"command": "del x"}) is True
    assert policy("WebFetch", {"url": "https://x"}, tainted=True) is True


def test_move_card_is_readable():
    card = describe_action("mcp__lia__agenda_mover", {"id": "e1", "inicio": "2026-10-30T14:00", "fim": "2026-10-30T15:00"})
    assert card.title == "Mudar horário de compromisso com convidados"
    assert "2026-10-30T14:00" in card.detail
    assert card.spoken == "Posso mudar o horário do compromisso que está na tela?"
