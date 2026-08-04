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


_ACCESO = frozenset({"on", "open", "heat", "cool", "heat_cool", "auto", "playing",
                     "cleaning", "unlocked"})
_APERTO_DOMINI = frozenset({"cover", "valve"})

# Un rilevatore di fumo che scatta NON e' un'apertura: e' un allarme, ed e' la
# cosa piu' importante che una casa possa dire. Queste classi hanno un secchio
# proprio, che nella resa viene per primo.
_ALLERTA_CLASSES = frozenset({"smoke", "gas", "moisture", "problem", "safety",
                              "tamper"})


def _meta(states: list[dict]) -> dict[str, dict]:
    """entity_id -> {"nome": str sanificato, "dc": device_class}."""
    out: dict[str, dict] = {}
    for raw in states or []:
        if isinstance(raw, dict) and raw.get("id"):
            out[str(raw["id"])] = {
                "nome": sanitize_ha_value(str(raw.get("name") or raw["id"])),
                "dc": str(raw.get("device_class") or ""),
            }
    return out


def build_portrait(*, area_map, states, baseline, changes) -> dict:
    """Compone il ritratto. Non solleva mai: ogni fonte assente degrada a vuoto."""
    meta = _meta(states)
    notable = notable_state(states or [])
    base = baseline if isinstance(baseline, dict) else {}

    aree: dict[str, dict] = {}
    for area, eids in (area_map or {}).items():
        if not isinstance(eids, (list, tuple)) or area == "__no_area__":
            continue
        acceso: list[str] = []
        aperto: list[str] = []
        allerta: list[str] = []
        for eid in eids:
            stato = notable.get(str(eid))
            if stato is None or stato.lower() not in _ACCESO:
                continue
            info = meta.get(str(eid)) or {}
            nome = info.get("nome") or str(eid)
            since = (base.get(str(eid)) or {}).get("since")
            etichetta = f"{nome} (da {since})" if since else nome
            dominio = str(eid).split(".")[0]
            if dominio == "binary_sensor" and info.get("dc") in _ALLERTA_CLASSES:
                allerta.append(etichetta)
            elif dominio in _APERTO_DOMINI or dominio == "binary_sensor":
                aperto.append(etichetta)
            else:
                acceso.append(etichetta)
        if acceso or aperto or allerta:
            aree[str(area)] = {"acceso": acceso, "aperto": aperto,
                               "allerta": allerta}

    cambiato = []
    for c in (changes or []):
        if not isinstance(c, dict) or not c.get("entity_id"):
            continue
        eid = str(c["entity_id"])
        was = c.get("was")
        now_ = c.get("now")
        cambiato.append({
            "nome": (meta.get(eid) or {}).get("nome") or eid, "entity_id": eid,
            # `was` e `now` sono stati di entita' HA come tutti gli altri: il
            # vincolo globale vale anche qui.
            "was": sanitize_ha_value(str(was)) if was is not None else None,
            "now": sanitize_ha_value(str(now_)) if now_ is not None else None,
            "since": c.get("since"),
        })

    return {
        "aree": aree,
        "cambiato": cambiato,
        "conteggi": {
            "entita": len(meta),
            "aree": len([a for a in (area_map or {}) if a != "__no_area__"]),
        },
    }
