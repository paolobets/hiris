from __future__ import annotations
import os
from collections import defaultdict
from typing import Any, Callable, Awaitable, Optional
import aiohttp

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

TOOL_DEF = {
    "name": "get_weather_forecast",
    "description": (
        "Get weather forecast for the home location. "
        "For ≤48 h returns hourly compact records: [{h: 'YYYY-MM-DDTHH', t, cc, r}]. "
        "For >48 h returns daily summaries: [{day: 'YYYY-MM-DD', t_lo, t_hi, r, cc}]. "
        "Fields: t=temperature °C, cc=cloud cover %, r=precipitation mm."
    ),
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


def _compress_weather(hourly: dict, hours: int) -> dict:
    """Compress Open-Meteo hourly dict into compact format.

    ≤48 h → {"hourly": [{"h": ..., "t": ..., "cc": ..., "r": ...}]}
    >48 h → {"daily":  [{"day": ..., "t_lo": ..., "t_hi": ..., "r": ..., "cc": ...}]}
    """
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    clouds = hourly.get("cloudcover", [])
    rain = hourly.get("precipitation", [])

    if not times:
        return {"hourly": []} if hours <= 48 else {"daily": []}

    if hours <= 48:
        return {
            "hourly": [
                {
                    "h": t[:13],        # "YYYY-MM-DDTHH"
                    "t": round(temp, 1),
                    "cc": int(cc),
                    "r": round(r, 2),
                }
                for t, temp, cc, r in zip(times, temps, clouds, rain)
            ]
        }

    # Daily summary for long forecasts
    by_day: dict[str, dict[str, list]] = defaultdict(lambda: {"t": [], "cc": [], "r": []})
    for t, temp, cc, r in zip(times, temps, clouds, rain):
        day = t[:10]
        by_day[day]["t"].append(temp)
        by_day[day]["cc"].append(cc)
        by_day[day]["r"].append(r)

    daily = []
    for day in sorted(by_day):
        d = by_day[day]
        daily.append({
            "day": day,
            "t_lo": round(min(d["t"]), 1),
            "t_hi": round(max(d["t"]), 1),
            "r":    round(sum(d["r"]), 2),
            "cc":   int(sum(d["cc"]) / len(d["cc"])),
        })
    return {"daily": daily}


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
    hours = int(hours)
    lat = latitude or float(os.environ.get("HA_LATITUDE", "45.4642"))
    lon = longitude or float(os.environ.get("HA_LONGITUDE", "9.1900"))
    url = (
        f"{OPEN_METEO_URL}?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,cloudcover,precipitation"
        f"&forecast_hours={hours}"
        f"&timezone=auto"
    )
    data = await _fetch(url)
    return _compress_weather(data.get("hourly", {}), hours)
