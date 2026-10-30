"""Google Agenda do usuário (calendário principal): consultar, criar, mover e cancelar."""
from datetime import date, datetime, time, timedelta


def _local(dt: datetime) -> datetime:
    return dt.astimezone()


def _parse_when(when: dict) -> tuple[datetime | date, bool]:
    if "dateTime" in when:
        return datetime.fromisoformat(when["dateTime"].replace("Z", "+00:00")), False
    return date.fromisoformat(when["date"]), True


def _parse(event: dict) -> dict:
    start, all_day = _parse_when(event.get("start", {}))
    end, _ = _parse_when(event.get("end", event.get("start", {})))
    return {"id": event["id"], "titulo": event.get("summary", "(sem título)"), "inicio": start, "fim": end,
            "dia_todo": all_day, "local": event.get("location", ""),
            "convidados": len(event.get("attendees", []) or [])}


def hhmm(item: dict) -> str:
    if item["dia_todo"]:
        return "Dia todo"
    return _local(item["inicio"]).strftime("%H:%M")


class CalendarClient:
    def __init__(self, service):
        self.service = service

    @classmethod
    def from_credentials(cls, creds):
        from googleapiclient.discovery import build
        return cls(build("calendar", "v3", credentials=creds, cache_discovery=False))

    def events_between(self, start: datetime, end: datetime) -> list[dict]:
        result = self.service.events().list(calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
                                            singleEvents=True, orderBy="startTime", maxResults=50).execute()
        return [_parse(e) for e in result.get("items", []) or []]

    def today(self, now: datetime) -> list[dict]:
        now = _local(now)
        midnight = datetime.combine(now.date(), time(0, 0), tzinfo=now.tzinfo)
        events = self.events_between(midnight, midnight + timedelta(days=1))
        # O Google devolve tudo que toca o dia, inclusive o que começou ontem e passa da meia-noite.
        # "Hoje" = começa hoje; eventos de dia inteiro que cobrem hoje continuam.
        return [e for e in events if e["dia_todo"] or _local(e["inicio"]) >= midnight]

    def get(self, event_id: str) -> dict:
        return _parse(self.service.events().get(calendarId="primary", eventId=event_id).execute())

    def create(self, titulo: str, inicio: datetime, fim: datetime, convidados: list[str] | None = None,
               local: str = "") -> str:
        body = {"summary": titulo, "start": {"dateTime": inicio.isoformat()}, "end": {"dateTime": fim.isoformat()}}
        if local:
            body["location"] = local
        if convidados:
            body["attendees"] = [{"email": e} for e in convidados]
        created = self.service.events().insert(calendarId="primary", body=body,
                                               sendUpdates="all" if convidados else "none").execute()
        return created["id"]

    def move(self, event_id: str, inicio: datetime, fim: datetime) -> None:
        # Mudar o horário não avisa convidados: avisar seria "enviar", que pede confirmação.
        self.service.events().patch(calendarId="primary", eventId=event_id, sendUpdates="none",
                                    body={"start": {"dateTime": inicio.isoformat()},
                                          "end": {"dateTime": fim.isoformat()}}).execute()

    def cancel(self, event_id: str) -> None:
        self.service.events().delete(calendarId="primary", eventId=event_id, sendUpdates="all").execute()
