"""Configuração da Lia, lida de um arquivo TOML opcional."""
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Config:
    hotkey: str = "tab"  # segurar a tecla; Ctrl+Alt+Espaço é o atalho do app do Claude
    hotkey_hold_s: float = 0.4  # 0 = "hotkey" é uma combinação, apertada normalmente
    voice: str = "pt-BR-AntonioNeural"
    piper_voice: str = "pt_BR-faber-medium"
    whisper_model: str = "auto"
    workspace: Path = field(default_factory=lambda: Path.home() / "Lia")
    session_idle_hours: float = 2.0
    confirm_timeout_s: int = 60
    voice_confirm_window_s: int = 15
    # Previsão do tempo no resumo ao abrir (vazio = sem previsão). Fica no config.toml, fora do GitHub.
    weather_place: str = ""          # como falar, ex. "no centro de São Paulo"
    weather_lat: float | None = None
    weather_lon: float | None = None


def load_config(path: Path) -> Config:
    """Lê o TOML em `path`; arquivo ausente usa os padrões e chaves desconhecidas são ignoradas."""
    if not Path(path).exists():
        return Config()
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    values = {k: v for k, v in data.items() if k in known}
    if "workspace" in values:
        values["workspace"] = Path(values["workspace"])
    return Config(**values)
