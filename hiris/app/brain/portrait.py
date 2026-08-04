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
        # Il nome area e' testo libero del registro aree di HA (l'utente lo
        # scrive a mano) e diventa qui la chiave con cui il ritratto finisce
        # in ENTRAMBI i prompt (reasoner.py e coverage_review.py bypassano
        # _san sul ritratto, fidandosi che sia "gia' sanificato alla fonte,
        # stringa per stringa"): senza questa riga quella fiducia sarebbe
        # falsa proprio per il nome area. Stesso trattamento gia' applicato
        # ai nomi area in semantic_context_map.py.
        area_nome = sanitize_ha_value(str(area))
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
            elif (
                dominio in _APERTO_DOMINI
                or dominio == "binary_sensor"
                # Una serratura aperta appartiene alle aperture, non alle
                # accensioni: "acceso: Serratura ingresso" si legge come una
                # lampada, ma una porta sbloccata e' semanticamente (e per
                # importanza) un'apertura. Lo stesso vale per una serratura
                # con otturatore aperto.
                or (dominio == "lock" and stato.lower() in ("unlocked", "open"))
            ):
                aperto.append(etichetta)
            else:
                acceso.append(etichetta)
        if acceso or aperto or allerta:
            if area_nome in aree:
                # Due nomi area diversi possono sanitizzarsi alla stessa chiave
                # (e.g. due nomi differing solo in frasi filtrate, o oltre il
                # limite dei 120 caratteri). Merge le liste anziche' sovrascrivere.
                aree[area_nome]["acceso"].extend(acceso)
                aree[area_nome]["aperto"].extend(aperto)
                aree[area_nome]["allerta"].extend(allerta)
            else:
                aree[area_nome] = {"acceso": acceso, "aperto": aperto,
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


def render_portrait(portrait, *, max_chars: int = 1800) -> str:
    """Blocco leggibile per il prompt. Stringa vuota se non c'e' niente da dire.

    Il chiamante deve trattare "" come "nessun blocco": e' il contratto che
    tiene i prompt identici a prima quando il ritratto non e' disponibile.
    """
    try:
        p = portrait if isinstance(portrait, dict) else {}
        aree = p.get("aree")
        aree = aree if isinstance(aree, dict) else {}
        cambiato = p.get("cambiato")
        cambiato = cambiato if isinstance(cambiato, list) else []

        righe: list[str] = []

        # L'allerta viene PRIMA di tutto: un rilevatore che ha scattato e' la
        # cosa piu' importante che la casa possa dire, e non deve finire in
        # fondo a una riga fra le luci accese.
        allerte = [
            f"- {area}: " + ", ".join(str(x) for x in
                                      ((aree.get(area) or {}).get("allerta") or []))
            for area in sorted(aree)
            if (aree.get(area) or {}).get("allerta")
        ]
        if allerte:
            righe.append("ALLERTA:")
            righe.extend(allerte)

        casa: list[str] = []
        for area in sorted(aree):
            dati = aree.get(area) or {}
            parti: list[str] = []
            acceso = dati.get("acceso") or []
            aperto = dati.get("aperto") or []
            if acceso:
                parti.append("acceso: " + ", ".join(str(x) for x in acceso))
            if aperto:
                parti.append("aperto: " + ", ".join(str(x) for x in aperto))
            if parti:
                casa.append(f"- {area} — " + " · ".join(parti))
        # L'intestazione solo se ha qualcosa sotto: una casa in cui l'unica cosa
        # da dire e' un allarme non deve mostrare "Com'e' la casa:" a vuoto.
        if casa:
            if righe:
                righe.append("")
            righe.append("Com'e' la casa:")
            righe.extend(casa)

        # Build changes items first, then add header only if there are actual items
        cambiato_righe: list[str] = []
        for c in (cambiato or []):
            if not isinstance(c, dict):
                continue
            nome = c.get("nome") or c.get("entity_id") or "?"
            was = c.get("was")
            da = f"da {was} " if was is not None else ""
            cambiato_righe.append(f"- {nome}: {da}a {c.get('now')}")

        if cambiato_righe:
            if righe:
                righe.append("")
            righe.append("Cos'e' cambiato dall'ultima volta:")
            righe.extend(cambiato_righe)

        testo = "\n".join(righe)
        if not testo.strip():
            return ""
        if len(testo) > max_chars:
            if max_chars <= 0:
                return ""
            testo = testo[: max_chars - 1].rstrip() + "…"
        return testo
    except Exception:
        return ""
