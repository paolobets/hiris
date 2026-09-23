"""Le rotte delle PROPOSTE da fare a mano (spec 2026-09-21 §3).

Le proposte costruibili hanno gia' le loro rotte (`handlers_constructions`):
conferma, rifiuta, ripristina, e sopra ci vive l'officina. Queste sono le
altre -- quelle che deve applicare una persona -- e ne hanno tre:

- **rifiuta**: chiude. Torna in coda solo se la prova cambia, e il confronto
  lo fa l'attuatore (`actuator.to_handle`), non questa rotta.
- **fatta fuori da HA**: chiude **come applicata**, dichiarando che non e'
  stato HIRIS a farlo e che non puo' verificarlo in nessun oggetto. Per il
  verificatore, un domani, «l'ho fatto io» e «lo hai fatto tu» sono due prove
  diverse, e appiattirle su «chiusa» le perderebbe entrambe.
- **rifalla**: non chiude niente. Apre un giro nuovo con le tue richieste di
  modifica davanti al modello, e **non ha limiti**: la si puo' far rifare
  finche' va bene.

`crea` non c'e', e non e' una dimenticanza: qui non c'e' nessun oggetto da
scrivere in Home Assistant. Quella strada e' l'officina.

I codici portano la distinzione che conta, come le rotte gemelle: 404 «non
esiste», 409 «esiste ma non e' piu' in attesa», 503 «non disponibile» -- cosi'
la pagina non deve leggere il testo dell'errore per sapere quale delle tre
mostrare.
"""
from __future__ import annotations

import json
import logging
import time

from aiohttp import web

logger = logging.getLogger(__name__)

_NOT_FOUND = "non ho nessuna proposta con quell’identificatore."
_NOT_PENDING = "quella proposta non e’ piu’ in attesa: qualcuno l’ha gia’ decisa."
_NO_STORE = "l’archivio delle proposte non e’ disponibile in questo momento."

#: La domanda del «Rifalla». Porta la proposta scartata e la richiesta di
#: modifica: **senza la scartata il modello potrebbe riproporla**, ed e' il
#: motivo per cui il filo dei giri si accoda invece di sostituirsi.
_REDO_SYSTEM = """Sei l'attuatore di HIRIS. Hai gia' fatto una proposta al
proprietario, e lui ti chiede di rifarla in un altro modo.

Non rifare la stessa cosa: cambia strada, tenendo la domanda a cui la proposta
risponde. Se la richiesta di modifica rende la proposta impossibile, dillo
invece di inventare qualcosa che non sta in piedi.

Rispondi SOLO con un oggetto JSON:
{"testo": "cosa fare, in una frase", "perche": "perche' lo proponi"}"""


def _store(request):
    return request.app.get("observations")


def _row(store, ident: str) -> dict | None:
    for row in store.proposals():
        if row["id"] == ident:
            return row
    return None


async def _close(request, outcome: str) -> web.Response:
    store = _store(request)
    if store is None:
        return web.json_response({"errore": _NO_STORE}, status=503)
    ident = request.match_info.get("id", "")
    row = _row(store, ident)
    if row is None:
        return web.json_response({"errore": _NOT_FOUND}, status=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    nota = str((body or {}).get("nota") or "").strip() or None
    if not store.close_proposal(ident, outcome, why=nota, now_ts=time.time()):
        return web.json_response({"errore": _NOT_PENDING}, status=409)
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
    store = _store(request)
    if store is None:
        return web.json_response({"errore": _NO_STORE}, status=503)
    ident = request.match_info.get("id", "")
    row = _row(store, ident)
    if row is None:
        return web.json_response({"errore": _NOT_FOUND}, status=404)
    if row["stato"] != "attesa":
        return web.json_response({"errore": _NOT_PENDING}, status=409)
    try:
        body = await request.json()
    except Exception:
        body = {}
    richiesta = str((body or {}).get("richiesta") or "").strip()
    if not richiesta:
        return web.json_response(
            {"errore": "scrivi cosa vuoi cambiare: senza, il giro rifarebbe "
                       "la stessa cosa."}, status=400)

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response(
            {"errore": "nessun modello collegato: non posso rifare la proposta "
                       "adesso."}, status=503)

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

    lines = ["La proposta che hai fatto, e che il proprietario non vuole cosi':",
             f"  {row['testo']}",
             f"  (il perche' che avevi scritto: {row['perche']})"]
    for giro in row["giri"]:
        lines.append(f"  gia' scartata prima: {giro.get('scartata')}")
        lines.append(f"  perche' lui aveva chiesto: {giro.get('richiesta')}")
    lines += ["", "Cosa ti chiede di cambiare:", f"  {richiesta}"]
    try:
        answer = await runner.chat(user_message="\n".join(lines),
                                   system_prompt=_REDO_SYSTEM)
    except Exception as error:
        logger.warning("proposta: il giro di «rifalla» non e' partito (%s: %s)",
                       type(error).__name__, error)
        return web.json_response(
            {"errore": "il modello non ha risposto: riprova."}, status=503)

    testo, perche = _read_proposal(answer)
    if testo is None:
        return web.json_response(
            {"errore": "la risposta del modello non si e' potuta leggere: "
                       "riprova."}, status=502)
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


def _read_proposal(answer: str) -> tuple[str | None, str | None]:
    """`(testo, perche)` dalla risposta del modello, o `(None, None)`.

    Stessa forma delle altre letture di questo prodotto: o esce un dato, o
    esce niente -- mai un'eccezione, perche' una risposta storta non deve far
    cadere una rotta.
    """
    text = str(answer or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    testo = str(data.get("testo") or "").strip()
    if not testo:
        return None, None
    return testo, str(data.get("perche") or "").strip() or None
