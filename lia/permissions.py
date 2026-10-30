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


# ---- Política: só o importante pede o cartão (decisão do usuário) ----------------------
# Pede: apagar, sobrescrever, enviar, instalar/desinstalar, administrador e configurações do
# Windows, dinheiro, contas e senhas. O resto (criar, editar, mover, organizar, abrir,
# comandos do dia a dia) roda direto. Comandos que escondem outro comando também pedem.
AUTO_TOOLS = {"Read", "Glob", "Grep", "LS", "Edit", "MultiEdit", "NotebookEdit", "TodoWrite",
              "WebFetch", "WebSearch", "mcp__lia__lia_abrir"}

_RISKY = [
    # apagar / destruir
    r"\b(rm|rmdir|rd|del|erase|Remove-Item|ri|Clear-Content|Clear-RecycleBin|shred|Format-Volume|diskpart)\b",
    r"\bformat\s+[a-z]:", r"\bcipher\s+/w",
    r"\bgit\s+(reset\s+--hard|clean|push\s+.*--force)",
    # sobrescrever
    r"(?<![\d>&])>(?![>&])(?!\s*(\$null|nul|/dev/null)\b)", r"\b(Set-Content|Out-File|sc)\b(?!.*-Append)",
    # instalar / desinstalar
    r"\b(winget|choco|scoop|msiexec|Install-Package|Install-Module|Add-AppxPackage|Remove-AppxPackage)\b",
    r"\bUninstall-\w+", r"\b(pip|pip3|npm|yarn|pnpm)\s+(install|uninstall|i|add|remove)\b", r"\.msi\b",
    # administrador / configurações do Windows
    r"\breg(\.exe)?\s+(add|delete|import|load)\b", r"\b(Set|New|Remove)-ItemProperty\b",
    r"\b(Set-ExecutionPolicy|bcdedit|netsh|icacls|takeown|schtasks|Register-ScheduledTask)\b",
    r"\bsc(\.exe)?\s+(config|delete|stop|create)\b", r"\b(Stop|Set|New)-Service\b",
    r"\b(Set|New|Remove)-NetFirewall\w*", r"\b(shutdown|Stop-Computer|Restart-Computer)\b",
    r"\bnet\s+(user|localgroup|share)\b", r"\b(Set|Add)-MpPreference\b", r"\b(Enable|Disable)-WindowsOptionalFeature\b",
    # enviar / rede com efeito
    r"\bSend-MailMessage\b", r"\bgit\s+push\b", r"\bgh\s+\w+\s+(create|merge|delete)\b",
    r"\b(curl|wget)\b.*(-X\s*(POST|PUT|DELETE|PATCH)|--data|\s-d\s|-F\s|--upload)",
    r"\b(Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b.*-Method\s+(Post|Put|Delete|Patch)",
    # contas, senhas e dinheiro
    r"\b(cmdkey|Get-Credential|ConvertTo-SecureString|vaultcmd)\b", r"(?i)\b(password|senha|passwd)\b",
    # comandos que escondem outros comandos (podem fazer qualquer coisa acima)
    r"\b(iex|Invoke-Expression|Invoke-Command|wscript|cscript|mshta|rundll32|regsvr32|certutil|bitsadmin)\b",
    # Start-Process/start abrindo programa ou site é inofensivo; como administrador ou rodando interpretador, não
    r"-Verb\s+[\"']?RunAs", r"\b(Start-Process|saps|start)\s+[\"']?(python3?|py|node|ruby|perl|bash|sh)\b",
    r"\b(powershell|pwsh)(\.exe)?\b", r"\bcmd(\.exe)?\s+/[ck]\b", r"\b(bash|sh|zsh)\s+-c\b",
    r"\b(python3?|py|node|ruby|perl)(\.exe)?\s+(-c|-e)\b", r"\.(ps1|bat|cmd|vbs|vbe|js|wsf|hta|reg)\b",
    r"\b(curl|wget|iwr|Invoke-WebRequest)\b.*(\||-OutFile|\s-o\s)",
]
_RISKY_RE = [re.compile(p, re.IGNORECASE) for p in _RISKY]


def needs_confirmation(tool_name: str, tool_input: dict) -> bool:
    if tool_name in AUTO_TOOLS:
        return False
    if tool_name == "Write":
        return Path(str(tool_input.get("file_path", ""))).exists()
    if tool_name in ("Bash", "PowerShell"):
        cmd = str(tool_input.get("command", ""))
        return any(r.search(cmd) for r in _RISKY_RE)
    return True  # administrador, envios e qualquer ferramenta desconhecida


@dataclass
class ActionCard:
    title: str
    detail: str
    spoken: str


def describe_action(tool_name: str, tool_input: dict) -> ActionCard:
    # O cartão mostra tudo; a fala é curta e nunca lê comandos, endereços ou caminhos.
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    name = Path(path).name[:40] if path else ""
    if tool_name in ("Bash", "PowerShell"):
        title, detail = "Executar comando", tool_input.get("command", "")
        spoken = "Posso executar o comando que está na tela?"
    elif tool_name == "Write":
        exists = bool(path) and Path(path).exists()
        title = "Substituir arquivo existente" if exists else "Criar ou substituir arquivo"
        detail = path
        spoken = f"Posso {'substituir' if exists else 'criar'} o arquivo {name}?"
    elif tool_name in ("Edit", "MultiEdit"):
        title, detail = "Alterar arquivo", path
        spoken = f"Posso alterar o arquivo {name}?"
    elif tool_name == "mcp__lia__lia_admin":
        title, detail = "Comando de administrador", tool_input.get("comando", "")
        spoken = "Posso executar o comando de administrador que está na tela?"
    else:
        title = f"Ação: {tool_name}"
        detail = json.dumps(tool_input, ensure_ascii=False)[:400]
        spoken = "Posso continuar com a ação que está na tela?"
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
