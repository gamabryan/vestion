"""Lembretes e tarefas do usuário, guardados só no PC (um JSON legível na pasta do Vestion).

O app e o servidor MCP (outro processo) usam o mesmo arquivo: cada operação relê, altera e grava
de forma atômica.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path


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


class ReminderStore:
    def __init__(self, path: Path):
        self.path = Path(path)
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

    # ---- operações ----------------------------------------------------------------
    def all(self) -> list[dict]:
        with self._lock:
            return self._read()

    def get(self, rid: str) -> dict | None:
        return next((r for r in self.all() if r["id"] == rid), None)

    def add(self, texto: str, quando: datetime | None = None) -> dict:
        item = {"id": uuid.uuid4().hex[:8], "texto": texto.strip(),
                "quando": quando.isoformat() if quando else None,
                "feito": False, "avisado": False, "criado": datetime.now().astimezone().isoformat()}
        self._update(lambda items: items.append(item))
        return item

    def _set(self, rid: str, **fields) -> bool:
        def change(items):
            for r in items:
                if r["id"] == rid:
                    r.update(fields)
                    return True
            return False
        return bool(self._update(change))

    def complete(self, rid: str) -> bool:
        return self._set(rid, feito=True)

    def mark_warned(self, rid: str) -> bool:
        return self._set(rid, avisado=True)

    def snooze(self, rid: str, minutes: int, now: datetime) -> bool:
        return self._set(rid, quando=(now + timedelta(minutes=minutes)).isoformat(), avisado=False)

    def delete(self, rid: str) -> bool:
        def change(items):
            before = len(items)
            items[:] = [r for r in items if r["id"] != rid]
            return len(items) != before
        return bool(self._update(change))

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
