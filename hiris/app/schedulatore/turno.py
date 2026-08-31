"""Il turno che si sveglia per una promessa «chiedi»: guarda, e risponde.

Non e' autonomia -- il QUANDO l'ha deciso l'utente -- ma e' un modello che
gira SENZA NESSUNO DAVANTI, e questo cambia cosa gli si mette in mano.

Il catalogo qui e' un ELENCO DI AMMISSIONE (`SOLA_LETTURA`), non di esclusione.
Con un elenco di esclusione, uno strumento nuovo che scrive entrerebbe qui da
solo il giorno in cui qualcuno lo aggiunge alla chat, e nessuno se ne
accorgerebbe. Il verso di questa derivazione e' una questione di sicurezza, non
di stile.

`concludi` esiste SOLO in questo catalogo: dalla chat non si vede, perche' li'
a concludere e' la risposta all'utente. E' l'unico modo in cui questo turno
puo' finire, ed e' cio' che rende il SILENZIO un fatto dichiarato invece di
un'assenza da interpretare.
"""
from __future__ import annotations

import logging
import time

from ..casa.strumenti import KNOWLEDGE_TOOLS
from ..decisione_modelli import _MOTIVI_RIPIEGO

logger = logging.getLogger(__name__)

# I sei che leggono e basta. Non `esegui` (tocca la casa), non `ricorda`
# (scrive nella memoria, che dal giro 1 di questa correzione entra nel
# prompt di sistema SANIFICATA -- C-2 -- non piu' verbatim), non
# `prometti`/`disdici` (un turno che si da' appuntamenti da solo e' autonomia
# costruita per sbaglio), non `costruisci`/`conferma` (scrivono
# configurazione: un turno che nessuno guarda non costruisce).
#
# `andamento` e `accaduto` (fetta «HIRIS e il tempo») entrano: leggono e
# basta, ed e' cio' che permette a una promessa delle 17:00 di confrontare la
# temperatura con quella di un'ora prima invece di portarsi dietro una
# fotografia scattata alla nascita.
SOLA_LETTURA = ("cerca", "guarda", "legami", "richiama", "andamento", "accaduto")

CONCLUDI_TOOL_DEF = {
    "name": "concludi",
    "description": (
        "Chiudi questa promessa dicendo cosa hai trovato. E' l'UNICO modo in cui "
        "questo turno puo' finire: se non lo chiami, chi ti ha svegliato non "
        "sapra' cosa dire alla persona. `avvisare` dice se c'e' qualcosa per cui "
        "valga la pena disturbarla: mettilo a `false` quando la condizione che ti "
        "era stata chiesta NON si e' verificata -- non e' un fallimento, e' la "
        "risposta giusta, e viene comunque registrata. Se lo metti a `true` la "
        "notifica alla persona la manda HIRIS per te, sul canale che lei aveva "
        "approvato quando ti ha fatto la promessa: qui non esiste uno strumento "
        "per notificare, e non serve -- chiamare «concludi» E' il modo di "
        "avvisarla. `testo` e' cio' che le diresti: una o due frasi, con i numeri "
        "veri e le loro unita', non un riassunto vago; ed e' anche cio' che le "
        "arriva nella notifica. Non puoi toccare la casa da qui: se la risposta "
        "implica un'azione, dilla come proposta e sara' la persona a decidere."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "avvisare": {
                "type": "boolean",
                "description": "Se c'e' qualcosa da dire adesso alla persona.",
            },
            "testo": {
                "type": "string",
                "description": "Cosa hai trovato, in una o due frasi, coi numeri veri.",
            },
        },
        "required": ["avvisare", "testo"],
    },
}


def tools_promise() -> list[dict]:
    """Il catalogo di questo turno, DERIVATO da quello della chat.

    Le definizioni sono gli STESSI dizionari di `STRUMENTI_CONOSCENZA`, non
    copie: una descrizione migliorata li' vale anche qui, senza che nessuno se
    ne debba ricordare.
    """
    ammessi = [d for d in KNOWLEDGE_TOOLS if d["name"] in SOLA_LETTURA]
    if len(ammessi) != len(SOLA_LETTURA):
        # Un nome ammesso che non esiste piu' nel catalogo della chat (un
        # rinomino) svuoterebbe questo catalogo IN SILENZIO, lasciando il turno
        # cieco. Si dichiara.
        trovati = {d["name"] for d in ammessi}
        logger.error("catalogo della promessa incompleto: mancano %s",
                     sorted(set(SOLA_LETTURA) - trovati))
    return ammessi + [CONCLUDI_TOOL_DEF]


class PromiseDispatcher:
    """Il guardiano del turno: lascia scendere solo i lettori, e tiene `concludi`.

    Sta DAVANTI a `DispatcherStrumenti` invece di modificarlo, per non mettere
    nel dispatcher della chat uno strumento che li' non deve esistere.
    """

    def __init__(self, sotto) -> None:
        self._sotto = sotto
        self.conclusione: dict | None = None

    async def dispatch(self, name: str, argomenti: dict | None) -> dict:
        argomenti = argomenti or {}
        if name == "concludi":
            avvisare = argomenti.get("avvisare")
            text = argomenti.get("testo")
            if not isinstance(avvisare, bool) or not isinstance(text, str):
                return {"errore": ("«concludi» vuole `avvisare` (vero o falso) e "
                                   "`testo` (cosa hai trovato).")}
            self.conclusione = {"avvisare": avvisare, "testo": text}
            return {"concluso": True}
        if name not in SOLA_LETTURA:
            return {"errore": (f"«{name}» non e' disponibile mentre mantengo una "
                               "promessa: qui posso guardare e rispondere, non "
                               "toccare la casa. Se serve un'azione, dilla nel "
                               "testo e decidera' la persona.")}
        return await self._sotto.dispatch(name, argomenti)


async def interpreta_promise(app, promise: dict) -> dict:
    """Sveglia il modello per una promessa «chiedi». Non solleva mai.

    Ritorna `{"avvisare": bool, "testo": str}` oppure `{"errore": str}`. Un
    turno che finisce senza chiamare `concludi` e' un errore dichiarato, non un
    «forse e' andata bene».
    """
    from ..api.handlers_casa import compose_briefing
    from ..api.handlers_chat import create_tool_dispatcher
    from ..instradamento import chi_risponde

    # La STESSA domanda che si fa la chat, dalla STESSA funzione. Fino al
    # 22/08/2026 questo turno non se la faceva affatto e andava dritto al
    # router -- dove il ponte non e' nemmeno un anello -- qualunque cosa
    # dicesse la gerarchia dei modelli che l'utente aveva ordinato. Su una
    # casa che gira interamente sul Piano Claude Max le promesse morivano su
    # chiavi API esaurite mentre la chat funzionava, e nessuna pagina lo
    # diceva.
    via, reason_downgrade = chi_risponde(app)
    if via == "ponte":
        return _accoda_al_bridge(app, promise)

    runner = app.get("llm_router") or app.get("claude_runner")
    if runner is None:
        return {"errore": "non c'era nessun modello a cui chiedere."}

    dispatcher = PromiseDispatcher(create_tool_dispatcher(app))
    try:
        # Lo STESSO nucleo della chat (`compose_briefing`), non una
        # composizione parallela: due contesti che descrivono la stessa casa
        # sono due verita' che divergono.
        briefing, _summary = compose_briefing(app)
    except Exception as error:
        logger.warning("nucleo non componibile per la promessa %s (%s: %s)",
                       promise["id"], type(error).__name__, error)
        briefing = ""

    try:
        answer = await runner.chat(
            user_message=_domanda(promise),
            system_prompt=_prompt_di_system(),
            context_str=briefing,
            conversation_history=[],
            model="auto",
            max_tokens=2000,
            agent_type="promessa",
            thinking_budget=0,
            strumenti=tools_promise(),
            dispatcher=dispatcher,
        )
    except Exception as error:
        logger.warning("turno della promessa %s fallito (%s: %s)",
                       promise["id"], type(error).__name__, error)
        return {"errore": f"il modello non ha risposto ({type(error).__name__})."}

    if dispatcher.conclusione is None:
        logger.warning("promessa %s: il turno non ha chiamato «concludi»; "
                       "aveva risposto %d caratteri di testo",
                       promise["id"], len(answer or ""))
        return {"errore": _senza_conclusione(answer)}
    conclusione = dict(dispatcher.conclusione)
    note = _note_del_downgrade(reason_downgrade)
    if note:
        conclusione["nota"] = note
    return conclusione


# Quanto della risposta del modello entra nel motivo. Il motivo finisce in una
# colonna di SQLite e in una riga della pagina Promesse: riportarla intera
# sarebbe un allegato, non un motivo.
_CEILING_RIPORTO = 300


def _senza_conclusione(answer) -> str:
    """Il motivo di un turno che NON ha chiamato `concludi`, con dentro cio'
    che il modello aveva risposto al suo posto.

    Fino al 21/08/2026 questa funzione non esisteva e il motivo era una
    costante: «il turno non ha concluso: non so cosa dirti». Vera, e
    inutilizzabile -- perche' le TRE uscite del ciclo di `claude_runner.chat`
    che portano qui restituiscono tre stringhe DIVERSE (il testo del modello,
    `_MAX_ITERATIONS_NOTICE`, `_TRUNCATION_NOTICE`) e quella stringa era
    l'unica cosa che le distingueva. `interpreta_promise` la scartava: per
    sapere quale delle tre fosse capitata sulla casa vera e' servita
    un'indagine con tre riproduzioni sull'add-on vivo.

    Quando non c'e' proprio niente da riportare si torna alla frase di prima:
    un virgolettato vuoto affermerebbe «ha detto questo», e questo e' niente.
    """
    detto = answer.strip() if isinstance(answer, str) else ""
    if not detto:
        return "il turno non ha concluso: non so cosa dirti."
    if len(detto) > _CEILING_RIPORTO:
        detto = detto[:_CEILING_RIPORTO].rstrip() + "…"
    return f"il turno non ha concluso. Aveva risposto a parole: «{detto}»"


def _note_del_downgrade(reason: str) -> str:
    """La riga che dichiara un ripiego dal piano alla catena, o "" se non ce n'e'.

    Il ripiego si annuncia OGNI VOLTA (decisione del proprietario, 13 agosto):
    un passaggio dal forfait al consumo che nessuno dichiara si scopre a fine
    mese. In chat lo dice una nota in coda alla risposta (`nota_ripiego`); una
    promessa non ha una risposta in cui metterla -- ha il suo motivo, che si
    legge dalla pagina.

    Non si dice CHI ha risposto, a differenza della chat: li' si misura dal
    registro degli esiti dopo la chiamata, qui non c'e' una request da cui
    leggerlo, e una riga che nominasse il provider sbagliato sarebbe peggio del
    silenzio -- questa riga parla di soldi. Si dice cio' che si sa per certo:
    il piano non ha risposto, e ha risposto la catena, a consumo.
    """
    fatto = _MOTIVI_RIPIEGO.get(reason)
    if not fatto:
        return ""
    return (f"Il Piano Claude Max {fatto}: questo turno l'ha mantenuto la catena, "
            "a consumo.")


def _accoda_al_bridge(app, promise: dict) -> dict:
    """Il turno va al piano: si accoda e si torna SUBITO.

    Il battito non aspetta -- e' cio' che tiene in piedi «mai in ritardo»
    (tolleranza 120 s) quando un turno del ponte dura minuti: le altre
    promesse dello stesso giro partono lo stesso, invece di essere marcate
    saltate mentre questa pensa.

    La promessa resta `in_corso`, e a concluderla sara' `concludi` attraverso
    la rotta MCP (`api/handlers_mcp`), oppure la consegna del job se il turno
    finisce senza aver concluso.

    Il ponte gira altrove e non ha gli archivi: **cio' che non entra nel job
    non esiste per lui**. Da cui `promessa_id` (senza, la rotta MCP non
    saprebbe quale turno sta parlando), la domanda gia' composta con
    l'istantanea, il prompt di sistema del turno di promessa, e il nucleo --
    composto qui perche' e' l'ultimo punto in cui esistono l'app e gli
    archivi, con la STESSA funzione del ramo sincrono.
    """
    from ..api.handlers_casa import compose_briefing
    from ..api.handlers_models import _PREDEFINITI_ARCHIVIO

    try:
        briefing, _summary = compose_briefing(app)
    except Exception as error:
        logger.warning("nucleo non componibile per la promessa %s (%s: %s)",
                       promise["id"], type(error).__name__, error)
        briefing = ""

    # La scadenza dall'ARCHIVIO, come fa `_enqueue_chat_job`: quella che
    # l'utente cambia dev'essere quella che il turno subisce.
    deadline_min = int((app.get("models_config") or {}).get("ponte", {}).get(
        "scadenza_min", _PREDEFINITI_ARCHIVIO["ponte"]["scadenza_min"]))
    now = time.time()
    app["reasoning_queue"].enqueue(
        "promessa",
        {"promessa_id": promise["id"]},
        {
            "promessa_id": promise["id"],
            # `history` e `system_prompt` sono le chiavi che il turno del
            # ponte legge davvero (`agent/runner._reason_chat` ->
            # `prompts.build_chat_messages`): un turno di promessa e' un turno
            # con un contenuto diverso, non una seconda macchina. La domanda
            # entra come l'unico messaggio dell'utente -- che e' esattamente
            # cio' che e': qualcuno, tempo fa, ha chiesto questo.
            "history": [{"role": "user", "content": _domanda(promise)}],
            "system_prompt": _prompt_di_system(),
            "contesto": briefing,
        },
        now + deadline_min * 60,
        now=now,
    )
    logger.info("promessa %s: turno accodato al piano (scadenza %d min)",
                promise["id"], deadline_min)
    return {"accodata": True}


def _prompt_di_system() -> str:
    # Fix finale ④ (review 2026-08-20): questo turno riceve lo STESSO nucleo
    # della chat (`compose_briefing`, vedi `interpreta_promise` sopra), coi
    # suoi `(id: X)` accanto ad aree/piani/automazioni/script -- ma senza
    # queste due righe il prompt non lo spiegava, e il modello non aveva modo
    # di sapere che poteva usarli direttamente invece di chiamare `cerca`.
    # Il parallelismo, qui, e' vero al 100%: il turno gira su `runner.chat`,
    # lo STESSO ciclo di `claude_runner.py` (`BASE_REGOLE_STRUMENTI`) che
    # conta un giro per risposta, non per chiamata -- a differenza del ponte
    # (vedi `agent/prompts._GUIDA_CON_STRUMENTI`, dove la stessa frase e'
    # falsa perche' il tetto MCP conta ogni `tools/call`).
    return (
        "Stai mantenendo una promessa: qualcuno ti ha chiesto, tempo fa, di "
        "guardare qualcosa a quest'ora e di dirgli com'e' andata. Adesso non c'e' "
        "nessuno davanti allo schermo.\n"
        "Gli id fra parentesi che vedi nell'albero della casa -- `Nome (id: X)` -- "
        "sono gia' gli identificatori esatti per gli strumenti: usali direttamente, "
        "non serve chiamare «cerca» per qualcosa che hai gia'.\n"
        "Se devi fare piu' letture indipendenti, chiamale IN PARALLELO nella stessa "
        "risposta: il ciclo conta un giro per risposta, non per chiamata.\n"
        "Guarda con gli strumenti che hai, poi chiama SEMPRE «concludi». Se la "
        "condizione che ti era stata chiesta non si e' verificata, concludi con "
        "avvisare=false: e' la risposta giusta, non un fallimento.\n"
        "Non puoi toccare la casa da qui. Se cio' che hai trovato richiede "
        "un'azione, scrivila come proposta nel campo `testo` di «concludi» -- "
        "non nella tua risposta, che nessuno legge. E se quello che ti era "
        "stato chiesto includeva l'avvisare la persona, leggi cosa fa "
        "`avvisare`: e' li' che si avvisa, non altrove."
    )


def _domanda(promise: dict) -> str:
    """La domanda, con l'istantanea di partenza accanto.

    L'istantanea porta valore, unita' e istante della misura: senza, «e'
    aumentata» non ha un termine di paragone e il modello se lo inventerebbe.
    """
    righe = ["Me l'hai chiesto cosi': «{}».".format(promise["frase"]),
             "Quello che devi guardare: {}".format(promise["domanda"])]
    for measurement in promise.get("istantanea") or []:
        righe.append(
            "Quando me l'hai chiesto, {} era {}{} (misurato allora, non adesso).".format(
                measurement.get("entita"),
                measurement.get("valore"),
                (" " + measurement["unita"]) if measurement.get("unita") else "",
            )
        )
    return "\n".join(righe)
