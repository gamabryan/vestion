import logging
from datetime import date, datetime

from lia.briefing import briefing_text
from lia.panels import NOT_CONNECTED_TEXT, PanelUpdater, agenda_panel, gmail_panel, not_connected_panel

LOCAL = datetime.now().astimezone().tzinfo


def event(title, hour=None, minute=0):
    if hour is None:
        return {"id": title, "titulo": title, "inicio": date(2026, 10, 29), "fim": date(2026, 10, 30),
                "dia_todo": True, "local": "", "convidados": 0}
    start = datetime(2026, 10, 29, hour, minute, tzinfo=LOCAL)
    return {"id": title, "titulo": title, "inicio": start, "fim": start, "dia_todo": False, "local": "", "convidados": 0}


def mail(de, assunto, importante=False):
    return {"id": de, "de": de, "assunto": assunto, "trecho": "", "importante": importante}


def test_agenda_panel_items_and_all_day():
    panel = agenda_panel([event("Feriado"), event("Reunião Carlos", 15)])
    assert panel == {"title": "AGENDA · HOJE", "items": [{"tag": "Dia todo", "text": "Feriado"},
                                                         {"tag": "15:00", "text": "Reunião Carlos"}]}


def test_gmail_panel_title_count_and_star():
    panel = gmail_panel([mail("Ana", "Proposta revisada com os valores finais do projeto", True), mail("Banco", "Fatura")], 7)
    assert panel["title"] == "GMAIL · 7 NÃO LIDOS"
    assert panel["items"][0]["tag"] == "★" and panel["items"][1]["tag"] == ""
    assert panel["items"][0]["text"].startswith("Ana — Proposta") and len(panel["items"][0]["text"]) <= 60


def test_not_connected_panel():
    assert not_connected_panel("GMAIL") == {"title": "GMAIL", "items": [{"tag": "", "text": NOT_CONNECTED_TEXT}]}


class FakeWindow:
    def __init__(self):
        self.panels = {}

    def update_panel(self, name, data):
        self.panels[name] = data


class Clients:
    def __init__(self):
        self.fail = False

    def get(self):
        if self.fail:
            raise OSError("sem internet")
        return FakeGmail(), FakeCalendar()


class FakeGmail:
    def unread(self, n=5):
        return [mail("Ana", "Oi", True)]

    def unread_count(self):
        return 1


class FakeCalendar:
    def today(self, now):
        return [event("Dentista", 10)]


def test_updater_shows_not_connected():
    win = FakeWindow()
    PanelUpdater(win, lambda: None).refresh_once()
    assert win.panels["gmail"]["items"][0]["text"] == NOT_CONNECTED_TEXT
    assert win.panels["agenda"]["items"][0]["text"] == NOT_CONNECTED_TEXT


def test_updater_keeps_last_data_on_error_and_logs_once(caplog):
    win, clients = FakeWindow(), Clients()
    up = PanelUpdater(win, clients.get)
    up.refresh_once()
    good = dict(win.panels)
    clients.fail = True
    with caplog.at_level(logging.WARNING):
        up.refresh_once()
        up.refresh_once()
    assert win.panels == good
    assert len([r for r in caplog.records if "painéis" in r.getMessage()]) == 1
    clients.fail = False
    up.refresh_once()
    clients.fail = True
    with caplog.at_level(logging.WARNING):
        up.refresh_once()
    assert len([r for r in caplog.records if "painéis" in r.getMessage()]) == 2  # nova sequência de falhas


def test_briefing_lists_each_event_with_time():
    now = datetime(2026, 10, 29, 8, 30, tzinfo=LOCAL)
    text = briefing_text(now, [event("Feriado"), event("Dentista", 10), event("Reunião Carlos", 15, 30)], [])
    assert text == ("Bom dia. Hoje você tem 3 compromissos: Feriado, o dia todo; Dentista às dez da manhã; "
                    "e Reunião Carlos às três e meia da tarde. Nenhum e-mail chegou hoje.")


def test_briefing_single_event():
    now = datetime(2026, 10, 29, 14, 0, tzinfo=LOCAL)
    text = briefing_text(now, [event("Reunião Carlos", 15)], [])
    assert text.startswith("Boa tarde. Hoje você tem 1 compromisso: Reunião Carlos às três da tarde.")


def test_briefing_summarizes_todays_emails():
    now = datetime(2026, 10, 29, 9, 0, tzinfo=LOCAL)
    mails = [mail("Ana Souza", "Proposta revisada", True), mail("Banco Inter", "Fatura disponível"),
             mail("LinkedIn", "Você apareceu em 3 pesquisas")]
    text = briefing_text(now, [], mails)
    assert text == ("Bom dia. Sua agenda está livre hoje. Hoje chegaram 3 e-mails: Ana Souza, sobre Proposta revisada, "
                    "que parece importante; Banco Inter, sobre Fatura disponível; e LinkedIn, sobre Você apareceu em 3 pesquisas.")


def test_briefing_caps_long_lists():
    now = datetime(2026, 10, 29, 9, 0, tzinfo=LOCAL)
    events = [event(f"Evento {i}", 9 + i) for i in range(7)]
    mails = [mail(f"Pessoa {i}", f"Assunto {i}") for i in range(9)]
    text = briefing_text(now, events, mails)
    assert "Evento 4" in text and "Evento 5" not in text and "e mais 2 compromissos" in text
    assert "Pessoa 4" in text and "Pessoa 5" not in text and "e mais 4 e-mails" in text


def test_briefing_free_day_no_mail():
    now = datetime(2026, 10, 29, 20, 0, tzinfo=LOCAL)
    assert briefing_text(now, [], []) == "Boa noite. Sua agenda está livre hoje. Nenhum e-mail chegou hoje."


def test_briefing_not_connected():
    assert briefing_text(datetime(2026, 10, 29, 9, tzinfo=LOCAL), None, None) == (
        "Oi, estou pronto. Preciso que você conecte sua conta Google para eu ver sua agenda e seus e-mails.")


def test_briefing_one_extra_is_singular():
    now = datetime(2026, 10, 29, 9, 0, tzinfo=LOCAL)
    mails = [mail(f"Pessoa {i}", f"Assunto {i}") for i in range(6)]
    events = [event(f"Evento {i}", 9 + i) for i in range(6)]
    text = briefing_text(now, events, mails)
    assert "e mais 1 e-mail." in text and "e mais 1 compromisso;" not in text and "mais 1 compromisso" in text


def test_reminders_panel_order_tags_and_kinds(tmp_path):
    from datetime import timedelta
    from lia.panels import reminders_panel
    from lia.reminders import ReminderStore
    now = datetime(2026, 10, 30, 9, 0, tzinfo=LOCAL)
    s = ReminderStore(tmp_path / "l.json")
    s.add("tarefa solta")
    s.add("amanhã", now + timedelta(days=1, hours=1))
    s.add("hoje", now + timedelta(hours=5))
    s.add("atrasado", now - timedelta(hours=2))
    panel = reminders_panel(s.groups(now), now)
    assert panel["title"] == "LEMBRETES · 4"
    assert [(i["text"], i["tag"], i["kind"]) for i in panel["items"]] == [
        ("atrasado", "07:00", "late"), ("hoje", "14:00", "today"),
        ("amanhã", "31/10 10:00", "next"), ("tarefa solta", "", "task")]
    assert all(i["id"] for i in panel["items"])


def test_updater_shows_reminders_even_without_google(tmp_path):
    from lia.reminders import ReminderStore
    s = ReminderStore(tmp_path / "l.json")
    s.add("comprar ração")
    win = FakeWindow()
    PanelUpdater(win, lambda: None, reminders=s).refresh_once()
    assert win.panels["lembretes"]["items"][0]["text"] == "comprar ração"


def test_briefing_includes_todays_and_late_reminders(tmp_path):
    from datetime import timedelta
    from lia.reminders import ReminderStore
    now = datetime(2026, 10, 30, 9, 0, tzinfo=LOCAL)
    s = ReminderStore(tmp_path / "l.json")
    s.add("pagar a conta", now.replace(hour=10))
    s.add("ligar para o Pedro", now.replace(hour=15))
    s.add("renovar a CNH", now - timedelta(days=1))
    s.add("comprar ração")  # sem hora: fica só no painel
    s.add("dentista", now + timedelta(days=2))
    text = briefing_text(now, [], [], s.groups(now))
    assert text.endswith("Você tem 2 lembretes hoje: pagar a conta às dez da manhã; e ligar para o Pedro às três da tarde. "
                         "1 está atrasado: renovar a CNH.")
    assert "ração" not in text and "dentista" not in text


def test_briefing_without_reminders_says_nothing_about_them(tmp_path):
    from lia.reminders import ReminderStore
    now = datetime(2026, 10, 30, 9, 0, tzinfo=LOCAL)
    text = briefing_text(now, [], [], ReminderStore(tmp_path / "l.json").groups(now))
    assert "lembrete" not in text.lower()


def test_briefing_reminders_even_when_google_not_connected(tmp_path):
    from lia.reminders import ReminderStore
    now = datetime(2026, 10, 30, 9, 0, tzinfo=LOCAL)
    s = ReminderStore(tmp_path / "l.json")
    s.add("pagar a conta", now.replace(hour=10))
    text = briefing_text(now, None, None, s.groups(now))
    assert text.startswith("Oi, estou pronto. Preciso que você conecte")
    assert text.endswith("Você tem 1 lembrete hoje: pagar a conta às dez da manhã.")
