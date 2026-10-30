from datetime import date, datetime, timedelta, timezone

from lia.google.calendar import CalendarClient, hhmm
from tests.google_fakes import fake_service

LOCAL = datetime.now().astimezone().tzinfo


def ev(eid, title, start, end, attendees=0):
    return {"id": eid, "summary": title, "start": start, "end": end, "location": "",
            "attendees": [{"email": f"p{i}@x.com"} for i in range(attendees)]}


def client(items=None, extra=None):
    responses = {"events.list": {"items": items or []}, "events.insert": {"id": "novo1"},
                 "events.patch": {}, "events.delete": {}, "events.get": ev("e9", "Dentista",
                 {"dateTime": "2026-10-30T10:00:00-03:00"}, {"dateTime": "2026-10-30T11:00:00-03:00"})}
    responses.update(extra or {})
    service, calls = fake_service(responses)
    return CalendarClient(service), calls


def test_today_range_is_local_midnight_to_midnight():
    c, calls = client()
    now = datetime(2026, 10, 29, 15, 30, tzinfo=LOCAL)
    c.today(now)
    kw = calls[0][1]
    assert kw["calendarId"] == "primary" and kw["singleEvents"] is True and kw["orderBy"] == "startTime"
    assert datetime.fromisoformat(kw["timeMin"]) == datetime(2026, 10, 29, 0, 0, tzinfo=LOCAL)
    assert datetime.fromisoformat(kw["timeMax"]) == datetime(2026, 10, 30, 0, 0, tzinfo=LOCAL)


def test_parses_timed_and_all_day_events():
    c, _ = client([ev("a", "Feriado", {"date": "2026-10-29"}, {"date": "2026-10-30"}),
                   ev("b", "Reunião", {"dateTime": "2026-10-29T15:00:00-03:00"}, {"dateTime": "2026-10-29T16:00:00-03:00"}, 2)])
    items = c.today(datetime(2026, 10, 29, 9, 0, tzinfo=LOCAL))
    assert items[0]["dia_todo"] is True and items[0]["inicio"] == date(2026, 10, 29)
    assert hhmm(items[0]) == "Dia todo"
    assert items[1]["titulo"] == "Reunião" and items[1]["convidados"] == 2 and items[1]["dia_todo"] is False


def test_hhmm_converts_other_timezone_to_local():
    utc = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
    item = {"inicio": utc, "dia_todo": False}
    assert hhmm(item) == utc.astimezone(LOCAL).strftime("%H:%M")


def test_create_with_guests_sends_updates_all():
    c, calls = client()
    start = datetime(2026, 10, 30, 10, 0, tzinfo=LOCAL)
    assert c.create("Reunião", start, start + timedelta(hours=1), convidados=["ana@x.com"]) == "novo1"
    kw = calls[-1][1]
    assert kw["sendUpdates"] == "all"
    assert kw["body"]["attendees"] == [{"email": "ana@x.com"}]
    assert kw["body"]["start"]["dateTime"] == start.isoformat()


def test_create_without_guests_sends_none():
    c, calls = client()
    start = datetime(2026, 10, 30, 10, 0, tzinfo=LOCAL)
    c.create("Dentista", start, start + timedelta(hours=1))
    assert calls[-1][1]["sendUpdates"] == "none"
    assert "attendees" not in calls[-1][1]["body"]


def test_move_never_notifies():
    c, calls = client()
    start = datetime(2026, 10, 30, 14, 0, tzinfo=LOCAL)
    c.move("e9", start, start + timedelta(hours=1))
    path, kw = calls[-1]
    assert path == "events.patch" and kw["sendUpdates"] == "none" and kw["eventId"] == "e9"


def test_cancel_notifies_guests():
    c, calls = client()
    c.cancel("e9")
    assert calls[-1] == ("events.delete", {"calendarId": "primary", "eventId": "e9", "sendUpdates": "all"})


def test_get_returns_parsed_event():
    c, _ = client()
    item = c.get("e9")
    assert item["titulo"] == "Dentista" and item["dia_todo"] is False


def test_today_skips_events_that_started_yesterday():
    late_night = ev("n", "Jogo da NBA", {"dateTime": "2026-10-29T23:30:00-03:00"}, {"dateTime": "2026-10-30T00:30:00-03:00"})
    morning = ev("m", "Reunião", {"dateTime": "2026-10-30T10:00:00-03:00"}, {"dateTime": "2026-10-30T11:00:00-03:00"})
    trip = ev("t", "Viagem", {"date": "2026-10-28"}, {"date": "2026-11-02"})  # dia inteiro que cobre hoje
    c, _ = client([late_night, morning, trip])
    now = datetime(2026, 10, 30, 0, 8).astimezone()
    assert [e["titulo"] for e in c.today(now)] == ["Reunião", "Viagem"]
