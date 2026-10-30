"""Resumo falado ao abrir: montado no PC a partir da agenda e do Gmail, sem gastar cota do plano."""
from datetime import datetime

NOT_CONNECTED = ("Oi, estou pronto. Preciso que você conecte sua conta Google para eu ver sua agenda e seus e-mails.")
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


def briefing_text(now: datetime, events: list[dict] | None, unread: list[dict] | None) -> str:
    if events is None or unread is None:
        return NOT_CONNECTED
    parts = [f"{_greeting(now)}."]
    if not events:
        parts.append("Sua agenda está livre hoje.")
    else:
        n = len(events)
        sentence = f"Hoje você tem {n} compromisso{'s' if n > 1 else ''}"
        upcoming = [e for e in events if not e["dia_todo"] and e["inicio"].astimezone() >= now.astimezone()]
        if upcoming:
            nxt = upcoming[0]
            sentence += f"; o próximo é {nxt['titulo']} {spoken_time(nxt['inicio'].astimezone())}"
        parts.append(sentence + ".")
    important = sum(1 for m in unread if m.get("importante"))
    if important:
        parts.append(f"Você tem {important} e-mail{'s' if important > 1 else ''} importante{'s' if important > 1 else ''} "
                     f"não lido{'s' if important > 1 else ''}.")
    return " ".join(parts)
