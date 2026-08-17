from __future__ import annotations
from aiohttp import web

from ..proxy.entity_cache import inventario_non_leggibile
from ..casa.anagrafe import dominio_di


def _csv(v: str | None):
    return {x.strip() for x in v.split(",") if x.strip()} if v else None


def filter_entities(states: list[dict], domains: set | None, device_classes: set | None,
                     q: str | None = None, limit: int = 1000) -> list[dict]:
    """Filtra l'inventario entità -- unica forma canonica per /api/entities.

    `domains`/`device_classes` sono set già pre-parsati (CSV split a monte,
    tipicamente dall'handler via `_csv`). `q` è un substring case-insensitive
    cercato sia sull'entity_id sia sul friendly_name (nome), combinabile con
    i filtri domain/device_class.
    """
    out = []
    q_low = (q or "").strip().lower()[:100] or None
    for s in states or []:
        eid = s.get("id") or s.get("entity_id")
        if not eid:
            continue
        dom = s.get("domain") or dominio_di(eid)
        dc = s.get("device_class")
        name = s.get("name") or ""
        if domains and dom not in domains:
            continue
        if device_classes and dc not in device_classes:
            continue
        if q_low and q_low not in eid.lower() and q_low not in name.lower():
            continue
        out.append({
            "entity_id": eid,
            # `name or None`, MAI `name or eid`: un id tecnico non e' un nome,
            # ne' tale e quale ne' ingentilito. E' la stessa disciplina che
            # `memoria/riconoscitore.costruisci_indice` dichiara e rispetta --
            # qui si faceva l'opposto, e chi legge non aveva modo di sapere se
            # «sensor.abc» fosse un nome vero o un ripiego. L'`entity_id` e'
            # nella stessa riga: chi vuole ripiegare lo fa sapendo cosa sta
            # mostrando.
            "friendly_name": name or None,
            "domain": dom,
            "device_class": dc,
            "state": s.get("state"),
            # Senza, `state: "72"` non dice se sono gradi Celsius o Fahrenheit
            # -- e chi consuma questa rotta non puo' ripiegare sull'unita'
            # della casa (vedi `casa.anagrafe.sistema_di_riferimento`).
            "unit": s.get("unit") or None,
            # Misura di adesso o contatore che sale: e' cio' che dice se ha
            # senso chiederne una statistica.
            "state_class": s.get("state_class"),
        })
        if len(out) >= limit:
            break
    return out


async def handle_list_entities(request: web.Request) -> web.Response:
    """Inventario entità per la UI.

    Un `{"entities": []}` con inventario non leggibile è la stessa bugia dei
    tool di chat: dice «questa casa non ha entità» quando la frase vera è «non
    ho potuto guardare». Qui diventa un 503 dichiarato, senza la chiave
    `entities`, così un chiamante che la legga fallisce invece di mostrare un
    elenco vuoto.

    Consumatori, aggiornato alla fetta E5 Task 6: **nessuno in questo repo**.
    I due che c'erano -- `static/config/entity-picker.js` e
    `static/config/agentbot-route.js`, che degradavano già su risposta
    non-ok -- sono usciti insieme alle pagine del workbench. La rotta
    **resta** lo stesso: è superficie API interna, consumata dall'MCP
    Gateway fuori da questo repo. Da lì in poi il censimento la classifica
    come «chiamata solo dai test»: è atteso e dichiarato, non un difetto
    da chiudere togliendo la rotta.
    """
    cache = request.app.get("entity_cache")
    if cache is not None and not hasattr(cache, "all_states"):
        cache = None
    guasto = inventario_non_leggibile(cache)
    if guasto is not None:
        return web.json_response(guasto, status=503)
    ents = filter_entities(cache.all_states(),
                           _csv(request.query.get("domain")),
                           _csv(request.query.get("device_class")),
                           request.rel_url.query.get("q"))
    return web.json_response({"entities": ents})
