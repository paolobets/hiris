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

**Tutte e cinque sono di chi amministra** (spec 2026-09-26 §3, decisione 5):
ognuna porta il gesto `amministrare` nella tabella delle rotte
(`admission.ADMISSION`), e il confine lo chiede per ogni soggetto prima di
qualunque gestore, quindi prima di toccare un archivio (F-01, Tappa 7).
"""
from __future__ import annotations

import time

from aiohttp import web

from ..action.construction.revisions import STATES_SOSPESO
from ..action.write_outcome import silent
from ..chat_thread import subject_from_thread, unknown_id_text, without_thread
from ..mind import automate_turn
from .boundary import error_response, occurrence_out
from .soffitto import approved_services, subject_name

# Un solo testo per «quell'id non esiste», usato sia da chi legge sia da chi
# agisce: due frasi diverse per lo stesso fatto sarebbero una piccola
# incoerenza da mantenere sincronizzata a mano per sempre.
_NOT_FOUND = unknown_id_text("nessuna costruzione")


def _store(request):
    return request.app.get("constructions")


async def handle_get_constructions(request: web.Request) -> web.Response:
    store = _store(request)
    if store is None:
        return error_response(503, "archivio non disponibile")
    # Una lettura non scrive: le scadute escono scadute da sole
    # (`revisions._EXPIRED_SQL`). Fino al 06/10/2026 questa rotta le segnava
    # sul disco prima di elencare, e la chat poteva confermarne una che
    # nessuno aveva ancora aperto (misura del Task 4.0 degli attori).
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

    **Il motivo di un tentativo si legge dalla cronaca** (D-26, Tappa 7,
    Task 3, 07/10/2026): l'officina non lo copia piu' nella riga, che porta
    l'`esecuzione_id` della voce che lo dice. Le righe che un motivo proprio
    ce l'hanno -- scaduta, disdetta, risanata al riavvio, e quelle scritte
    prima di quel giorno -- lo tengono.
    """
    if row.get("motivo") is None and row.get("esecuzione_id"):
        journal = app.get("journal")
        voce = journal.read(row["esecuzione_id"]) if journal is not None else None
        if voce is not None and voce.get("errore"):
            row = {**row, "motivo": voce["errore"]}
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
    # copia del testo nell'archivio delle costruzioni. Si chiede per legame,
    # fra le chiuse comprese (e' proprio chiudendosi che la proposta a mano
    # porta il legame), e non fra le ultime 200 (Tappa 8, T3).
    built = store.list(now=time.time(), pending_only=pending_only, limit=200)
    origins = (observations.proposal_origins(row["id"] for row in built)
               if observations is not None else {})
    rows = [{**await _out(app, row, approved), "chi_applica": _APPLIES_HIRIS,
             "sospesa": _construction_suspended(row),
             "nata_da": origins.get(row["id"])}
            for row in built]
    if observations is not None:
        from ..mind import proposal_redo

        # Se il comando «Rendila automatica» c'e', e se un turno la sta
        # preparando: la regola e' quella della rotta (`automate_turn.refusal`),
        # e la pagina riceve la risposta invece di ricalcolarla (C-12).
        # `rifacimento`: un «Rifalla» sul ponte non ancora arrivato, come lo
        # dice la coda (attori, Task 4.4). La pagina lo disegna nella riga, e
        # cosi' sopravvive a una ricarica.
        in_flight = automate_turn.preparing(app)
        rows += [{**await _out(app, row, approved), "chi_applica": _APPLIES_YOU,
                  "a_mano": True,
                  "sospesa": row["stato"] == observations.PROPOSAL_PENDING,
                  "rifacimento": proposal_redo.state(app, row),
                  "in_preparazione": in_flight == row["id"],
                  "automatizzabile": automate_turn.refusal(
                      row, pending=observations.PROPOSAL_PENDING,
                      in_flight=in_flight,
                      redoing=proposal_redo.redoing(app, row)) is None}
                 for row in by_hand]
    return sorted(rows, key=lambda r: r.get("creata_ts") or 0, reverse=True)


async def handle_get_construction(request: web.Request) -> web.Response:
    store = _store(request)
    if store is None:
        return error_response(503, "archivio non disponibile")
    row = store.read(request.match_info["id"], now=time.time())
    if row is None:
        return error_response(404, _NOT_FOUND)
    return web.json_response(
        {"construction": {**await _out(request.app, row, approved_services(request.app)),
                          "sospesa": _construction_suspended(row)}})


async def _act(request: web.Request, verb: str) -> web.Response:
    """Le due scritture della pagina verso Home Assistant, da un punto solo.

    Passano dallo stesso cancello di tutte le rotte di questa pagina (il
    gesto `amministrare` in `admission.ADMISSION`): dal 26/09/2026 la pagina
    intera e' di chi amministra (spec 2026-09-26 §3, decisione 5), e una
    regola per le scritture e un'altra per le letture sarebbero due regole.
    """
    store = _store(request)
    workshop = request.app.get("workshop")
    if store is None or workshop is None:
        return error_response(503, "officina non disponibile")
    ident = request.match_info["id"]
    if store.read(ident, now=time.time()) is None:
        return error_response(404, _NOT_FOUND)
    method = getattr(workshop, verb)
    occurrence = await method(ident, actor="pagina", exchange=None,
                              now=time.time(),
                              subject=request.get("soggetto"))
    if not occurrence["eseguito"]:
        # Un guasto di TRASPORTO verso Home Assistant (ondata finale, punto
        # 7, terza pulizia) non e' «la proposta non e' piu' in attesa»: e' la
        # stessa indisponibilita' che le due GET, qui sopra, dichiarano con
        # 503. Si legge la `causa` dell'esito, la forma delle due porte
        # (`action/write_outcome.py`, E-04): fino al 07/10/2026 era un flag
        # dell'officina, `guasto_rete`, che questa rotta toglieva dal corpo.
        status = 503 if silent(occurrence) else 409
        return web.json_response(occurrence_out(occurrence), status=status)
    return web.json_response(occurrence_out(occurrence))


async def handle_confirm_construction(request: web.Request) -> web.Response:
    return await _act(request, "apply")


async def handle_restore_construction(request: web.Request) -> web.Response:
    return await _act(request, "restore")


async def handle_reject_construction(request: web.Request) -> web.Response:
    """Il «no»: passa dall'officina, che lo scrive nell'archivio e basta.

    Non tocca Home Assistant -- non c'e' niente da scrivere -- ma passa
    dalla porta del canale della configurazione (`Workshop.reject`, E-12,
    Tappa 7, Task 3, 07/10/2026): fino a quel giorno questa rotta chiamava
    l'archivio da se', e le transizioni di una proposta avevano due porte.

    **E passa dal cancello** (spec 2026-09-26 §3, decisione 5): fino al
    26/09 dire di no era di tutti, perche' chi non costruiva vedeva comunque
    la coda. Adesso la coda e' di chi costruisce, e il suo «no» con lei.
    """
    store = _store(request)
    workshop = request.app.get("workshop")
    if store is None or workshop is None:
        return error_response(503, "officina non disponibile")
    ident = request.match_info["id"]
    if store.read(ident, now=time.time()) is None:
        return error_response(404, _NOT_FOUND)
    occurrence = workshop.reject(ident, now=time.time())
    if "errore" in occurrence:
        return web.json_response(occurrence_out(occurrence), status=409)
    return web.json_response(occurrence_out(occurrence))
