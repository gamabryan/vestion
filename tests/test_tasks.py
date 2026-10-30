from datetime import date

from lia.google.tasks import TasksClient
from tests.google_fakes import fake_service


class _Gone(Exception):
    class resp:
        status = 404


def test_pending_parses_day_and_pages():
    pages = {None: {"items": [{"id": "a", "title": "pagar", "due": "2026-10-31T00:00:00.000Z"}],
                    "nextPageToken": "p2"},
             "p2": {"items": [{"id": "b", "title": "ração"}, {"id": "c", "title": "x", "status": "completed"}]}}
    svc, calls = fake_service({"tasks.list": lambda **kw: pages[kw["pageToken"]]})
    items = TasksClient(svc).pending()
    assert items == [{"id": "a", "titulo": "pagar", "dia": date(2026, 10, 31)},
                     {"id": "b", "titulo": "ração", "dia": None}]
    assert calls[0][1]["tasklist"] == "@default" and calls[0][1]["showCompleted"] is False


def test_create_sends_date_only():
    svc, calls = fake_service({"tasks.insert": {"id": "new"}})
    assert TasksClient(svc).create("pagar", date(2026, 10, 31)) == "new"
    assert calls[0][1]["body"] == {"title": "pagar", "due": "2026-10-31T00:00:00.000Z"}
    TasksClient(svc).create("ração", None)
    assert calls[1][1]["body"] == {"title": "ração"}


def test_complete_set_day_delete():
    svc, calls = fake_service({"tasks.patch": {}, "tasks.delete": ""})
    c = TasksClient(svc)
    c.complete("a")
    c.set_day("a", None)
    c.delete("a")
    assert calls[0][1]["body"] == {"status": "completed"}
    assert calls[1][1]["body"] == {"due": None}
    assert calls[2] == ("tasks.delete", {"tasklist": "@default", "task": "a"})


def test_already_gone_is_ignored():
    def gone(**kw):
        raise _Gone()
    svc, _ = fake_service({"tasks.patch": gone, "tasks.delete": gone})
    c = TasksClient(svc)
    c.complete("a")
    c.delete("a")
