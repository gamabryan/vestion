"""O que a Lia pode fazer sem perguntar, e como cada ação aparece no cartão de confirmação."""
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Só leitura. Tudo que não está aqui passa pelo cartão PODE / CANCELAR.
# Nenhum comando de shell é pré-liberado: prefixos não protegem contra redirecionamento (dir > x).
ALLOWED_TOOLS = ["Read", "Glob", "Grep", "mcp__lia__lia_abrir"]

# Abrir sem perguntar só vale para documentos e mídia (lista do que pode, não do que não pode).
SAFE_TO_OPEN = {".pdf", ".txt", ".md", ".rtf", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".csv",
                ".ppt", ".pptx", ".odp", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
                ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mkv", ".avi", ".mov", ".webm"}

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


def _clean(target: str) -> str:
    # O Windows ignora ponto e espaço no fim do nome ("x.bat." abre x.bat).
    return target.strip().rstrip(" .")


def _in_start_menu(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved.is_relative_to(root.resolve()) for root in START_MENUS if str(root))


def is_safe_to_open(target: str) -> bool:
    """Documentos/mídia, pastas, sites e atalhos do menu Iniciar. Qualquer outra coisa precisa do cartão."""
    cleaned = _clean(target)
    if re.match(r"(?i)^https?://", cleaned):
        return True
    path = Path(os.path.expandvars(os.path.expanduser(cleaned)))
    suffix = path.suffix.lower()
    if suffix == ".lnk":
        return _in_start_menu(path)
    if suffix in SAFE_TO_OPEN:
        return True
    return path.is_dir()


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
    """Abre um documento, pasta, site ou programa do menu Iniciar para o usuário ver."""
    cleaned = _clean(target)
    path = Path(os.path.expandvars(os.path.expanduser(cleaned)))
    is_name = not path.suffix and "\\" not in cleaned and "/" not in cleaned
    if is_name:
        resolved = _find_shortcut(cleaned)  # nome de programa: só o que está no menu Iniciar
        if not resolved:
            return f"Não encontrei o programa {cleaned} no menu Iniciar."
    elif is_safe_to_open(cleaned):
        resolved = cleaned if re.match(r"(?i)^https?://", cleaned) else path
    else:
        return "Por segurança não abro esse tipo de arquivo."
    try:
        os.startfile(str(resolved))
    except OSError:
        return f"Não encontrei {cleaned}."
    return f"Abri {resolved.stem if isinstance(resolved, Path) else cleaned}."


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
