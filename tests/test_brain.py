from datetime import datetime, timedelta
from pathlib import Path

from lia import brain
from lia.brain import Brain, BrainEvent, build_command, clean_env, friendly_error, parse_line
from lia.config import Config

FIX = Path(__file__).parent / "fixtures"


def events(name):
    out = []
    for line in (FIX / name).read_text(encoding="utf-8").splitlines():
        ev = parse_line(line)
        if ev:
            out.append(ev)
    return out


def test_clean_env_removes_keys():
    env, removed = clean_env({"ANTHROPIC_API_KEY": "x", "ANTHROPIC_AUTH_TOKEN": "y", "PATH": "p"})
    assert env == {"PATH": "p"}
    assert removed is True
    assert clean_env({"PATH": "p"}) == ({"PATH": "p"}, False)


def _cmd(resume):
    return build_command("abc", resume, Path("cfg.json"), ["Read", "Glob"], ["C:\\", "D:\\"])


def test_build_command_first_turn_uses_session_id():
    cmd = _cmd(False)
    assert cmd[cmd.index("--session-id") + 1] == "abc"
    assert "--resume" not in cmd
    assert cmd[cmd.index("--permission-prompt-tool") + 1] == "mcp__lia__lia_confirmar"
    assert "--strict-mcp-config" in cmd
    assert cmd.count("--add-dir") == 2


def test_build_command_later_turn_uses_resume():
    cmd = _cmd(True)
    assert cmd[cmd.index("--resume") + 1] == "abc"
    assert "--session-id" not in cmd


def test_build_command_never_contains_prompt_text():
    assert not any("oi lia" in part for part in _cmd(False))


def test_parse_ok_fixture_yields_text_then_done():
    evs = [e for e in events("stream_ok.jsonl") if e.kind != "usage"]
    assert evs[0] == BrainEvent("text", "oi")
    assert evs[-1].kind == "done"


def test_parse_usage_event():
    usage = [e for e in events("stream_ok.jsonl") if e.kind == "usage"]
    assert usage == [BrainEvent("usage", "11")]


def test_parse_limit_fixture_yields_error():
    evs = events("stream_limit.jsonl")
    assert evs[-1].kind == "error"
    assert "limit" in evs[-1].text
    assert BrainEvent("limit") in evs


def test_parse_invalid_json_is_error():
    assert parse_line("isto não é json").kind == "error"


def test_friendly_error_limit():
    assert friendly_error("Claude AI usage limit reached").startswith("Atingi o limite")


def test_friendly_error_offline():
    assert friendly_error("getaddrinfo ENOTFOUND api.anthropic.com") == "Estou sem conexão agora."


def test_friendly_error_login():
    assert friendly_error("Not logged in. Please run /login") == "Preciso que você entre no Claude Code de novo."


def test_needs_new_session_after_2h(tmp_path):
    b = Brain(Config(workspace=tmp_path), Path("cfg.json"), lambda: None)
    t0 = datetime(2026, 10, 29, 10, 0)
    b.last_activity = t0
    assert not b.needs_new_session(t0 + timedelta(hours=1, minutes=59))
    assert b.needs_new_session(t0 + timedelta(hours=2))


def test_missing_claude_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(brain.shutil, "which", lambda name: None)
    b = Brain(Config(workspace=tmp_path), Path("cfg.json"), lambda: None)
    assert list(b.ask("oi")) == [BrainEvent("error", "Não encontrei o Claude Code instalado.")]
