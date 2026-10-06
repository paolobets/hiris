"""Le cinque rotte della pagina Costruzioni.

Non serializzano niente per conto proprio: la forma di una costruzione e' UNA
e vive in `action/construction/revisions.py::_row`, gia' usata dall'archivio.
Una seconda forma costruita qui renderebbe la pagina e la chat due racconti
diversi dello stesso atto il primo giorno in cui qualcuno aggiunge un campo da
una parte sola (fondamenta 3).

**Confermare dalla pagina non passa dalla guardia del turno**, e non e' una
scappatoia: la guardia esiste per impedire a un MODELLO di darsi il permesso
da solo (spec §7). Un clic sulla pagina e' gia' l'umano. L'origine lo dice
esplicitamente -- `pagina` -- e finisce nella cronaca, cosi' resta scritto chi
ha deciso.

I codici portano la distinzione che conta: 404 «non esiste», 409 «esiste ma
non e' piu' in attesa», 503 «non disponibile» (l'archivio per le due GET e
per il rifiuto, l'archivio o l'officina per conferma e ripristino -- vedi i
messaggi qui sotto, che sono testo VERO e non una parafrasi). Un 400 unico
avrebbe costretto la pagina a leggere il testo dell'errore per sapere quale
dei tre mostrare.

**Il rifiuto non passa dall'officina.** Le altre due POST scrivono su Home
Assistant; questa no -- il «no» del proprietario si scrive nell'archivio e
basta, e farlo passare dall'officina gli darebbe la stessa superficie di
rischio di una conferma. Non e' una quinta rotta uguale alle altre: e'
un'assenza deliberata.

**Tutte e cinque sono di chi costruisce** (spec 2026-09-26 §3, decisione 5):
ognuna chiama per prima `soffitto.require_builder`, prima di toccare un
archivio. `tests/test_soffitto_cancello.py` deriva l'elenco dal router e lo
verifica.
"""
from __future__ import annotations

import time

from aiohttp import web

from ..action.construction.revisions import STATES_SOSPESO
from ..chat_thread import subject_from_thread, unknown_id_text, without_thread
from ..mind import automate_turn
from .boundary import error_response, occurrence_out
from .soffitto import approved_services, require_builder, subject_name

# Un solo testo per «quell'id non esiste», usato sia da chi legge sia da chi
# agisce: due frasi diverse per lo stesso fatto sarebbero una piccola
# incoerenza da mantenere sincronizzata a mano per sempre.
_NOT_FOUND = unknown_id_text("nessuna costruzione")


def _store(request):
    return request.app.get("constructions")


async def handle_get_constructions(request: web.Request) -> web.Response:
    refusal = require_builder(request)
    if refusal is not None:
        return refusal
    store = _store(request)
    if store is None:
        return error_response(503, "archivio non disponibile")
    # Le scadute si segnano PRIMA di elencare, o la pagina mostrerebbe come
    # «da approvare» proposte che l'officina rifiuterebbe di applicare -- e il
    # bottone mentirebbe.
    store.scadi(time.time())
    pending_only = request.query.get("pending_only") in ("1", "true", "si")
    return web.json_response(
        {"constructions": await _both_queues(request.app, store, pending_only)})


#: Chi applica una proposta. Le costruibili le scrive HIRIS in Home Assistant
#: (con il tuo si'), le altre le fai tu: **e' un campo, non una seconda
#: pagina** -- «un posto solo dove si decide» e' una promessa sulla pagina, e i
#: due archivi restano due perche' una frase in prosa dentro una tabella di
#: diff sarebbe il doppione per forma (spec 2026-09-21 §3).
_APPLIES_HIRIS = "hiris"
_APPLIES_YOU = "tu"

async def _out(app, row: dict, approved: list[dict]) -> dict:
    """Una riga come esce dalle due rotte GET: senza il filo, con chi l'ha
    chiesta.

    Il filo di chi ha proposto NON attraversa il confine (fix round 1 Task 7
    delle chat divise): `_row()` lo porta perche' l'officina deve poterlo
    leggere, ma la risposta no -- `chat_thread.without_thread`, la funzione di
    tutte le righe col filo. Al suo posto esce `chiesta_da`, il NOME di chi
    l'ha chiesta (spec 2026-09-26 §3): una riga senza filo -- le proposte a
    mano, nate dall'osservatore, e le orfane -- porta `None`, cosi' le due
    code hanno la stessa forma. Il nome viene da `soffitto.subject_name`, la
    stessa casa dell'autore di un giudizio; `approved` e' l'archivio dei
    servizi letto UNA volta per risposta, non una per riga.
    """
    return {**without_thread(row),
            "chiesta_da": await subject_name(app, subject_from_thread(row.get("thread")),
                                             approved=approved)}


def _construction_suspended(row: dict) -> bool:
    """Se una costruzione aspetta ancora: `STATES_SOSPESO`, anche `in_corso`
    (rivendicata e non ancora decisa). E' il campo `sospesa` delle righe
    delle due GET (C-12, Tappa 4, Task 5): la pagina lo legge, e non sa piu'
    quali stati lo dicano."""
    return row["stato"] in STATES_SOSPESO


async def _both_queues(app, store, pending_only: bool) -> list[dict]:
    """Le due code in un elenco solo, dalla piu' recente.

    **Si riordina**, e non si concatena: due code messe in fila darebbero un
    elenco il cui ordine dipende da quale archivio si legge per primo, cioe'
    da un dettaglio di implementazione.
    """
    approved = approved_services(app)
    # `sospesa` e' la regola di ciascuna coda, decisa qui e non nella pagina
    # (C-12): le costruzioni con `_construction_suspended`, le proposte a mano
    # finche' sono `PROPOSAL_PENDING`.
    observations = app.get("observations")
    by_hand = (observations.proposals(pending_only=pending_only)
               if observations is not None else [])
    # «Nata da» (attori, Task 4.5): la proposta a mano da cui e' nata una
    # costruzione, letta per id dall'archivio gemello -- un legame, non una
    # copia del testo nell'archivio delle costruzioni. Si cerca anche fra le
    # chiuse: e' proprio chiudendosi che la proposta a mano porta il legame.
    every_hand = (by_hand if not pending_only or observations is None
                  else observations.proposals())
    origins = {p["costruzione_id"]: {"id": p["id"], "testo": p["testo"]}
               for p in every_hand if p.get("costruzione_id")}
    rows = [{**await _out(app, row, approved), "chi_applica": _APPLIES_HIRIS,
             "sospesa": _construction_suspended(row),
             "nata_da": origins.get(row["id"])}
            for row in store.list(pending_only=pending_only, limit=200)]
    if observations is not None:
        # Se il comando «Rendila automatica» c'e', e se un turno la sta
        # preparando: la regola e' quella della rotta (`automate_turn.refusal`),
        # e la pagina riceve la risposta invece di ricalcolarla (C-12).
        in_flight = automate_turn.preparing(app)
        rows += [{**await _out(app, row, approved), "chi_applica": _APPLIES_YOU,
                  "a_mano": True,
                  "sospesa": row["stato"] == observations.PROPOSAL_PENDING,
                  "in_preparazione": in_flight == row["id"],
                  "automatizzabile": automate_turn.refusal(
                      row, pending=observations.PROPOSAL_PENDING,
                      in_flight=in_flight) is None}
                 for row in by_hand]
    return sorted(rows, key=lambda r: r.get("creata_ts") or 0, reverse=True)


async def handle_get_construction(request: web.Request) -> web.Response:
    refusal = require_builder(request)
    if refusal is not None:
        return refusal
    store = _store(request)
    if store is None:
        return error_response(503, "archivio non disponibile")
    row = store.read(request.match_info["id"])
    if row is None:
        return error_response(404, _NOT_FOUND)
    return web.json_response(
        {"construction": {**await _out(request.app, row, approved_services(request.app)),
                          "sospesa": _construction_suspended(row)}})


async def _act(request: web.Request, verb: str) -> web.Response:
    """Le due scritture della pagina verso Home Assistant, da un punto solo.

    Passano dallo stesso cancello di tutte le rotte di questa pagina
    (`soffitto.require_builder`): dal 26/09/2026 la pagina intera e' di chi
    costruisce (spec 2026-09-26 §3, decisione 5), e una regola per le
    scritture e un'altra per le letture sarebbero due regole.
    """
    refusal = require_builder(request)
    if refusal is not None:
        return refusal

    store = _store(request)
    workshop = request.app.get("workshop")
    if store is None or workshop is None:
        return error_response(503, "officina non disponibile")
    ident = request.match_info["id"]
    if store.read(ident) is None:
        return error_response(404, _NOT_FOUND)
    method = getattr(workshop, verb)
    occurrence = await method(ident, actor="pagina", exchange=None,
                              now=time.time(),
                              subject=request.get("soggetto"))
    if "errore" in occurrence:
        # Un guasto di TRASPORTO verso Home Assistant (ondata finale, punto
        # 7, terza pulizia) non e' «la proposta non e' piu' in attesa»: e' la
        # stessa indisponibilita' che le due GET, qui sopra, dichiarano con
        # 503. Prima questo ramo appiattiva ogni errore dell'officina su 409,
        # anche quando la causa era Home Assistant irraggiungibile. Il flag
        # e' interno (`Workshop._fallita`/`_rete`): non deve uscire nel corpo
        # della risposta.
        status = 503 if occurrence.pop("guasto_rete", False) else 409
        return web.json_response(occurrence_out(occurrence), status=status)
    return web.json_response(occurrence_out(occurrence))


async def handle_confirm_construction(request: web.Request) -> web.Response:
    return await _act(request, "apply")


async def handle_restore_construction(request: web.Request) -> web.Response:
    return await _act(request, "restore")


async def handle_reject_construction(request: web.Request) -> web.Response:
    """Il «no»: si scrive nell'archivio e basta.

    Non passa dall'officina, e non e' una svista: non c'e' niente da scrivere
    su Home Assistant, e farlo passare da li' darebbe a un rifiuto la stessa
    superficie di rischio di una conferma.

    **Ma passa dal cancello** (spec 2026-09-26 §3, decisione 5): fino al
    26/09 dire di no era di tutti, perche' chi non costruiva vedeva comunque
    la coda. Adesso la coda e' di chi costruisce, e il suo «no» con lei.
    """
    refusal = require_builder(request)
    if refusal is not None:
        return refusal
    store = _store(request)
    if store is None:
        return error_response(503, "archivio non disponibile")
    ident = request.match_info["id"]
    if store.read(ident) is None:
        return error_response(404, _NOT_FOUND)
    occurrence = store.mark_cancelled(ident, now=time.time())
    if "errore" in occurrence:
        return web.json_response(occurrence_out(occurrence), status=409)
    return web.json_response(occurrence_out(occurrence))
