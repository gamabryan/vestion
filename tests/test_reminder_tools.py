import json
from datetime import datetime

import pytest

from lia import mcp_server
from lia.permissions import describe_action, make_describer, needs_confirmation
from lia.reminders import ReminderStore

LOCAL = datetime.now().astimezone().tzinfo


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = ReminderStore(tmp_path / "lembretes.json")
    monkeypatch.setattr(mcp_server, "_reminders", lambda: s)
    return s


def test_criar_with_time_and_without(store):
    out = mcp_server.lembrete_criar("pagar a conta", "2026-10-31T10:00")
    assert "criado" in out.lower()
    mcp_server.lembrete_criar("comprar ração")
    items = store.all()
    assert datetime.fromisoformat(items[0]["quando"]) == datetime(2026, 10, 31, 10, tzinfo=LOCAL)
    assert items[1]["quando"] is None


def test_listar_returns_pending_json(store):
    store.add("a")
    done = store.add("b")
    store.complete(done["id"])
    items = json.loads(mcp_server.lembrete_listar())
    assert [r["texto"] for r in items] == ["a"]


def test_concluir_and_apagar(store):
    r = store.add("x")
    assert "feito" in mcp_server.lembrete_concluir(r["id"]).lower()
    assert "apagado" in mcp_server.lembrete_apagar(r["id"]).lower()
    assert store.all() == []
    assert "não encontrei" in mcp_server.lembrete_apagar("zzz").lower()


@pytest.mark.parametrize("tool", ["lembrete_criar", "lembrete_listar", "lembrete_concluir", "lembrete_apagar"])
def test_all_reminder_tools_run_directly(tool):
    assert not needs_confirmation(f"mcp__lia__{tool}", {"texto": "x", "id": "1"})


def test_delete_card_shows_real_text(tmp_path):
    s = ReminderStore(tmp_path / "lembretes.json")
    r = s.add("renovar a CNH")
    card = make_describer(lambda: None, reminders=s)("mcp__lia__lembrete_apagar", {"id": r["id"]})
    assert card.title == "Apagar lembrete"
    assert card.detail == "renovar a CNH"
    assert card.spoken == "Posso apagar o lembrete que está na tela?"
    assert describe_action("mcp__lia__lembrete_apagar", {"id": "q"}).title == "Apagar lembrete"
