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


def test_spoken_short_question_even_for_huge_command():
    card = describe_action("Bash", {"command": "echo " + "palavra " * 400})
    assert len(card.spoken.split()) <= 12
    assert card.spoken.startswith("Posso") and card.spoken.endswith("?")


def test_unknown_tool_detail_truncated():
    card = describe_action("FerramentaX", {"dado": "a" * 2000})
    assert card.title == "Ação: FerramentaX"
    assert len(card.detail) <= 400


def test_allowed_tools_has_no_write_or_edit():
    assert not any(t.split("(")[0] in ("Write", "Edit", "MultiEdit", "NotebookEdit") for t in ALLOWED_TOOLS)
    assert "Bash" not in ALLOWED_TOOLS


def test_spoken_card_never_reads_command_or_url():
    cmd = r'Remove-Item "https://www.google.com/maps/search/padaria" C:\Users\PC\Desktop\velho.txt'
    spoken = describe_action("Bash", {"command": cmd}).spoken
    assert "http" not in spoken and "Remove-Item" not in spoken and "\\" not in spoken
    assert len(spoken.split()) <= 12
    assert spoken.endswith("?")


def test_spoken_card_short_for_files():
    spoken = describe_action("Write", {"file_path": r"C:\Users\PC\Desktop\lista.txt", "content": "x"}).spoken
    assert "lista.txt" in spoken and "\\" not in spoken
    assert len(spoken.split()) <= 12
