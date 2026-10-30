import json
from datetime import datetime, timedelta

from lia.reminders import ReminderStore

LOCAL = datetime.now().astimezone().tzinfo
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=LOCAL)


def store(tmp_path):
    return ReminderStore(tmp_path / "lembretes.json")


def test_add_and_reload_from_disk(tmp_path):
    s = store(tmp_path)
    r = s.add("pagar a conta", NOW + timedelta(hours=1))
    again = store(tmp_path)
    [item] = again.all()
    assert item["id"] == r["id"] and item["texto"] == "pagar a conta"
    assert datetime.fromisoformat(item["quando"]) == NOW + timedelta(hours=1)
    assert item["feito"] is False and item["avisado"] is False
    assert json.loads((tmp_path / "lembretes.json").read_text(encoding="utf-8"))  # arquivo legível


def test_task_without_time(tmp_path):
    s = store(tmp_path)
    s.add("comprar ração")
    assert s.all()[0]["quando"] is None


def test_due_only_timed_pending_not_yet_warned(tmp_path):
    s = store(tmp_path)
    past = s.add("vencido", NOW - timedelta(minutes=1))
    s.add("futuro", NOW + timedelta(hours=1))
    s.add("sem hora")
    done = s.add("já feito", NOW - timedelta(hours=1))
    s.complete(done["id"])
    assert [r["id"] for r in s.due(NOW)] == [past["id"]]
    s.mark_warned(past["id"])
    assert s.due(NOW) == []


def test_snooze_moves_time_and_rearms(tmp_path):
    s = store(tmp_path)
    r = s.add("ligar pro Pedro", NOW)
    s.mark_warned(r["id"])
    s.snooze(r["id"], 10, NOW)
    item = s.get(r["id"])
    assert datetime.fromisoformat(item["quando"]) == NOW + timedelta(minutes=10)
    assert item["avisado"] is False
    assert s.due(NOW + timedelta(minutes=10)) and not s.due(NOW + timedelta(minutes=9))


def test_complete_and_delete(tmp_path):
    s = store(tmp_path)
    a = s.add("a")
    b = s.add("b")
    assert s.complete(a["id"]) is True
    assert s.delete(b["id"]) is True
    assert s.delete("nao-existe") is False
    assert [r["texto"] for r in s.all()] == ["a"] and s.all()[0]["feito"] is True


def test_groups_for_panel_and_summary(tmp_path):
    s = store(tmp_path)
    s.add("atrasado ontem", NOW - timedelta(days=1))
    s.add("hoje cedo já passou", NOW - timedelta(hours=1))
    s.add("hoje mais tarde", NOW + timedelta(hours=3))
    s.add("amanhã", NOW + timedelta(days=1))
    s.add("tarefa solta")
    feito = s.add("feito hoje", NOW + timedelta(hours=1))
    s.complete(feito["id"])
    g = s.groups(NOW)
    assert [r["texto"] for r in g["atrasados"]] == ["atrasado ontem", "hoje cedo já passou"]
    assert [r["texto"] for r in g["hoje"]] == ["hoje mais tarde"]
    assert [r["texto"] for r in g["proximos"]] == ["amanhã"]
    assert [r["texto"] for r in g["sem_hora"]] == ["tarefa solta"]


def test_corrupted_file_starts_empty_and_keeps_backup(tmp_path):
    (tmp_path / "lembretes.json").write_text("{quebrado", encoding="utf-8")
    s = store(tmp_path)
    assert s.all() == []
    s.add("novo")
    assert (tmp_path / "lembretes.json.bak").exists()
