from lia.workspace import ensure_workspace


def test_creates_files(tmp_path):
    root = ensure_workspace(tmp_path / "ws")
    assert (root / "CLAUDE.md").read_text(encoding="utf-8").startswith("# Lia")
    assert (root / "memoria.md").exists()


def test_does_not_overwrite_existing_memoria(tmp_path):
    root = ensure_workspace(tmp_path / "ws")
    (root / "memoria.md").write_text("Pedro é meu irmão", encoding="utf-8")
    (root / "CLAUDE.md").write_text("editado", encoding="utf-8")
    ensure_workspace(root)
    assert (root / "memoria.md").read_text(encoding="utf-8") == "Pedro é meu irmão"
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "editado"
