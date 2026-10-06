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
- **rifalla**: non chiude niente. Apre un giro nuovo con le tue richieste di
  modifica davanti al modello, e **non ha limiti**: la si puo' far rifare
  finche' va bene.
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
mostrare. Prima di tutti, 403: le proposte sono di chi costruisce (spec
2026-09-26 §3, decisione 5), e ognuna chiama per prima
`soffitto.require_builder`, lo stesso cancello della pagina Costruzioni.

Le rotte le registra `add_routes`, qui: `server.py` non cresce (regola del
proprietario del 06/10/2026).
"""
from __future__ import annotations

import logging
import time

from aiohttp import web

from ..chat_thread import unknown_id_text
from ..mind import automate_turn
from ..steering import chain_runner, chain_turn, read_json
from .boundary import error_response, json_object
from .soffitto import require_builder

logger = logging.getLogger(__name__)

_NOT_FOUND = unknown_id_text("nessuna proposta")
_NOT_PENDING = "quella proposta non e’ piu’ in attesa: qualcuno l’ha gia’ decisa."
_NO_STORE = "l’archivio delle proposte non e’ disponibile in questo momento."

#: La domanda del «Rifalla». Porta la proposta scartata e la richiesta di
#: modifica: **senza la scartata il modello potrebbe riproporla**, ed e' il
#: motivo per cui il filo dei giri si accoda invece di sostituirsi.
_REDO_SYSTEM = """Sei l'attuatore di HIRIS. Hai gia' fatto una proposta a
chi amministra la casa, che ti chiede di rifarla in un altro modo.

Non rifare la stessa cosa: cambia strada, tenendo la domanda a cui la proposta
risponde. Se la richiesta di modifica rende la proposta impossibile, dillo
invece di inventare qualcosa che non sta in piedi.

Rispondi SOLO con un oggetto JSON:
{"testo": "cosa fare, in una frase", "perche": "perche' lo proponi"}"""


#: Il tetto del «Rifalla», dichiarato (Tappa 6, Task 4): e' il 4.096 di
#: fabbrica di `claude_runner.MAX_TOKENS` che prendeva senza dirlo, ora
#: scritto. Non misurato: la risposta e' una frase e un perche'.
_REDO_MAX_TOKENS = 4096


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
    """«Non cosi'.» Rifa' il turno con le tue richieste di modifica davanti.

    **Non chiude niente e non ha limiti**: ogni giro resta attaccato alla
    proposta -- la forma scartata e cio' che hai chiesto -- cosi' il modello
    vede il filo intero e non ripropone quello che hai appena rifiutato.

    **Il giro si scrive solo a risposta arrivata**: una proposta riscritta a
    meta' sarebbe peggio di una non riscritta.
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

    runner = chain_runner(request.app)
    if runner is None:
        return error_response(503, "nessun modello collegato: non posso rifare la proposta "
                                   "adesso.")

    # **La stessa domanda che si fanno le altre sei porte, dalla stessa
    # funzione** (reperto C-5, 23/09/2026). `steering.py` dichiara dal
    # 22/08/2026 che «una terza porta che nascesse domani non potrebbe
    # inventarsene una terza senza accorgersene»: questa porta e' nata dopo e
    # se n'era inventata una, andando dritta al router. Su una casa che gira
    # interamente sul Piano Max ogni «Rifalla» finiva a consumo, e non lo
    # diceva nessuno -- il difetto pagato dal vivo il 21/08 sulle promesse.
    #
    # **Qui si DICHIARA, non si devia**: «Rifalla» risponde nello stesso
    # istante in cui la si preme, e il piano risponde in differita da un altro
    # processo. Mandarla sul ponte e' la forma giusta e costa una fetta sua --
    # il bottone smette di rispondere e la pagina deve interrogare -- ed e' in
    # `docs/BACKLOG.md` con questa ragione accanto. Fino ad allora il giro si
    # paga a consumo, e si dice.
    from ..steering import who_answers
    route, downgrade = who_answers(request.app)

    lines = ["La proposta che hai fatto, e che chi amministra la casa non vuole cosi':",
             f"  {row['testo']}",
             f"  (il perche' che avevi scritto: {row['perche']})"]
    for giro in row["giri"]:
        lines.append(f"  gia' scartata prima: {giro.get('scartata')}")
        lines.append(f"  la richiesta di allora: {giro.get('richiesta')}")
    lines += ["", "Cosa ti chiede di cambiare:", f"  {richiesta}"]
    try:
        # «Rifalla» è un turno di chat a tutti gli effetti: parte da un gesto
        # del proprietario nella pagina, e il suo costo va contato con gli
        # altri suoi — non in una specie a parte che nessuno guarderebbe.
        answer, turn = await chain_turn(
            runner, "chat", usage=request.app.get("usage"),
            soggetto=request.get("soggetto"), max_tokens=_REDO_MAX_TOKENS,
            user_message="\n".join(lines), system_prompt=_REDO_SYSTEM)
    except Exception as error:
        logger.warning("proposta: il giro di «rifalla» non e' partito (%s: %s)",
                       type(error).__name__, error)
        return error_response(503, _NO_ANSWER)
    # La frase del router quando nessun backend risponde non e' una proposta
    # illeggibile (502): e' il modello che non ha risposto, come sopra (G29-1).
    if not turn.answered:
        return error_response(503, _NO_ANSWER)

    testo, perche = _read_proposal(answer, truncated=turn.truncated)
    if testo is None:
        return error_response(502, "la risposta del modello non si e' potuta leggere: "
                                   "riprova.")
    store.add_proposal_round(ident, request=richiesta, text=testo,
                             now_ts=time.time())
    if perche:
        store.rewrite_proposal_why(ident, perche)
    corpo = {"proposta": _row(store, ident)}
    # La nota si compone DOPO la chiamata: chi ha risposto si misura, e prima
    # si misurerebbe l'esito del turno precedente.
    nota = _nota_porta(request.app, route=route, downgrade=downgrade)
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
    reason = automate_turn.refusal(row, pending=store.PROPOSAL_PENDING,
                                   in_flight=automate_turn.preparing(request.app))
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


def _nota_porta(app, *, route: str, downgrade: str) -> str:
    """La riga che dichiara da dove e' passato questo giro. `""` se non c'e'
    niente da dichiarare.

    **Tre casi, e sono tre cose diverse.**

    - Il piano non e' in gioco (spento, o mai avuto): niente da dire. Dirlo a
      ogni giro direbbe al proprietario che sta perdendo qualcosa che non ha.
    - Il piano non PUO' rispondere (token assente, tetto pieno): e' il ripiego
      che le altre porte gia' dichiarano, con le sue parole di vocabolario.
    - Il piano potrebbe, ma questa porta risponde subito: frase sua. Dire «il
      piano non ha risposto» qui sarebbe falso.
    """
    from ..model_resolution import downgrade_note, synchronous_door_note
    from ..steering import who_answered

    chi = who_answered(app)
    if not chi:
        # Chi ha risposto non si e' potuto misurare: nessuna nota. Questa riga
        # parla di soldi, e una riga falsa sui soldi e' peggio del silenzio.
        return ""
    if downgrade:
        return downgrade_note(reason=downgrade, who_answered=chi)
    if route == "ponte":
        return synchronous_door_note(who_answered=chi)
    return ""


def _read_proposal(answer: str, *,
                   truncated: bool = False) -> tuple[str | None, str | None]:
    """`(testo, perche)` dalla risposta del modello, o `(None, None)`.

    Il JSON lo cava il lettore unico (`steering.read_json`, D-11), con la
    stessa tolleranza degli altri mestieri: fino al 05/10/2026 questo era un
    quinto lettore, che rifiutava «Ecco la proposta: {...}». Un turno troncato
    non si legge (D2). Qui resta la forma della proposta.
    """
    data, _reason = read_json(answer, shape=dict, what="una proposta",
                              truncated=truncated)
    if data is None:
        return None, None
    testo = str(data.get("testo") or "").strip()
    if not testo:
        return None, None
    return testo, str(data.get("perche") or "").strip() or None
