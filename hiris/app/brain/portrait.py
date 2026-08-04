"""Il ritratto della casa: cosa HIRIS sa, in forma componibile e resa.

Tutte le funzioni qui sono PURE: prendono dati, ritornano dati, non leggono
niente e non scrivono niente. Le fonti sono iniettate dal chiamante
(server.py), cosi' il ritratto e' interamente testabile senza Home Assistant.

IL NOTEVOLE E' DISCRETO. Una porta e' aperta o chiusa, una serratura e'
chiusa o aperta, un termostato scalda o no: sono fatti che cambiano di rado e
il cui cambiamento significa qualcosa. Una temperatura, una potenza,
un'umidita' cambiano di continuo: metterle nel notevole vorrebbe dire che a
ogni osservazione "e' cambiato tutto", che e' lo stesso che dire niente. I
numeri restano disponibili al ragionamento tramite gli strumenti di lettura;
non entrano nella memoria del cambiamento.
"""
from __future__ import annotations

from ..proxy._sanitize import sanitize_ha_value

# Domini il cui stato e' per natura discreto.
_NOTABLE_DOMAINS = frozenset({
    "light", "switch", "lock", "cover", "climate", "alarm_control_panel",
    "fan", "media_player", "person", "device_tracker", "valve", "water_heater",
    "vacuum",
})

# I binary_sensor entrano SOLO con queste classi: sono quelle il cui
# cambiamento e' un evento della casa. Volutamente ESCLUSE motion/occupancy:
# cambiano decine di volte l'ora e sommergerebbero il delta.
_NOTABLE_BINARY_CLASSES = frozenset({
    "door", "window", "garage_door", "opening",
    "smoke", "gas", "moisture", "problem", "safety", "tamper",
})

_UNREADABLE = frozenset({"unavailable", "unknown", ""})


def notable_state(states: list[dict]) -> dict[str, str]:
    """entity_id -> stato, per le sole entita' il cui stato merita memoria.

    `states` ha la forma di EntityCache.all_states(): la chiave dell'id e'
    ``id``, non ``entity_id``.
    """
    out: dict[str, str] = {}
    for raw in states or []:
        if not isinstance(raw, dict):
            continue
        eid = raw.get("id")
        state = raw.get("state")
        if not eid or not isinstance(state, str):
            continue
        if state.strip().lower() in _UNREADABLE:
            continue
        domain = raw.get("domain") or str(eid).split(".")[0]
        if domain == "binary_sensor":
            if (raw.get("device_class") or "") not in _NOTABLE_BINARY_CLASSES:
                continue
        elif domain not in _NOTABLE_DOMAINS:
            continue
        out[str(eid)] = sanitize_ha_value(state)
    return out
