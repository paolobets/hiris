from __future__ import annotations
from collections import defaultdict
from typing import Optional
from ..proxy.ha_client import HAClient

TOOL_DEF = {
    "name": "get_energy_history",
    "description": (
        "Get energy history for the last N days. "
        "Returns compressed daily records: "
        "[{id, day (YYYY-MM-DD), start (first reading), end (last reading), n (samples)}]. "
        "Use start/end to compute daily delta. "
        "Source entities: consumption meters, solar production, grid import/export."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days of history to retrieve (1-30)",
                "minimum": 1,
                "maximum": 30,
            }
        },
        "required": ["days"],
    },
}


def _compress_energy_history(raw: list[dict]) -> list[dict]:
    """Group raw HA history records by (entity_id, day).

    Input:  [{"entity_id": ..., "state": ..., "last_changed": "YYYY-MM-DDTHH:..."}]
    Output: [{"id": ..., "day": "YYYY-MM-DD", "start": ..., "end": ..., "n": int}]
    """
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in raw:
        eid = item.get("entity_id", "")
        ts = item.get("last_changed", "")
        if not eid or not ts:
            continue
        day = ts[:10]
        buckets[(eid, day)].append(item.get("state", ""))
    result = []
    for (eid, day), readings in sorted(buckets.items()):
        result.append({"id": eid, "day": day, "start": readings[0], "end": readings[-1], "n": len(readings)})
    return result


async def get_energy_history(
    ha: HAClient,
    days: int,
    semantic_map: Optional[object] = None,
) -> list[dict] | dict:
    if semantic_map is not None:
        entity_ids = (
            semantic_map.get_category("energy_meter") +
            semantic_map.get_category("solar_production") +
            semantic_map.get_category("grid_import")
        )
        if not entity_ids:
            return {
                "error": "Nessun contatore energia nella mappa semantica.",
                "hint": "Attendi la classificazione automatica o aggiungi sensori energia.",
            }
    else:
        return {
            "error": "Mappa semantica non disponibile.",
            "hint": "Il sistema sta inizializzando la mappa degli sensori.",
        }
    raw = await ha.get_history(entity_ids=entity_ids, days=int(days))
    return _compress_energy_history(raw)
