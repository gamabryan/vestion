"""O "cérebro" da Lia: roda o Claude Code instalado em modo não interativo, pelo plano do usuário."""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, Literal

import psutil

from lia.config import Config
from lia.workspace import ensure_workspace

# Nunca deixar o subprocesso cobrar pela API (ou por outro provedor) em vez do plano.
BILLING_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")

MISSING_CLAUDE = "Não encontrei o Claude Code instalado."
LIMIT_MSG = "Atingi o limite do seu plano por agora. Os painéis continuam funcionando."
LOGIN_MSG = "Preciso que você entre no Claude Code de novo."
OFFLINE_MSG = "Estou sem conexão agora."
GENERIC_MSG = "Tive um problema e não consegui fazer isso."
BILLING_MSG = "O Claude Code ia usar uma chave de API paga. Parei para não gerar cobrança."
TIMEOUT_MSG = "O Claude Code parou de responder, então cancelei esse pedido."
_FRIENDLY = {MISSING_CLAUDE, LIMIT_MSG, LOGIN_MSG, OFFLINE_MSG, GENERIC_MSG, BILLING_MSG, TIMEOUT_MSG}

CREATE_NO_WINDOW = 0x08000000
IDLE_TIMEOUT_S = 180  # sem nenhuma saída do Claude por esse tempo (e sem cartão aberto) = travado


@dataclass
class BrainEvent:
    kind: Literal["text", "done", "error", "usage", "limit", "billing"]
    text: str = ""


def clean_env(env: dict[str, str]) -> tuple[dict[str, str], bool]:
    cleaned = {k: v for k, v in env.items() if k not in BILLING_KEYS}
    return cleaned, len(cleaned) != len(env)


def fixed_drives() -> list[str]:
    return [p.mountpoint for p in psutil.disk_partitions(all=False) if "fixed" in p.opts]


def build_command(session_id: str, resume: bool, mcp_config: Path, allowed: list[str],
                  drives: list[str], exe: str = "claude", deny_read: list[str] | None = None) -> list[str]:
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
    # Só as configurações da pasta da Lia: regras, modo, hooks e env pessoais do usuário não valem aqui.
    cmd += ["--setting-sources", "project", "--permission-mode", "default"]
    cmd += ["--mcp-config", str(mcp_config), "--strict-mcp-config",
            "--permission-prompt-tool", "mcp__lia__lia_confirmar",
            "--allowedTools", ",".join(allowed)]
    if deny_read:  # ex.: a pasta com o token do Google
        cmd += ["--disallowedTools", ",".join(f"{tool}({p}/**)" for p in deny_read for tool in ("Read", "Grep", "Glob"))]
    for d in drives:
        cmd += ["--add-dir", d]
    return cmd


def parse_line(line: str) -> BrainEvent | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return BrainEvent("error", line.strip())
    kind = data.get("type")
    if kind == "system":
        source = data.get("apiKeySource")
        if data.get("subtype") == "init" and source and source != "none":
            return BrainEvent("billing", source)
        return None
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
    if re.search(r"(?i)ENOTFOUND|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|network|offline|"
                 r"fetch failed|connection|connect|timed? ?out", msg):
        return OFFLINE_MSG
    return GENERIC_MSG


def _kill_tree(proc: subprocess.Popen) -> None:
    """Encerra o Claude e os processos filhos dele (servidor MCP, node...)."""
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass


class Brain:
    def __init__(self, cfg: Config, mcp_config: Path, on_api_key_removed: Callable[[], None],
                 allowed: list[str] | None = None):
        self.cfg = cfg
        self.mcp_config = mcp_config
        self.on_api_key_removed = on_api_key_removed
        self.allowed = allowed or []
        self.workspace = ensure_workspace(cfg.workspace)
        self.idle_timeout_s = IDLE_TIMEOUT_S
        self.is_waiting_user: Callable[[], bool] = lambda: False  # cartão aberto = não é travamento
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
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

    def kill(self) -> None:
        proc = self._proc
        if proc and proc.poll() is None:
            _kill_tree(proc)

    def _read_lines(self, proc: subprocess.Popen) -> Iterator[str | None]:
        """Linhas do stdout; None quando passa tempo demais sem nada (e sem cartão aberto)."""
        lines: queue.Queue = queue.Queue()

        def pump(stream, sink, end_marker: bool):
            for line in stream:
                sink(line)
            if end_marker:
                sink(None)

        threading.Thread(target=pump, args=(proc.stdout, lines.put, True), daemon=True).start()
        self._stderr: list[str] = []
        # stderr é drenado sempre, para o Claude nunca travar com o buffer cheio
        threading.Thread(target=pump, args=(proc.stderr, self._stderr.append, False), daemon=True).start()
        last_output = time.monotonic()
        while True:
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                if self.is_waiting_user():
                    last_output = time.monotonic()
                elif time.monotonic() - last_output > self.idle_timeout_s:
                    yield None
                    return
                continue
            if line is None:
                return
            last_output = time.monotonic()
            yield line

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
                                fixed_drives(), exe,
                                deny_read=[(self.workspace / ".lia").as_posix()])
            try:
                proc = subprocess.Popen(cmd, cwd=self.workspace, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding="utf-8", errors="replace",
                                        creationflags=CREATE_NO_WINDOW)
            except OSError as e:
                yield BrainEvent("error", str(e))
                return
            self._proc = proc
            try:
                proc.stdin.write(text)
                proc.stdin.close()
            except OSError:
                pass  # o Claude saiu cedo; o erro real vem pelo stderr abaixo
            finished = False
            try:
                for line in self._read_lines(proc):
                    if line is None:
                        _kill_tree(proc)
                        finished = True
                        yield BrainEvent("error", TIMEOUT_MSG)
                        break
                    if not line.strip():
                        continue
                    if '"session_id"' in line:
                        self._started = True  # a sessão existe; próximos turnos usam --resume
                    ev = parse_line(line)
                    if ev is None:
                        continue
                    if ev.kind == "billing":
                        _kill_tree(proc)
                        finished = True
                        yield BrainEvent("error", BILLING_MSG)
                        break
                    if ev.kind == "usage":
                        self.usage_pct = int(ev.text)
                        self.limit_hit = False
                    elif ev.kind == "limit":
                        self.limit_hit = True
                    elif ev.kind in ("done", "error"):
                        finished = True
                    yield ev
            finally:
                if proc.poll() is None and not finished:
                    _kill_tree(proc)  # consumidor parou de ler (ex.: app saindo)
                proc.wait()
                self._proc = None
            if not finished:
                err = "".join(self._stderr).strip()
                yield BrainEvent("error", err or GENERIC_MSG)
