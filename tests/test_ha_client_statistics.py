import pytest
from hiris.app.proxy.ha_client import HAClient


@pytest.mark.asyncio
async def test_statistiche_returns_dict(monkeypatch):
    ha = HAClient("http://ha.local:8123", "tok")
    captured = {}

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        captured["msg_type"] = msg_type
        captured["extra"] = extra
        return {"sensor.temp": [{"start": "2026-06-20T00:00:00+00:00",
                                 "mean": 21.6, "min": 19.1, "max": 24.3}]}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.statistiche(["sensor.temp"], periodo="day", giorni=30)
    assert captured["msg_type"] == "recorder/statistics_during_period"
    assert captured["extra"]["statistic_ids"] == ["sensor.temp"]
    assert captured["extra"]["period"] == "day"
    assert "sensor.temp" in out["serie"]


@pytest.mark.asyncio
async def test_statistiche_un_guasto_non_e_una_serie_vuota(monkeypatch):
    """Prima un risultato non-dict (websocket giu') valeva {} -- indistinguibile
    da "nessuna statistica per queste entita'". Adesso e' un guasto dichiarato."""
    ha = HAClient("http://ha.local:8123", "tok")

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return None

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.statistiche(["sensor.temp"], periodo="hour", giorni=1)
    assert "serie" not in out
    assert "errore" in out
