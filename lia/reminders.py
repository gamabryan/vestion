"""Lembretes e tarefas do usuário: no Google Tasks quando a conta está conectada, com cópia no PC.

O app e o servidor MCP (outro processo) usam o mesmo arquivo: cada operação relê, altera e grava
de forma atômica.

Com o Google, cada mudança vale primeiro no PC (marcada "sujo") e é enviada na hora; sem internet,
vai no próximo sync(). O Google Tasks só guarda a data: a hora do aviso fica no PC. Tarefa criada
no celular com data e sem hora avisa às 9h.
"""
import json
import logging
import os
import threading
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)
PHONE_HOUR = time(9, 0)

_DONE = {"feito", "pronto", "ja fiz", "fiz", "concluido", "ok", "beleza", "certo", "ja foi"}
_SNOOZE = {"adia", "adiar", "depois", "mais tarde", "daqui a pouco", "me lembra depois", "soneca"}


def parse_reminder_answer(text: str) -> str | None:
    """Resposta falada ao aviso: 'done' (feito), 'snooze' (adiar) ou None (outra coisa)."""
    import re
    import unicodedata
    norm = unicodedata.normalize("NFKD", text.lower())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = " ".join(re.sub(r"[^\w\s]", " ", norm).split())
    if norm.startswith("vestion "):
        norm = norm[len("vestion "):]
    if norm in _DONE:
        return "done"
    if norm in _SNOOZE:
        return "snooze"
    return None


def _when(item: dict) -> datetime | None:
    return datetime.fromisoformat(item["quando"]) if item.get("quando") else None


def _day(item: dict) -> date | None:
    w = _when(item)
    return w.astimezone().date() if w else None


def _at_phone_hour(d: date | None) -> str | None:
    if not d:
        return None
    return datetime.combine(d, PHONE_HOUR, tzinfo=datetime.now().astimezone().tzinfo).isoformat()


def _to_push(r: dict) -> bool:
    """Tem mudança do PC que o Google ainda não sabe (inclui lembretes de antes do Google)."""
    return bool(r.get("sujo")) or (not r.get("gid") and not r["feito"] and not r.get("apagado"))


class ReminderStore:
    def __init__(self, path: Path, remote: Callable[[], object] | None = None):
        """remote: devolve o cliente do Google Tasks; None sem conta conectada (levanta sem internet)."""
        self.path = Path(path)
        self.remote = remote
        self._lock = threading.Lock()

    # ---- arquivo ------------------------------------------------------------------
    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except (ValueError, OSError):
            # arquivo estragado: guarda uma cópia para não perder nada e recomeça
            try:
                os.replace(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
            except OSError:
                pass
            return []

    def _write(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _update(self, change) -> object:
        with self._lock:
            items = self._read()
            result = change(items)
            self._write(items)
            return result

    def _raw(self) -> list[dict]:
        with self._lock:
            return self._read()

    # ---- operações ----------------------------------------------------------------
    def all(self) -> list[dict]:
        return [r for r in self._raw() if not r.get("apagado")]

    def get(self, rid: str) -> dict | None:
        return next((r for r in self.all() if r["id"] == rid), None)

    def add(self, texto: str, quando: datetime | None = None) -> dict:
        item = {"id": uuid.uuid4().hex[:8], "texto": texto.strip(),
                "quando": quando.isoformat() if quando else None,
                "feito": False, "avisado": False, "criado": datetime.now().astimezone().isoformat()}
        if self.remote:
            item.update(gid=None, sujo=True)
        self._update(lambda items: items.append(item))
        self._push_now(item["id"])
        return item

    def _set(self, rid: str, **fields) -> bool:
        def change(items):
            for r in items:
                if r["id"] == rid:
                    r.update(fields)
                    return True
            return False
        return bool(self._update(change))

    def _changed(self, rid: str, **fields) -> bool:
        if self.remote:
            fields["sujo"] = True
        if not self._set(rid, **fields):
            return False
        self._push_now(rid)
        return True

    def complete(self, rid: str) -> bool:
        return self._changed(rid, feito=True)

    def mark_warned(self, rid: str) -> bool:
        return self._set(rid, avisado=True)

    def snooze(self, rid: str, minutes: int, now: datetime) -> bool:
        return self._changed(rid, quando=(now + timedelta(minutes=minutes)).isoformat(), avisado=False)

    def delete(self, rid: str) -> bool:
        item = self.get(rid)
        if item is None:
            return False
        if self.remote and item.get("gid"):
            return self._changed(rid, apagado=True)  # some daqui já; sai do Google no envio
        self._remove(rid)
        return True

    def _remove(self, rid: str) -> None:
        def change(items):
            items[:] = [r for r in items if r["id"] != rid]
        self._update(change)

    # ---- Google Tasks -------------------------------------------------------------
    def _push_now(self, rid: str) -> None:
        """Envia já; sem internet ou sem conta, fica para o próximo sync()."""
        if not self.remote:
            return
        try:
            client = self.remote()
            if client:
                self._push(client, rid)
        except Exception as e:
            log.info("lembrete fica para enviar depois: %s", e)

    def _push(self, client, rid: str) -> None:
        r = next((x for x in self._raw() if x["id"] == rid), None)
        if r is None or not _to_push(r):
            return
        gid = r.get("gid")
        if r.get("apagado"):
            if gid:
                client.delete(gid)
            self._remove(rid)
            return
        if not gid:
            if r["feito"]:  # feito antes de chegar ao Google: nada a enviar
                self._set(rid, sujo=False)
                return
            gid = client.create(r["texto"], _day(r))
        elif r["feito"]:
            client.complete(gid)
        else:
            client.set_day(gid, _day(r))
        self._set(rid, gid=gid, sujo=False, sinc=datetime.now().astimezone().isoformat())

    def sync(self) -> bool:
        """Envia o que mudou no PC e traz o que mudou no Google (inclusive pelo celular).

        False quando não deu: sem conta conectada ou sem internet (a cópia do PC continua valendo).
        """
        if not self.remote:
            return False
        try:
            client = self.remote()
            if not client:
                return False
            for r in self._raw():
                if _to_push(r):
                    self._push(client, r["id"])
            started = datetime.now().astimezone()
            tasks = client.pending()
        except Exception as e:
            log.info("sem sync dos lembretes: %s", e)
            return False
        self._update(lambda items: _merge(items, tasks, started))
        return True

    # ---- consultas ----------------------------------------------------------------
    def due(self, now: datetime) -> list[dict]:
        """Com hora, pendentes, já na hora e ainda não avisados."""
        return [r for r in self.all() if not r["feito"] and not r["avisado"]
                and _when(r) is not None and _when(r) <= now]

    def groups(self, now: datetime) -> dict[str, list[dict]]:
        """Pendentes separados em atrasados, hoje (ainda por vir), próximos e sem hora; em ordem de hora."""
        pending = [r for r in self.all() if not r["feito"]]
        timed = sorted((r for r in pending if _when(r)), key=_when)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
        return {
            "atrasados": [r for r in timed if _when(r) <= now],
            "hoje": [r for r in timed if now < _when(r) <= end_of_day],
            "proximos": [r for r in timed if _when(r) > end_of_day],
            "sem_hora": [r for r in pending if not _when(r)],
        }


def _merge(items: list[dict], tasks: list[dict], started: datetime) -> None:
    """Aplica na cópia do PC as tarefas pendentes lidas do Google."""
    remote = {t["id"]: t for t in tasks}
    keep = []
    for r in items:
        gid = r.get("gid")
        if not gid:
            if not r["feito"]:
                keep.append(r)  # ainda vai para o Google
            continue
        if r.get("sujo"):  # mudança do PC ainda não enviada vale mais
            remote.pop(gid, None)
            keep.append(r)
            continue
        t = remote.pop(gid, None)
        if t is None:
            # Feito ou apagado em outro lugar, a não ser que tenha sido enviado depois desta leitura.
            if r.get("sinc") and datetime.fromisoformat(r["sinc"]) >= started:
                keep.append(r)
            continue
        r["texto"] = t["titulo"]
        if t["dia"] != _day(r):  # data mudada no celular
            r["quando"] = _at_phone_hour(t["dia"])
            r["avisado"] = False
        keep.append(r)
    for t in remote.values():  # criadas no celular
        keep.append({"id": uuid.uuid4().hex[:8], "texto": t["titulo"], "quando": _at_phone_hour(t["dia"]),
                     "feito": False, "avisado": False, "criado": datetime.now().astimezone().isoformat(),
                     "gid": t["id"], "sujo": False})
    items[:] = keep
