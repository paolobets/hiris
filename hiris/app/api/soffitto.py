"""Il soffitto: quanto si concede a chi chiede (spec 2026-09-21, §2 e §4).

**Il principio, del proprietario**: *HIRIS non concede mai piu' di quanto il
chiamante gia' puo' in Home Assistant.* Ne' piu' ne' meno.

**Meno sarebbe teatro.** Un utente non amministratore comanda gia' le sue entita'
dalla plancia; impedirglielo dentro HIRIS non toglie un potere a nessuno,
aggiunge una frustrazione e una falsa sensazione di sicurezza.

**Piu' e' quello che HIRIS faceva.** Verificato sul sorgente di Home Assistant:
il Supervisor proxa verso il nucleo con la propria sessione privilegiata, e
`websocket_api/connection.py::context` costruisce il contesto dall'utente
autenticato **ignorando il messaggio** -- nessuna delega, nessuna impersonazione
possibile. Quindi HIRIS parla con HA da amministratore qualunque sia la persona
che ha scritto in chat: non restringeva, **amplificava**.

**Dove sta la differenza, misurata e non supposta.** Non nei servizi:
`action/verification.py` dichiara che quelli di sistema (`homeassistant.restart`,
`hassio.host_reboot`, `recorder.purge`, `shell_command.*`) sono gia'
irraggiungibili dalla porta, perche' non dichiarano un bersaglio e un bersaglio
vuoto e' sempre un rifiuto. L'amplificazione vera e' **una porta sola**: la
configurazione. Un non amministratore, via HIRIS, puo' far scrivere automazioni
in casa -- e Home Assistant glielo nega (`helpers/service.py`: `if not
user.is_admin: if admin_only: raise Unauthorized`).

**La forma, dopo la decisione del 21/09 sui canali.** Il ruolo non si deduce da
dove arriva una richiesta: **viaggia con la credenziale**. Per una persona lo
dice Home Assistant, per un servizio lo dice l'approvazione, per un turno senza
soggetto lo dice il suo mestiere. Quattro sorgenti, **una funzione sola** che
decide.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import NamedTuple

from aiohttp import web

from ..chat_thread import subject_key_for
from ..proxy._sanitize import sanitize_ha_value
from .boundary import error_response
from .canali import PUO, RUOLI
from .servizi import SPECIE as SERVICE_SPECIES

logger = logging.getLogger(__name__)

#: Per quanto si tiene buona la risposta di Home Assistant su chi e'
#: amministratore. Una lettura per ogni richiesta metterebbe il pannello alla
#: merce' della latenza di HA su un percorso che gira a ogni clic; nessuna
#: scadenza vorrebbe dire che un utente promosso o degradato aspetta il riavvio
#: dell'add-on. Un minuto e' il compromesso, ed e' dichiarato invece che dedotto.
RUOLI_VALIDI_S = 60.0

#: I gesti su cui questo modulo si pronuncia. Insieme CHIUSO: un gesto che non
#: c'e' non e' «permesso», e' un gesto su cui nessuno ha deciso -- e la prova
#: `test_ogni_esito_risponde_a_TUTTI_i_gesti` lo trasforma in un rosso invece
#: che in un silenzio. `amministrare` (spec 2026-09-27, ruling R-2.25 e fix
#: round 1) e' toccare cio' che Home Assistant riserva ai soli
#: amministratori: le letture `@websocket_api.require_admin` (registro di
#: sistema, tracce, corpo delle automazioni) e i servizi registrati con
#: `async_register_admin_service` (`homeassistant.restart` e fratelli).
GESTI = ("leggere", "comandare", "costruire", "amministrare")

#: Quanto il cancello al confine tiene per buono un guasto nella lettura dei
#: ruoli (spec 2026-09-27, ruling R-2.8/2.9). Il cancello gira su ogni
#: richiesta dell'ingress, asset compresi: senza questo freno un Home
#: Assistant che non risponde riceverebbe un `config/auth/list` per ogni file
#: della pagina. Cinque secondi: il guasto chiude comunque, e passati quelli si
#: riprova alla richiesta dopo. Dichiarato, non misurato.
GATE_FAILURE_HOLD_S = 5.0

#: Cosa vale una persona di cui non si e' potuto leggere il ruolo.
#:
#: **`lettore`, dal 27/09/2026** (fix round 1 del Task 2, ruling L-4). Prima
#: valeva `utente`, sul presupposto che chi e' passato dall'ingress comandi
#: gia' dalla plancia: non e' vero per tutti -- un utente di sola lettura, o
#: senza gruppi, in Home Assistant non comanda niente -- e un guasto nella
#: lettura non deve dargli piu' di quanto ha. Un ingress non arriva qui (il
#: cancello al confine lo chiude prima): ci arriva un turno servito dal ponte,
#: che il ruolo lo rilegge al momento dello strumento.
_PERSONA_IGNOTA = "lettore"

_TEATRO = ("comandare le entità è ciò che Home Assistant concede già dalla "
           "plancia: vietarlo qui non toglierebbe nessun potere a nessuno")
_SOLO_AMMINISTRATORI = ("scrivere automazioni, script o scene in Home Assistant "
                        "è riservato agli amministratori: è la stessa cosa che "
                        "Home Assistant rifiuterebbe a questa utenza")
#: Il `perche` di chi ha il ruolo di sola lettura: una persona del gruppo
#: `system-read-only` di Home Assistant, o un servizio approvato come
#: `lettore`. Il testo di `_TEATRO` qui sarebbe falso: a lei Home Assistant il
#: comando lo nega davvero.
_READ_ONLY = ("questa utenza ha il ruolo di sola lettura: legge, ma non "
                 "comanda la casa e non costruisce, come Home Assistant non "
                 "le concede di fare")
#: Il rifiuto degli strumenti che leggono cio' che Home Assistant riserva agli
#: amministratori (il gesto `amministrare`).
ADMIN_READS_REFUSAL = ("il registro di sistema e le tracce delle automazioni "
                       "Home Assistant li mostra solo agli amministratori: "
                       "HIRIS non li legge per chi non lo è")
#: Il rifiuto dei servizi di Home Assistant riservati agli amministratori.
ADMIN_SERVICES_REFUSAL = ("questo servizio di Home Assistant è riservato agli "
                          "amministratori (riavviare, fermare, ricaricare la "
                          "configurazione): HIRIS non lo chiama per chi non lo "
                          "è")
_IGNOTO = ("non ho potuto sapere che ruolo ha questa utenza in Home "
           "Assistant, e finché non lo so leggo soltanto: un guasto nella "
           "lettura non deve diventare un permesso in più")
#: **Corretto il 22/09/2026 leggendolo dal vivo.** Diceva «si decide quando la
#: si registra», e la registrazione non esiste piu': un rifiuto che manda a
#: compiere un gesto che il prodotto non ha e' peggio di un rifiuto muto --
#: manda a cercare. Adesso nomina il gesto vero, e dove si compie.
_MACCHINA_MUTA = ("questa richiesta arriva da un servizio senza un ruolo "
                  "dichiarato: il perimetro di un’integrazione si decide "
                  "quando il proprietario la approva, nella pagina Servizi, "
                  "e non si eredita")


def consente(soggetto: dict | None, *, ruolo: str | None) -> dict:
    """Cosa può fare questo soggetto — un esito per ogni gesto di `GESTI`.

    Il ruolo arriva già risolto: da Home Assistant per una persona, dalla
    l'approvazione per un servizio. Qui si decide soltanto, e si decide una volta.

    **Il verso del dubbio è diverso per le due specie**: una persona senza
    ruolo leggibile vale `lettore` (legge, e basta); una macchina senza ruolo
    **non ha superato niente**, e non può niente.
    """
    specie = (soggetto or {}).get("specie") or "persona"
    persona = specie == "persona"

    if ruolo in RUOLI:
        puo = PUO[ruolo]
        if puo["costruire"]:
            perche = None
        elif puo["comandare"]:
            perche = f"{_SOLO_AMMINISTRATORI}. {_TEATRO}."
        else:
            perche = f"{_READ_ONLY}."
        return {**puo, "ruolo": ruolo, "perche": perche}

    if persona:
        puo = PUO[_PERSONA_IGNOTA]
        return {**puo, "ruolo": _PERSONA_IGNOTA, "perche": f"{_IGNOTO}."}

    return {**{gesto: False for gesto in GESTI},
            "ruolo": None, "perche": _MACCHINA_MUTA}


def ruolo_letto(soffitto: dict) -> bool:
    """Il `ruolo` di questo soffitto viene da una lettura vera, o e' il
    ripiego per una persona di cui non si e' potuto sapere se e'
    amministratore?

    Serve a chi deve DIRLO a qualcuno (fix round 1, Task 5, Important 3: la
    sezione "Chi ti sta parlando" del contesto della chat), non solo a
    deciderlo -- `consente()` sopra restituisce `_PERSONA_IGNOTA` ("lettore",
    dal fix round 1 del Task 2 della spec 2026-09-27) ANCHE quando il ruolo
    e' stato letto davvero da Home Assistant e la persona e' del gruppo di
    sola lettura: la stessa stringa copre due fatti diversi, e solo
    `perche'` li distingue (contiene `_IGNOTO` solo nel ramo di ripiego).
    Non si ridichiara qui il testo di `_IGNOTO` -- lo si CONFRONTA con
    quello vero, o i due potrebbero divergere."""
    return _IGNOTO not in (soffitto.get("perche") or "")


async def _person_row(app, soggetto: dict | None) -> dict | None:
    """La riga di questa utenza fra gli utenti di Home Assistant — o `None`.

    Una lettura sola per tre domande: il ruolo (`_ruolo_persona`), se è il
    proprietario (`is_owner`, fetta «le chat divise») e come si chiama
    (`subject_name`, fetta «il seguito delle chat divise»). Letture
    separate sarebbero cache che scadono in momenti diversi.
    """
    identificatore = (soggetto or {}).get("id")
    if not identificatore:
        return None
    return (await _ha_users(app) or {}).get(identificatore)


async def _ha_users(app, *, hold_failure_s: float = 0.0) -> dict | None:
    """Gli utenti di Home Assistant per id, riletti se la copia e' scaduta --
    o `None` se non si possono sapere.

    La risposta si tiene per `RUOLI_VALIDI_S`. **Un guasto non si mette in
    cache**: se la lettura fallisce si riprova alla richiesta dopo, altrimenti
    un singolo momento storto di Home Assistant chiuderebbe la costruzione per
    un minuto intero. L'eccezione e' `hold_failure_s`, che passa solo il
    cancello al confine (`GATE_FAILURE_HOLD_S`): per quei secondi un guasto
    appena visto vale ancora, senza richiamare Home Assistant.

    **E' anche chi la RIEMPIE**: la copia nasce vuota (`prepara_ruoli`) e
    nessuno la carica all'avvio. Chi legge un nome senza passare di qui
    leggerebbe il vuoto ogni volta che nessun ruolo di persona e' stato
    chiesto nell'ultimo minuto -- un servizio amministratore che apre le
    Costruzioni, per esempio.
    """
    client = app.get("ha_client")
    visti = app.get("ruoli")
    if client is None or visti is None:
        return None

    if time.time() - visti["quando"] >= RUOLI_VALIDI_S:
        if time.time() - visti.get("fallito", float("-inf")) < hold_failure_s:
            return None
        # **Una lettura in volo alla volta** (fix round 1, I2): una pagina che
        # si apre chiede i suoi file tutti insieme, e ogni richiesta passa dal
        # cancello. Senza questo, a copia scaduta, partirebbero tante
        # `config/auth/list` quanti file: chi arriva mentre una e' in volo
        # aspetta quella.
        in_flight = visti.get("in_volo")
        if in_flight is None:
            in_flight = asyncio.ensure_future(_refresh_users(client, visti))
            visti["in_volo"] = in_flight
            in_flight.add_done_callback(lambda _done: visti.pop("in_volo", None))
        return await asyncio.shield(in_flight)
    return visti["per_id"]


async def _refresh_users(client, visti: dict) -> dict | None:
    """La lettura vera di `config/auth/list`, e cio' che se ne tiene: la
    copia se riesce, l'ora del guasto e la sua riga d'errore se no.

    **Anche un'eccezione e' un guasto** (review finale, punto 3): oggi
    `HAClient` la trasforma gia' in `{"errore"}`, ma il cancello non deve
    dipendere da come e' scritto un altro modulo. Senza, salirebbe fino ad
    aiohttp come 500: niente attesa, niente testo dei ruoli illeggibili,
    niente riga nel registro."""
    try:
        esito = await client.users()
    except Exception as exc:
        esito = {"errore": type(exc).__name__}
    if "errore" in esito:
        visti["fallito"] = time.time()
        # `error` e non `warning`, e con le CONSEGUENZE scritte: finché
        # questa lettura non riesce NESSUNO può costruire — nemmeno il
        # proprietario — e la cronologia della chat di prima delle chat
        # divise resta orfana (`is_owner` non sa chi è il proprietario),
        # una promessa di prima che si sveglia si chiude senza agire
        # (`sole_owner`), i nomi delle persone non si leggono
        # (`subject_name`), e nessuna persona entra dall'ingress --
        # proprietario compreso -- perche' il cancello al confine non sa
        # chi amministra (`admission.py`). Chi
        # aggiunge un lettore aggiunge qui la sua conseguenza. È il verso
        # giusto, ma è anche il guasto che spegne una funzione, e chi
        # legge il registro deve capirlo alla prima riga invece di
        # inseguire un 403 che non si spiega.
        #
        # **Il guasto non si mette in cache, la sua riga si'** (fix round
        # 1 del Task 4): ogni `GET /api/pending` rilegge, e durante un
        # guasto di HA ogni clic scriverebbe questa riga. Una volta ogni
        # `RUOLI_VALIDI_S` basta a dire che il guasto dura.
        adesso = time.time()
        if adesso - visti.get("guasto_detto", 0.0) < RUOLI_VALIDI_S:
            return None
        visti["guasto_detto"] = adesso
        logger.error(
            "soffitto: non ho potuto leggere gli utenti da Home Assistant "
            "(%s). Finché non ci riesco nessuna persona entra in HIRIS "
            "dal pannello, e NESSUNO può far scrivere "
            "automazioni a HIRIS, perché non so chi è amministratore, e la "
            "cronologia della chat e le promesse di prima restano orfane, "
            "perché non so chi è il proprietario: il comando è "
            "`config/auth/list` sul canale "
            "websocket",
            esito["errore"])
        return None
    # Si MUTA il contenitore, non si riscrive `app[...]`: scrivere in `app`
    # a richiesta già servita fa emettere ad aiohttp «Changing state of
    # started or joined application is deprecated» — oggi un avviso, con
    # aiohttp 4 un errore.
    visti["per_id"] = {u["id"]: u for u in esito["utenti"] if u.get("id")}
    visti["quando"] = time.time()
    return visti["per_id"]


def _role_of(row: dict | None) -> str | None:
    """**La regola del ruolo di una persona**, una sola: dalla riga di
    `ha_client.users()` al vocabolario di `canali.RUOLI`. Chi e' amministratore
    e chi e' di sola lettura lo dice `users()`, che legge i gruppi di Home
    Assistant; qui si traduce e basta.

    **Senza gruppi, nessun ruolo** (fix round 1, I5): verificato il 27/09/2026
    su Core 2026.9.3, un utente che non e' il proprietario e non ha gruppi ha
    `merge_policies([])` -- nessun permesso su nessuna entita'. Non e'
    `utente`, e non e' nemmeno `lettore`: per Home Assistant non puo' niente.
    """
    if row is None:
        return None
    if row.get("amministratore"):
        return "amministratore"
    if row.get("senza_gruppi"):
        return None
    return "lettore" if row.get("sola_lettura") else "utente"


async def _ruolo_persona(app, soggetto: dict | None) -> str | None:
    """Il ruolo di questa utenza in Home Assistant — o `None`.

    `None` non è «utente»: è «non l'ho potuto sapere». I due casi si separano
    qui perché a valle si comportano allo stesso modo ma vanno detti in modo
    diverso a chi legge il rifiuto.
    """
    return _role_of(await _person_row(app, soggetto))


class BoundaryRole(NamedTuple):
    """Cio' che il cancello al confine sa di una persona dall'ingress.

    `role`: il ruolo di `_role_of`, o `None`. I tre «non lo so» si separano
    perche' si dicono in tre modi diversi: `read` falso -- Home Assistant non
    ha risposto; `known` falso -- ha risposto, e questa persona non c'e' o non
    ha un id; tutti e due veri e `role` `None` -- c'e', ma senza gruppi.
    """
    role: str | None
    read: bool
    known: bool


async def boundary_role(app, subject: dict | None) -> BoundaryRole:
    """Il ruolo di una persona arrivata dall'ingress, per il cancello al
    confine (spec 2026-09-27 §3). La regola e' quella di `_role_of`, la
    stessa del soffitto; la sola differenza e' il freno sul guasto,
    `GATE_FAILURE_HOLD_S`."""
    users = await _ha_users(app, hold_failure_s=GATE_FAILURE_HOLD_S)
    if users is None:
        return BoundaryRole(None, False, False)
    user_id = (subject or {}).get("id")
    row = users.get(user_id) if user_id else None
    return BoundaryRole(_role_of(row), True, row is not None)


def denies(ceiling: dict | None, gesture: str, subject: dict | None) -> bool:
    """Questo soffitto nega questo gesto? La domanda degli strumenti del
    turno (`tools._ceiling_denies`) e di `can_configure` nei pallini.

    **Non e' l'unica** (review finale, punto 5): il cancello di chi
    costruisce (`require_builder`), quello dei servizi
    (`handlers_servizi._solo_amministratori`) e `can_build` leggono
    `ceiling["costruire"]` nudo. Misurato il 27/09/2026 su ogni specie per
    ogni ruolo, interruttore acceso e spento: una differenza sola, lo
    sviluppo con l'interruttore acceso -- per loro non costruisce, per questa
    funzione si'. La pinna `test_chi_costruisce.py::
    test_il_cancello_decide_per_ogni_ingresso`; unirle cambierebbe lo
    sviluppo, e la scelta sta in `docs/BACKLOG.md`.

    `None` (nessuna persona ha aperto il turno: l'osservatore, lo
    schedulatore) non nega niente -- il perimetro delle macchine e'
    l'invariante dei canali esterni. **Lo sviluppo non si restringe per
    ruolo** (fix round 1, I3): con `HIRIS_ALLOW_NO_TOKEN` l'autenticazione e'
    spenta per definizione, e restringerlo darebbe solo un prodotto diverso da
    provare.

    **A decidere e' l'interruttore dello sviluppo, non la specie** (fix round
    2): un soggetto `sviluppo` e' nato quando l'interruttore era acceso, ma
    una promessa nata allora si puo' svegliare in produzione -- e li' non
    deve leggere cio' che Home Assistant riserva agli amministratori. Le due
    condizioni insieme: l'interruttore da solo aprirebbe anche le persone e i
    servizi che passano di li'.
    """
    from .middleware_internal_auth import allow_no_token

    if ceiling is None:
        return False
    if allow_no_token() and (subject or {}).get("specie") == "sviluppo":
        return False
    return not ceiling.get(gesture)


async def is_owner(app, soggetto: dict | None) -> bool:
    """Home Assistant dice che questa persona è il proprietario?

    `False` anche quando non lo si è potuto sapere: chi la usa
    (`chat_thread.adopt_if_owner`) fa un gesto che non si ripara -- dare la
    cronologia di prima a qualcuno -- e nel dubbio non lo fa. Ci riprova la
    richiesta dopo.
    """
    return bool((await _person_row(app, soggetto) or {}).get("proprietario"))


async def sole_owner(app) -> dict | None:
    """Il soggetto (`{"specie", "id"}`) del proprietario della casa, se Home
    Assistant ne dice UNO e uno solo -- altrimenti `None`.

    Lo usa l'orologio quando si sveglia una promessa di prima delle promesse
    divise e il proprietario non ha ancora aperto il pannello (review finale
    della fetta «il seguito delle chat divise», ruling del coordinatore).
    Stessa lettura e stesso campo di `is_owner`. Nessuna risposta, nessun
    proprietario o due: «non lo so», e l'adozione -- che non si ripara --
    non si fa.
    """
    owners = [uid for uid, row in (await _ha_users(app) or {}).items()
              if row.get("proprietario")]
    return {"specie": "persona", "id": owners[0]} if len(owners) == 1 else None


async def ceiling_for(app, soggetto: dict | None) -> dict:
    """Il soffitto di questo soggetto.

    Si calcola da un soggetto e non da una richiesta (fetta «le chat divise»):
    un turno di chat servito dal ponte arriva su `/api/mcp` con la credenziale
    del ponte, e chi ha scritto il messaggio viaggia nel job, non nella
    richiesta. Una regola sola per entrambi i casi, `consente`: qui il ruolo
    di una persona si legge da Home Assistant, per una richiesta l'ha gia'
    letto il cancello al confine e `request_ceiling` lo prende da li'.

    Il ruolo arriva da Home Assistant se è una persona, e **viaggia già col
    soggetto** se è un servizio, perché gliel'ha dato l'approvazione.
    """
    soggetto = soggetto or {}
    if soggetto.get("specie") == "persona":
        return consente(soggetto, ruolo=await _ruolo_persona(app, soggetto))
    return consente(soggetto, ruolo=soggetto.get("ruolo"))


#: Il `perche` di un'azione a scadenza che non parte perche' non si e' potuto
#: sapere chi l'aveva chiesta (una persona senza id, sparita dagli utenti di
#: Home Assistant, o Home Assistant che non risponde).
WAKE_UNVERIFIED_PERSON = ("non ho potuto verificare in Home Assistant chi aveva "
                          "chiesto questa azione: a scadenza, nel dubbio, non "
                          "si comanda")


def _approved_service_role(app, subject: dict) -> str | None:
    """Il ruolo del servizio approvato che porta questo nome, letto adesso
    dall'archivio dei servizi -- o `None` se non si puo' sapere con certezza.

    Il soggetto ricostruito da un filo (`chat_thread.subject_from_thread`)
    porta specie e id -- per un servizio l'id e' il nome con cui e' stato
    approvato (`middleware_internal_auth`) -- ma non il ruolo, che viaggiava
    con la firma. Si rilegge dall'archivio, e nel dubbio si chiude: un
    servizio revocato, sconosciuto o con due approvazioni di ruolo diverso
    sotto lo stesso nome non ha un ruolo che si possa dedurre.
    """
    roles = {row.get("ruolo") for row in _service_rows(subject, approved_services(app))}
    return roles.pop() if len(roles) == 1 else None


def approved_services(app) -> list[dict]:
    """Le righe dei servizi APPROVATI, lette una volta -- vuoto se
    l'archivio non c'e' o non si legge.

    Chi deve nominare molti soggetti in una risposta (l'elenco delle
    Costruzioni) la legge una volta e la passa a `subject_name`, invece di
    rileggere l'archivio per ogni riga."""
    services = app.get("servizi")
    if services is None:
        return []
    try:
        rows = services.elenco()
    except Exception as exc:
        logger.warning("soffitto: archivio dei servizi non leggibile (%s)",
                       type(exc).__name__)
        return []
    return [row for row in rows if row.get("stato") == "autorizzato"]


def _service_rows(subject: dict, approved: list[dict]) -> list[dict]:
    """Le righe approvate che portano il nome e la specie di questo soggetto:
    una ricerca sola per il ruolo al risveglio (`_approved_service_role`) e
    il nome sulla pagina (`subject_name`)."""
    return [row for row in approved
            if row.get("nome") == subject.get("id")
            and (row.get("specie") or "integrazione") == subject.get("specie")]


#: Le specie che hanno un nome da qualche parte: una persona fra gli utenti
#: di Home Assistant, un servizio nel suo archivio. `nessuno` (il ponte, un
#: turno interno) e `sviluppo` non ne hanno: il loro «nome» al confine e' il
#: mestiere, non qualcuno da mostrare.
_NAMED_SPECIES = ("persona", *SERVICE_SPECIES)


async def subject_name(app, subject: dict | None, *,
                       approved: list[dict] | None = None) -> str | None:
    """Il nome leggibile di un soggetto -- **la casa di questo fatto** (fix
    round 1 del Task 4): chi ha chiesto una proposta (`chiesta_da`) e chi ha
    scritto un giudizio si nominano qui, allo stesso modo.

    Si legge da chi lo SA: per una persona gli utenti di Home Assistant, per
    un servizio l'archivio -- dove il nome e' lo stesso id con cui e' stato
    approvato, e la lettura aggiunge che e' **ancora** approvato. Se non c'e',
    il nome che il confine ha attaccato al soggetto (l'intestazione
    dell'ingress, la firma); un soggetto rifatto da un filo non ne porta. Mai
    la chiave: sulla pagina sarebbe un identificatore interno, non un nome.
    `None` quando nessuno lo sa. Il nome e' testo scrivibile da fuori (un
    utente di HA, un servizio che si presenta): passa da `sanitize_ha_value`
    una volta, qui.

    `approved`: le righe di `approved_services`, se chi chiama le ha gia'.
    """
    subject = subject or {}
    if subject.get("specie") not in _NAMED_SPECIES:
        return None
    name = None
    if subject.get("id"):
        if subject["specie"] == "persona":
            name = ((await _person_row(app, subject)) or {}).get("nome")
        else:
            rows = _service_rows(subject, approved_services(app) if approved is None
                                 else approved)
            name = next((row.get("nome") for row in rows), None)
    name = sanitize_ha_value(name or subject.get("nome"))
    return name or None


async def ceiling_at_wake(app, subject: dict | None) -> dict:
    """Il soffitto di chi ha chiesto una promessa, al suo risveglio.

    Lo usa l'orologio (`keeper/sweeper.py`) prima di eseguire un `fai`
    (extra 2 del Task 3 della fetta «il seguito delle chat divise»): fra la
    nascita e la scadenza possono passare trenta giorni, e il soffitto di
    allora non vale piu'. Per una persona il ruolo lo rilegge
    `ceiling_for` da Home Assistant; per un servizio si rilegge
    dall'archivio -- il ruolo eventualmente presente nel soggetto NON conta.
    """
    subject = dict(subject or {})
    if not subject.get("specie"):
        # Senza soggetto `consente` ripiegherebbe su «persona ignota», che
        # legge (`lettore`): per un'azione a scadenza di cui non si sa il
        # padrone nemmeno quello -- una macchina senza ruolo, che non puo'
        # niente.
        return consente({"specie": "nessuno"}, ruolo=None)
    if subject.get("specie") == "persona":
        # **Al risveglio il dubbio chiude** (fix round 1, punto 2). In chat
        # una persona senza ruolo leggibile vale «lettore» (`_PERSONA_IGNOTA`):
        # legge e basta. Al risveglio nemmeno quello -- l'utente puo' essere
        # stato cancellato, o Home Assistant non rispondere -- e nel dubbio
        # non si fa niente: nessun gesto, nemmeno le letture riservate.
        role = await _ruolo_persona(app, subject)
        if role is None:
            return {**{g: False for g in GESTI}, "ruolo": None,
                    "perche": WAKE_UNVERIFIED_PERSON}
        return consente(subject, ruolo=role)
    subject["ruolo"] = _approved_service_role(app, subject)
    return await ceiling_for(app, subject)


def is_admin_role(role: str | None) -> bool:
    """**La regola dell'amministratore**, scritta una volta: il cancello al
    confine (`admission.py`) e le pagine che si adattano a chi guarda
    (`restricted_person`) la chiedono qui."""
    return role == "amministratore"


def request_role(request) -> str | None:
    """**Il ruolo di chi fa questa richiesta, gia' letto** (spec 2026-09-27,
    fix round 1 del Task 2, I4): per una persona dall'ingress quello che il
    cancello al confine ha lasciato su `request["ruolo"]`, per un servizio
    quello dell'approvazione, che viaggia col soggetto. Nessuna seconda
    domanda a Home Assistant: le pagine che si adattano a chi guarda
    (salute, memorie, impostazioni, pallini) lo prendono tutte da qui."""
    if request.get("auth_via") == "ingress":
        return request.get("ruolo")
    return (request.get("soggetto") or {}).get("ruolo")


def request_ceiling(request) -> dict:
    """**Il soffitto di questa richiesta**, dal ruolo gia' letto
    (`request_role`): la stessa regola di `ceiling_for`, senza rileggere i
    ruoli. E' la sola strada per chi decide su una richiesta -- il cancello di
    chi costruisce, quello dei servizi, il turno di chat, i pallini."""
    return consente(request.get("soggetto") or {}, ruolo=request_role(request))


def restricted_person(request) -> bool:
    """Una persona dall'ingress che il cancello non ha letto come
    amministratrice -- un ruolo ignoto compreso. E' a lei che le pagine
    mostrano solo cio' che e' suo (spec 2026-09-27 §4). Servizi, ponte e
    sviluppo hanno le loro regole e restano come prima."""
    return (request.get("auth_via") == "ingress"
            and not is_admin_role(request_role(request)))


def _route_pattern(request) -> str:
    """Il MODELLO della rotta (`/api/constructions/{id}`), non il percorso:
    `request.path` e' decodificato, e un `%0A` nell'id diventerebbe una riga
    falsa nel registro (fix round 1 del Task 4, Low-3). `?` fuori da una
    rotta registrata."""
    info = getattr(request, "match_info", None)
    resource = getattr(getattr(info, "route", None), "resource", None)
    return getattr(resource, "canonical", None) or "?"


def require_builder(request) -> web.Response | None:
    """**Il cancello di chi costruisce** (spec 2026-09-26 §3, decisioni 5 e
    6): `None` se questa richiesta puo' costruire, altrimenti il 403 col
    motivo del soffitto.

    Una funzione sola per ogni rotta della pagina Costruzioni, delle proposte
    a mano e dei giudizi: la regola e' una, e due copie divergerebbero al
    primo ritocco. Si chiama PRIMA di toccare qualunque archivio -- anche la
    lettura dell'elenco scrive (`store.scadi`), e un 403 detto dopo avrebbe
    gia' scritto.

    Il rifiuto si registra a `info`: un non amministratore che apre la pagina
    per URL e' un caso normale, non un allarme. Si scrive la chiave del
    soggetto e non il nome visualizzato, che e' testo di chi chiede.
    """
    permesso = request_ceiling(request)
    if permesso["costruire"]:
        return None
    logger.info("soffitto: %s %s negato a %s — %s", request.method, _route_pattern(request),
                subject_key_for(request.get("soggetto")), permesso["perche"])
    return error_response(403, permesso["perche"])


def prepara_ruoli(app) -> None:
    """Il contenitore dei ruoli nasce quando l'app si compone, non alla prima
    richiesta servita: vedi il commento in fondo a `_refresh_users`.

    `quando = 0` vuol dire «mai letto», e la prima richiesta che serve un ruolo
    lo legge — non c'è nessun ramo «prima volta» da ricordarsi.
    """
    app["ruoli"] = {"quando": 0.0, "per_id": {}}
