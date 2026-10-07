import ipaddress
import logging
import os
import re
import time

from aiohttp import web

from ..chat_thread import new_subject
from .admission import admission_refusal, gesture_refusal
from .boundary import error_response

logger = logging.getLogger(__name__)

# Supervisor adds X-Ingress-Path = "/api/hassio_ingress/<token>/..." to every
# proxied request. Validate the pattern so an attacker forwarded through a
# different proxy cannot just attach the header with an arbitrary value.
_INGRESS_PATH_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]+(/.*)?$")



def allow_no_token() -> bool:
    """L'interruttore dello sviluppo, riletto a ogni richiesta (cosi' le prove
    lo cambiano senza dipendere dall'ordine degli import). La sua sola casa:
    lo legge anche `soffitto.denies`."""
    return os.environ.get("HIRIS_ALLOW_NO_TOKEN", "").strip() == "1"


def _supervisor_cidrs(request: web.Request) -> list[str]:
    """Le reti che l'avvio ha calcolato (`ingresso.perimetro_fidato`), e
    nient'altro. **Un elenco vuoto resta vuoto** (S-15, Tappa 7): fino al
    07/10/2026 ripiegava sulla rete Docker intera, proprio nel caso in cui
    l'avvio aveva scritto nel registro «nessuna rete e' fidata». Il valore di
    fabbrica ha una casa sola, `ingresso.RETE_PREDEFINITA`, e vale quando il
    campo e' vuoto, non quando e' sbagliato."""
    return list(request.app.get("supervisor_ingress_cidrs") or [])


async def _is_supervisor_ingress(request: web.Request) -> bool:
    """Se questa richiesta viene DAVVERO dall'ingress del Supervisor.

    **Due controlli, e il secondo e' quello che stringe** (reperto A-2):

    1. `X-Ingress-Path` c'e' e ha la forma del Supervisor -- che chiunque puo'
       scrivere, quindi da solo non dimostra niente;
    2. l'indirizzo sorgente sta nel perimetro che l'avvio ha calcolato
       (`ingresso.perimetro_fidato`): dal 22/09/2026 **l'indirizzo a cui
       risponde il nome «supervisor»**, uno solo. Se il nome non si risolve
       valgono le reti scritte nelle opzioni (o, se il campo e' vuoto,
       `ingresso.RETE_PREDEFINITA`); un elenco vuoto non si fida di nessuno.

    Un add-on vicino puo' falsificare l'intestazione. Col nome risolto non
    puo' presentarsi dall'indirizzo del Supervisor.
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

    # **Qui la 3.60.0 chiedeva al Supervisor di verificare la sessione, e il
    # Supervisor rispondeva 403.** Quella rotta e' riservata a Home Assistant
    # Core: nessun ruolo di add-on la apre. Il risultato e' stato il
    # proprietario chiuso fuori dal proprio pannello -- vedi `api/ingresso.py`,
    # dove la lezione sta scritta per esteso.
    #
    # A stringere e' adesso l'INDIRIZZO: vedi il docstring qui sopra.
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

#: Le intestazioni con cui il Supervisor dice CHI sta chiamando. Verificato il
#: 21/09/2026 sul sorgente (`supervisor/api/ingress.py::_init_header`): le
#: compone da `session_data.user` e **filtra via le stesse in ingresso** prima
#: di aggiungere le proprie, quindi attraverso l'ingress non sono falsificabili.
#: Su ogni altra strada lo sono, ed e' il motivo per cui si leggono in un ramo
#: solo.
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
        return new_subject(specie)
    return new_subject("persona", ident=request.headers.get(_CHI),
                       nome=(request.headers.get(_NOME)
                             or request.headers.get(_UTENTE)),
                       utente=request.headers.get(_UTENTE))


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
        request["soggetto"] = new_subject("nessuno")
        return await handler(request)

    firmato, motivo = await _firmatario(request)
    if motivo is not None:
        logger.warning("servizio: richiesta rifiutata da %s — %s",
                       request.remote, motivo)
        return error_response(401, motivo)
    if firmato is not None:
        # **Il gesto della rotta, come per una persona** (F-17, D4 della
        # Tappa 7): fino al 07/10/2026 un servizio passava da un controllo
        # suo, che guardava solo lettura contro scrittura, e un servizio
        # `utente` scriveva la configurazione dei modelli. Il soggetto e'
        # quello che la firma ha riconosciuto (`canali.riconosci`), col ruolo
        # dell'approvazione.
        request["auth_via"] = "canale"
        request["soggetto"] = firmato
        refusal = gesture_refusal(request)
        if refusal is not None:
            return refusal
        return await handler(request)

    if await _is_supervisor_ingress(request):
        request["auth_via"] = "ingress"
        request["soggetto"] = _soggetto(request, "persona")
        # **Il cancello al confine** (spec 2026-09-27 §3): una persona passa
        # solo se amministra, o se la lista la ammette e l'opzione e' accesa.
        # Qui e non nel gestore perche' il ruolo si legge SOLO per chi arriva
        # dall'ingress, e prima di qualunque archivio.
        refusal = await admission_refusal(request.app, request)
        if refusal is not None:
            return refusal
        return await handler(request)

    # **La credenziale EFFIMERA del ponte** (spec §5, ingresso 7).
    #
    # Il ponte non e' una persona e non e' un'integrazione registrata: e' HIRIS
    # che lavora per conto suo, per il tempo di un turno. Da cui `specie:
    # nessuno`, che e' cio' che la cronaca deve scrivere.
    from .credenziali import RUOLO_TURNO, riconosci

    turno = riconosci(request.app.get("credenziali") or {},
                      request.headers.get("X-HIRIS-Internal-Token"),
                      adesso=time.time())
    if turno is not None:
        request["auth_via"] = "turno"
        request["soggetto"] = new_subject("nessuno", ident=turno["mestiere"],
                                          nome=turno["mestiere"], ruolo=RUOLO_TURNO)
        refusal = gesture_refusal(request)
        if refusal is not None:
            return refusal
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
    if allow_no_token():
        logger.critical(
            "SECURITY: HIRIS_ALLOW_NO_TOKEN=1 is set — authentication is DISABLED")
        request["auth_via"] = "no_token"
        request["soggetto"] = _soggetto(request, "sviluppo")
        # Lo stesso cancello di tutti: con l'interruttore acceso lo sviluppo
        # non si restringe per ruolo (`soffitto.denies`), quindi qui passa --
        # ma passa dalla stessa domanda, non da una strada che non la fa.
        refusal = gesture_refusal(request)
        if refusal is not None:
            return refusal
        return await handler(request)

    logger.warning(
        "rifiutata una richiesta non autenticata da %s su %s %s%s",
        request.remote, request.method, request.path,
        " — portava un segreto condiviso, che dal 22/09/2026 non apre più niente"
        if request.headers.get("X-HIRIS-Internal-Token") else "")
    return error_response(401, _ISTRUZIONI)
