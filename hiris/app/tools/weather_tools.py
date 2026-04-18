import os
from typing import Any, Callable, Awaitable, Optional
import aiohttp

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

TOOL_DEF = {
    "name": "get_weather_forecast",
    "description": "Get weather forecast for the home location for the next N hours. Uses Open-Meteo (free, no API key required).",
    "input_schema": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "Number of hours of forecast to retrieve (1-168)",
                "minimum": 1,
                "maximum": 168,
            }
        },
        "required": ["hours"],
    },
}


async def _default_fetch(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_weather_forecast(
    hours: int,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    _fetch: Callable[[str], Awaitable[dict]] = _default_fetch,
) -> dict[str, Any]:
    lat = latitude or float(os.environ.get("HA_LATITUDE", "45.4642"))
    lon = longitude or float(os.environ.get("HA_LONGITUDE", "9.1900"))
    url = (
        f"{OPEN_METEO_URL}?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,cloudcover,precipitation"
        f"&forecast_hours={hours}"
        f"&timezone=auto"
    )
    data = await _fetch(url)
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            {"time": t, "temperature": temp, "cloudcover": cc, "precipitation": p}
            for t, temp, cc, p in zip(
                times,
                hourly.get("temperature_2m", []),
                hourly.get("cloudcover", []),
                hourly.get("precipitation", []),
            )
        ],
    }
