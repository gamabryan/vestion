import io
import json

from lia import weather
from lia.weather import fetch_forecast, weather_sentence

SAMPLE = {"current": {"temperature_2m": 24.4},
          "daily": {"weather_code": [2], "temperature_2m_max": [28.6], "temperature_2m_min": [20.8],
                    "precipitation_probability_max": [40]}}


def test_sentence_with_rain_chance():
    s = weather_sentence("no centro de São Paulo", SAMPLE)
    assert s == ("No centro de São Paulo agora faz 24 graus. Previsão para hoje: parcialmente nublado, "
                 "mínima de 21 e máxima de 29 graus, e 40% de chance de chuva.")


def test_sentence_without_rain():
    data = json.loads(json.dumps(SAMPLE))
    data["daily"]["weather_code"] = [0]
    data["daily"]["precipitation_probability_max"] = [5]
    s = weather_sentence("no centro", data)
    assert s.endswith("Previsão para hoje: céu limpo, mínima de 21 e máxima de 29 graus, sem previsão de chuva.")


def test_sentence_handles_missing_data():
    assert weather_sentence("no centro", {}) == ""
    assert weather_sentence("no centro", None) == ""


def test_fetch_builds_url_and_parses(monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout):
        seen["url"], seen["timeout"] = url, timeout
        return io.BytesIO(json.dumps(SAMPLE).encode())

    monkeypatch.setattr(weather, "urlopen", fake_urlopen)
    assert fetch_forecast(-23.02, -43.46, timeout=2) == SAMPLE
    assert "latitude=-23.02" in seen["url"] and "longitude=-43.46" in seen["url"]
    assert "api.open-meteo.com" in seen["url"] and seen["timeout"] == 2


def test_fetch_failure_returns_none(monkeypatch):
    def boom(url, timeout):
        raise OSError("sem internet")
    monkeypatch.setattr(weather, "urlopen", boom)
    assert fetch_forecast(-23.02, -43.46) is None
