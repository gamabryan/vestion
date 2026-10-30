"""Testes das correções da revisão final."""
import os
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from lia import brain as brain_mod
from lia.brain import BILLING_KEYS, BILLING_MSG, Brain, BrainEvent, build_command, clean_env, friendly_error, parse_line
from lia.config import Config
from lia.permissions import ALLOWED_TOOLS, START_MENUS, is_safe_to_open, open_target


# 1. Lista de "abrir sem perguntar" não pode ser contornada
@pytest.mark.parametrize("target", [r"C:\x\setup.bat.", r"C:\x\setup.cmd ", r"C:\x\a.CPL", r"C:\x\a.msc",
                                    r"C:\x\a.url", r"C:\x\a.appref-ms", r"C:\Users\PC\Downloads\evil.lnk",
                                    r"C:\x\app.exe", r"C:\x\semextensao"])
def test_unsafe_targets_refused(target):
    assert not is_safe_to_open(target)


def test_start_menu_shortcut_still_safe():
    assert is_safe_to_open(str(START_MENUS[0] / "Accessories" / "Paint.lnk"))


def test_open_target_refuses_trailing_dot_bat(tmp_path):
    bat = tmp_path / "x.bat"
    bat.write_text("echo hi", encoding="utf-8")
    assert open_target(str(bat) + ".") == "Por segurança não abro esse tipo de arquivo."


def test_bash_not_preallowed_at_all():
    assert not any(t.startswith("Bash") for t in ALLOWED_TOOLS)


# 3. Não herdar configurações pessoais do Claude Code
def test_command_isolates_user_settings():
    cmd = build_command("abc", False, Path("cfg.json"), ["Read"], [])
    assert cmd[cmd.index("--setting-sources") + 1] == "project"
    assert cmd[cmd.index("--permission-mode") + 1] == "default"


# 4. Todas as formas de cobrança por API ficam de fora
def test_clean_env_removes_all_billing_routes():
    env = {k: "1" for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                            "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")}
    env["PATH"] = "p"
    assert clean_env(env) == ({"PATH": "p"}, True)


def test_init_with_api_key_source_is_billing_event():
    assert parse_line('{"type":"system","subtype":"init","apiKeySource":"ANTHROPIC_API_KEY"}') == BrainEvent("billing", "ANTHROPIC_API_KEY")
    assert parse_line('{"type":"system","subtype":"init","apiKeySource":"none"}') is None


# 7. Sem conexão
@pytest.mark.parametrize("msg", ["API Error: Connection error.", "Unable to connect to API", "ETIMEDOUT", "request timed out"])
def test_friendly_error_offline_variants(msg):
    assert friendly_error(msg) == "Estou sem conexão agora."


# 4, 5, 8. Processo do Claude: stderr grande, travamento, cobrança e encerramento
def _fake_claude(tmp_path, monkeypatch, body):
    script = tmp_path / "fake_claude.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.setattr(brain_mod.shutil, "which", lambda name: "fake")
    monkeypatch.setattr(brain_mod, "build_command", lambda *a, **k: [sys.executable, str(script)])
    return Brain(Config(workspace=tmp_path / "ws"), Path("cfg.json"), lambda: None)


def test_large_stderr_does_not_deadlock(tmp_path, monkeypatch):
    b = _fake_claude(tmp_path, monkeypatch, """
        import sys
        sys.stdin.read()
        sys.stderr.write("x" * 300000)
        sys.stderr.flush()
        print('{"type":"result","is_error":false,"result":"ok"}', flush=True)
    """)
    out = []
    t = threading.Thread(target=lambda: out.extend(b.ask("oi")))
    t.start()
    t.join(15)
    assert not t.is_alive()
    assert out[-1].kind == "done"


def test_hung_claude_is_killed_by_watchdog(tmp_path, monkeypatch):
    b = _fake_claude(tmp_path, monkeypatch, """
        import sys, time
        sys.stdin.read()
        time.sleep(60)
    """)
    b.idle_timeout_s = 1.0
    start = time.time()
    out = list(b.ask("oi"))
    assert time.time() - start < 15
    assert out[-1].kind == "error"


def test_watchdog_waits_while_card_pending(tmp_path, monkeypatch):
    b = _fake_claude(tmp_path, monkeypatch, """
        import sys, time
        sys.stdin.read()
        time.sleep(2.5)
        print('{"type":"result","is_error":false,"result":"ok"}', flush=True)
    """)
    b.idle_timeout_s = 1.0
    b.is_waiting_user = lambda: True
    assert list(b.ask("oi"))[-1].kind == "done"


def test_api_key_source_aborts_turn(tmp_path, monkeypatch):
    b = _fake_claude(tmp_path, monkeypatch, """
        import sys, time
        sys.stdin.read()
        print('{"type":"system","subtype":"init","apiKeySource":"ANTHROPIC_API_KEY"}', flush=True)
        time.sleep(30)
        print('{"type":"result","is_error":false,"result":"cobrou"}', flush=True)
    """)
    start = time.time()
    out = list(b.ask("oi"))
    assert time.time() - start < 15
    assert out[-1] == BrainEvent("error", BILLING_MSG)
    assert friendly_error(BILLING_MSG) == BILLING_MSG


def test_kill_stops_running_claude(tmp_path, monkeypatch):
    b = _fake_claude(tmp_path, monkeypatch, """
        import sys, time
        sys.stdin.read()
        time.sleep(60)
    """)
    out = []
    t = threading.Thread(target=lambda: out.extend(b.ask("oi")))
    t.start()
    time.sleep(1.5)
    b.kill()
    t.join(10)
    assert not t.is_alive()


def test_usage_and_request_count_survive_restart(tmp_path, monkeypatch):
    b = _fake_claude(tmp_path, monkeypatch, """
        import sys
        sys.stdin.read()
        print('{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","unifiedWindows":{"five_hour":{"utilization":0.42,"resetsAt":9999999999}}}}', flush=True)
        print('{"type":"result","is_error":false,"result":"ok"}', flush=True)
    """)
    list(b.ask("oi"))
    list(b.ask("oi de novo"))
    reopened = Brain(Config(workspace=tmp_path / "ws"), Path("cfg.json"), lambda: None)
    assert reopened.usage_pct == 42
    assert reopened.requests_today == 2


def test_old_usage_from_finished_window_is_dropped(tmp_path):
    import json
    ws = tmp_path / "ws"
    (ws / ".lia").mkdir(parents=True)
    (ws / ".lia" / "usage.json").write_text(json.dumps({"day": "2000-01-01", "requests": 9, "pct": 80, "resets_at": 1}), encoding="utf-8")
    b = Brain(Config(workspace=ws), Path("cfg.json"), lambda: None)
    assert b.usage_pct is None and b.requests_today == 0
