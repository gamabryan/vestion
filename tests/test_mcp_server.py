import json

from lia import mcp_server
from lia.mcp_config import write_mcp_config


def test_confirmar_allow_echoes_input(monkeypatch):
    monkeypatch.setattr(mcp_server, "_ask_bridge", lambda tool_name, tool_input: True)
    out = json.loads(mcp_server.lia_confirmar("Write", {"file_path": "a.txt", "content": "x"}))
    assert out == {"behavior": "allow", "updatedInput": {"file_path": "a.txt", "content": "x"}}


def test_confirmar_deny(monkeypatch):
    monkeypatch.setattr(mcp_server, "_ask_bridge", lambda tool_name, tool_input: False)
    out = json.loads(mcp_server.lia_confirmar("Bash", {"command": "del x"}))
    assert out == {"behavior": "deny", "message": "O usuário não autorizou."}


def test_confirmar_bridge_down_denies(monkeypatch):
    monkeypatch.setenv("LIA_BRIDGE_PORT", "1")
    monkeypatch.setenv("LIA_BRIDGE_TOKEN", "x")
    out = json.loads(mcp_server.lia_confirmar("Bash", {"command": "del x"}))
    assert out["behavior"] == "deny"


def test_abrir_refuses_bat():
    assert mcp_server.lia_abrir(r"C:\x\run.bat") == "Por segurança não abro esse tipo de arquivo."


def test_mcp_config_shape(tmp_path):
    path = write_mcp_config(tmp_path / "mcp.json", 1234, "tok")
    lia = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["lia"]
    assert lia["args"] == ["-m", "lia.mcp_server"]
    assert lia["env"]["LIA_BRIDGE_PORT"] == "1234"
    assert lia["env"]["LIA_BRIDGE_TOKEN"] == "tok"
    assert "PYTHONPATH" in lia["env"]


def test_confirmar_returns_plain_text_not_structured(monkeypatch):
    import asyncio
    monkeypatch.setattr(mcp_server, "_ask_bridge", lambda tool_name, tool_input: True)
    result = asyncio.run(mcp_server.server.call_tool("lia_confirmar", {"tool_name": "Bash", "input": {"command": "dir"}}))
    assert result.structured_content is None
    assert json.loads(result.content[0].text)["behavior"] == "allow"
