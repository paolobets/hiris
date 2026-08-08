"""Test di tools/weather_tools.py.

fetta E2 Task 8 ("escono i trentaquattro"): questo file era test_tools.py e
provava insieme sei moduli di hiris/app/tools/. Cinque sono usciti dal file
(le loro funzioni esecutrici sono uscite dal codice, orfane dal Task 7 -- il
`ToolDispatcher` che le chiamava e' uscito lui per primo): `ha_tools.
get_entity_states`/`get_area_entities`/`get_home_status`/`get_entities_on`/
`get_entities_by_domain`, `energy_tools.get_energy_history`/
`_compress_energy_history`, `automation_tools.get_ha_automations`/
`trigger_automation`/`toggle_automation`. `weather_tools.get_weather_forecast`
resta invece VIVA: la chiama davvero `server.py` (situazioni/Sentinella,
`_snap_deps["get_weather"]`), non e' orfana -- e' l'unico soggetto rimasto in
questo file, rinominato per dirlo.

I test su `notifiche.send_notification` (telegram, retropanel -- non
duplicati in tests/test_notifications.py, che copre ha_persistent/ha_push/
alias/canale ignoto) sono stati spostati LI', non cancellati: quel modulo non
c'entra con tools/ e non ha mai smesso di essere vivo."""
import pytest
from hiris.app.tools.weather_tools import get_weather_forecast, _compress_weather


@pytest.mark.asyncio
async def test_get_weather_forecast_returns_compact_hourly():
    """hours <= 48 → compact hourly format, no lat/lon."""
    mock_resp_data = {
        "hourly": {
            "time": ["2026-04-18T12:00", "2026-04-18T13:00"],
            "temperature_2m": [22.1, 23.5],
            "cloudcover": [10, 20],
            "precipitation": [0.0, 0.1],
        }
    }

    async def fake_fetch(url: str) -> dict:
        return mock_resp_data

    result = await get_weather_forecast(hours=2, _fetch=fake_fetch)
    assert "latitude" not in result
    assert "longitude" not in result
    assert "hourly" in result
    assert len(result["hourly"]) == 2
    h0 = result["hourly"][0]
    assert h0["h"] == "2026-04-18T12"   # truncated to hour
    assert h0["t"] == 22.1
    assert h0["cc"] == 10
    assert h0["r"] == 0.0


def test_compress_weather_hourly_for_short_forecast():
    hourly = {
        "time": ["2026-04-18T10:00", "2026-04-18T11:00"],
        "temperature_2m": [20.0, 21.0],
        "cloudcover": [30, 40],
        "precipitation": [0.0, 0.5],
    }
    result = _compress_weather(hourly, hours=2)
    assert "hourly" in result
    assert "daily" not in result
    assert result["hourly"][0] == {"h": "2026-04-18T10", "t": 20.0, "cc": 30, "r": 0.0}
    assert result["hourly"][1] == {"h": "2026-04-18T11", "t": 21.0, "cc": 40, "r": 0.5}


def test_compress_weather_daily_for_long_forecast():
    times = (
        ["2026-04-18T00:00", "2026-04-18T06:00", "2026-04-18T12:00", "2026-04-18T18:00"] +
        ["2026-04-19T00:00", "2026-04-19T12:00"]
    )
    temps = [10.0, 15.0, 22.0, 18.0, 8.0, 20.0]
    clouds = [10, 20, 30, 40, 50, 60]
    rain   = [0.0, 0.0, 0.5, 0.2, 0.0, 1.0]
    hourly = {
        "time": times,
        "temperature_2m": temps,
        "cloudcover": clouds,
        "precipitation": rain,
    }
    result = _compress_weather(hourly, hours=72)
    assert "daily" in result
    assert "hourly" not in result
    days = {d["day"]: d for d in result["daily"]}
    assert "2026-04-18" in days
    d18 = days["2026-04-18"]
    assert d18["t_lo"] == 10.0
    assert d18["t_hi"] == 22.0
    assert abs(d18["r"] - 0.7) < 0.001
    assert "2026-04-19" in days


def test_compress_weather_handles_empty_hourly():
    result = _compress_weather({"time": [], "temperature_2m": [], "cloudcover": [], "precipitation": []}, hours=24)
    assert result == {"hourly": []}


def test_compress_weather_daily_empty_for_long():
    result = _compress_weather({"time": [], "temperature_2m": [], "cloudcover": [], "precipitation": []}, hours=72)
    assert result == {"daily": []}
