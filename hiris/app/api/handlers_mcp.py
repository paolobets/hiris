"""`POST /api/mcp` -- l'adattatore JSON-RPC che porta gli strumenti al ponte.

**Perche' esiste.** HIRIS ha due percorsi di chat. Il turno sincrono passa gli
strumenti (`STRUMENTI_CONOSCENZA`) direttamente al runner, che li
dispaccia con `DispatcherStrumenti`. Il ponte via abbonamento invece invoca la
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
`guarda` risponderebbe sempre `stato_non_letto`, e avremmo due intelligenze nella
stessa casa che ne vedono due diverse.

**Cosa NON e'.** Non e' una superficie remota: la chiama solo il sottoprocesso
`claude` che gira dentro l'add-on, su `127.0.0.1`, e nessuna opzione `Network`
la espone. Non e' un secondo catalogo: `tools/list` **ri-forma**
`STRUMENTI_CONOSCENZA` (una sola chiave rinominata) e non ne dichiara uno
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
definizioni di `STRUMENTI_CONOSCENZA` invece di riscriverle. Senza questo, un
turno di promessa sul ponte non avrebbe `concludi` -- cioe' nessun modo di
finire -- e vedrebbe `esegui`, cioe' potrebbe toccare la casa senza nessuno
davanti.

**E' anche un canale di azione, dalla fetta «comandare», e dalla fetta
«costruire» anche di configurazione.** Fino a quel momento qui si leggeva «gli
strumenti restano quattro e nessuno tocca Home Assistant -- HIRIS conosce e
non agisce»: era vero, e ha smesso di esserlo su entrambe le meta'. Gli
strumenti sono tredici, lo stesso catalogo del turno sincrono: `esegui` chiama
un servizio di Home Assistant, `costruisci`/`conferma` compongono e scrivono
configurazione. Cio' che NON cambia e' il motivo per cui la frase stava qui:
questa rotta non e' una porta di scrittura propria. `tools/call` dispaccia con
la stessa funzione del turno sincrono, che dispaccia alle stesse due porte --
`azione/porta.py` per i servizi, `azione/costruzione/officina.py` per la
configurazione -- il ponte non ha una strada verso la casa che la chat non
abbia, e non ne ha una sua. Un secondo punto di scrittura sarebbe un difetto,
non un'ottimizzazione.

**Chi la chiama.** Due chiamanti di produzione, entrambi in
`hiris/app/agent/runner.py`: il sottoprocesso `claude` del ponte, a cui l'argv
passa questa rotta nella voce `--mcp-config` (`config_mcp`), e la sonda
`tools/list` che il runner fa PRIMA di comporre il turno (`sonda_strumenti`),
per decidere se il prompt puo' affermare gli strumenti. La registrazione
in `server.py` (`app.router.add_post("/api/mcp", handle_mcp)`) porta lo stesso
elenco: i due file devono restare d'accordo.

Fra il Task 1 e il Task 3 di questa fetta la rotta e' stata un **orfano
dichiarato** -- `scripts/censimento.py` la contava fra le «rotte HTTP chiamate
solo dai test» -- mai un orfano nascosto. Col Task 3 l'orfano e' stato raccolto
e il censimento e' tornato a 43.
"""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict

from aiohttp import web

from ..casa.strumenti import KNOWLEDGE_TOOLS
from ..schedulatore.turno import PromiseDispatcher, promise_tools
from ..version import read_version
from .handlers_chat import create_tool_dispatcher

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
# mitigazione minima (progetto, §5.2): il modello puo' incatenare `cerca` ->
# `guarda` -> `richiama` -> ancora, e ogni giro costa un turno di
# `chat_daily_cap` mentre ne consuma N. `claude 2.1.226` pero' NON ha un
# `--max-turns` ne' alcun flag che limiti i giri di strumento (verificato su
# `claude --help`, decisione A.7 del progetto): il tetto non puo' stare
# sull'argv del ponte (`agent/runner.py::_chat_claude_args`), deve stare QUI,
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
# guardare + 1 `cerca` + la `prometti` finale) moriva esattamente come
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
# comprese quelle parallele della stessa risposta della CLI: 8 `guarda`
# richiesti insieme dal modello costano comunque 8 giri qui, non 1. Stesso
# tetto, contatori diversi -- e' per questo che `agent/prompts.py::
# _GUIDA_CON_STRUMENTI` insegna al ponte una parsimonia che
# `claude_runner.BASE_REGOLE_STRUMENTI` non ha bisogno di insegnare al ramo
# sincrono (vedi `tests/test_prompt_parallelismo.py`).
#
# **Costante di modulo, non un'opzione dell'add-on** (regole della fetta): un
# opzione vive in cinque posti (config.yaml options+schema, run.sh, le due
# traduzioni, il lettore Python), e qui non c'e' niente che l'utente debba
# toccare oggi -- se un giorno servira' configurarla, si fara' il giro dei
# cinque posti allora.
MAX_TOOL_ROUNDS = 50

# Quante identita' di turno diverse restano tracciate insieme. Piccolo di
# proposito (Step 2 del brief, "N piccolo"): serve solo a impedire che il
# dizionario cresca senza fine per l'intera vita del processo -- un turno del
# ponte dura al piu' i due `subprocess.run(timeout=300)` di
# `agent/runner.py::_reason_chat`, la sua identita' non serve piu' un istante
# dopo, e tenerne migliaia sarebbe una perdita di memoria scritta apposta.
# L'espulsione e' **LRU, non FIFO** (l'etichetta era sbagliata fino alla
# review totale della fetta, M-1): `_count_round` fa `move_to_end` a ogni
# chiamata, quindi l'`OrderedDict` e' ordinato per ULTIMO USO e
# `popitem(last=False)` scarta il turno che tace da piu' tempo, non quello
# iniziato per primo. La differenza non e' terminologica: e' cio' che rende
# vera la proprieta' portante di questo tetto -- **un turno ancora attivo non
# viene mai espulso**, per quanti altri turni gli passino accanto. Con una
# FIFO vera un turno lungo verrebbe scartato dopo `_MAX_TRACKED_EXCHANGES`
# turni altrui e il suo contatore ripartirebbe da zero, cioe' il tetto si
# potrebbe aggirare semplicemente durando. La proprieta' e' pinnata in
# `tests/test_rotta_mcp.py::test_un_turno_attivo_non_viene_mai_espulso`.
_MAX_TRACKED_EXCHANGES = 64

# La chiave sotto cui i contatori vivono nell'`Application`. Costante e non una
# stringa ripetuta: chi la crea (`server.create_app`) e chi la legge
# (`_count_round`) devono per forza nominare la stessa cosa.
ROUNDS_PER_EXCHANGE_KEY = "mcp_giri_per_turno"


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
    un'autenticazione, che resta il token interno (vedi il docstring in cima a
    questo modulo).

    Proprio perche' non autentica, si VERIFICA: un id che non corrisponde a una
    promessa `in_corso` non vale niente. Senza questo controllo l'intestazione
    sarebbe un modo per farsi servire un catalogo diverso -- quello che contiene
    `concludi` -- mostrando un identificatore qualunque.

    Fetta «le promesse seguono la catena» (22/08/2026).
    """
    ident = (request.headers.get("X-HIRIS-Promessa") or "").strip()
    if not ident:
        return ""
    store = request.app.get("promesse")
    if store is None:
        return ""
    row = store.read(ident)
    return ident if row and row.get("stato") == "in_corso" else ""


def mcp_catalog(definitions: list[dict] | None = None) -> list[dict]:
    """Un catalogo di strumenti nella grafia di MCP: `input_schema` -> `inputSchema`.

    Trasformazione **meccanica**, e deve restare tale: nessun testo nuovo,
    nessuna descrizione riscritta, nessun nome aggiunto o tolto. Le altre chiavi
    passano invariate, cosi' che una chiave nuova in `casa/strumenti.py` arrivi
    qui da sola invece di essere dimenticata.

    Il parametro serve al turno di una promessa, che ha un catalogo suo
    (`promise_tools()`: i sei lettori piu' `concludi`). E' la STESSA
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


def _count_round(app, exchange_id: str) -> int:
    """Incrementa il contatore dei giri di strumento del turno `exchange_id` e
    restituisce il valore **prima** dell'incremento (quanti giri erano gia'
    passati per questo turno).

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

    **Dimensione limitata** (`_MAX_TRACKED_EXCHANGES`, "le ultime N identita' di
    turno" del brief): quando arriva un'identita' MAI vista e il dizionario e'
    gia' pieno, si scarta quella usata da PIU' TEMPO -- LRU e non FIFO, ed e'
    il `move_to_end` qui sotto a farne la differenza. Un turno che continua a
    chiamare si rimette in coda a ogni giro e non puo' essere espulso: se lo
    fosse, il suo contatore ripartirebbe da zero e il tetto si aggirerebbe
    durando (vedi il commento su `_MAX_TRACKED_EXCHANGES`).

    **La struttura la crea `server.create_app()`**, non questa funzione (M-2
    della review totale): scriverla qui, a richiesta gia' servita, faceva
    emettere ad aiohttp «Changing state of started or joined application»,
    che con aiohttp 4 diventa un errore. Lo stato di un'app aiohttp si compone
    prima che l'app parta."""
    rounds_per_exchange: OrderedDict[str, int] = app[ROUNDS_PER_EXCHANGE_KEY]
    if exchange_id in rounds_per_exchange:
        rounds_per_exchange.move_to_end(exchange_id)
        rounds = rounds_per_exchange[exchange_id]
    else:
        rounds = 0
        if len(rounds_per_exchange) >= _MAX_TRACKED_EXCHANGES:
            rounds_per_exchange.popitem(last=False)  # il piu' vecchio
    rounds_per_exchange[exchange_id] = rounds + 1
    return rounds


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
    `DispatcherStrumenti._archivio_mancante`: si dichiara COSA e' successo
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
    forma nel protocollo: `isError: True`) e' il TESTO, leggibile sia nel log
    sia da chi ispeziona `debug.tools_called` (Task 5): un fallimento del
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
    # `ricorda`, per dire) sarebbe gia' avvenuto quando lo si rifiuta.
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
        rounds_so_far = _count_round(request.app, exchange_id)
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

    # Il nome accettato e' quello nudo (`cerca`, ...): il prefisso
    # `mcp__hiris__` lo mette la CLI dal lato modello, non arriva nel
    # protocollo. Se un giorno arrivasse, il dispatcher lo direbbe con un
    # `errore` leggibile invece di sollevare -- non c'e' niente da sbucciare
    # qui a indovinare.
    #
    # fetta «costruire»: si ripropone al dispatcher la STESSA `exchange_id` gia'
    # letta sopra da `X-HIRIS-Turno` per il tetto dei giri -- non se ne conia
    # una seconda. E' l'identita' che la guardia dell'officina usa per
    # rifiutare una `conferma` nello stesso turno della `costruisci` che
    # l'ha proposta. Quando l'intestazione manca (`exchange_id` e' `None`, il
    # ramo del log qui sopra) il dispatcher la propaga cosi' com'e':
    # l'officina rifiuta di applicare e lo dichiara, non finge un turno che
    # non esiste.
    dispatcher = create_tool_dispatcher(request.app, exchange=exchange_id)
    promise_id = _exchange_promise_id(request)
    if promise_id:
        # Lo STESSO guardiano del ramo sincrono, non una seconda regola:
        # `SOLA_LETTURA` e' un elenco di AMMISSIONE, e con due implementazioni
        # uno strumento nuovo che scrive entrerebbe da solo in una delle due il
        # giorno in cui qualcuno lo aggiunge alla chat. `concludi` non esiste
        # nel dispatcher della chat: lo serve il wrapper, ed e' li' che il
        # turno finisce.
        dispatcher = PromiseDispatcher(dispatcher)
    result = await dispatcher.dispatch(name, arguments)

    if promise_id and dispatcher.conclusione is not None:
        # Il turno ha chiamato `concludi`: la promessa si chiude ADESSO, e la
        # notifica parte adesso. Non si aspetta la consegna del job -- se la
        # CLI morisse dopo aver concluso, la decisione del modello sarebbe gia'
        # al sicuro, e il `submit` che arriva dopo trovera' una promessa non
        # piu' `in_corso` e non toccheranno niente (`handlers_reasoning`).
        #
        # A concludere e' l'orologio, non questa rotta: un secondo punto che
        # decide se notificare e con quali parole sarebbe libero di divergere
        # dal primo, sul gesto piu' visibile che il prodotto compia.
        sweeper = request.app.get("orologio")
        store = (request.app.get("promesse") or None)
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
        else:
            await sweeper.concludi_chiedi(
                row, dispatcher.conclusione, now=time.time())

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
        # gestori (`casa/strumenti.py`, `azione/porta.py`) e puo' contenere
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
    lascia passare tre categorie di richieste -- ingress genuino del Supervisor,
    token interno valido, e (nella sola suite di test) la valvola
    `HIRIS_ALLOW_NO_TOKEN`. Questa rotta ne accetta **una sola**: il token, cioe'
    esattamente cio' che il worker del ponte manda gia'
    (`agent/runner.py::build_headers`). Il controllo e' su `request["auth_via"]`,
    che il middleware scrive: non si ricopia qui un secondo confronto di segreti
    (sarebbe un secondo posto da tenere allineato), si restringe. Se il
    middleware non ha girato affatto, la chiave non c'e' e la rotta nega: chiuso
    per difetto.

    **Il CSRF, che non e' l'autenticazione.** `csrf_middleware` blocca ogni POST
    su `/api/*` privo di `X-Requested-With`, ed esenta chi porta un
    `X-HIRIS-Internal-Token` valido. La CLI `claude` manda il token e **non**
    manda `X-Requested-With`: passa quindi da quell'esenzione, che a sua volta
    e' viva solo perche' l'add-on genera un token interno quando l'opzione e'
    vuota (`token_interno.py`). Entrambe le vie sono pinnate in
    `tests/test_rotta_mcp.py` con le valvole della suite rimosse -- e il Task 3,
    che scrive gli header della voce `--mcp-config`, ha per iscritto la
    raccomandazione di mandare **anche** `X-Requested-With`, cosi' che nessuno
    dei due rami resti da solo a reggere la rotta.
    """
    if request.get("auth_via") != "token":
        logger.warning(
            "MCP: richiesta rifiutata da %s -- questa rotta accetta solo "
            "l'X-HIRIS-Internal-Token dell'add-on (autenticazione vista: %s)",
            request.remote, request.get("auth_via"),
        )
        return web.json_response({"error": "unauthorized"}, status=401)

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
            # Il turno di una promessa vede il catalogo della promessa:
            # i sei lettori piu' `concludi`, che li' e' l'unico modo
            # in cui il turno puo' finire. Le definizioni sono le STESSE
            # di `STRUMENTI_CONOSCENZA` (promise_tools le filtra, non
            # le riscrive), quindi una descrizione migliorata vale su
            # entrambe le strade.
            return _answer(request_id, {"tools": mcp_catalog(
                promise_tools() if _promise_id else None)})
        if method == "tools/call":
            return await _call_tool(request, body.get("params") or {}, request_id)
        return _error(
            -32601,
            f"metodo «{method}» sconosciuto: questa rotta e' un adattatore di "
            f"tre metodi ({', '.join(METHODS)}) piu' le notifiche.",
            request_id,
        )
    except Exception as error:
        # Stessa proprieta' di `DispatcherStrumenti.dispatch`: da qui non
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
