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
`costruisci_dispatcher_strumenti(app)`, la stessa funzione del turno sincrono.

**E' anche un canale di azione, dalla fetta «comandare».** Fino a quel momento
qui si leggeva «gli strumenti restano quattro e nessuno tocca Home Assistant --
HIRIS conosce e non agisce»: era vero, e ha smesso di esserlo su entrambe le
meta'. Gli strumenti sono cinque e il quinto, `esegui`, chiama un servizio di
Home Assistant. Cio' che NON cambia e' il motivo per cui la frase stava qui:
questa rotta non e' una porta di scrittura propria. `tools/call` dispaccia con
la stessa funzione del turno sincrono, che dispaccia alla stessa porta unica
(`azione/porta.py`) -- il ponte non ha una strada verso la casa che la chat non
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
from collections import OrderedDict

from aiohttp import web

from ..casa.strumenti import STRUMENTI_CONOSCENZA
from ..version import read_version
from .handlers_chat import costruisci_dispatcher_strumenti

logger = logging.getLogger(__name__)

# Il nome con cui il server MCP si presenta alla CLI. Costante di modulo e NON
# un'opzione dell'add-on: un'opzione vive in cinque posti (config.yaml options+
# schema, run.sh, le due traduzioni, il lettore Python) e qui non c'e' niente
# da configurare. Il Task 3 la riusa per la voce di `--mcp-config` e per il
# prefisso `mcp__hiris__` con cui la CLI presenta gli strumenti al modello: un
# nome solo, in un posto solo.
NOME_SERVER_MCP = "hiris"

# La versione di protocollo che dichiariamo quando il client non ne manda una.
# Nel caso normale `initialize` rimanda indietro **quella ricevuta**: e' il
# client (la CLI `claude`) a sapere quale sa parlare, e negoziare al ribasso una
# versione che non ci serve sarebbe un modo in piu' di non partire.
PROTOCOLLO_PREDEFINITO = "2025-06-18"

# I tre metodi che questa rotta conosce. Serve anche a scrivere un errore
# `-32601` che DICE cosa esiste, invece di un "method not found" nudo.
METODI = ("initialize", "tools/list", "tools/call")

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
# `response.content` in `claude_runner.chat()`). `MAX_GIRI_STRUMENTI` (qui)
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
MAX_GIRI_STRUMENTI = 50

# Quante identita' di turno diverse restano tracciate insieme. Piccolo di
# proposito (Step 2 del brief, "N piccolo"): serve solo a impedire che il
# dizionario cresca senza fine per l'intera vita del processo -- un turno del
# ponte dura al piu' i due `subprocess.run(timeout=300)` di
# `agent/runner.py::_reason_chat`, la sua identita' non serve piu' un istante
# dopo, e tenerne migliaia sarebbe una perdita di memoria scritta apposta.
# L'espulsione e' **LRU, non FIFO** (l'etichetta era sbagliata fino alla
# review totale della fetta, M-1): `_conta_giro` fa `move_to_end` a ogni
# chiamata, quindi l'`OrderedDict` e' ordinato per ULTIMO USO e
# `popitem(last=False)` scarta il turno che tace da piu' tempo, non quello
# iniziato per primo. La differenza non e' terminologica: e' cio' che rende
# vera la proprieta' portante di questo tetto -- **un turno ancora attivo non
# viene mai espulso**, per quanti altri turni gli passino accanto. Con una
# FIFO vera un turno lungo verrebbe scartato dopo `_MAX_TURNI_TRACCIATI`
# turni altrui e il suo contatore ripartirebbe da zero, cioe' il tetto si
# potrebbe aggirare semplicemente durando. La proprieta' e' pinnata in
# `tests/test_rotta_mcp.py::test_un_turno_attivo_non_viene_mai_espulso`.
_MAX_TURNI_TRACCIATI = 64

# La chiave sotto cui i contatori vivono nell'`Application`. Costante e non una
# stringa ripetuta: chi la crea (`server.create_app`) e chi la legge
# (`_conta_giro`) devono per forza nominare la stessa cosa.
CHIAVE_GIRI_PER_TURNO = "mcp_giri_per_turno"


def prepara_contatori(app) -> None:
    """Crea la struttura dei contatori **prima che l'app parta**.

    M-2 della review totale della fetta. Prima, `_conta_giro` la creava con
    `app.setdefault(...)` alla prima `tools/call` servita: aiohttp lo vede
    come una modifica dello stato di un'applicazione gia' avviata ed emette
    «Changing state of started or joined application is deprecated» -- oggi un
    `DeprecationWarning` visibile nell'output della suite, con **aiohttp 4 un
    errore**. Lo stato di un'app aiohttp si compone in `create_app()`, cioe'
    prima del `freeze`, e non a richiesta servita.

    Non e' `setdefault`: chiamarla due volte sulla stessa app azzererebbe i
    contatori, e non esiste nessun motivo per chiamarla due volte."""
    app[CHIAVE_GIRI_PER_TURNO] = OrderedDict()


def _risposta(id_richiesta, risultato: dict) -> web.Response:
    return web.json_response({"jsonrpc": "2.0", "id": id_richiesta, "result": risultato})


def _errore(codice: int, messaggio: str, id_richiesta=None, *, stato: int = 200) -> web.Response:
    """Un errore JSON-RPC che dice **cosa** e' successo.

    Un codice generico su una chiamata malformata e' un silenzio travestito: chi
    legge il log (o il modello, che riceve il testo) deve poter capire quale
    campo mancava senza rileggere questo file.
    """
    return web.json_response(
        {"jsonrpc": "2.0", "id": id_richiesta,
         "error": {"code": codice, "message": messaggio}},
        status=stato,
    )


def catalogo_mcp() -> list[dict]:
    """`STRUMENTI_CONOSCENZA` nella grafia di MCP: `input_schema` -> `inputSchema`.

    Trasformazione **meccanica**, e deve restare tale: nessun testo nuovo,
    nessuna descrizione riscritta, nessun nome aggiunto o tolto. Le altre chiavi
    passano invariate, cosi' che una chiave nuova in `casa/strumenti.py` arrivi
    qui da sola invece di essere dimenticata.
    """
    voci: list[dict] = []
    for definizione in STRUMENTI_CONOSCENZA:
        voce = {chiave: valore for chiave, valore in definizione.items()
                if chiave != "input_schema"}
        if "input_schema" in definizione:
            voce["inputSchema"] = definizione["input_schema"]
        voci.append(voce)
    return voci


def _conta_giro(app, id_turno: str) -> int:
    """Incrementa il contatore dei giri di strumento del turno `id_turno` e
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

    **Dimensione limitata** (`_MAX_TURNI_TRACCIATI`, "le ultime N identita' di
    turno" del brief): quando arriva un'identita' MAI vista e il dizionario e'
    gia' pieno, si scarta quella usata da PIU' TEMPO -- LRU e non FIFO, ed e'
    il `move_to_end` qui sotto a farne la differenza. Un turno che continua a
    chiamare si rimette in coda a ogni giro e non puo' essere espulso: se lo
    fosse, il suo contatore ripartirebbe da zero e il tetto si aggirerebbe
    durando (vedi il commento su `_MAX_TURNI_TRACCIATI`).

    **La struttura la crea `server.create_app()`**, non questa funzione (M-2
    della review totale): scriverla qui, a richiesta gia' servita, faceva
    emettere ad aiohttp «Changing state of started or joined application»,
    che con aiohttp 4 diventa un errore. Lo stato di un'app aiohttp si compone
    prima che l'app parta."""
    contatori: OrderedDict[str, int] = app[CHIAVE_GIRI_PER_TURNO]
    if id_turno in contatori:
        contatori.move_to_end(id_turno)
        giri = contatori[id_turno]
    else:
        giri = 0
        if len(contatori) >= _MAX_TURNI_TRACCIATI:
            contatori.popitem(last=False)  # il piu' vecchio
    contatori[id_turno] = giri + 1
    return giri


def _rifiuto_tetto_raggiunto(nome: str) -> dict:
    """Il `content` che il modello vede quando il tetto per-turno e' pieno.

    **La forma scelta, motivata (non un dettaglio di stile).** Resta una
    risposta JSON-RPC 2.0 NORMALE (`result`, non un `error` di protocollo
    `-32xxx`): esattamente la stessa scelta che questo file fa gia' per un
    guasto DICHIARATO del dispatcher (vedi `_chiama_strumento`, il ramo
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
    risultato = {
        "errore": (
            f"hai raggiunto il tetto di {MAX_GIRI_STRUMENTI} chiamate di "
            f"strumento per questo turno (l'ultima tentata: «{nome}»): non "
            "chiamare altri strumenti, rispondi con cio' che hai gia' "
            "raccolto.")
    }
    return {
        "content": [{"type": "text", "text": json.dumps(risultato, ensure_ascii=False)}],
        "isError": True,
    }


async def _chiama_strumento(request: web.Request, parametri, id_richiesta) -> web.Response:
    """`tools/call`: il nome nudo, gli argomenti, e il dispatcher che c'e' gia'."""
    if not isinstance(parametri, dict):
        return _errore(
            -32602,
            "«tools/call» richiede un oggetto «params» con «name» e «arguments»; "
            f"ricevuto invece {type(parametri).__name__}.",
            id_richiesta,
        )
    nome = parametri.get("name")
    if not isinstance(nome, str) or not nome.strip():
        return _errore(
            -32602,
            "«tools/call» richiede «params.name», il nome NUDO dello strumento "
            f"(uno fra {', '.join(sorted(d['name'] for d in STRUMENTI_CONOSCENZA))}); "
            f"ricevuto invece {nome!r}.",
            id_richiesta,
        )
    argomenti = parametri.get("arguments")
    if argomenti is None:
        argomenti = {}
    if not isinstance(argomenti, dict):
        return _errore(
            -32602,
            f"«params.arguments» di «{nome}» dev'essere un oggetto; "
            f"ricevuto invece {type(argomenti).__name__}.",
            id_richiesta,
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
    id_turno = request.headers.get("X-HIRIS-Turno")
    if not id_turno:
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
            "non la propaga", nome, MAX_GIRI_STRUMENTI)
    else:
        giri_gia_fatti = _conta_giro(request.app, id_turno)
        if giri_gia_fatti >= MAX_GIRI_STRUMENTI:
            if giri_gia_fatti == MAX_GIRI_STRUMENTI:
                # Un log.warning al PRIMO superamento per turno (Step 3 del
                # brief), non a ogni chiamata successiva: il turno e' gia'
                # dichiarato pieno, ripeterlo per ogni ulteriore tentativo
                # sarebbe rumore invece di un segnale.
                logger.warning(
                    "MCP: tetto di %d chiamate di strumento raggiunto per il "
                    "turno %s -- «%s» NON viene eseguita, il dispatcher non "
                    "e' invocato", MAX_GIRI_STRUMENTI, id_turno, nome)
            return _risposta(id_richiesta, _rifiuto_tetto_raggiunto(nome))

    # Il nome accettato e' quello nudo (`cerca`, ...): il prefisso
    # `mcp__hiris__` lo mette la CLI dal lato modello, non arriva nel
    # protocollo. Se un giorno arrivasse, il dispatcher lo direbbe con un
    # `errore` leggibile invece di sollevare -- non c'e' niente da sbucciare
    # qui a indovinare.
    dispatcher = costruisci_dispatcher_strumenti(request.app)
    risultato = await dispatcher.dispatch(nome, argomenti)

    contenuto: dict = {
        "content": [{"type": "text", "text": json.dumps(risultato, ensure_ascii=False)}],
    }
    # Un guasto dello strumento (archivi non ancora caricati, argomenti
    # mancanti, nome sconosciuto) e' un `errore` dichiarato dal dispatcher, mai
    # un'eccezione: `dispatch()` non solleva per contratto. Lo si rimanda al
    # modello com'e' -- e lo si marca `isError`, che nel protocollo e' l'unico
    # modo di distinguere una chiamata fallita da una riuscita. Senza questa
    # riga il fallimento arriverebbe travestito da successo: il difetto numero
    # uno di questo prodotto.
    if isinstance(risultato, dict) and "errore" in risultato:
        contenuto["isError"] = True
        # A livello DEBUG, non `info`: il testo dell'errore lo compongono i
        # gestori (`casa/strumenti.py`, `azione/porta.py`) e puo' contenere
        # dati di casa -- id di entita', nomi di aree, frammenti di frase. Un
        # log e' un posto in cui quelle cose restano scritte, e il livello
        # predefinito dell'add-on non e' `debug`. Che la chiamata sia fallita
        # lo dice comunque `isError` al modello, che e' chi deve saperlo.
        logger.debug("MCP tools/call «%s» ha dichiarato un errore: %s",
                     nome, risultato.get("errore"))
    return _risposta(id_richiesta, contenuto)


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
        corpo = await request.json()
    except Exception as errore:
        return _errore(
            -32700,
            f"il corpo della richiesta non e' JSON valido "
            f"({type(errore).__name__}: {errore}).",
            stato=400,
        )

    if not isinstance(corpo, dict):
        return _errore(
            -32600,
            "il corpo dev'essere un singolo oggetto JSON-RPC 2.0; ricevuto "
            f"invece {type(corpo).__name__} (i batch non sono supportati).",
            stato=400,
        )

    metodo = corpo.get("method")
    id_richiesta = corpo.get("id")
    # Notifica = richiesta **senza** il membro `id` (JSON-RPC 2.0). Non
    # `id is None`: un `id` esplicitamente nullo resta una richiesta.
    e_notifica = "id" not in corpo

    if not isinstance(metodo, str) or not metodo:
        if e_notifica:
            # Anche una notifica malformata non riceve un corpo (per
            # protocollo), ma il guasto si dichiara nel log invece di sparire.
            logger.warning("MCP: notifica senza «method» utilizzabile: %r", metodo)
            return web.Response(status=202)
        return _errore(
            -32600,
            f"campo «method» assente o non testuale (ricevuto: {metodo!r}); "
            f"i metodi conosciuti sono {', '.join(METODI)}.",
            id_richiesta,
            stato=400,
        )

    if e_notifica:
        # `notifications/initialized` e compagne: si accettano e basta. Non
        # abbiamo stato di sessione da aggiornare, e rispondere a una notifica
        # sarebbe una violazione del protocollo.
        logger.debug("MCP: notifica «%s» accettata", metodo)
        return web.Response(status=202)

    try:
        if metodo == "initialize":
            return _risposta(id_richiesta, {
                # Si rimanda indietro la versione ricevuta: e' il client a
                # sapere quale sa parlare. Nessun `Mcp-Session-Id` richiesto ne'
                # emesso -- non abbiamo stato di sessione da difendere, e
                # pretenderlo sarebbe solo un modo in piu' di non partire.
                "protocolVersion": (corpo.get("params") or {}).get(
                    "protocolVersion") or PROTOCOLLO_PREDEFINITO,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": NOME_SERVER_MCP, "version": read_version()},
            })
        if metodo == "tools/list":
            return _risposta(id_richiesta, {"tools": catalogo_mcp()})
        if metodo == "tools/call":
            return await _chiama_strumento(request, corpo.get("params") or {}, id_richiesta)
        return _errore(
            -32601,
            f"metodo «{metodo}» sconosciuto: questa rotta e' un adattatore di "
            f"tre metodi ({', '.join(METODI)}) piu' le notifiche.",
            id_richiesta,
        )
    except Exception as errore:
        # Stessa proprieta' di `DispatcherStrumenti.dispatch`: da qui non
        # risale mai un'eccezione, e non esce mai un 500 nudo. Un turno del
        # ponte spezzato da una traccia Python sarebbe indistinguibile, per
        # l'utente, da una risposta che non arriva.
        logger.exception("MCP: «%s» ha sollevato", metodo)
        return _errore(
            -32603,
            f"«{metodo}» ha incontrato un problema interno "
            f"({type(errore).__name__}: {errore}).",
            id_richiesta,
        )
