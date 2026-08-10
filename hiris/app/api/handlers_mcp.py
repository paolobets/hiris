"""`POST /api/mcp` -- l'adattatore JSON-RPC che porta i quattro strumenti al ponte.

**Perche' esiste.** HIRIS ha due percorsi di chat. Il turno sincrono passa i
quattro strumenti (`STRUMENTI_CONOSCENZA`) direttamente al runner, che li
dispaccia con `DispatcherConoscenza`. Il ponte via abbonamento invece invoca la
CLI `claude` come sottoprocesso, e **l'unico modo in cui quella CLI accetta
strumenti nostri e' MCP**: senza questa rotta il ponte risponde su una
fotografia (il nucleo composto all'accodamento) e non puo' ne' cercare, ne'
guardare, ne' ricordare, ne' richiamare.

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
`costruisci_dispatcher_conoscenza(app)`, la stessa funzione del turno sincrono.
Non e' un canale di azione: gli strumenti restano quattro e nessuno tocca Home
Assistant -- HIRIS conosce e non agisce.

**Nessuno la chiama ancora.** Il chiamante di produzione -- l'argv del ponte con
`--mcp-config` -- nasce al Task 3 della stessa fetta. Fino ad allora la rotta e'
un **orfano dichiarato** (`scripts/censimento.py` la conta fra le «rotte HTTP
chiamate solo dai test»), non un orfano nascosto.
"""
from __future__ import annotations

import json
import logging

from aiohttp import web

from ..casa.strumenti import STRUMENTI_CONOSCENZA
from ..version import read_version
from .handlers_chat import costruisci_dispatcher_conoscenza

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

    # Il nome accettato e' quello nudo (`cerca`, ...): il prefisso
    # `mcp__hiris__` lo mette la CLI dal lato modello, non arriva nel
    # protocollo. Se un giorno arrivasse, il dispatcher lo direbbe con un
    # `errore` leggibile invece di sollevare -- non c'e' niente da sbucciare
    # qui a indovinare.
    dispatcher = costruisci_dispatcher_conoscenza(request.app)
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
        logger.info("MCP tools/call «%s» ha dichiarato un errore: %s",
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
        # Stessa proprieta' di `DispatcherConoscenza.dispatch`: da qui non
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
