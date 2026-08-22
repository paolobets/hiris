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

from ..casa.strumenti import STRUMENTI_CONOSCENZA
from ..decisione_modelli import _MOTIVI_RIPIEGO

logger = logging.getLogger(__name__)

# I quattro che leggono e basta. Non `esegui` (tocca la casa), non `ricorda`
# (scrive nella memoria, che entra verbatim nel prompt di sistema), non
# `prometti`/`disdici` (un turno che si da' appuntamenti da solo e' autonomia
# costruita per sbaglio).
SOLA_LETTURA = ("cerca", "guarda", "legami", "richiama")

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


def strumenti_promessa() -> list[dict]:
    """Il catalogo di questo turno, DERIVATO da quello della chat.

    Le definizioni sono gli STESSI dizionari di `STRUMENTI_CONOSCENZA`, non
    copie: una descrizione migliorata li' vale anche qui, senza che nessuno se
    ne debba ricordare.
    """
    ammessi = [d for d in STRUMENTI_CONOSCENZA if d["name"] in SOLA_LETTURA]
    if len(ammessi) != len(SOLA_LETTURA):
        # Un nome ammesso che non esiste piu' nel catalogo della chat (un
        # rinomino) svuoterebbe questo catalogo IN SILENZIO, lasciando il turno
        # cieco. Si dichiara.
        trovati = {d["name"] for d in ammessi}
        logger.error("catalogo della promessa incompleto: mancano %s",
                     sorted(set(SOLA_LETTURA) - trovati))
    return ammessi + [CONCLUDI_TOOL_DEF]


class DispatcherPromessa:
    """Il guardiano del turno: lascia scendere solo i lettori, e tiene `concludi`.

    Sta DAVANTI a `DispatcherStrumenti` invece di modificarlo, per non mettere
    nel dispatcher della chat uno strumento che li' non deve esistere.
    """

    def __init__(self, sotto) -> None:
        self._sotto = sotto
        self.conclusione: dict | None = None

    async def dispatch(self, nome: str, argomenti: dict | None) -> dict:
        argomenti = argomenti or {}
        if nome == "concludi":
            avvisare = argomenti.get("avvisare")
            testo = argomenti.get("testo")
            if not isinstance(avvisare, bool) or not isinstance(testo, str):
                return {"errore": ("«concludi» vuole `avvisare` (vero o falso) e "
                                   "`testo` (cosa hai trovato).")}
            self.conclusione = {"avvisare": avvisare, "testo": testo}
            return {"concluso": True}
        if nome not in SOLA_LETTURA:
            return {"errore": ("«%s» non e' disponibile mentre mantengo una "
                               "promessa: qui posso guardare e rispondere, non "
                               "toccare la casa. Se serve un'azione, dilla nel "
                               "testo e decidera' la persona." % nome)}
        return await self._sotto.dispatch(nome, argomenti)


async def interpreta_promessa(app, promessa: dict) -> dict:
    """Sveglia il modello per una promessa «chiedi». Non solleva mai.

    Ritorna `{"avvisare": bool, "testo": str}` oppure `{"errore": str}`. Un
    turno che finisce senza chiamare `concludi` e' un errore dichiarato, non un
    «forse e' andata bene».
    """
    from ..api.handlers_casa import costruisci_nucleo
    from ..api.handlers_chat import costruisci_dispatcher_strumenti
    from ..instradamento import chi_risponde

    # La STESSA domanda che si fa la chat, dalla STESSA funzione. Fino al
    # 22/08/2026 questo turno non se la faceva affatto e andava dritto al
    # router -- dove il ponte non e' nemmeno un anello -- qualunque cosa
    # dicesse la gerarchia dei modelli che l'utente aveva ordinato. Su una
    # casa che gira interamente sul Piano Claude Max le promesse morivano su
    # chiavi API esaurite mentre la chat funzionava, e nessuna pagina lo
    # diceva.
    via, motivo_ripiego = chi_risponde(app)
    if via == "ponte":
        return _accoda_al_ponte(app, promessa)

    runner = app.get("llm_router") or app.get("claude_runner")
    if runner is None:
        return {"errore": "non c'era nessun modello a cui chiedere."}

    dispatcher = DispatcherPromessa(costruisci_dispatcher_strumenti(app))
    try:
        # Lo STESSO nucleo della chat (`costruisci_nucleo`), non una
        # composizione parallela: due contesti che descrivono la stessa casa
        # sono due verita' che divergono.
        nucleo, _riepilogo = costruisci_nucleo(app)
    except Exception as errore:
        logger.warning("nucleo non componibile per la promessa %s (%s: %s)",
                       promessa["id"], type(errore).__name__, errore)
        nucleo = ""

    try:
        risposta = await runner.chat(
            user_message=_domanda(promessa),
            system_prompt=_prompt_di_sistema(),
            context_str=nucleo,
            conversation_history=[],
            model="auto",
            max_tokens=2000,
            agent_type="promessa",
            thinking_budget=0,
            strumenti=strumenti_promessa(),
            dispatcher=dispatcher,
        )
    except Exception as errore:
        logger.warning("turno della promessa %s fallito (%s: %s)",
                       promessa["id"], type(errore).__name__, errore)
        return {"errore": "il modello non ha risposto (%s)." % type(errore).__name__}

    if dispatcher.conclusione is None:
        logger.warning("promessa %s: il turno non ha chiamato «concludi»; "
                       "aveva risposto %d caratteri di testo",
                       promessa["id"], len(risposta or ""))
        return {"errore": _senza_conclusione(risposta)}
    conclusione = dict(dispatcher.conclusione)
    nota = _nota_del_ripiego(motivo_ripiego)
    if nota:
        conclusione["nota"] = nota
    return conclusione


# Quanto della risposta del modello entra nel motivo. Il motivo finisce in una
# colonna di SQLite e in una riga della pagina Promesse: riportarla intera
# sarebbe un allegato, non un motivo.
_TETTO_RIPORTO = 300


def _senza_conclusione(risposta) -> str:
    """Il motivo di un turno che NON ha chiamato `concludi`, con dentro cio'
    che il modello aveva risposto al suo posto.

    Fino al 21/08/2026 questa funzione non esisteva e il motivo era una
    costante: «il turno non ha concluso: non so cosa dirti». Vera, e
    inutilizzabile -- perche' le TRE uscite del ciclo di `claude_runner.chat`
    che portano qui restituiscono tre stringhe DIVERSE (il testo del modello,
    `_MAX_ITERATIONS_NOTICE`, `_TRUNCATION_NOTICE`) e quella stringa era
    l'unica cosa che le distingueva. `interpreta_promessa` la scartava: per
    sapere quale delle tre fosse capitata sulla casa vera e' servita
    un'indagine con tre riproduzioni sull'add-on vivo.

    Quando non c'e' proprio niente da riportare si torna alla frase di prima:
    un virgolettato vuoto affermerebbe «ha detto questo», e questo e' niente.
    """
    detto = risposta.strip() if isinstance(risposta, str) else ""
    if not detto:
        return "il turno non ha concluso: non so cosa dirti."
    if len(detto) > _TETTO_RIPORTO:
        detto = detto[:_TETTO_RIPORTO].rstrip() + "…"
    return "il turno non ha concluso. Aveva risposto a parole: «%s»" % detto


def _nota_del_ripiego(motivo: str) -> str:
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
    fatto = _MOTIVI_RIPIEGO.get(motivo)
    if not fatto:
        return ""
    return ("Il Piano Claude Max %s: questo turno l'ha mantenuto la catena, "
            "a consumo." % fatto)


def _accoda_al_ponte(app, promessa: dict) -> dict:
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
    from ..api.handlers_casa import costruisci_nucleo
    from ..api.handlers_models import _PREDEFINITI_ARCHIVIO

    try:
        nucleo, _riepilogo = costruisci_nucleo(app)
    except Exception as errore:
        logger.warning("nucleo non componibile per la promessa %s (%s: %s)",
                       promessa["id"], type(errore).__name__, errore)
        nucleo = ""

    # La scadenza dall'ARCHIVIO, come fa `_enqueue_chat_job`: quella che
    # l'utente cambia dev'essere quella che il turno subisce.
    scadenza_min = int((app.get("models_config") or {}).get("ponte", {}).get(
        "scadenza_min", _PREDEFINITI_ARCHIVIO["ponte"]["scadenza_min"]))
    adesso = time.time()
    app["reasoning_queue"].enqueue(
        "promessa",
        {"promessa_id": promessa["id"]},
        {
            "promessa_id": promessa["id"],
            "frase": promessa.get("frase") or "",
            "domanda": _domanda(promessa),
            "system_prompt": _prompt_di_sistema(),
            "contesto": nucleo,
        },
        adesso + scadenza_min * 60,
        now=adesso,
    )
    logger.info("promessa %s: turno accodato al piano (scadenza %d min)",
                promessa["id"], scadenza_min)
    return {"accodata": True}


def _prompt_di_sistema() -> str:
    # Fix finale ④ (review 2026-08-20): questo turno riceve lo STESSO nucleo
    # della chat (`costruisci_nucleo`, vedi `interpreta_promessa` sopra), coi
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


def _domanda(promessa: dict) -> str:
    """La domanda, con l'istantanea di partenza accanto.

    L'istantanea porta valore, unita' e istante della misura: senza, «e'
    aumentata» non ha un termine di paragone e il modello se lo inventerebbe.
    """
    righe = ["Me l'hai chiesto cosi': «%s»." % promessa["frase"],
             "Quello che devi guardare: %s" % promessa["domanda"]]
    for misura in promessa.get("istantanea") or []:
        righe.append(
            "Quando me l'hai chiesto, %s era %s%s (misurato allora, non adesso)."
            % (misura.get("entita"), misura.get("valore"),
               (" " + misura["unita"]) if misura.get("unita") else ""))
    return "\n".join(righe)
