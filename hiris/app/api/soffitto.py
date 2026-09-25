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


async def per_richiesta(app, request) -> dict:
    """Il soffitto di questa richiesta.

    Il soggetto lo ha stabilito il confine (`middleware_internal_auth`); il
    ruolo arriva da Home Assistant se è una persona, e **viaggia già col
    soggetto** se è un servizio, perché gliel'ha dato l'approvazione.
    """
    soggetto = request.get("soggetto") or {}
    if soggetto.get("specie") == "persona":
        return consente(soggetto, ruolo=await _ruolo_persona(app, soggetto))
    return consente(soggetto, ruolo=soggetto.get("ruolo"))


def prepara_ruoli(app) -> None:
    """Il contenitore dei ruoli nasce quando l'app si compone, non alla prima
    richiesta servita: vedi il commento dentro `_ruolo_persona`.

    `quando = 0` vuol dire «mai letto», e la prima richiesta che serve un ruolo
    lo legge — non c'è nessun ramo «prima volta» da ricordarsi.
    """
    app["ruoli"] = {"quando": 0.0, "per_id": {}}
