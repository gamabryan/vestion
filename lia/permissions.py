"""O que a Lia pode fazer sem perguntar, e como cada ação aparece no cartão de confirmação."""
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Só leitura. Tudo que não está aqui passa pelo cartão PODE / CANCELAR.
ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "mcp__lia__lia_abrir",
    "Bash(dir:*)", "Bash(Get-ChildItem:*)", "Bash(Get-Process:*)", "Bash(Get-Date:*)",
    "Bash(whoami)", "Bash(hostname)",
]

UNSAFE_TO_OPEN = {".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
                  ".msi", ".reg", ".scr", ".hta", ".com", ".pif"}

START_MENUS = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

CREATE_NO_WINDOW = 0x08000000


@dataclass
class ActionCard:
    title: str
    detail: str
    spoken: str


def _short(text: str, words: int) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + (" …" if len(parts) > words else "")


def describe_action(tool_name: str, tool_input: dict) -> ActionCard:
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if tool_name in ("Bash", "PowerShell"):
        cmd = tool_input.get("command", "")
        title, detail, said = "Executar comando", cmd, _short(cmd, 8)
    elif tool_name == "Write":
        title, detail, said = "Criar ou substituir arquivo", path, Path(path).name
    elif tool_name in ("Edit", "MultiEdit"):
        title, detail, said = "Alterar arquivo", path, Path(path).name
    elif tool_name == "mcp__lia__lia_admin":
        cmd = tool_input.get("comando", "")
        title, detail, said = "Comando de administrador", cmd, _short(cmd, 8)
    else:
        title = f"Ação: {tool_name}"
        detail = json.dumps(tool_input, ensure_ascii=False)[:400]
        said = ""
    spoken = f"{title}: {said}. Posso?" if said else f"{title}. Posso?"
    words = spoken.split()
    if len(words) > 25:
        spoken = " ".join(words[:23]) + " … Posso?"
    return ActionCard(title, detail, spoken)


def is_safe_to_open(target: str) -> bool:
    return Path(target).suffix.lower() not in UNSAFE_TO_OPEN


def _find_shortcut(name: str) -> Path | None:
    wanted = name.lower().strip()
    for root in START_MENUS:
        if not root.exists():
            continue
        for lnk in root.rglob("*.lnk"):
            if lnk.stem.lower() == wanted:
                return lnk
        for lnk in root.rglob("*.lnk"):
            if wanted in lnk.stem.lower():
                return lnk
    return None


def open_target(target: str) -> str:
    """Abre um arquivo, pasta ou programa (pelo nome do menu Iniciar) para o usuário ver."""
    if not is_safe_to_open(target):
        return "Por segurança não abro esse tipo de arquivo."
    path = Path(os.path.expandvars(os.path.expanduser(target)))
    resolved = path if path.exists() else _find_shortcut(target)
    try:
        os.startfile(str(resolved or target))
    except OSError:
        return f"Não encontrei {target}."
    return f"Abri {resolved.stem if resolved else target}."


def run_elevated(command: str) -> str:
    """Roda um comando PowerShell como administrador; o Windows mostra o UAC ao usuário."""
    inner = command.replace("'", "''")
    ps = ("$p = Start-Process powershell -Verb RunAs -Wait -PassThru "
          f"-ArgumentList '-NoProfile','-Command','{inner}'; exit $p.ExitCode")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                            text=True, creationflags=CREATE_NO_WINDOW)
    if result.returncode != 0 and "cancel" in (result.stderr or "").lower():
        return "Você recusou a permissão do Windows."
    if result.returncode != 0:
        return f"O comando terminou com erro (código {result.returncode})."
    return "Feito."
