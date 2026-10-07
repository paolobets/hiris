"""`POST /api/mcp` -- l'adattatore JSON-RPC che porta gli strumenti al ponte.

**Perche' esiste.** HIRIS ha due percorsi di chat. Il turno sincrono passa gli
strumenti (`KNOWLEDGE_TOOLS`) direttamente al runner, che li
dispaccia con `ToolDispatcher`. Il ponte via abbonamento invece invoca la
CLI `claude` come sottoprocesso, e **l'unico modo in cui quella CLI accetta
strumenti nostri e' MCP**: senza questa rotta il ponte risponde su una
fotografia (il nucleo composto all'accodamento) e non puo' ne' cercare, ne'
guardare, ne' ricordare, ne' richiamare -- ne' far succedere niente in casa.

**Perche' e' una rotta e non un server.** Il server MCP interno del vecchio
prodotto e' uscito per intero con la fetta E2 (`2e78354`) e non e' ripristinabile
nemmeno volendo: il suo unico modo di raggiungere la logica degli strumenti era
`POST /api/execute`, che non esiste piu'. Cio' che rientra su questo ramo rientra
**rifatto e con un progetto**, mai per eredita' -- e il disegno scelto
(`docs/design/2026-08-10-parita-ponte-chat.md`, §4.1) e' il piu' piccolo che
funziona: tre metodi JSON-RPC su una rotta aiohttp dell'app che c'e' gia'.
Nessuna dipendenza nuova, nessun processo da governare, nessuna porta nuova da
configurare -- e soprattutto **la stessa `entity_cache`** del turno sincrono, che
e' la ragione per cui un sottoprocesso stdio e' stato scartato: senza di essa
gli strumenti risponderebbero sempre `stato_non_letto`, e avremmo due
intelligenze nella stessa casa che ne vedono due diverse.

**Cosa NON e'.** Non e' una superficie remota: la chiama solo il sottoprocesso
`claude` che gira dentro l'add-on, su `127.0.0.1`, e nessuna opzione `Network`
la espone. Non e' un secondo catalogo: `tools/list` **ri-forma**
`KNOWLEDGE_TOOLS` (una sola chiave rinominata) e non ne dichiara uno
proprio -- tre cataloghi divergenti della stessa cosa sono il difetto da cui e'
nata l'intera fetta E2. Non e' un secondo dispatcher: `tools/call` chiama
`create_tool_dispatcher(app, exchange=exchange_id)`, la stessa funzione del
turno sincrono -- con l'identita' di `X-HIRIS-Turno` ripropagata, dalla fetta
«costruire».

**Dalla fetta «le promesse seguono la catena» (22/08/2026) e' consapevole del
TURNO.** Quando il job che il ponte sta servendo e' un `kind="promessa"`, la
`--mcp-config` porta `X-HIRIS-Promessa`, questa rotta lo VERIFICA contro una
promessa `in_corso`, e per quel turno serve `promise_tools()` dispacciando
con `PromiseDispatcher`. Non incrina niente di quanto scritto qui sopra: sono
gli STESSI due oggetti del ramo sincrono, e `promise_tools()` filtra le
definizioni di `KNOWLEDGE_TOOLS` invece di riscriverle. Senza questo, un
turno di promessa sul ponte non avrebbe `conclude` -- cioe' nessun modo di
finire -- e vedrebbe `execute`, cioe' potrebbe toccare la casa senza nessuno
davanti.

**Dalla fetta «le chat divise» sa anche CHI parla.** Per un turno di chat la
`--mcp-config` porta `X-HIRIS-Chat`, la rotta la verifica contro un job di chat
`claimed` (`_exchange_chat_job`) e costruisce il dispatcher col soffitto, il
soggetto e la frase di quel job -- la stessa costruzione del ramo sincrono.
Un `X-HIRIS-Chat` PRESENTE ma che non vale piu' (il job non e' piu' `claimed`
quando la CLI risponde) **chiude la chiamata** (`_stale_chat_rejection`)
invece di ricadere sul dispatcher senza soffitto -- fail closed, non un
ripiego: ricadere riaprirebbe la porta di scrittura che l'intestazione
esiste per chiudere. L'ASSENZA dell'intestazione (promesse, osservatore)
non da' piu' il dispatcher della chat senza soffitto: dal 07/10/2026
(decisione 13) il suo soffitto non concede nessun gesto (`_build_dispatcher`).

**Dagli attori (Task 3.6, 06/10/2026) sa anche QUALE mestiere.** Un mestiere
di sfondo con strumenti (l'analista) porta `X-HIRIS-Lavoro`, l'id del suo job;
la rotta lo verifica contro un job preso in carico (`_exchange_species`), e
per quel turno serve il catalogo della dichiarazione del mestiere
(`steering.Species.catalog`) e dispaccia col suo guardiano
(`Species.guard`). Presente ma non valida, l'intestazione chiude: il catalogo
torna vuoto e la chiamata si rifiuta, come per `X-HIRIS-Chat`.

**E' anche un canale di azione, dalla fetta «comandare», e dalla fetta
«costruire» anche di configurazione.** Il catalogo e' quello del turno
sincrono: `execute` chiama un servizio di Home Assistant, `propose`/`confirm`
compongono e scrivono configurazione. Ma
questa rotta non e' una porta di scrittura propria. `tools/call` dispaccia con
la stessa funzione del turno sincrono, che dispaccia alle stesse due porte --
`action/actuator.py` per i servizi, `action/construction/workshop.py` per la
configurazione -- il ponte non ha una strada verso la casa che la chat non
abbia, e non ne ha una sua. Un secondo punto di scrittura sarebbe un difetto,
non un'ottimizzazione.

**Chi la chiama.** Due chiamanti di produzione, entrambi in
`hiris/app/agent/runner.py`: il sottoprocesso `claude` del ponte, a cui l'argv
passa questa rotta nella voce `--mcp-config` (`config_mcp`), e la sonda
`tools/list` che il runner fa PRIMA di comporre il turno (`probe_tools`),
per decidere se il prompt puo' affermare gli strumenti. La registrazione
in `server.py` (`app.router.add_post("/api/mcp", handle_mcp)`) porta lo stesso
elenco: i due file devono restare d'accordo.
"""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

from aiohttp import web

from ..home_space.tools import KNOWLEDGE_TOOLS, ToolDispatcher
from ..keeper.exchange import PromiseDispatcher, promise_ceiling, promise_tools
from ..models_store import bridge_deadline_min
from ..providers import SUBSCRIPTION
from ..steering import JOB_SPECIES, SPECIES
from ..usage.bridge_loads import BRIDGE_LOADS_KEY, MAX_TRACKED
from ..usage.giro import pesa_in_caratteri
from ..version import read_version
from .boundary import error_response
from .handlers_chat import create_tool_dispatcher, last_phrase
from .soffitto import ceiling_for, nothing_granted

logger = logging.getLogger(__name__)

# Il nome con cui il server MCP si presenta alla CLI. Costante di modulo e NON
# un'opzione dell'add-on: un'opzione vive in cinque posti (config.yaml options+
# schema, run.sh, le due traduzioni, il lettore Python) e qui non c'e' niente
# da configurare. Il Task 3 la riusa per la voce di `--mcp-config` e per il
# prefisso `mcp__hiris__` con cui la CLI presenta gli strumenti al modello: un
# nome solo, in un posto solo.
MCP_SERVER_NAME = "hiris"

# La versione di protocollo che dichiariamo quando il client non ne manda una.
# Nel caso normale `initialize` rimanda indietro **quella ricevuta**: e' il
# client (la CLI `claude`) a sapere quale sa parlare, e negoziare al ribasso una
# versione che non ci serve sarebbe un modo in piu' di non partire.
DEFAULT_PROTOCOL = "2025-06-18"

# I tre metodi che questa rotta conosce. Serve anche a scrivere un errore
# `-32601` che DICE cosa esiste, invece di un "method not found" nudo.
METHODS = ("initialize", "tools/list", "tools/call")

# Task 6 della fetta ("il ponte riceve gli strumenti", parita' B): il tetto ai
# giri di strumento PER TURNO -- l'unico freno che l'abbonamento abbia.
#
# **Perche' qui e non sulla riga di comando.** Il piano lo chiede come
# mitigazione minima (progetto, §5.2): il modello puo' incatenare `search` ->
# `related` -> `fetch` -> ancora, e il tetto giornaliero del ponte conta un
# turno mentre ne consuma N. Quando questo tetto e' nato la CLI (`claude
# 2.1.226`) NON aveva un `--max-turns` ne' alcun flag che limitasse i giri di
# strumento (verificato allora su `claude --help`, decisione A.7 del
# progetto; non riverificato sulla versione che il `Dockerfile` pinna oggi):
# il tetto non sta
# sull'argv del ponte (`agent/runner.py::_chat_claude_args`), sta QUI,
# l'unico punto che vede passare OGNI `tools/call` -- comprese, se mai
# arrivassero, quelle di una SECONDA invocazione dello stesso turno (Task 4:
# oggi quella seconda invocazione riparte sempre SENZA strumenti, quindi non
# chiama mai questa rotta -- ma il tetto e' scritto per continuare a valere
# anche il giorno in cui smettesse di essere cosi', vedi `runner.config_mcp`).
#
# **Il valore.** Il ramo sincrono ha il suo tetto ai giri di strumento,
# `MAX_TOOL_ITERATIONS` (`hiris/app/claude_runner.py`) -- alla nascita di
# questo commento era 10 e i due tetti erano lo stesso numero per parita'.
# Fetta "i riferimenti" (Task 5, R3): il tetto sincrono e' salito a 50 (8
# stanze da guardare una a una servivano 10 round-trip minimi contro un
# tetto di 10 -- morte garantita a esecuzione perfetta). Questo qui, il tetto
# del PONTE, era rimasto a 10 per una ragione SUA: la fetta "come sta la
# casa" (2026-08-15) aveva deciso esplicitamente di non alzarlo -- "non si
# alza un freno: si toglie il motivo per cui mordeva".
#
# Fix "il ponte muore a 9" (2026-08-21, misurato dal vivo): quella ragione non
# regge quando il ponte E' la chat del proprietario. La decisione della fetta
# "i riferimenti" era "tetto a 50 per chat e promessa" -- non "per il ramo
# sincrono": sul ponte l'abbonamento e' forfettario, quindi 50 chiamate non
# hanno un costo marginale in piu' di 10, e un turno reale (8 stanze da
# guardare + 1 `search` + la `promise` finale) moriva esattamente come
# sarebbe morto il ramo sincrono col vecchio tetto. Il numero torna a essere
# lo stesso su entrambi i percorsi, per la stessa decisione del proprietario.
#
# **Cio' che NON torna uguale: il CONTATORE.** I due tetti condividono il
# valore ma non l'unita' che contano, ed e' questo che resta vero e va
# tenuto a mente leggendo l'uno alla luce dell'altro. `MAX_TOOL_ITERATIONS`
# (sincrono) conta un giro per RISPOSTA del modello: N blocchi `tool_use`
# nella stessa risposta costano una sola iterazione (vedi il for su
# `response.content` in `claude_runner.chat()`). `MAX_TOOL_ROUNDS` (qui)
# conta un giro per OGNI singola `tools/call` che arriva su questa rotta,
# comprese quelle parallele della stessa risposta della CLI: 8 `fetch`
# richiesti insieme dal modello costano comunque 8 giri qui, non 1. Stesso
# tetto, contatori diversi -- e' per questo che `agent/prompts.py::
# _GUIDE_WITH_TOOLS` insegna al ponte una parsimonia che
# `claude_runner.BASE_TOOL_RULES` non ha bisogno di insegnare al ramo
# sincrono (vedi `tests/test_prompt_parallelism.py`).
#
# **Costante di modulo, non un'opzione dell'add-on** (regole della fetta): un
# opzione vive in cinque posti (config.yaml options+schema, run.sh, le due
# traduzioni, il lettore Python), e qui non c'e' niente che l'utente debba
# toccare oggi -- se un giorno servira' configurarla, si fara' il giro dei
# cinque posti allora.
MAX_TOOL_ROUNDS = 50

# Quante identita' di turno diverse restano tracciate insieme: `MAX_TRACKED`
# di `usage/bridge_loads.py`, **lo stesso numero e non un secondo uguale**
# (B-53, Tappa 6 Task 2): i contatori dei giri qui e i carichi la' tengono le
# stesse identita' di turno, con la stessa ragione. Fino al 05/10/2026 erano
# due `64` legati solo da un commento. Piccolo di
# proposito (Step 2 del brief, "N piccolo"): serve solo a impedire che il
# dizionario cresca senza fine per l'intera vita del processo -- un turno del
# ponte dura al piu' fino alla sua scadenza (il `timeout` della CLI in
# `agent/runner.py::_reason_chat`, S-09), la sua identita' non serve piu' un istante
# dopo, e tenerne migliaia sarebbe una perdita di memoria scritta apposta.
# L'espulsione e' **LRU, non FIFO** (l'etichetta era sbagliata fino alla
# review totale della fetta, M-1): `_count_round` fa `move_to_end` a ogni
# chiamata, quindi l'`OrderedDict` e' ordinato per ULTIMO USO e
# `popitem(last=False)` scarta il turno che tace da piu' tempo, non quello
# iniziato per primo. La differenza non e' terminologica: e' cio' che rende
# vera la proprieta' portante di questo tetto -- **un turno ancora attivo non
# viene mai espulso**, per quanti altri turni gli passino accanto. Con una
# FIFO vera un turno lungo verrebbe scartato dopo `MAX_TRACKED`
# turni altrui e il suo contatore ripartirebbe da zero, cioe' il tetto si
# potrebbe aggirare semplicemente durando. La proprieta' e' pinnata in
# `tests/test_mcp_route.py::test_un_turno_attivo_non_viene_mai_espulso`.

# La chiave sotto cui i contatori vivono nell'`Application`. Costante e non una
# stringa ripetuta: chi la crea (`server.create_app`) e chi la legge
# (`_count_round`) devono per forza nominare la stessa cosa.
ROUNDS_PER_EXCHANGE_KEY = "mcp_rounds_per_exchange"


@dataclass
class ExchangeTurn:
    """Cio' che la rotta tiene di UN turno del ponte, sotto la sua identita'
    (`X-HIRIS-Turno`): una casa sola per lo stato del turno, non un dizionario
    per ogni cosa che si ricorda.

    - `rounds`: i giri di strumento gia' passati (il tetto, Task 6).
    - `dispatcher`: il dispatcher del turno (Tappa 6, Task 8; D-63), costruito
      alla PRIMA chiamata e riusato dalle altre -- come la catena, che ne
      costruisce uno per turno. Con lui resta la `House` che ha letto: il turno
      guarda la casa del suo inizio, e la rilegge negli stessi due casi della
      catena (`ToolDispatcher._turn_house`: l'anagrafe ricostruita, un comando
      di questo turno andato a segno). Fino al 06/10/2026 ogni chiamata
      vedeva la casa nuova; ora il ponte ha lo stesso contratto della catena.
    - `since`: quando il turno ha chiamato la prima volta. Serve a lasciar
      andare il dispatcher di un turno scaduto (`_release_expired`)."""

    rounds: int = 0
    dispatcher: ToolDispatcher | None = None
    since: float = 0.0


def create_rounds_per_exchange(app) -> None:
    """Crea la struttura dei contatori **prima che l'app parta**.

    M-2 della review totale della fetta. Prima, `_count_round` la creava con
    `app.setdefault(...)` alla prima `tools/call` servita: aiohttp lo vede
    come una modifica dello stato di un'applicazione gia' avviata ed emette
    «Changing state of started or joined application is deprecated» -- oggi un
    `DeprecationWarning` visibile nell'output della suite, con **aiohttp 4 un
    errore**. Lo stato di un'app aiohttp si compone in `create_app()`, cioe'
    prima del `freeze`, e non a richiesta servita.

    Non e' `setdefault`: chiamarla due volte sulla stessa app azzererebbe i
    contatori, e non esiste nessun motivo per chiamarla due volte."""
    app[ROUNDS_PER_EXCHANGE_KEY] = OrderedDict()


def _answer(request_id, result: dict) -> web.Response:
    return web.json_response({"jsonrpc": "2.0", "id": request_id, "result": result})


def _annota_risultato(request: web.Request, risposta: web.Response) -> None:
    """Quanti caratteri di risultato tornano al modello per questo turno.

    Si misura la RISPOSTA che esce, non il risultato del dispatcher: cosi'
    contano anche il tetto dei giri e la chiamata chiusa, che al modello
    arrivano allo stesso modo. Mai il contenuto: solo la lunghezza del testo.
    Un errore JSON-RPC (chiamata malformata) non ha `result`: al modello
    arriva il suo `error.message`, e si pesa quello -- non zero.
    Non solleva: e' una misura (spec «le misure complete», legge del §4)."""
    carichi = request.app.get(BRIDGE_LOADS_KEY)
    turno = request.headers.get("X-HIRIS-Turno", "")
    if carichi is None or not turno:
        return
    try:
        corpo = json.loads(risposta.body)
        errore_rpc = corpo.get("error")
        if corpo.get("result") is None and isinstance(errore_rpc, dict):
            testo = str(errore_rpc.get("message") or "")
        else:
            testo = "".join(b.get("text", "") for b in
                            ((corpo.get("result") or {}).get("content") or [])
                            if isinstance(b, dict))
        carichi.result_served(turno, len(testo))
    except Exception as errore:  # pragma: no cover - forma inattesa
        logger.warning("MCP: il peso del risultato non si e' annotato (%s)",
                       type(errore).__name__)


def _error(code: int, message: str, request_id=None, *, status: int = 200) -> web.Response:
    """Un errore JSON-RPC che dice **cosa** e' successo.

    Un codice generico su una chiamata malformata e' un silenzio travestito: chi
    legge il log (o il modello, che riceve il testo) deve poter capire quale
    campo mancava senza rileggere questo file.
    """
    return web.json_response(
        {"jsonrpc": "2.0", "id": request_id,
         "error": {"code": code, "message": message}},
        status=status,
    )


def _exchange_promise_id(request: web.Request) -> str:
    """L'id della promessa che questo turno sta mantenendo, oppure `""`.

    `X-HIRIS-Promessa` e' l'intestazione che `agent/runner.py::config_mcp`
    aggiunge alla `--mcp-config` quando il job che il ponte sta servendo e' un
    `kind="promessa"`. Dice QUALE turno sta parlando -- non e'
    un'autenticazione, che resta la credenziale di turno (vedi `handle_mcp`).

    Proprio perche' non autentica, si VERIFICA: un id che non corrisponde a una
    promessa `in_corso` non vale niente. Senza questo controllo l'intestazione
    sarebbe un modo per farsi servire un catalogo diverso -- quello che contiene
    `conclude` -- mostrando un identificatore qualunque.

    Fetta «le promesse seguono la catena» (22/08/2026).
    """
    ident = (request.headers.get("X-HIRIS-Promessa") or "").strip()
    if not ident:
        return ""
    store = request.app.get("agenda")
    if store is None:
        return ""
    row = store.read(ident)
    return ident if row and row.get("stato") == "in_corso" else ""


def _exchange_chat_job(request: web.Request) -> tuple[bool, dict | None]:
    """`(intestazione presente, job di chat)` per questo turno.

    Un tri-stato e non un `None` solo, perche' «assente» e «presente ma non
    valida» chiedono decisioni opposte (dispatcher di sempre contro chiamata
    chiusa) e il chiamante deve decidere UNA volta su una lettura sola
    dell'intestazione: `(False, None)` assente, `(True, None)` non valida,
    `(True, job)` valida.

    `X-HIRIS-Chat` la aggiunge `agent/runner.py::config_mcp` quando il ponte
    serve un `kind="chat"` (fetta «le chat divise», spec §4). Come
    `X-HIRIS-Promessa` NON e' un'autenticazione -- quella resta la credenziale
    di turno -- e per questo si VERIFICA: vale solo un job di chat `claimed`
    (`ReasoningQueue.claimed_chat`). Un id che non vale non concede niente:
    `(True, None)` qui, e `_call_tool` rifiuta la chiamata invece di ricadere
    sul dispatcher senza soffitto (`_stale_chat_rejection`). Lo si scrive nel
    log perche' un ponte che la manda sbagliata e' un guasto.
    """
    ident = (request.headers.get("X-HIRIS-Chat") or "").strip()
    if not ident:
        return False, None
    queue = request.app.get("reasoning_queue")
    job = queue.claimed_chat(ident) if queue is not None else None
    if job is None:
        logger.warning(
            "MCP: X-HIRIS-Chat nomina un job che non e' una chat presa in "
            "carico (%s): nessuno strumento gira per questa chiamata", ident)
    return True, job


def _exchange_species(request: web.Request) -> tuple[bool, str | None]:
    """`(intestazione presente, mestiere)` per questo turno: lo stesso
    tri-stato di `_exchange_chat_job`. Il mestiere vale solo se il job e'
    preso in carico (`ReasoningQueue.claimed`) e se la sua dichiarazione ha
    un guardiano (`steering.Species.guard`). Il runner la manda per ogni
    turno che non e' chat ne' promessa (attori, Task 3.6; G23-1): un mestiere
    con un catalogo e senza guardiano si fa riconoscere lo stesso, e qui si
    chiude invece di ricevere il catalogo della chat."""
    ident = (request.headers.get("X-HIRIS-Lavoro") or "").strip()
    if not ident:
        return False, None
    queue = request.app.get("reasoning_queue")
    job = queue.claimed(ident) if queue is not None else None
    species = SPECIES.get(JOB_SPECIES.get((job or {}).get("kind")))
    if species is None or species.guard is None:
        logger.warning(
            "MCP: X-HIRIS-Lavoro nomina un job che non e' il turno preso in "
            "carico di un mestiere con guardiano (%s): nessuno strumento", ident)
        return True, None
    return True, species.name


def _stale_work_rejection(name: str) -> dict:
    """Il `content` per un `X-HIRIS-Lavoro` presente che non vale: si chiude,
    come `_stale_chat_rejection` e per la stessa ragione -- ricadere sul
    catalogo della chat darebbe a un attore `execute`."""
    return _closed_call(
        "non riconosco questo turno come un lavoro in corso con strumenti: è "
        "scaduto, è già stato consegnato, o il suo mestiere non ne ha. Non uso "
        f"nessuno strumento (l'ultimo tentato: «{name}»).")


def _stale_chat_rejection(name: str) -> dict:
    """Il `content` per un `X-HIRIS-Chat` presente che non vale piu'.

    **Si chiude, non si ripiega** (fix round 1 del Task 4). Il job puo'
    smettere di essere `claimed` mentre la CLI gira ancora: scaduto e
    ripiegato sulla catena da un poll, spazzato, o gia' consegnato. Ricadere
    sul dispatcher di prima -- senza soffitto e senza soggetto -- riaprirebbe
    proprio la porta di scrittura che questa intestazione chiude. Il runner la
    manda solo per i job di chat, quindi nessun turno legittimo perde niente.
    Stessa forma del tetto dei giri: un esito dello strumento, non un guasto
    di protocollo.
    """
    return _closed_call(
        "questo turno di chat non è più valido: la risposta è scaduta o è "
        "già stata data, e senza sapere chi sta parlando non uso nessuno "
        f"strumento (l'ultimo tentato: «{name}»).")


#: Il `perche` del soffitto di un turno che non dice chi e': ne' una chat, ne'
#: una promessa, ne' un mestiere di sfondo (decisione 13).
_UNKNOWN_TURN = ("non so di quale turno è questa chiamata -- non è una chat, una "
                 "promessa né il lavoro di un mestiere -- e senza sapere chi l'ha "
                 "aperto non concedo nessun gesto")


def _closed_call(text: str) -> dict:
    """Il `content` di una chiamata chiusa da un'intestazione che non vale:
    un esito dello strumento, non un guasto di protocollo. Una forma sola per
    `X-HIRIS-Chat` e `X-HIRIS-Lavoro`."""
    result = {"errore": text}
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "isError": True,
    }


def mcp_catalog(definitions: list[dict] | None = None) -> list[dict]:
    """Un catalogo di strumenti nella grafia di MCP: `input_schema` -> `inputSchema`.

    Trasformazione **meccanica**, e deve restare tale: nessun testo nuovo,
    nessuna descrizione riscritta, nessun nome aggiunto o tolto. Le altre chiavi
    passano invariate, cosi' che una chiave nuova in `home_space/tools.py` arrivi
    qui da sola invece di essere dimenticata.

    Il parametro serve al turno di una promessa, che ha un catalogo suo
    (`promise_tools()`: i lettori di `SOLA_LETTURA` piu' `conclude`). E' la STESSA
    trasformazione, non una seconda: due funzioni che riformattano cataloghi
    sarebbero il difetto da cui e' nata la fetta E2 (tre cataloghi divergenti).
    """
    entries: list[dict] = []
    for definition in (KNOWLEDGE_TOOLS if definitions is None else definitions):
        entry = {key: value for key, value in definition.items()
                 if key != "input_schema"}
        if "input_schema" in definition:
            entry["inputSchema"] = definition["input_schema"]
        entries.append(entry)
    return entries


def _count_round(app, exchange_id: str, *, now: float) -> tuple[int, ExchangeTurn]:
    """Incrementa il contatore dei giri di strumento del turno `exchange_id` e
    restituisce il valore **prima** dell'incremento (quanti giri erano gia'
    passati per questo turno), insieme al turno stesso (`ExchangeTurn`), che
    la chiamata usa dopo per il suo dispatcher.

    **Vive solo nel processo e solo nel loop asyncio.** `handle_mcp` e' un
    handler aiohttp: gira sempre nel thread del loop dell'add-on. Il
    chiamante di produzione (il sottoprocesso `claude` del ponte) parla con
    questa rotta solo via HTTP -- non tocca mai questo dizionario
    direttamente -- e il runner che lo invoca (`agent/runner.py::run_loop`)
    gira si' in un thread executor, ma quel thread fa solo `subprocess.run` e
    non vede mai `app`. Non esiste quindi nessun accesso concorrente da due
    thread allo stesso dizionario: e' la ragione per cui qui non c'e' nessun
    lock, e va scritta perche' e' cio' che rende la struttura sicura SENZA
    sincronizzazione, non un'omissione.

    **Dimensione limitata** (`MAX_TRACKED`, "le ultime N identita' di
    turno" del brief): quando arriva un'identita' MAI vista e il dizionario e'
    gia' pieno, si scarta quella usata da PIU' TEMPO -- LRU e non FIFO, ed e'
    il `move_to_end` qui sotto a farne la differenza. Un turno che continua a
    chiamare si rimette in coda a ogni giro e non puo' essere espulso: se lo
    fosse, il suo contatore ripartirebbe da zero e il tetto si aggirerebbe
    durando (vedi il commento su `MAX_TRACKED`, in testa a questo file).

    **La struttura la crea `server.create_app()`**, non questa funzione (M-2
    della review totale): scriverla qui, a richiesta gia' servita, faceva
    emettere ad aiohttp «Changing state of started or joined application»,
    che con aiohttp 4 diventa un errore. Lo stato di un'app aiohttp si compone
    prima che l'app parta."""
    rounds_per_exchange: OrderedDict[str, ExchangeTurn] = app[ROUNDS_PER_EXCHANGE_KEY]
    turn = rounds_per_exchange.get(exchange_id)
    if turn is not None:
        rounds_per_exchange.move_to_end(exchange_id)
    else:
        if len(rounds_per_exchange) >= MAX_TRACKED:
            rounds_per_exchange.popitem(last=False)  # il piu' vecchio
        turn = rounds_per_exchange[exchange_id] = ExchangeTurn(since=now)
    rounds_so_far = turn.rounds
    turn.rounds += 1
    return rounds_so_far, turn


def _release_expired(app, now: float) -> None:
    """Lascia andare il dispatcher (e la casa che tiene) dei turni piu'
    vecchi della scadenza del ponte (`bridge_deadline_min`, la scadenza che
    viaggia col turno dalla Tappa 6, Task 2): oltre quella, la risposta del
    turno non la aspetta piu' nessuno. Il turno non ha un segnale di chiusura
    che arrivi a questa rotta -- la CLI finisce e basta -- e senza questo
    rilascio fino a `MAX_TRACKED` case di turni finiti resterebbero in
    memoria.

    **Il contatore dei giri resta**: se ripartisse, il tetto si aggirerebbe
    durando. Se un turno scaduto chiama ancora, si costruisce un dispatcher
    nuovo, come si faceva per ogni chiamata fino al 06/10/2026."""
    window = bridge_deadline_min(app.get("models_config")) * 60
    for turn in app[ROUNDS_PER_EXCHANGE_KEY].values():
        if turn.dispatcher is not None and now - turn.since > window:
            turn.dispatcher = None


def _ceiling_rejection(name: str) -> dict:
    """Il `content` che il modello vede quando il tetto per-turno e' pieno.

    **La forma scelta, motivata (non un dettaglio di stile).** Resta una
    risposta JSON-RPC 2.0 NORMALE (`result`, non un `error` di protocollo
    `-32xxx`): esattamente la stessa scelta che questo file fa gia' per un
    guasto DICHIARATO del dispatcher (vedi `_call_tool`, il ramo
    `isError`) contro un guasto VERO (l'`except` di `handle_mcp`, che quello
    si' risponde `-32603`). Il tetto raggiunto non e' un guasto del
    protocollo -- la richiesta era benformata e la rotta funziona -- e' un
    esito di merito dello strumento, la stessa categoria di
    `ToolDispatcher._missing_resource`: si dichiara COSA e' successo
    invece di restituire un guasto opaco. Un `error` di protocollo rischia
    inoltre di far trattare l'intera chiamata dal client MCP della CLI come
    una rottura del canale (schema non risolto, connessione da riprovare)
    invece che come l'esito leggibile di UNO strumento fra tanti: il modello
    deve poter leggere il testo e chiudere il turno con una risposta, non
    restare a interpretare un errore di trasporto.

    `isError: True`: non e' un successo travestito (nessun `content` finto
    che pretenda che lo strumento abbia fatto il suo lavoro) -- il dispatcher
    non e' stato invocato, e la chiamata NON ha prodotto l'effetto richiesto.
    Cio' che la distingue da una chiamata fallita del dispatcher (stessa
    forma nel protocollo: `isError: True`) e' il TESTO, che il modello legge: un fallimento del
    dispatcher nomina l'archivio o l'argomento mancante, questo nomina
    ESPLICITAMENTE il tetto e il numero. Un quarto stato nella forma del
    protocollo non esiste in questo prodotto (tre bastano: riuscita, fallita,
    mai risolta -- Task 5) e non lo si inventa qui: si dichiara nel contenuto,
    dove sia il modello sia un umano che legga il log lo trovano."""
    result = {
        "errore": (
            f"hai raggiunto il tetto di {MAX_TOOL_ROUNDS} chiamate di "
            f"strumento per questo turno (l'ultima tentata: «{name}»): non "
            "chiamare altri strumenti, rispondi con cio' che hai gia' "
            "raccolto.")
    }
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "isError": True,
    }


async def _build_dispatcher(request: web.Request, exchange_id: str | None,
                            chat_job: dict | None, promise_id: str | None):
    """Il dispatcher di un turno del ponte, con cio' che il turno porta: il
    soffitto, il soggetto, la frase e il filo di un job di chat; il soffitto di
    chi ha chiesto una promessa. Lo si costruisce una volta per turno
    (`_call_tool`, D-63).

    **Un turno che non si fa riconoscere non ha nessun gesto** (decisione 13,
    Tappa 7, Task 7): il soffitto e' `soffitto.nothing_granted`, e ogni
    strumento che chiede un gesto -- comandare, costruire, leggere cio' che
    Home Assistant riserva agli amministratori -- si rifiuta col suo perche'.
    Fino al 07/10/2026 riceveva il soffitto `None`, cioe' tutto. I mestieri di
    sfondo si fanno riconoscere con `X-HIRIS-Lavoro` e passano dal loro
    guardiano, che porta il soffitto dichiarato (`Species.ceiling`)."""
    if chat_job is not None:
        ctx = chat_job.get("context") or {}
        soggetto = ctx.get("soggetto")
        return create_tool_dispatcher(
            request.app, exchange=exchange_id,
            soffitto=await ceiling_for(request.app, soggetto),
            soggetto=soggetto,
            frase=last_phrase(ctx.get("history")),
            # Fetta «le chat divise» (Task 7): il filo DEL JOB, gia' un
            # `ChatThread` -- `claimed_chat()` lo costruisce da
            # `subject_key`/`entry_point` della riga (`reasoning/queue.py::
            # _row`), non dal `context` serializzato (quello porta il
            # soggetto INTERO per il soffitto/la cronaca, non il filo).
            # `None` per un job accodato prima di questa versione.
            thread=chat_job.get("thread"))
    if promise_id:
        # Il turno di una promessa porta il soffitto di chi l'ha chiesta, come
        # il ramo sincrono (`keeper/exchange.promise_ceiling`, fix round 1 del
        # Task 2, H-1): senza, il ponte leggerebbe per lei cio' che Home
        # Assistant le nega.
        agenda = request.app.get("agenda")
        subject, ceiling = await promise_ceiling(
            request.app, agenda.read(promise_id) if agenda is not None else None)
        return create_tool_dispatcher(request.app, exchange=exchange_id,
                                      soffitto=ceiling, soggetto=subject)
    return create_tool_dispatcher(request.app, exchange=exchange_id,
                                  soffitto=nothing_granted(_UNKNOWN_TURN))


async def _call_tool(request: web.Request, params, request_id) -> web.Response:
    """`tools/call`: il nome nudo, gli argomenti, e il dispatcher che c'e' gia'."""
    if not isinstance(params, dict):
        return _error(
            -32602,
            "«tools/call» richiede un oggetto «params» con «name» e «arguments»; "
            f"ricevuto invece {type(params).__name__}.",
            request_id,
        )
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        return _error(
            -32602,
            "«tools/call» richiede «params.name», il nome NUDO dello strumento "
            f"(uno fra {', '.join(sorted(d['name'] for d in KNOWLEDGE_TOOLS))}); "
            f"ricevuto invece {name!r}.",
            request_id,
        )
    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _error(
            -32602,
            f"«params.arguments» di «{name}» dev'essere un oggetto; "
            f"ricevuto invece {type(arguments).__name__}.",
            request_id,
        )

    # Task 6, Step 2 e 3: il tetto per-turno, DOPO la validazione (una
    # `params` malformata e' un guasto di protocollo, non un giro speso) e
    # PRIMA del dispatcher -- il dispatcher non deve mai vedere una chiamata
    # oltre il tetto, o l'effetto (una scrittura in `memoria.db` per un
    # `remember`, per dire) sarebbe gia' avvenuto quando lo si rifiuta.
    #
    # `X-HIRIS-Turno` e' l'intestazione che `agent/runner.py::config_mcp`
    # aggiunge alla voce `--mcp-config` del ponte: la CLI la ripete su OGNI
    # `tools/call` che fa verso questa rotta. Il runner conia UNA identita'
    # sola per TURNO (non una per invocazione della CLI) e la riuserebbe se
    # una seconda invocazione dello stesso turno chiamasse ancora strumenti
    # (Task 4: oggi non succede -- il ritentativo riparte sempre senza
    # strumenti -- ma se succedesse, questo e' cio' che impedirebbe al tetto
    # di raddoppiare in silenzio).
    exchange_id = request.headers.get("X-HIRIS-Turno")
    turn: ExchangeTurn | None = None
    if not exchange_id:
        # Silenzio dichiarato (5) della fetta: un chiamante che non propaga
        # questa intestazione (una CLI diversa dal ponte, un test, un
        # chiamante futuro) non e' un guasto -- rifiutare lo strumento
        # romperebbe il prodotto per un contatore che quel chiamante non sa
        # nemmeno di dover portare. Si esegue lo strumento come se il tetto
        # non esistesse, e si dichiara nel log che questa chiamata e' FUORI
        # dal conteggio, invece di fingere che sia normale.
        logger.warning(
            "MCP tools/call «%s» senza l'intestazione X-HIRIS-Turno: non "
            "viene contata nel tetto per-turno (%d/turno) -- il chiamante "
            "non la propaga", name, MAX_TOOL_ROUNDS)
    else:
        now = time.time()
        _release_expired(request.app, now)
        rounds_so_far, turn = _count_round(request.app, exchange_id, now=now)
        if rounds_so_far >= MAX_TOOL_ROUNDS:
            if rounds_so_far == MAX_TOOL_ROUNDS:
                # Un log.warning al PRIMO superamento per turno (Step 3 del
                # brief), non a ogni chiamata successiva: il turno e' gia'
                # dichiarato pieno, ripeterlo per ogni ulteriore tentativo
                # sarebbe rumore invece di un segnale.
                logger.warning(
                    "MCP: tetto di %d chiamate di strumento raggiunto per il "
                    "turno %s -- «%s» NON viene eseguita, il dispatcher non "
                    "e' invocato", MAX_TOOL_ROUNDS, exchange_id, name)
            return _answer(request_id, _ceiling_rejection(name))

    # Il nome accettato e' quello nudo (`search`, ...): il prefisso
    # `mcp__hiris__` lo mette la CLI dal lato modello, non arriva nel
    # protocollo. Se un giorno arrivasse, il dispatcher lo direbbe con un
    # `errore` leggibile invece di sollevare -- non c'e' niente da sbucciare
    # qui a indovinare.
    #
    # fetta «costruire»: si ripropone al dispatcher la STESSA `exchange_id` gia'
    # letta sopra da `X-HIRIS-Turno` per il tetto dei giri -- non se ne conia
    # una seconda. E' l'identita' che la guardia dell'officina usa per
    # rifiutare una `confirm` nello stesso turno della `propose` che
    # l'ha proposta. Quando l'intestazione manca (`exchange_id` e' `None`, il
    # ramo del log qui sopra) il dispatcher la propaga cosi' com'e':
    # l'officina rifiuta di applicare e lo dichiara, non finge un turno che
    # non esiste.
    #
    # Fetta «le chat divise» (spec §4): per un turno di chat il dispatcher
    # riceve soffitto, soggetto e frase DEL JOB, come il ramo sincrono. Prima
    # di questa riga il ponte costruiva senza soffitto: una persona non
    # amministratrice poteva far scrivere un'automazione passando dal piano.
    # Una promessa non porta `X-HIRIS-Chat`, ma una persona l'ha chiesta: il
    # suo soffitto si rifa' dal filo della promessa (`_build_dispatcher`). Un
    # mestiere di sfondo porta `X-HIRIS-Lavoro` e il soffitto dichiarato; un
    # turno che non porta niente non ha nessun gesto (decisione 13).
    # Un'intestazione PRESENTE che non vale chiude la chiamata: vedi
    # `_stale_chat_rejection`.
    #
    # Tappa 6, Task 8 (D-63): il dispatcher si costruisce alla PRIMA chiamata
    # del turno e resta nel turno (`ExchangeTurn`). Le intestazioni del job e
    # della promessa si rileggono comunque a ogni chiamata: un job che non
    # vale piu' chiude la chiamata anche a turno avviato.
    work_header_present, species = _exchange_species(request)
    if work_header_present and species is None:
        return _answer(request_id, _stale_work_rejection(name))
    chat_header_present, chat_job = _exchange_chat_job(request)
    if chat_header_present and chat_job is None:
        return _answer(request_id, _stale_chat_rejection(name))
    promise_id = _exchange_promise_id(request)
    dispatcher = turn.dispatcher if turn is not None else None
    if dispatcher is None and species is not None:
        # Il guardiano del mestiere, lo stesso della catena: lascia passare
        # solo il catalogo della dichiarazione (attori, Task 3.6).
        dispatcher = await SPECIES[species].guard(request.app, exchange_id)
        if turn is not None:
            turn.dispatcher = dispatcher = turn.dispatcher or dispatcher
    if dispatcher is None:
        dispatcher = await _build_dispatcher(request, exchange_id, chat_job, promise_id)
        if turn is not None:
            # Due prime chiamate in parallelo possono costruirne due: resta il
            # primo arrivato, e l'altro non ha ancora letto niente.
            turn.dispatcher = dispatcher = turn.dispatcher or dispatcher
    if promise_id:
        # Lo STESSO guardiano del ramo sincrono, non una seconda regola:
        # `SOLA_LETTURA` e' un elenco di AMMISSIONE, e con due implementazioni
        # uno strumento nuovo che scrive entrerebbe da solo in una delle due il
        # giorno in cui qualcuno lo aggiunge alla chat. `conclude` non esiste
        # nel dispatcher della chat: lo serve il wrapper, ed e' li' che il
        # turno finisce. Il guardiano e' di QUESTA chiamata, non del turno:
        # `conclusione` dice cosa ha fatto lei.
        dispatcher = PromiseDispatcher(dispatcher)
    result = await dispatcher.dispatch(name, arguments)

    if promise_id and dispatcher.conclusione is not None:
        # Il turno ha chiamato `conclude`: la promessa si chiude ADESSO, e la
        # notifica parte adesso. Non si aspetta la consegna del job -- se la
        # CLI morisse dopo aver concluso, la decisione del modello sarebbe gia'
        # al sicuro, e il `submit` che arriva dopo trovera' una promessa non
        # piu' `in_corso` e non toccheranno niente (`reasoning/consegna`).
        #
        # A concludere e' l'orologio, non questa rotta: un secondo punto che
        # decide se notificare e con quali parole sarebbe libero di divergere
        # dal primo, sul gesto piu' visibile che il prodotto compia.
        sweeper = request.app.get("sweeper")
        store = (request.app.get("agenda") or None)
        row = store.read(promise_id) if store is not None else None
        if sweeper is None or row is None:
            # Silenzio dichiarato: il modello ha concluso e noi non abbiamo di
            # che chiudere. Non si finge che sia andata: lo si dice a lui, che
            # e' l'unico che puo' ancora fare qualcosa (riprovare, o dirlo nel
            # testo), e lo si scrive nel log per chi indaga.
            logger.error(
                "MCP «conclude» per la promessa %s: orologio o archivio "
                "assenti, la promessa NON e' stata chiusa", promise_id)
            result = {"errore": ("ho ricevuto la conclusione ma non ho "
                                 "potuto chiudere la promessa.")}
        elif row.get("stato") != "in_corso":
            # Riletta adesso, non al primo controllo dell'intestazione: fra i
            # due puo' essere arrivata la scadenza, o un `conclude` gemello.
            # Una promessa gia' chiusa non si riconsegna (Task 3, fix round 1:
            # niente seconda riga in chat, niente seconda push) -- e lo si dice
            # al modello invece di fingere.
            logger.info("MCP «conclude» per la promessa %s: gia' conclusa (%s)",
                        promise_id, row.get("stato"))
            result = {"errore": ("questa promessa era gia' conclusa: la tua "
                                 "conclusione non cambia niente.")}
        else:
            await sweeper.concludi_chiedi(
                row, dispatcher.conclusione, now=time.time())
            # Rilievo R1 della revisione indipendente sul tratto
            # `v3.22.2..HEAD`: prima di questa riga nessun punto del
            # prodotto registrava MAI un successo per una promessa mantenuta
            # dal ponte -- il gemello di questo `.successo(...)` per la chat
            # sta in `server.py::_submit_chat_reply`, ed e' l'unica altra
            # strada per cui il piano puo' rispondere. Qui il modello HA
            # concluso: e' un fatto gia' accertato, non un'ipotesi.
            registry = request.app.get("occurrence_registry")
            if registry is not None:
                registry.successo(SUBSCRIPTION.id)

    content: dict = {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
    }
    # Un guasto dello strumento (archivi non ancora caricati, argomenti
    # mancanti, nome sconosciuto) e' un `errore` dichiarato dal dispatcher, mai
    # un'eccezione: `dispatch()` non solleva per contratto. Lo si rimanda al
    # modello com'e' -- e lo si marca `isError`, che nel protocollo e' l'unico
    # modo di distinguere una chiamata fallita da una riuscita. Senza questa
    # riga il fallimento arriverebbe travestito da successo: il difetto numero
    # uno di questo prodotto.
    if isinstance(result, dict) and "errore" in result:
        content["isError"] = True
        # A livello DEBUG, non `info`: il testo dell'errore lo compongono i
        # gestori (`home_space/tools.py`, `action/actuator.py`) e puo' contenere
        # dati di casa -- id di entita', nomi di aree, frammenti di frase. Un
        # log e' un posto in cui quelle cose restano scritte, e il livello
        # predefinito dell'add-on non e' `debug`. Che la chiamata sia fallita
        # lo dice comunque `isError` al modello, che e' chi deve saperlo.
        logger.debug("MCP tools/call «%s» ha dichiarato un errore: %s",
                     name, result.get("errore"))
    return _answer(request_id, content)


async def handle_mcp(request: web.Request) -> web.Response:
    """L'adattatore: `initialize`, `tools/list`, `tools/call`, piu' le notifiche.

    **L'autenticazione non riposa su un ramo solo.** `internal_auth_middleware`
    lascia passare piu' categorie di richieste -- l'ingress genuino del
    Supervisor, un canale firmato, la credenziale di un turno del ponte, e
    (nella sola suite di test) la valvola `HIRIS_ALLOW_NO_TOKEN`. Questa rotta
    ne accetta **una sola**: `turno`, la credenziale effimera che il worker del
    ponte manda (la conia `server.py::_intestazioni_ponte`). Fino al 22/09/2026 era il
    segreto condiviso (`auth_via == "token"`), che da quel giorno il middleware
    non assegna piu'. Il controllo e' su `request["auth_via"]`,
    che il middleware scrive: non si ricopia qui un secondo confronto di segreti
    (sarebbe un secondo posto da tenere allineato), si restringe. Se il
    middleware non ha girato affatto, la chiave non c'e' e la rotta nega: chiuso
    per difetto.

    **Il CSRF, che non e' l'autenticazione.** `csrf_middleware` blocca ogni POST
    su `/api/*` privo di `X-Requested-With`, ed esenta chi il confine ha gia'
    riconosciuto come macchina (`auth_via` «canale», «turno», «accoppiamento»).
    La CLI `claude` manda la credenziale di turno nell'intestazione
    `X-HIRIS-Internal-Token` e **non** manda `X-Requested-With`: passa quindi da
    quell'esenzione. Entrambe le vie sono pinnate in `tests/test_mcp_route.py`
    con le valvole della suite rimosse.
    """
    # «turno» e' la credenziale EFFIMERA del ponte, che dal 22/09/2026
    # sostituisce il segreto condiviso su questo percorso: stessa rotta,
    # stesso portatore, credenziale che muore col turno.
    if request.get("auth_via") != "turno":
        logger.warning(
            "MCP: richiesta rifiutata da %s -- questa rotta accetta solo la "
            "credenziale di un turno del ponte (autenticazione vista: %s)",
            request.remote, request.get("auth_via"),
        )
        return error_response(401, "unauthorized")

    try:
        body = await request.json()
    except Exception as error:
        return _error(
            -32700,
            f"il corpo della richiesta non e' JSON valido "
            f"({type(error).__name__}: {error}).",
            status=400,
        )

    if not isinstance(body, dict):
        return _error(
            -32600,
            "il corpo dev'essere un singolo oggetto JSON-RPC 2.0; ricevuto "
            f"invece {type(body).__name__} (i batch non sono supportati).",
            status=400,
        )

    method = body.get("method")
    request_id = body.get("id")
    # Notifica = richiesta **senza** il membro `id` (JSON-RPC 2.0). Non
    # `id is None`: un `id` esplicitamente nullo resta una richiesta.
    is_notification = "id" not in body

    if not isinstance(method, str) or not method:
        if is_notification:
            # Anche una notifica malformata non riceve un corpo (per
            # protocollo), ma il guasto si dichiara nel log invece di sparire.
            logger.warning("MCP: notifica senza «method» utilizzabile: %r", method)
            return web.Response(status=202)
        return _error(
            -32600,
            f"campo «method» assente o non testuale (ricevuto: {method!r}); "
            f"i metodi conosciuti sono {', '.join(METHODS)}.",
            request_id,
            status=400,
        )

    if is_notification:
        # `notifications/initialized` e compagne: si accettano e basta. Non
        # abbiamo stato di sessione da aggiornare, e rispondere a una notifica
        # sarebbe una violazione del protocollo.
        logger.debug("MCP: notifica «%s» accettata", method)
        return web.Response(status=202)

    try:
        if method == "initialize":
            return _answer(request_id, {
                # Si rimanda indietro la versione ricevuta: e' il client a
                # sapere quale sa parlare. Nessun `Mcp-Session-Id` richiesto ne'
                # emesso -- non abbiamo stato di sessione da difendere, e
                # pretenderlo sarebbe solo un modo in piu' di non partire.
                "protocolVersion": (body.get("params") or {}).get(
                    "protocolVersion") or DEFAULT_PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": MCP_SERVER_NAME, "version": read_version()},
            })
        if method == "tools/list":
            _promise_id = _exchange_promise_id(request)
            _work_present, _species = _exchange_species(request)
            # Il turno di una promessa vede il catalogo della promessa:
            # i lettori di `SOLA_LETTURA` piu' `conclude`, che li' e' l'unico modo
            # in cui il turno puo' finire. Le definizioni sono le STESSE
            # di `KNOWLEDGE_TOOLS` (promise_tools le filtra, non
            # le riscrive), quindi una descrizione migliorata vale su
            # entrambe le strade. Il turno di un mestiere con guardiano vede
            # il catalogo della sua dichiarazione, e un'intestazione che non
            # vale non vede niente (attori, Task 3.6).
            if _work_present:
                catalogo = mcp_catalog(SPECIES[_species].catalog_for_turn()
                                       if _species else [])
            else:
                catalogo = mcp_catalog(promise_tools() if _promise_id else None)
            # Spec «le misure complete» §4(2): quante definizioni la CLI ha
            # ricevuto per QUESTO turno. La sonda di `probe_tools` non porta
            # `X-HIRIS-Turno` e non si annota: non e' un turno.
            # Come `_annota_risultato`: una misura rotta non toglie il
            # catalogo alla CLI -- si avverte e si risponde lo stesso.
            try:
                carichi = request.app.get(BRIDGE_LOADS_KEY)
                if carichi is not None:
                    carichi.tools_listed(
                        request.headers.get("X-HIRIS-Turno", ""),
                        pesa_in_caratteri(catalogo), len(catalogo))
            except Exception as errore:
                logger.warning("MCP: il peso delle definizioni non si e' "
                               "annotato (%s)", type(errore).__name__)
            return _answer(request_id, {"tools": catalogo})
        if method == "tools/call":
            risposta = await _call_tool(request, body.get("params") or {}, request_id)
            _annota_risultato(request, risposta)
            return risposta
        return _error(
            -32601,
            f"metodo «{method}» sconosciuto: questa rotta e' un adattatore di "
            f"tre metodi ({', '.join(METHODS)}) piu' le notifiche.",
            request_id,
        )
    except Exception as error:
        # Stessa proprieta' di `ToolDispatcher.dispatch`: da qui non
        # risale mai un'eccezione, e non esce mai un 500 nudo. Un turno del
        # ponte spezzato da una traccia Python sarebbe indistinguibile, per
        # l'utente, da una risposta che non arriva.
        logger.exception("MCP: «%s» ha sollevato", method)
        return _error(
            -32603,
            f"«{method}» ha incontrato un problema interno "
            f"({type(error).__name__}: {error}).",
            request_id,
        )
