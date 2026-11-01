"""Resumo falado ao abrir: montado no PC a partir da agenda e do Gmail, sem gastar cota do plano."""
from datetime import datetime

NOT_CONNECTED = ("Oi, estou pronto. Preciso que você conecte sua conta Google para eu ver sua agenda e seus e-mails.")
MAX_EVENTS = 5
MAX_MAILS = 5
_HOURS = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete", 8: "oito",
          9: "nove", 10: "dez", 11: "onze"}


def spoken_time(dt: datetime) -> str:
    """'às três da tarde', 'às dez e meia da manhã', 'ao meio-dia'."""
    h, m = dt.hour, dt.minute
    minutes = "" if m == 0 else " e meia" if m == 30 else f" e {m}"
    if h == 0:
        return f"à meia-noite{minutes}"
    if h == 12:
        return f"ao meio-dia{minutes}"
    period = "da manhã" if h < 12 else "da tarde" if h < 18 else "da noite"
    return f"às {_HOURS[h % 12]}{minutes} {period}"


def _greeting(now: datetime) -> str:
    return "Bom dia" if now.hour < 12 else "Boa tarde" if now.hour < 18 else "Boa noite"


def _join(parts: list[str], rest: int, rest_word: str) -> str:
    """'a; b; e c' — com 'e mais N ...' quando a lista foi cortada."""
    if rest:
        parts = parts + [f"mais {rest} {rest_word if rest > 1 else rest_word.rstrip('s')}"]
    if len(parts) == 1:
        return parts[0]
    return "; ".join(parts[:-1]) + "; e " + parts[-1]


def _events_sentence(events: list[dict]) -> str:
    if not events:
        return "Sua agenda está livre hoje."
    n = len(events)
    parts = [f"{e['titulo']}, o dia todo" if e["dia_todo"] else f"{e['titulo']} {spoken_time(e['inicio'].astimezone())}"
             for e in events[:MAX_EVENTS]]
    rest = n - len(parts)
    return f"Hoje você tem {n} compromisso{'s' if n > 1 else ''}: {_join(parts, rest, 'compromissos')}."


def _mails_sentence(mails: list[dict]) -> str:
    if not mails:
        return "Nenhum e-mail chegou hoje."
    n = len(mails)
    parts = [f"{m['de']}, sobre {m['assunto']}" + (", que parece importante" if m.get("importante") else "")
             for m in mails[:MAX_MAILS]]
    rest = n - len(parts)
    return f"Hoje chegaram {n} e-mail{'s' if n > 1 else ''}: {_join(parts, rest, 'e-mails')}."


def _reminders_sentence(groups: dict[str, list[dict]] | None) -> str:
    """Lembretes de hoje (com hora) e atrasados. Os sem hora ficam só no painel."""
    if not groups:
        return ""
    parts = []
    today = groups.get("hoje", [])
    if today:
        n = len(today)
        items = [f"{r['texto']} {spoken_time(datetime.fromisoformat(r['quando']).astimezone())}" for r in today[:MAX_EVENTS]]
        parts.append(f"Você tem {n} lembrete{'s' if n > 1 else ''} hoje: {_join(items, n - len(items), 'lembretes')}.")
    late = groups.get("atrasados", [])
    if late:
        n = len(late)
        items = [r["texto"] for r in late[:MAX_EVENTS]]
        parts.append(f"{n} {'estão atrasados' if n > 1 else 'está atrasado'}: {_join(items, n - len(items), 'lembretes')}.")
    return " ".join(parts)


def briefing_text(now: datetime, events: list[dict] | None, mails: list[dict] | None,
                  reminders: dict[str, list[dict]] | None = None, weather: str = "") -> str:
    """Saudação, previsão do tempo, compromissos de hoje (com horário), e-mails de hoje e lembretes do dia."""
    if events is None or mails is None:
        parts = [NOT_CONNECTED, weather]
    else:
        parts = [f"{_greeting(now)}.", weather, _events_sentence(events), _mails_sentence(mails)]
    parts.append(_reminders_sentence(reminders))
    return " ".join(p for p in parts if p)
