from pathlib import Path

from lia.config import load_config


def test_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nao_existe.toml")
    assert cfg.hotkey == "ctrl+alt+a"
    assert cfg.confirm_timeout_s == 60
    assert cfg.voice == "pt-BR-FranciscaNeural"
    assert cfg.workspace == Path.home() / "Lia"


def test_overrides_from_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('hotkey = "ctrl+shift+l"\nworkspace = "D:/LiaWs"\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.hotkey == "ctrl+shift+l"
    assert cfg.workspace == Path("D:/LiaWs")


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('banana = 3\nvoice_confirm_window_s = 10\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.voice_confirm_window_s == 10
    assert not hasattr(cfg, "banana")
