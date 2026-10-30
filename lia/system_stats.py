"""Números do painel Sistema: lidos direto do Windows, sem gastar cota do plano."""
import psutil


def snapshot(requests_today: int, limit_hit: bool, usage_pct: int | None = None) -> dict:
    return {
        "cpu": round(psutil.cpu_percent(interval=None)),
        "mem": round(psutil.virtual_memory().percent),
        "pedidos_hoje": requests_today,
        "limite": limit_hit,
        "uso_plano": usage_pct,
    }
