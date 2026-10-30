"""Google Tasks do usuário (lista padrão "Minhas tarefas").

A API só guarda a DATA de vencimento (a hora é descartada); a hora do aviso fica no PC.
"""
from datetime import date

LIST = "@default"


def _due(d: date | None) -> str | None:
    return f"{d.isoformat()}T00:00:00.000Z" if d else None


def _parse(task: dict) -> dict:
    due = task.get("due")
    return {"id": task["id"], "titulo": task.get("title", "") or "(sem título)",
            "dia": date.fromisoformat(due[:10]) if due else None}


def _gone(e: Exception) -> bool:
    """Tarefa que já não existe no Google (apagada no celular, por exemplo)."""
    return getattr(getattr(e, "resp", None), "status", None) in (404, 410)


class TasksClient:
    def __init__(self, service):
        self.service = service

    @classmethod
    def from_credentials(cls, creds):
        from googleapiclient.discovery import build
        return cls(build("tasks", "v1", credentials=creds, cache_discovery=False))

    def pending(self) -> list[dict]:
        """Tarefas não concluídas: [{id, titulo, dia (date ou None)}]."""
        out, token = [], None
        while True:
            result = self.service.tasks().list(tasklist=LIST, showCompleted=False, showHidden=False,
                                               maxResults=100, pageToken=token).execute()
            out += [_parse(t) for t in result.get("items", []) or [] if t.get("status") != "completed"]
            token = result.get("nextPageToken")
            if not token:
                return out

    def create(self, titulo: str, dia: date | None) -> str:
        body = {"title": titulo}
        if dia:
            body["due"] = _due(dia)
        return self.service.tasks().insert(tasklist=LIST, body=body).execute()["id"]

    def complete(self, task_id: str) -> None:
        try:
            self.service.tasks().patch(tasklist=LIST, task=task_id, body={"status": "completed"}).execute()
        except Exception as e:
            if not _gone(e):
                raise

    def set_day(self, task_id: str, dia: date | None) -> None:
        try:
            self.service.tasks().patch(tasklist=LIST, task=task_id, body={"due": _due(dia)}).execute()
        except Exception as e:
            if not _gone(e):
                raise

    def delete(self, task_id: str) -> None:
        try:
            self.service.tasks().delete(tasklist=LIST, task=task_id).execute()
        except Exception as e:
            if not _gone(e):
                raise
