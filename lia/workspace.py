"""Pasta de trabalho da Lia: personalidade (CLAUDE.md) e memória do usuário."""
import shutil
from pathlib import Path

PERSONA = Path(__file__).with_name("persona.md")


def ensure_workspace(root: Path) -> Path:
    """Cria a pasta e os arquivos que faltarem, sem sobrescrever edições do usuário."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        shutil.copyfile(PERSONA, claude_md)
    memoria = root / "memoria.md"
    if not memoria.exists():
        memoria.write_text("", encoding="utf-8")
    return root
