"""Il soffitto: quanto si concede a chi chiede (invariante I-1, 21/09/2026).

**Il principio, del proprietario**: *HIRIS non concede mai piu' di quanto il
chiamante gia' puo' in Home Assistant.* Ne' piu' ne' meno.

**Meno sarebbe teatro.** Un utente non amministratore comanda gia' le sue entita'
dalla plancia; impedirglielo dentro HIRIS non toglie un potere a nessuno,
aggiunge una frustrazione e una falsa sensazione di sicurezza.

**Piu' e' quello che HIRIS fa oggi.** Verificato sul sorgente di Home Assistant:
il Supervisor proxa verso il nucleo con la propria sessione privilegiata, e
`websocket_api/connection.py::context` costruisce il contesto dall'utente
autenticato **ignorando il messaggio** -- nessuna delega, nessuna impersonazione
possibile. Quindi HIRIS parla con HA da amministratore qualunque sia la persona
che ha scritto in chat.

**Dove sta la differenza, misurata e non supposta.** Non nei servizi:
`action/verification.py` dichiara che quelli di sistema (`homeassistant.restart`,
`hassio.host_reboot`, `recorder.purge`, `shell_command.*`) sono gia'
irraggiungibili dalla porta, perche' non dichiarano un bersaglio e un bersaglio
vuoto e' sempre un rifiuto. L'amplificazione vera e' **una porta sola**: la
configurazione. Un non amministratore, via HIRIS, puo' far scrivere automazioni
in casa -- e Home Assistant glielo nega (`helpers/service.py`: `if not
user.is_admin: if admin_only: raise Unauthorized`).

**Da cui la forma di questo modulo: una porta, due valori.** Nessun servizio
elencato. Un elenco di servizi invecchierebbe a ogni rilascio di Home Assistant
e si aggirerebbe comunque scrivendo il servizio dentro il corpo di
un'automazione -- che e' precisamente la porta che qui si chiude.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

#: Per quanto si tiene buona la risposta di Home Assistant su chi è
#: amministratore. Una lettura per ogni richiesta metterebbe il pannello alla
#: mercé della latenza di HA su un percorso che gira a ogni clic; nessuna
#: scadenza vorrebbe dire che un utente promosso o degradato aspetta il riavvio
#: dell'add-on. Un minuto è il compromesso, ed è dichiarato invece che dedotto.
RUOLI_VALIDI_S = 60.0

#: I gesti su cui questo modulo si pronuncia. Insieme CHIUSO: un gesto che non
#: c'e' non e' «permesso», e' un gesto su cui nessuno ha deciso -- e la prova
#: `test_ogni_gesto_conosciuto_ha_una_risposta` lo trasforma in un rosso invece
#: che in un silenzio.
GESTI = ("comandare", "costruire")

_TEATRO = ("comandare le entità è ciò che Home Assistant concede già dalla "
           "plancia: vietarlo qui non toglierebbe nessun potere a nessuno")
_SOLO_AMMINISTRATORI = ("scrivere automazioni, script o scene in Home Assistant "
                       "è riservato agli amministratori: è la stessa cosa che "
                       "Home Assistant rifiuterebbe a questa utenza")
_IGNOTO = ("non ho potuto sapere se questa utenza è amministratore, e finché "
           "non lo so vale il grado più basso: un guasto nella lettura non "
           "deve diventare un permesso in più")
_MACCHINA = ("questa richiesta porta un token, non una persona: il suo "
             "perimetro è deciso dal canale da cui arriva, non da un ruolo di "
             "Home Assistant")


def consente(soggetto: dict | None, *, amministratore: bool | None) -> dict:
    """Cosa può fare questo soggetto — un esito per ogni gesto di `GESTI`.

    `amministratore` è **a tre valori**, e il terzo è quello che conta: `None`
    vuol dire «non l'ho potuto leggere», non «no». Il verso del dubbio è sempre
    il grado più basso, perché il contrario renderebbe un guasto di rete un
    aumento di privilegi.

    Per una macchina (`specie` diversa da `persona`) il ruolo di Home Assistant
    non si applica e non si deduce: tiene il soffitto che aveva, e l'esito lo
    **dichiara** con `rinviato`. È una decisione rimandata all'invariante dei
    canali esterni, e un rinvio taciuto è indistinguibile da una svista.
    """
    specie = (soggetto or {}).get("specie") or "persona"
    if specie != "persona":
        return {"comandare": True, "costruire": True, "rinviato": True,
                "perche": _MACCHINA}
    if amministratore is True:
        return {"comandare": True, "costruire": True, "rinviato": False,
                "perche": None}
    perche = _SOLO_AMMINISTRATORI if amministratore is False else _IGNOTO
    return {"comandare": True, "costruire": False, "rinviato": False,
            "perche": f"{perche}. {_TEATRO}."}


async def _amministratore(app, soggetto: dict | None) -> bool | None:
    """Se questa utenza è amministratore in Home Assistant — o `None`.

    `None` non è «no»: è «non l'ho potuto sapere», e i due casi si separano qui
    perché a valle si comportano allo stesso modo ma vanno detti in modo diverso
    a chi legge il rifiuto.

    La risposta si tiene per `RUOLI_VALIDI_S`. **Un guasto non si mette in
    cache**: se la lettura fallisce si riprova alla richiesta dopo, altrimenti
    un singolo momento storto di Home Assistant spegnerebbe la costruzione per
    un minuto intero.
    """
    identificatore = (soggetto or {}).get("id")
    if not identificatore:
        return None
    client = app.get("ha_client")
    if client is None:
        return None

    visti = app.get("ruoli")
    if visti is None:
        return None
    if time.time() - visti["quando"] >= RUOLI_VALIDI_S:
        esito = await client.users()
        if "errore" in esito:
            # `error` e non `warning`, e con la CONSEGUENZA scritta: finché
            # questa lettura non riesce, NESSUNO può costruire — nemmeno il
            # proprietario. È il verso giusto (un guasto non deve diventare un
            # permesso in più) ma è anche il guasto che spegne una funzione, e
            # chi legge il registro deve capirlo alla prima riga invece di
            # inseguire un 403 che non si spiega.
            logger.error(
                "soffitto: non ho potuto leggere i ruoli da Home Assistant "
                "(%s). Finché non ci riesco NESSUNO può far scrivere "
                "automazioni a HIRIS, perché non so chi è amministratore: "
                "il comando è `config/auth/list` sul canale websocket",
                esito["errore"])
            return None
        # Si MUTA il contenitore, non si riscrive `app[...]`: scrivere in
        # `app` a richiesta gia' servita fa emettere ad aiohttp «Changing
        # state of started or joined application is deprecated» -- oggi un
        # avviso, con aiohttp 4 un errore. Stesso motivo per cui i contatori
        # dei giri di strumento nascono quando l'app si compone.
        visti["per_id"] = {u["id"]: u for u in esito["utenti"] if u.get("id")}
        visti["quando"] = time.time()

    riga = visti["per_id"].get(identificatore)
    return None if riga is None else bool(riga.get("amministratore"))


async def per_richiesta(app, request) -> dict:
    """Il soffitto di questa richiesta: soggetto dal confine, ruolo da HA."""
    soggetto = request.get("soggetto")
    return consente(soggetto, amministratore=await _amministratore(app, soggetto))


def prepara_ruoli(app) -> None:
    """Il contenitore dei ruoli nasce quando l'app si compone, non alla prima
    richiesta servita: vedi il commento dentro `_amministratore`.

    `quando = 0` vuol dire «mai letto», e la prima richiesta che serve un ruolo
    lo legge -- non c'e' nessun ramo «prima volta» da ricordarsi.
    """
    app["ruoli"] = {"quando": 0.0, "per_id": {}}
