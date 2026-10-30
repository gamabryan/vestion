"""Lembretes guardados no Google Tasks: o PC guarda a hora do aviso e uma cópia para usar sem internet."""
from datetime import date, datetime, time, timedelta

from lia.reminders import ReminderStore

LOCAL = datetime.now().astimezone().tzinfo
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=LOCAL)


class FakeTasks:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.n = 0
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("sem internet")

    def pending(self):
        self._check()
        return [dict(t) for t in self.tasks.values() if not t.get("feito")]

    def create(self, titulo, dia):
        self._check()
        self.n += 1
        tid = f"g{self.n}"
        self.tasks[tid] = {"id": tid, "titulo": titulo, "dia": dia}
        return tid

    def complete(self, tid):
        self._check()
        if tid in self.tasks:
            self.tasks[tid]["feito"] = True

    def set_day(self, tid, dia):
        self._check()
        self.tasks[tid]["dia"] = dia

    def delete(self, tid):
        self._check()
        self.tasks.pop(tid, None)


def make(tmp_path, google=None):
    google = google or FakeTasks()
    return ReminderStore(tmp_path / "lembretes.json", remote=lambda: google), google


def test_add_goes_to_google_with_date_and_keeps_time_locally(tmp_path):
    s, g = make(tmp_path)
    r = s.add("pagar a conta", NOW + timedelta(hours=1))
    [task] = g.tasks.values()
    assert task["titulo"] == "pagar a conta" and task["dia"] == date(2026, 10, 30)
    assert datetime.fromisoformat(s.get(r["id"])["quando"]) == NOW + timedelta(hours=1)


def test_complete_snooze_delete_reach_google(tmp_path):
    s, g = make(tmp_path)
    a = s.add("a", NOW)
    b = s.add("b", NOW)
    s.complete(a["id"])
    assert g.tasks["g1"]["feito"] is True
    s.snooze(b["id"], 60 * 24, NOW)
    assert g.tasks["g2"]["dia"] == date(2026, 10, 31)
    s.delete(b["id"])
    assert "g2" not in g.tasks and s.get(b["id"]) is None


def test_offline_changes_are_sent_on_next_sync(tmp_path):
    s, g = make(tmp_path)
    old = s.add("antigo")
    g.fail = True
    new = s.add("novo sem internet")
    s.complete(old["id"])
    assert [r["texto"] for r in s.all() if not r["feito"]] == ["novo sem internet"]
    assert s.sync() is False
    g.fail = False
    assert s.sync() is True
    assert g.tasks["g1"]["feito"] is True
    assert [t["titulo"] for t in g.pending()] == ["novo sem internet"]
    assert s.get(new["id"])["texto"] == "novo sem internet"


def test_offline_delete_is_sent_later(tmp_path):
    s, g = make(tmp_path)
    r = s.add("x")
    g.fail = True
    s.delete(r["id"])
    assert s.all() == []
    g.fail = False
    s.sync()
    assert g.tasks == {}


def test_sync_brings_tasks_from_phone_at_nine(tmp_path):
    s, g = make(tmp_path)
    g.create("ligar pro banco", date(2026, 10, 31))
    g.create("comprar pão", None)
    s.sync()
    items = {r["texto"]: r for r in s.all()}
    assert datetime.fromisoformat(items["ligar pro banco"]["quando"]) == datetime.combine(
        date(2026, 10, 31), time(9), tzinfo=LOCAL)
    assert items["comprar pão"]["quando"] is None


def test_sync_keeps_local_time_when_day_unchanged_and_follows_phone_changes(tmp_path):
    s, g = make(tmp_path)
    r = s.add("dentista", NOW.replace(hour=15, minute=30))
    s.mark_warned(r["id"])
    s.sync()
    assert datetime.fromisoformat(s.get(r["id"])["quando"]).hour == 15
    g.tasks["g1"]["titulo"] = "dentista (remarcado)"
    g.tasks["g1"]["dia"] = date(2026, 11, 2)
    s.sync()
    item = s.get(r["id"])
    assert item["texto"] == "dentista (remarcado)" and item["avisado"] is False
    assert datetime.fromisoformat(item["quando"]) == datetime(2026, 11, 2, 9, tzinfo=LOCAL)


def test_done_or_deleted_on_phone_disappears(tmp_path):
    s, g = make(tmp_path)
    a = s.add("a")
    b = s.add("b")
    g.complete("g1")
    g.delete("g2")
    s.sync()
    assert s.all() == [] and s.get(a["id"]) is None and s.get(b["id"]) is None


def test_old_local_reminders_are_uploaded_once(tmp_path):
    local = ReminderStore(tmp_path / "lembretes.json")
    local.add("de antes", NOW)
    done = local.add("já feito")
    local.complete(done["id"])
    s, g = make(tmp_path)
    s.sync()
    s.sync()
    assert [t["titulo"] for t in g.tasks.values()] == ["de antes"]


def test_not_connected_works_locally(tmp_path):
    s = ReminderStore(tmp_path / "lembretes.json", remote=lambda: None)
    r = s.add("x")
    assert s.sync() is False
    assert s.get(r["id"])["texto"] == "x"
