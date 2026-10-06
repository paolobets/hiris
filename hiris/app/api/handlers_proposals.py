"""Le rotte delle PROPOSTE da fare a mano (spec 2026-09-21 §3).

Le proposte costruibili hanno gia' le loro rotte (`handlers_constructions`):
conferma, rifiuta, ripristina, e sopra ci vive l'officina. Queste sono le
altre -- quelle che deve applicare una persona -- e ne hanno tre:

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

`crea` non c'e', e non e' una dimenticanza: qui non c'e' nessun oggetto da
scrivere in Home Assistant. Quella strada e' l'officina.

I codici portano la distinzione che conta, come le rotte gemelle: 404 «non
esiste», 409 «esiste ma non e' piu' in attesa», 503 «non disponibile» -- cosi'
la pagina non deve leggere il testo dell'errore per sapere quale delle tre
mostrare. Prima di tutti, 403: le proposte sono di chi costruisce (spec
2026-09-26 §3, decisione 5), e ognuna delle tre chiama per prima
`soffitto.require_builder`, lo stesso cancello della pagina Costruzioni.
"""
from __future__ import annotations

import logging

from aiohttp import web

from ..chat_thread import unknown_id_text
from ..mind import proposal_redo
from .boundary import error_response, json_object
from .soffitto import require_builder

logger = logging.getLogger(__name__)

_NOT_FOUND = unknown_id_text("nessuna proposta")
_NOT_PENDING = "quella proposta non e’ piu’ in attesa: qualcuno l’ha gia’ decisa."
_NO_STORE = "l’archivio delle proposte non e’ disponibile in questo momento."

def _store(request):
    return request.app.get("observations")


def _row(store, ident: str) -> dict | None:
    for row in store.proposals():
        if row["id"] == ident:
            return row
    return None


async def _close(request, outcome: str) -> web.Response:
    refusal = require_builder(request)
    if refusal is not None:
        return refusal
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
    refusal = require_builder(request)
    if refusal is not None:
        return refusal
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
