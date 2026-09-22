import ipaddress
import logging
import os
import re
import time

from aiohttp import web

logger = logging.getLogger(__name__)

# Supervisor adds X-Ingress-Path = "/api/hassio_ingress/<token>/..." to every
# proxied request. Validate the pattern so an attacker forwarded through a
# different proxy cannot just attach the header with an arbitrary value.
_INGRESS_PATH_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]+(/.*)?$")

# Default HA Supervisor Docker network. The ingress proxy always reaches the
# add-on from inside this range; a direct LAN/tunnel client never does.
_DEFAULT_SUPERVISOR_CIDRS = ["172.30.32.0/23"]


def _allow_no_token() -> bool:
    """Re-read env var at each request so tests can patch it without import-order issues."""
    return os.environ.get("HIRIS_ALLOW_NO_TOKEN", "").strip() == "1"


def _supervisor_cidrs(request: web.Request) -> list[str]:
    cidrs = request.app.get("supervisor_ingress_cidrs")
    return cidrs if cidrs else _DEFAULT_SUPERVISOR_CIDRS


async def _is_supervisor_ingress(request: web.Request) -> bool:
    """Se questa richiesta viene DAVVERO dall'ingress del Supervisor.

    **Tre controlli, e il terzo e' l'unico che dimostra qualcosa** (reperto A-2,
    chiuso il 22/09/2026):

    1. `X-Ingress-Path` c'e' e ha la forma del Supervisor;
    2. l'indirizzo sorgente sta in una rete fidata;
    3. **il Supervisor riconosce il biscotto di sessione.**

    I primi due sembrano stretti e non lo sono: l'intestazione la scrive
    chiunque, e la rete predefinita non e' l'indirizzo del proxy -- e' la rete
    Docker in cui vive **ogni add-on installato**. Se il tunnel che pubblica la
    casa gira come add-on (il caso normale), il suo indirizzo e' li' dentro, e
    fino a oggi gli bastava scrivere un'intestazione per avere `/api/*` intero.

    Il terzo chiude quel buco: un add-on vicino puo' falsificare l'intestazione
    e puo' stare nella rete, ma non puo' avere un biscotto che il Supervisor
    riconosce senza averlo rubato a una persona.

    I primi due restano perche' costano zero e fermano prima cio' che non deve
    nemmeno arrivare a una chiamata di rete.
    """
    ingress_path = request.headers.get("X-Ingress-Path", "")
    if not ingress_path or not _INGRESS_PATH_RE.match(ingress_path):
        return False
    remote = request.remote
    if not remote:
        return False
    try:
        remote_ip = ipaddress.ip_address(remote)
    except (ValueError, TypeError):
        return False
    dentro = False
    for cidr in _supervisor_cidrs(request):
        try:
            if remote_ip in ipaddress.ip_network(cidr, strict=False):
                dentro = True
                break
        except (ValueError, TypeError):
            continue
    if not dentro:
        logger.warning(
            "CR-1: X-Ingress-Path present but source IP %s not in supervisor CIDRs "
            "%s — treating as direct request (internal_token required)",
            remote, _supervisor_cidrs(request),
        )
        return False

    # **Il controllo che dimostra qualcosa.** Vedi il docstring: i due qui sopra
    # non distinguono il proxy da un add-on vicino, questo si'.
    from .ingresso import BISCOTTO, sessione_valida

    if not await sessione_valida(request.app, request.cookies.get(BISCOTTO, "")):
        logger.warning(
            "ingress: %s porta l’intestazione del proxy ma non una sessione "
            "che il Supervisor riconosce — trattata come richiesta diretta",
            remote)
        return False
    return True


#: Le intestazioni con cui un SERVIZIO firma (spec 2026-09-21 §6, rifatta il
#: 22/09). `X-HIRIS-Servizio` porta la sua **chiave pubblica**, che e' la sua
#: identita': un nome sarebbe una seconda rappresentazione dello stesso fatto.
#: Viaggia anche senza firma durante la convivenza, e li' non autentica niente
#: -- serve solo a MISURARE chi non firma ancora.
_SERVIZIO = "X-HIRIS-Servizio"
_MOMENTO = "X-HIRIS-Momento"
_UNICO = "X-HIRIS-Unico"
_FIRMA = "X-HIRIS-Firma"

#: Le intestazioni con cui il Supervisor dice CHI sta chiamando. Verificato il
#: 21/09/2026 sul sorgente (`supervisor/api/ingress.py::_init_header`): le
#: compone da `session_data.user` e **filtra via le stesse in ingresso** prima
#: di aggiungere le proprie, quindi attraverso l'ingress non sono falsificabili.
#: Su ogni altra strada lo sono, ed e' il motivo per cui si leggono in un ramo
#: solo.
#: Il rifiuto di chi non ha nessuna delle tre credenziali. **Dice cosa fare**:
#: un'integrazione non aggiornata trova una porta chiusa, e senza questa frase
#: chi la mantiene passerebbe il pomeriggio a leggere il registro.
_ISTRUZIONI = (
    "non ti riconosco. Un servizio esterno entra firmando le proprie "
    "richieste: fatti accoppiare dal proprietario nella pagina Servizi di "
    "HIRIS — apre una finestra di dieci minuti, tu ti presenti con la tua "
    "chiave pubblica, e lui approva il tuo ruolo confrontando un codice di "
    "quattro cifre. Il segreto condiviso non esiste più dal 22/09/2026."
)

_CHI = "X-Remote-User-Id"
_NOME = "X-Remote-User-Display-Name"
_UTENTE = "X-Remote-User-Name"


def _soggetto(request: web.Request, specie: str) -> dict:
    """Chi sta chiamando — sempre un oggetto, mai `None`.

    **«Non so chi sei» non e' «sei il proprietario».** Un ingress senza identita'
    (i provider di autenticazione non nativi non la portano: l'intestazione non
    e' garantita) da' una PERSONA ANONIMA, non l'assenza di un soggetto: un
    campo mancante e un campo vuoto si confondono al primo lettore distratto,
    due parole diverse no.

    La `specie` c'e' sempre perche' e' il primo fatto che serve a decidere un
    soffitto: una persona di Home Assistant e una macchina che porta un token
    non si autenticano nello stesso modo e non possono valere lo stesso.
    """
    if specie != "persona":
        return {"specie": specie, "id": None, "nome": None, "utente": None}
    return {"specie": "persona",
            "id": request.headers.get(_CHI) or None,
            "nome": (request.headers.get(_NOME)
                     or request.headers.get(_UTENTE) or None),
            "utente": request.headers.get(_UTENTE) or None}


async def _firmatario(request: web.Request):
    """Il servizio che ha firmato questa richiesta — o `None` se non ci prova.

    **Chi prova a firmare e sbaglia non scivola sul ripiego del token**: sarebbe
    una porta aperta da qualunque firma storta, cioe' il contrario di una
    difesa. Per questo la funzione distingue tre esiti e non due: non ci prova
    (`None`), ci prova e regge (il canale), ci prova e non regge (il motivo).
    """
    from . import canali

    # **A dire «sto firmando» e' la FIRMA, non il nome del servizio.** Durante
    # la convivenza (spec §8) chi usa ancora il token dichiara
    # `X-HIRIS-Servizio` per farsi misurare: trattare quella dichiarazione come
    # un tentativo di firma lo rifiuterebbe, cioe' spegnerebbe l'integrazione
    # che stiamo cercando di contare. Misurato scrivendo la prova, non supposto.
    if not request.headers.get(_FIRMA):
        return None, None
    return canali.riconosci(
        chiave=request.headers.get(_SERVIZIO, ""),
        momento=request.headers.get(_MOMENTO, ""),
        unico=request.headers.get(_UNICO, ""),
        firma=request.headers.get(_FIRMA, ""),
        metodo=request.method, percorso=request.path,
        corpo=await request.read(),
        servizi=request.app.get("servizi"),
        visti=request.app.get("canali_visti"),
        adesso=time.time())


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    """Chi sta chiamando, e se puo' entrare — **il confine del prodotto**.

    Dal 22/09/2026 ci sono **tre strade, e ognuna dice chi e'**:

    1. la **firma** di un servizio che il proprietario ha approvato
       (`api/canali.py` piu' `api/servizi.py`);
    2. l'**ingress** del Supervisor, con la sessione che il Supervisor stesso
       riconosce (`api/ingresso.py`);
    3. la **credenziale di turno** del ponte, che vive dieci minuti
       (`api/credenziali.py`).

    Chi non ne ha nessuna non entra, e il rifiuto gli dice cosa fare. Il
    segreto condiviso — uno per tutti i portatori, eterno, in chiaro nei
    backup — e' uscito con la fetta 3 dello sprint sicurezza.

    `HIRIS_ALLOW_NO_TOKEN=1` spegne tutto questo, e lo grida nel registro: e'
    per lo sviluppo locale, e in produzione e' un guasto.
    """
    # **L'unica superficie che questo prodotto non puo' autenticare**, e
    # esiste solo nei dieci minuti in cui il proprietario ha aperto
    # l'accoppiamento (decisione del 22/09/2026). Un servizio che non e' ancora
    # approvato NON HA MODO di autenticarsi -- e' tutto il punto -- e invece di
    # difendere quella rotta per sempre si e' scelto di non farla esistere:
    # fuori dalla finestra risponde 401 come qualunque altra.
    #
    # Una difesa permanente invecchia; una porta chiusa no.
    from .handlers_servizi import ROTTA_APERTA
    from .servizi import finestra_aperta

    if (request.path == ROTTA_APERTA
            and finestra_aperta(request.app.get("finestra_servizi"),
                                adesso=time.time())):
        request["auth_via"] = "accoppiamento"
        request["soggetto"] = {"specie": "nessuno", "id": None, "nome": None,
                               "utente": None, "ruolo": None}
        return await handler(request)

    from .canali import consente_metodo

    firmato, motivo = await _firmatario(request)
    if motivo is not None:
        logger.warning("servizio: richiesta rifiutata da %s — %s",
                       request.remote, motivo)
        return web.json_response({"errore": motivo}, status=401)
    if firmato is not None:
        if not consente_metodo(firmato["ruolo"], request.method):
            logger.warning(
                "servizio: «%s» ha ruolo «%s» e ha chiesto %s %s — negato",
                firmato["servizio"], firmato["ruolo"], request.method,
                request.path)
            return web.json_response(
                {"errore": f"il servizio «{firmato['servizio']}» ha il ruolo "
                           f"«{firmato['ruolo']}»: legge e non scrive"},
                status=403)
        request["auth_via"] = "canale"
        request["soggetto"] = {"specie": firmato["specie"],
                               "id": firmato["servizio"],
                               "nome": firmato["servizio"],
                               "utente": None,
                               "ruolo": firmato["ruolo"]}
        return await handler(request)

    if await _is_supervisor_ingress(request):
        request["auth_via"] = "ingress"
        request["soggetto"] = _soggetto(request, "persona")
        return await handler(request)

    # **La credenziale EFFIMERA del ponte** (spec §5, ingresso 7), e si guarda
    # PRIMA del segreto condiviso per la stessa ragione per cui la firma si
    # guarda prima di entrambi: finche' il segreto lungo vince, chi ce l'ha non
    # ha nessun motivo di passare a una credenziale che scade, e il ripiego non
    # finisce mai.
    #
    # Il ponte non e' una persona e non e' un'integrazione registrata: e' HIRIS
    # che lavora per conto suo, per il tempo di un turno. Da cui `specie:
    # nessuno`, che e' cio' che la cronaca deve scrivere.
    from .credenziali import riconosci

    turno = riconosci(request.app.get("credenziali") or {},
                      request.headers.get("X-HIRIS-Internal-Token"),
                      adesso=time.time())
    if turno is not None:
        request["auth_via"] = "turno"
        request["soggetto"] = {"specie": "nessuno", "id": turno["mestiere"],
                               "nome": turno["mestiere"], "utente": None,
                               "ruolo": None}
        return await handler(request)

    # **Qui finiva la convivenza col segreto condiviso, e il 22/09/2026 e'
    # finita davvero** (reperto A-5, fetta 3 dello sprint sicurezza).
    #
    # Per una fetta HIRIS ha accettato «la firma oppure il token», perche' il
    # gateway MCP e il proxy di Retro Panel vivevano in due repository separati
    # e un taglio netto li avrebbe spenti. La fine la doveva decidere una
    # MISURA, non una data -- ed e' quello che e' successo: il registro
    # dell'add-on ha smesso di nominare chiunque non fosse la porta di
    # sviluppo, che adesso firma.
    #
    # Un segreto condiviso non e' un'identita': e' una parola d'ordine. Uno per
    # tutti i portatori, in chiaro nei backup di Home Assistant, e chi lo legge
    # una volta e' tutti per sempre; compromessa una strada, l'unica mossa era
    # cambiarlo e romperle tutte insieme. Adesso ogni portatore ha la propria
    # credenziale e il registro puo' dire QUALE ha chiamato.
    #
    # Restano tre strade, e ognuna dice chi e': la FIRMA di un servizio
    # approvato, l'INGRESS con la sessione che il Supervisor riconosce, la
    # CREDENZIALE DI TURNO del ponte.
    if _allow_no_token():
        logger.critical(
            "SECURITY: HIRIS_ALLOW_NO_TOKEN=1 is set — authentication is DISABLED")
        request["auth_via"] = "no_token"
        request["soggetto"] = _soggetto(request, "sviluppo")
        return await handler(request)

    logger.warning(
        "rifiutata una richiesta non autenticata da %s su %s %s%s",
        request.remote, request.method, request.path,
        " — portava un segreto condiviso, che dal 22/09/2026 non apre più niente"
        if request.headers.get("X-HIRIS-Internal-Token") else "")
    return web.json_response({"errore": _ISTRUZIONI}, status=401)
