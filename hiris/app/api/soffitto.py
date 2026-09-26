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

import logging
import time

from .canali import PUO, RUOLI

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
#: che in un silenzio.
GESTI = ("leggere", "comandare", "costruire")

#: Cosa vale una persona di cui non si e' potuto leggere il ruolo.
#:
#: **Non `lettore`**, e la ragione e' il fatto che distingue una persona da una
#: macchina: chi e' passato dall'ingress *ha comunque superato Home Assistant*,
#: quindi comanda gia' dalla plancia. Negarglielo per un guasto di rete gli
#: toglierebbe cio' che ha comunque, cioe' sarebbe teatro pagato con un guasto.
#: Costruire invece resta chiuso: quello HA glielo negherebbe davvero.
_PERSONA_IGNOTA = "utente"

_TEATRO = ("comandare le entità è ciò che Home Assistant concede già dalla "
           "plancia: vietarlo qui non toglierebbe nessun potere a nessuno")
_SOLO_AMMINISTRATORI = ("scrivere automazioni, script o scene in Home Assistant "
                        "è riservato agli amministratori: è la stessa cosa che "
                        "Home Assistant rifiuterebbe a questa utenza")
_IGNOTO = ("non ho potuto sapere se questa utenza è amministratore, e finché "
           "non lo so non si costruisce: un guasto nella lettura non deve "
           "diventare un permesso in più")
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

    **Il verso del dubbio è diverso per le due specie**, e la differenza è il
    fatto che le distingue: una persona senza ruolo leggibile ha comunque
    superato l'ingress di Home Assistant, quindi vale `utente`; una macchina
    senza ruolo **non ha superato niente**, e non può niente.
    """
    specie = (soggetto or {}).get("specie") or "persona"
    persona = specie == "persona"

    if ruolo in RUOLI:
        puo = PUO[ruolo]
        perche = None if puo["costruire"] else f"{_SOLO_AMMINISTRATORI}. {_TEATRO}."
        return {**puo, "ruolo": ruolo, "perche": perche}

    if persona:
        puo = PUO[_PERSONA_IGNOTA]
        return {**puo, "ruolo": _PERSONA_IGNOTA,
                "perche": f"{_IGNOTO}. {_TEATRO}."}

    return {"leggere": False, "comandare": False, "costruire": False,
            "ruolo": None, "perche": _MACCHINA_MUTA}


def ruolo_letto(soffitto: dict) -> bool:
    """Il `ruolo` di questo soffitto viene da una lettura vera, o e' il
    ripiego per una persona di cui non si e' potuto sapere se e'
    amministratore?

    Serve a chi deve DIRLO a qualcuno (fix round 1, Task 5, Important 3: la
    sezione "Chi ti sta parlando" del contesto della chat), non solo a
    deciderlo -- `consente()` sopra restituisce `_PERSONA_IGNOTA` ("utente")
    ANCHE quando il ruolo e' stato letto davvero da Home Assistant e la
    persona e' un'utenza non amministratrice: la stessa stringa copre due
    fatti diversi, e solo `perche'` li distingue (contiene `_IGNOTO` solo nel
    ramo di ripiego). Non si ridichiara qui il testo di `_IGNOTO` --
    lo si CONFRONTA con quello vero, o i due potrebbero divergere."""
    return _IGNOTO not in (soffitto.get("perche") or "")


async def _person_row(app, soggetto: dict | None) -> dict | None:
    """La riga di questa utenza fra gli utenti di Home Assistant — o `None`.

    Una lettura sola per due domande: il ruolo (`_ruolo_persona`) e se è il
    proprietario (`is_owner`, fetta «le chat divise»). Due letture separate
    sarebbero due cache che scadono in momenti diversi.

    La risposta si tiene per `RUOLI_VALIDI_S`. **Un guasto non si mette in
    cache**: se la lettura fallisce si riprova alla richiesta dopo, altrimenti
    un singolo momento storto di Home Assistant chiuderebbe la costruzione per
    un minuto intero.
    """
    identificatore = (soggetto or {}).get("id")
    if not identificatore:
        return None
    client = app.get("ha_client")
    visti = app.get("ruoli")
    if client is None or visti is None:
        return None

    if time.time() - visti["quando"] >= RUOLI_VALIDI_S:
        esito = await client.users()
        if "errore" in esito:
            # `error` e non `warning`, e con le CONSEGUENZE scritte: finché
            # questa lettura non riesce NESSUNO può costruire — nemmeno il
            # proprietario — e la cronologia della chat di prima delle chat
            # divise resta orfana (`is_owner` non sa chi è il proprietario).
            # Sono i due lettori di questa riga; chi ne aggiunge un terzo
            # aggiunge qui la sua conseguenza. È il verso giusto, ma è anche il
            # guasto che spegne una funzione, e chi legge il registro deve
            # capirlo alla prima riga invece di inseguire un 403 che non si
            # spiega.
            logger.error(
                "soffitto: non ho potuto leggere gli utenti da Home Assistant "
                "(%s). Finché non ci riesco NESSUNO può far scrivere "
                "automazioni a HIRIS, perché non so chi è amministratore, e la "
                "cronologia della chat di prima resta orfana, perché non so chi "
                "è il proprietario: il comando è `config/auth/list` sul canale "
                "websocket",
                esito["errore"])
            return None
        # Si MUTA il contenitore, non si riscrive `app[...]`: scrivere in `app`
        # a richiesta già servita fa emettere ad aiohttp «Changing state of
        # started or joined application is deprecated» — oggi un avviso, con
        # aiohttp 4 un errore.
        visti["per_id"] = {u["id"]: u for u in esito["utenti"] if u.get("id")}
        visti["quando"] = time.time()

    return visti["per_id"].get(identificatore)


async def _ruolo_persona(app, soggetto: dict | None) -> str | None:
    """Il ruolo di questa utenza in Home Assistant — o `None`.

    `None` non è «utente»: è «non l'ho potuto sapere». I due casi si separano
    qui perché a valle si comportano allo stesso modo ma vanno detti in modo
    diverso a chi legge il rifiuto.
    """
    riga = await _person_row(app, soggetto)
    if riga is None:
        return None
    return "amministratore" if riga.get("amministratore") else "utente"


async def is_owner(app, soggetto: dict | None) -> bool:
    """Home Assistant dice che questa persona è il proprietario?

    `False` anche quando non lo si è potuto sapere: chi la usa
    (`chat_thread.adopt_if_owner`) fa un gesto che non si ripara -- dare la
    cronologia di prima a qualcuno -- e nel dubbio non lo fa. Ci riprova la
    richiesta dopo.
    """
    return bool((await _person_row(app, soggetto) or {}).get("proprietario"))


async def ceiling_for(app, soggetto: dict | None) -> dict:
    """Il soffitto di questo soggetto.

    Si calcola da un soggetto e non da una richiesta (fetta «le chat divise»):
    un turno di chat servito dal ponte arriva su `/api/mcp` con la credenziale
    del ponte, e chi ha scritto il messaggio viaggia nel job, non nella
    richiesta. Una regola sola per entrambi i casi -- `per_richiesta` e' una
    riga che la chiama.

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
    services = app.get("servizi")
    if services is None:
        return None
    try:
        rows = services.elenco()
    except Exception as exc:
        logger.warning("soffitto: archivio dei servizi non leggibile (%s)",
                       type(exc).__name__)
        return None
    roles = {row.get("ruolo") for row in rows
             if row.get("stato") == "autorizzato"
             and row.get("nome") == subject.get("id")
             and (row.get("specie") or "integrazione") == subject.get("specie")}
    return roles.pop() if len(roles) == 1 else None


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
        # comanda: giusto per chi e' passato dall'ingress, sbagliato per
        # un'azione a scadenza di cui non si sa il padrone.
        return consente({"specie": "nessuno"}, ruolo=None)
    if subject.get("specie") == "persona":
        # **Al risveglio il dubbio chiude** (fix round 1, punto 2). In chat
        # una persona senza ruolo leggibile vale «utente», perche' e' appena
        # passata dall'ingress: e' una prova. Un'azione a scadenza non ha
        # nessuna prova fresca -- l'utente puo' essere stato cancellato, o
        # Home Assistant non rispondere -- e nel dubbio non si comanda.
        role = await _ruolo_persona(app, subject)
        if role is None:
            return {"leggere": False, "comandare": False, "costruire": False,
                    "ruolo": None, "perche": WAKE_UNVERIFIED_PERSON}
        return consente(subject, ruolo=role)
    subject["ruolo"] = _approved_service_role(app, subject)
    return await ceiling_for(app, subject)


async def per_richiesta(app, request) -> dict:
    """Il soffitto di questa richiesta: quello del soggetto che il confine
    (`middleware_internal_auth`) le ha attaccato."""
    return await ceiling_for(app, request.get("soggetto") or {})


def prepara_ruoli(app) -> None:
    """Il contenitore dei ruoli nasce quando l'app si compone, non alla prima
    richiesta servita: vedi il commento dentro `_person_row`.

    `quando = 0` vuol dire «mai letto», e la prima richiesta che serve un ruolo
    lo legge — non c'è nessun ramo «prima volta» da ricordarsi.
    """
    app["ruoli"] = {"quando": 0.0, "per_id": {}}
