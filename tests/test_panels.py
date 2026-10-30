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


def test_briefing_morning_two_events_one_important_mail():
    now = datetime(2026, 10, 29, 8, 30, tzinfo=LOCAL)
    text = briefing_text(now, [event("Dentista", 10), event("Reunião Carlos", 15)],
                         [mail("Ana", "Oi", True), mail("Banco", "Fatura")])
    assert text == ("Bom dia. Hoje você tem 2 compromissos; o próximo é Dentista às dez da manhã. "
                    "Você tem 1 e-mail importante não lido.")


def test_briefing_next_event_skips_past_ones_and_singular():
    now = datetime(2026, 10, 29, 14, 0, tzinfo=LOCAL)
    text = briefing_text(now, [event("Reunião Carlos", 15, 30)], [])
    assert text == "Boa tarde. Hoje você tem 1 compromisso; o próximo é Reunião Carlos às três e meia da tarde."


def test_briefing_free_day_no_mail():
    now = datetime(2026, 10, 29, 20, 0, tzinfo=LOCAL)
    assert briefing_text(now, [], []) == "Boa noite. Sua agenda está livre hoje."


def test_briefing_not_connected():
    assert briefing_text(datetime(2026, 10, 29, 9, tzinfo=LOCAL), None, None) == (
        "Oi, estou pronto. Preciso que você conecte sua conta Google para eu ver sua agenda e seus e-mails.")
