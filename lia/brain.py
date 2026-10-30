"""O "cérebro" da Lia: roda o Claude Code instalado em modo não interativo, pelo plano do usuário."""
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, Literal

import psutil

from lia.config import Config
from lia.workspace import ensure_workspace

# Nunca deixar o subprocesso cobrar pela API em vez do plano.
BILLING_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

MISSING_CLAUDE = "Não encontrei o Claude Code instalado."
LIMIT_MSG = "Atingi o limite do seu plano por agora. Os painéis continuam funcionando."
LOGIN_MSG = "Preciso que você entre no Claude Code de novo."
OFFLINE_MSG = "Estou sem conexão agora."
GENERIC_MSG = "Tive um problema e não consegui fazer isso."
_FRIENDLY = {MISSING_CLAUDE, LIMIT_MSG, LOGIN_MSG, OFFLINE_MSG, GENERIC_MSG}

CREATE_NO_WINDOW = 0x08000000


@dataclass
class BrainEvent:
    kind: Literal["text", "done", "error", "usage", "limit"]
    text: str = ""


def clean_env(env: dict[str, str]) -> tuple[dict[str, str], bool]:
    cleaned = {k: v for k, v in env.items() if k not in BILLING_KEYS}
    return cleaned, len(cleaned) != len(env)


def fixed_drives() -> list[str]:
    return [p.mountpoint for p in psutil.disk_partitions(all=False) if "fixed" in p.opts]


def build_command(session_id: str, resume: bool, mcp_config: Path, allowed: list[str],
                  drives: list[str], exe: str = "claude") -> list[str]:
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
    cmd += ["--mcp-config", str(mcp_config), "--strict-mcp-config",
            "--permission-prompt-tool", "mcp__lia__lia_confirmar",
            "--allowedTools", ",".join(allowed)]
    for d in drives:
        cmd += ["--add-dir", d]
    return cmd


def parse_line(line: str) -> BrainEvent | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return BrainEvent("error", line.strip())
    kind = data.get("type")
    if kind == "stream_event":
        ev = data.get("event", {})
        delta = ev.get("delta", {})
        if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            return BrainEvent("text", delta.get("text", ""))
        return None
    if kind == "rate_limit_event":
        info = data.get("rate_limit_info", {})
        if info.get("status") == "rejected":
            return BrainEvent("limit")
        window = info.get("unifiedWindows", {}).get("five_hour", {})
        if "utilization" in window:
            return BrainEvent("usage", str(round(window["utilization"] * 100)))
        return None
    if kind == "result":
        if data.get("is_error"):
            return BrainEvent("error", str(data.get("result") or data.get("subtype") or "erro"))
        return BrainEvent("done")
    return None


def friendly_error(msg: str) -> str:
    if msg in _FRIENDLY:
        return msg
    if re.search(r"(?i)not logged in|/login|authenticat", msg):
        return LOGIN_MSG
    if re.search(r"(?i)limit|quota|usage", msg):
        return LIMIT_MSG
    if re.search(r"(?i)ENOTFOUND|ECONNRESET|ECONNREFUSED|network|offline|fetch failed", msg):
        return OFFLINE_MSG
    return GENERIC_MSG


class Brain:
    def __init__(self, cfg: Config, mcp_config: Path, on_api_key_removed: Callable[[], None],
                 allowed: list[str] | None = None):
        self.cfg = cfg
        self.mcp_config = mcp_config
        self.on_api_key_removed = on_api_key_removed
        self.allowed = allowed or []
        self.workspace = ensure_workspace(cfg.workspace)
        self._lock = threading.Lock()
        self.requests_today = 0
        self._count_day = date.today()
        self.limit_hit = False
        self.usage_pct: int | None = None
        self.last_activity = datetime.now()
        self.new_session()

    def new_session(self) -> None:
        self.session_id = str(uuid.uuid4())
        self._started = False

    def needs_new_session(self, now: datetime) -> bool:
        return now - self.last_activity >= timedelta(hours=self.cfg.session_idle_hours)

    def ask(self, text: str) -> Iterator[BrainEvent]:
        with self._lock:
            exe = shutil.which("claude")
            if not exe:
                yield BrainEvent("error", MISSING_CLAUDE)
                return
            env, removed = clean_env(dict(os.environ))
            if removed:
                self.on_api_key_removed()
            if date.today() != self._count_day:
                self._count_day, self.requests_today = date.today(), 0
            self.requests_today += 1
            self.last_activity = datetime.now()
            cmd = build_command(self.session_id, self._started, self.mcp_config, self.allowed,
                                fixed_drives(), exe)
            try:
                proc = subprocess.Popen(cmd, cwd=self.workspace, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding="utf-8", errors="replace",
                                        creationflags=CREATE_NO_WINDOW)
            except OSError as e:
                yield BrainEvent("error", str(e))
                return
            proc.stdin.write(text)
            proc.stdin.close()
            finished = False
            for line in proc.stdout:
                if not line.strip():
                    continue
                if '"session_id"' in line:
                    self._started = True  # a sessão existe; próximos turnos usam --resume
                ev = parse_line(line)
                if ev is None:
                    continue
                if ev.kind == "usage":
                    self.usage_pct = int(ev.text)
                    self.limit_hit = False
                elif ev.kind == "limit":
                    self.limit_hit = True
                elif ev.kind in ("done", "error"):
                    finished = True
                yield ev
            err = proc.stderr.read()
            proc.wait()
            if not finished:
                yield BrainEvent("error", err.strip() or GENERIC_MSG)
