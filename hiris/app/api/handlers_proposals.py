"""Le rotte delle PROPOSTE da fare a mano (spec 2026-09-21 §3).

Le proposte costruibili hanno gia' le loro rotte (`handlers_constructions`):
conferma, rifiuta, ripristina, e sopra ci vive l'officina. Queste sono le
altre -- quelle che deve applicare una persona -- e ne hanno quattro:

- **rifiuta**: chiude. Torna in coda solo se la prova cambia, e il confronto
  lo fa il proponente (`proposer_turn.open_observations`), non questa rotta.
- **fatta fuori da HA**: chiude **come applicata**, dichiarando che non e'
  stato HIRIS a farlo e che non puo' verificarlo in nessun oggetto. Per il
  verificatore, un domani, «l'ho fatto io» e «lo hai fatto tu» sono due prove
  diverse, e appiattirle su «chiusa» le perderebbe entrambe.
- **rifalla**: apre un turno del proponente con le tue richieste di modifica
  davanti, e **non ha limiti**: la si puo' far rifare finche' va bene. La
  chiude solo se ne nasce una proposta costruibile, come `superata`
  (`mind/proposal_redo.py`).
- **rendila automatica** (attori, Task 4.5): non chiude niente subito. Fa
  comporre al proponente un'automazione, che arriva fra le costruzioni con
  anteprima e conferma; quando nasce, questa proposta si chiude col legame
  (`mind/automate_turn.py`). Su una proposta `alto` la rotta non c'e': 403.

`crea` non c'e', e non e' una dimenticanza: qui non c'e' nessun oggetto da
scrivere in Home Assistant. Quella strada e' l'officina, e «rendila
automatica» ci arriva passando dal proponente.

I codici portano la distinzione che conta, come le rotte gemelle: 404 «non
esiste», 409 «esiste ma non e' piu' in attesa», 503 «non disponibile» -- cosi'
la pagina non deve leggere il testo dell'errore per sapere quale delle tre
mostrare. Prima di tutti, 403: le proposte sono di chi amministra (spec
2026-09-26 §3, decisione 5), e ognuna porta il gesto `amministrare` in
`admission.ADMISSION`, lo stesso della pagina Costruzioni: lo chiede il
confine, prima del gestore.

Le rotte le registra `add_routes`, qui: `server.py` non cresce (regola del
proprietario del 06/10/2026).
"""
from __future__ import annotations

import logging

from aiohttp import web

from ..chat_thread import unknown_id_text
from ..mind import automate_turn, proposal_redo
from .boundary import error_response, json_object

logger = logging.getLogger(__name__)

_NOT_FOUND = unknown_id_text("nessuna proposta")
_NOT_PENDING = "quella proposta non e’ piu’ in attesa: qualcuno l’ha gia’ decisa."
_NO_STORE = "l’archivio delle proposte non e’ disponibile in questo momento."

def _store(request):
    return request.app.get("observations")


def _row(store, ident: str) -> dict | None:
    return store.proposal(ident)


async def _close(request, outcome: str) -> web.Response:
    store = _store(request)
    if store is None:
        return error_response(503, _NO_STORE)
    ident = request.match_info.get("id", "")
    row = _row(store, ident)
    if row is None:
        return error_response(404, _NOT_FOUND)
    body = await json_object(request, optional=True)
    nota = str(body.get("nota") or "").strip() or None
    if not store.close_proposal(ident, outcome, why=nota):
        return error_response(409, _NOT_PENDING)
    return web.json_response({"proposta": _row(store, ident)})


async def handle_proposal_reject(request: web.Request) -> web.Response:
    """«No.» Chiude la proposta, e resta visibile con la sua data."""
    return await _close(request, "rifiutata")


async def handle_proposal_done(request: web.Request) -> web.Response:
    """«Si', ma l'ho fatta io, fuori da Home Assistant.»

    Chiude **come applicata**: e' un esito positivo, e HIRIS dichiara di non
    averlo fatto lui e di non poterlo verificare in nessun oggetto.
    """
    return await _close(request, "fatta_fuori")


async def handle_proposal_redo(request: web.Request) -> web.Response:
    """«Non cosi'.» Rifa' la proposta con le tue richieste di modifica davanti.

    E' un turno del proponente (`mind/proposal_redo.py`, D16), dalla partenza
    unica: **sul ponte risponde 202** e la risposta arriva in differita -- la
    pagina la trova rileggendo le Proposte, dove la riga porta il suo
    `rifacimento`; **sulla catena risponde subito**, con l'esito.

    **Non ha limiti**: ogni giro resta attaccato alla proposta, cosi' il
    modello vede il filo intero e non ripropone quello che hai appena
    rifiutato. Uno alla volta, pero': un secondo mentre il primo e' in volo e'
    409.
    """
    store = _store(request)
    if store is None:
        return error_response(503, _NO_STORE)
    ident = request.match_info.get("id", "")
    row = _row(store, ident)
    if row is None:
        return error_response(404, _NOT_FOUND)
    if row["stato"] != store.PROPOSAL_PENDING:
        return error_response(409, _NOT_PENDING)
    body = await json_object(request, optional=True)
    richiesta = str(body.get("richiesta") or "").strip()
    if not richiesta:
        return error_response(400, "scrivi cosa vuoi cambiare: senza, il giro rifarebbe "
                                   "la stessa cosa.")
    try:
        result = await proposal_redo.redo(request.app, store, row, richiesta,
                                          subject=request.get("soggetto"))
    except proposal_redo.InFlight:
        return error_response(409, "su questa proposta c’e’ gia’ un rifacimento in "
                                   "corso: aspetta che finisca.")
    except proposal_redo.NoModel:
        return error_response(503, "nessun modello collegato: non posso rifare la proposta "
                                   "adesso.")
    except proposal_redo.NoAnswer:
        return error_response(503, _NO_ANSWER)
    except Exception as error:
        logger.warning("proposta: il giro di «rifalla» non e' partito (%s: %s)",
                       type(error).__name__, error)
        return error_response(503, _NO_ANSWER)

    if result["esito"] is None:
        return web.json_response({"proposta": _row(store, ident)}, status=202)
    if result["esito"] == proposal_redo.UNREADABLE:
        return error_response(502, "la risposta del modello non si e' potuta leggere: "
                                   "riprova.")
    corpo = {"proposta": _row(store, ident), "esito": result["esito"]}
    # La nota si compone DOPO la chiamata: chi ha risposto si misura, e prima
    # si misurerebbe l'esito del turno precedente.
    nota = _nota_porta(request.app, downgrade=result["ripiego"])
    if nota:
        corpo["nota"] = nota
    return web.json_response(corpo)


async def handle_proposal_automate(request: web.Request) -> web.Response:
    """«Rendila automatica»: fa partire il turno, e torna subito (202).

    La regola di quando il comando esiste e' una sola
    (`automate_turn.refusal`), e la legge anche la pagina: 403 per una
    proposta `alto` -- il comando non esiste --, 409 per tutto cio' che
    cambia col tempo (gia' decisa, gia' provata, un turno in corso), 503
    senza modello.
    """
    store = _store(request)
    if store is None:
        return error_response(503, _NO_STORE)
    ident = request.match_info.get("id", "")
    row = _row(store, ident)
    if row is None:
        return error_response(404, _NOT_FOUND)
    reason = automate_turn.refusal(row, pending=store.PROPOSAL_PENDING,
                                   in_flight=automate_turn.preparing(request.app),
                                   redoing=proposal_redo.redoing(request.app, row))
    if reason is not None:
        return error_response(403 if reason == automate_turn.HIGH_REFUSAL else 409,
                              reason)
    reason = automate_turn.begin(request.app, row)
    if reason is not None:
        return error_response(503, reason)
    return web.json_response({"proposta": _row(store, ident)}, status=202)


def add_routes(router) -> None:
    """Le rotte delle proposte da fare a mano."""
    router.add_post("/api/proposals/{id}/reject", handle_proposal_reject)
    router.add_post("/api/proposals/{id}/done", handle_proposal_done)
    router.add_post("/api/proposals/{id}/redo", handle_proposal_redo)
    router.add_post("/api/proposals/{id}/automate", handle_proposal_automate)


#: La risposta di «Rifalla» quando il modello non risponde: il giro non e'
#: partito (`chain_turn` solleva) o nessun backend ha risposto
#: (`TurnOutcome.answered`). Per chi preme il bottone e' la stessa cosa.
_NO_ANSWER = "il modello non ha risposto: riprova."


def _nota_porta(app, *, downgrade: str) -> str:
    """La riga che dichiara il ripiego a consumo di un giro sulla catena, o
    `""` se non c'e' niente da dichiarare.

    Fino al 06/10/2026 aveva un terzo caso -- «il piano potrebbe, ma questa
    porta risponde subito» -- perche' il «Rifalla» non passava mai dal ponte.
    Ora ci passa (D16): sulla catena si arriva solo quando il piano non e' in
    gioco (niente da dire) o non puo' rispondere (il ripiego, con le parole
    di vocabolario delle altre porte).
    """
    from ..model_resolution import downgrade_note
    from ..steering import who_answered

    chi = who_answered(app)
    if not chi or not downgrade:
        # Chi ha risposto non si e' potuto misurare: nessuna nota. Questa riga
        # parla di soldi, e una riga falsa sui soldi e' peggio del silenzio.
        return ""
    return downgrade_note(reason=downgrade, who_answered=chi)
