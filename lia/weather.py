"""Previsão do tempo para o resumo ao abrir: Open-Meteo (grátis, sem chave e sem conta)."""
import json
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

log = logging.getLogger(__name__)
API = "https://api.open-meteo.com/v1/forecast"

# Códigos WMO do Open-Meteo → como falar
_CODES = {
    0: "céu limpo", 1: "poucas nuvens", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina",
    51: "garoa", 53: "garoa", 55: "garoa forte", 56: "garoa", 57: "garoa",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva", 67: "chuva forte",
    80: "pancadas de chuva", 81: "pancadas de chuva", 82: "pancadas fortes de chuva",
    95: "trovoadas", 96: "trovoadas e granizo", 99: "trovoadas e granizo",
}


def fetch_forecast(lat: float, lon: float, timeout: float = 3) -> dict | None:
    """Agora e hoje no lugar dado; None sem internet ou se o serviço falhar (o resumo segue sem o tempo)."""
    query = urlencode({"latitude": lat, "longitude": lon, "current": "temperature_2m",
                       "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                       "timezone": "auto", "forecast_days": 1})
    try:
        with urlopen(f"{API}?{query}", timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.info("sem previsão do tempo: %s", e)
        return None


def weather_sentence(place: str, data: dict | None) -> str:
    """'No centro agora faz 24 graus. Previsão para hoje: nublado, mínima de 21 e máxima de 28 graus, e 40% de chance de chuva.'"""
    try:
        daily = data["daily"]
        low, high = round(daily["temperature_2m_min"][0]), round(daily["temperature_2m_max"][0])
        sky = _CODES.get(daily["weather_code"][0], "")
        rain = daily.get("precipitation_probability_max", [None])[0]
    except (KeyError, IndexError, TypeError):
        return ""
    now = (data.get("current") or {}).get("temperature_2m")
    place = place[:1].upper() + place[1:]
    parts = [f"{place} agora faz {round(now)} graus." if now is not None else f"Previsão {place[:1].lower() + place[1:]}."]
    rain_txt = f"e {rain}% de chance de chuva" if rain is not None and rain >= 20 else "sem previsão de chuva"
    parts.append(f"Previsão para hoje: {sky + ', ' if sky else ''}mínima de {low} e máxima de {high} graus, {rain_txt}.")
    return " ".join(parts)
