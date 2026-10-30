from lia.permissions import ALLOWED_TOOLS, describe_action, is_safe_to_open


def test_bat_not_safe():
    assert not is_safe_to_open(r"C:\x\script.BAT")
    assert not is_safe_to_open("instalar.ps1")


def test_pdf_safe():
    assert is_safe_to_open(r"C:\docs\fatura.pdf")


def test_lnk_safe():
    assert is_safe_to_open(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Notepad.lnk")


def test_describe_bash_shows_exact_command():
    card = describe_action("Bash", {"command": r"Remove-Item C:\temp\x.txt"})
    assert card.title == "Executar comando"
    assert card.detail == r"Remove-Item C:\temp\x.txt"


def test_describe_write_and_admin():
    assert describe_action("Write", {"file_path": r"C:\a.txt", "content": "x"}).title == "Criar ou substituir arquivo"
    assert describe_action("Edit", {"file_path": r"C:\a.txt"}).title == "Alterar arquivo"
    assert describe_action("mcp__lia__lia_admin", {"comando": "ipconfig"}).title == "Comando de administrador"


def test_spoken_under_25_words_and_ends_with_posso():
    card = describe_action("Bash", {"command": "echo " + "palavra " * 400})
    assert len(card.spoken.split()) <= 25
    assert card.spoken.endswith("Posso?")


def test_unknown_tool_detail_truncated():
    card = describe_action("FerramentaX", {"dado": "a" * 2000})
    assert card.title == "Ação: FerramentaX"
    assert len(card.detail) <= 400


def test_allowed_tools_has_no_write_or_edit():
    assert not any(t.split("(")[0] in ("Write", "Edit", "MultiEdit", "NotebookEdit") for t in ALLOWED_TOOLS)
    assert "Bash" not in ALLOWED_TOOLS
