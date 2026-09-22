"""Come si sa che una richiesta viene DAVVERO dall'ingress del Supervisor.

Reperti A-2 e A-3 del registro dei rischi (spec 2026-09-21), chiusi il 22/09.

Fino a oggi la risposta era: `X-Ingress-Path` combacia con un'espressione
regolare **e** l'indirizzo sorgente sta in `172.30.32.0/23`. Il secondo
controllo sembra stretto e non lo e': quel `/23` non e' l'indirizzo del proxy,
e' **la rete Docker in cui vive ogni add-on installato**. Qualunque add-on
vicino manda l'intestazione e ottiene `/api/*` per intero senza conoscere nessun
segreto -- e se il tunnel che pubblica la casa gira come add-on (Cloudflared,
Tailscale: il caso normale), il suo indirizzo e' li' dentro.

**La risposta vera e' il biscotto di sessione.** Verificato il 22/09/2026 sulla
sorgente del Supervisor, non supposto:

- `supervisor/api/__init__.py` registra
  `web.post("/ingress/validate_session", api_ingress.validate_session)`;
- il corpo e' `{"session": "<valore>"}`, l'autenticazione e' il
  `SUPERVISOR_TOKEN` come `Bearer`, e la risposta e' 200 oppure 401;
- `handler()` legge la sessione da `request.cookies.get(COOKIE_INGRESS, "")`,
  dove `COOKIE_INGRESS = "ingress_session"`;
- `_init_header()` filtra dodici intestazioni prima di inoltrare, e **il
  biscotto non e' fra quelle**: arriva all'add-on.

Un add-on vicino puo' falsificare `X-Ingress-Path` e puo' trovarsi nel `/23`.
Non puo' avere un biscotto che il Supervisor riconosce senza averlo **rubato a
una persona** -- e a quel punto ha gia' la sessione di quella persona su Home
Assistant, cioe' il problema non e' piu' HIRIS.

**Una cosa da sapere su `validate_session`**: allunga la sessione di quindici
minuti a ogni chiamata. Non e' un effetto che introduciamo noi -- il proxy la
chiama gia' per ogni richiesta che inoltra, quindi quando HIRIS la vede la
sessione e' stata appena allungata comunque. La cache qui sotto esiste per non
aggiungere una chiamata di rete a ogni richiesta, non per evitare quell'effetto.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import time

logger = logging.getLogger(__name__)

#: La rete Docker del Supervisor, e il default dell'add-on. **E' piu' larga del
#: necessario e lo dichiariamo**: ci vive ogni add-on installato. A renderla
#: accettabile e' la sessione, non lei.
RETE_PREDEFINITA = "172.30.32.0/23"

#: Il prefisso piu' largo che si accetta. Il proxy del Supervisor e' **uno**:
#: un `/8`, anche privato, sono sedici milioni di indirizzi, e chi lo scrive
#: crede di aver ristretto mentre ha aperto.
PREFISSO_MINIMO = 16

#: Il nome del biscotto, da `supervisor/api/ingress.py::COOKIE_INGRESS`.
BISCOTTO = "ingress_session"

#: Per quanto si ricorda l'esito di una sessione. Corto: una sessione revocata
#: deve smettere di valere in fretta, e la sessione del Supervisor dura quindici
#: minuti — ricordarne l'esito per piu' di un minuto vorrebbe dire servirne una
#: morta per una frazione apprezzabile della sua vita.
RICORDO_S = 60.0


def reti_fidate(testo: str) -> tuple[list, list[str]]:
    """Le reti fidate lette dalle opzioni — `(reti, rifiuti)`.

    **Un campo vuoto e un campo sbagliato non sono la stessa cosa.** Vuoto vuol
    dire «non ho deciso», e allora decide il prodotto col suo default.
    Sbagliato vuol dire «ho deciso, e ho deciso una cosa che non si può fare»:
    lì non si ripiega su niente, perché ripiegare sul default largo vorrebbe
    dire che scrivere male **allarga** il perimetro invece di stringerlo — il
    proprietario crede di aver ristretto, e ha aperto.

    Ogni rifiuto nomina la voce e dice perché: un rifiuto che non nomina la
    voce costringe a indovinare quale delle tre righe è quella sbagliata.
    """
    voci = [v.strip() for v in str(testo or "").split(",") if v.strip()]
    if not voci:
        return [ipaddress.ip_network(RETE_PREDEFINITA)], []

    reti, rifiuti = [], []
    for voce in voci:
        try:
            rete = ipaddress.ip_network(voce, strict=False)
        except (ValueError, TypeError):
            rifiuti.append(
                f"«{voce}» non è una rete scritta in forma indirizzo/prefisso, "
                f"per esempio {RETE_PREDEFINITA}")
            continue
        if not rete.is_private:
            rifiuti.append(
                f"«{voce}» è una rete pubblica: il proxy del Supervisor vive "
                "nella rete interna di Docker, quindi un indirizzo pubblico lì "
                "non può essere lui")
            continue
        if rete.prefixlen < PREFISSO_MINIMO:
            rifiuti.append(
                f"«{voce}» comprende {rete.num_addresses} indirizzi: è più "
                f"larga di un /{PREFISSO_MINIMO}, e il proxy del Supervisor è "
                "uno solo")
            continue
        reti.append(rete)
    return reti, rifiuti


def prepara_ingresso(app) -> None:
    """I contenitori nascono quando l'app si compone, non alla prima richiesta.

    Scrivere in `app[...]` a richiesta già servita è deprecato in aiohttp 3 e un
    errore in aiohttp 4 — la stessa ragione per cui nascono lì le credenziali
    effimere, i valori irripetibili già visti e la cache dei ruoli.
    """
    app["sessioni_ingress"] = {}


def _pota(ricordi: dict, adesso: float) -> None:
    for chiave in [c for c, (_, quando) in ricordi.items()
                   if adesso - quando > RICORDO_S]:
        del ricordi[chiave]


async def sessione_valida(app, sessione: str, *, adesso: float | None = None) -> bool:
    """Se il Supervisor riconosce questa sessione di ingress.

    **Chiude per difetto in ogni verso**: nessun biscotto, nessun token del
    Supervisor, il Supervisor che non risponde, una risposta che non è 200 —
    tutti «no». E non è severità gratuita: una richiesta arrivata *attraverso*
    il proxy dimostra che il Supervisor era vivo un istante prima, quindi un
    guasto di rete proprio lì è già anomalo. Il ripiego sarebbe esattamente il
    buco che questa funzione esiste per chiudere.
    """
    adesso = time.time() if adesso is None else adesso
    sessione = str(sessione or "").strip()
    if not sessione:
        return False

    ricordi = app.get("sessioni_ingress")
    if ricordi is not None:
        _pota(ricordi, adesso)
        ricordato = ricordi.get(sessione)
        if ricordato is not None:
            return ricordato[0]

    # **La guardia sta QUI e non dentro la domanda**, ed e' una scelta: questa
    # funzione sta sul percorso di ogni richiesta di ingress, quindi e' lei che
    # non deve poter sollevare. Metterla nella domanda lascerebbe scoperto il
    # giorno in cui qualcuno aggiunge una seconda riga qui sopra.
    try:
        esito = await _domanda_supervisor(sessione)
    except Exception as errore:
        logger.warning(
            "ingress: non ho potuto verificare la sessione col Supervisor "
            "(%s) — rifiuto, perché il ripiego sarebbe proprio il buco che "
            "questa verifica chiude", errore.__class__.__name__)
        return False
    if ricordi is not None:
        ricordi[sessione] = (esito, adesso)
    return esito


async def _domanda_supervisor(sessione: str) -> bool:
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        logger.warning(
            "ingress: non ho il token del Supervisor, quindi non posso "
            "verificare nessuna sessione — le richieste di ingress sono "
            "rifiutate. Fuori dal Supervisor questo è normale; dentro, è un "
            "guasto dell'add-on")
        return False

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as sessione_http, sessione_http.post(
            "http://supervisor/ingress/validate_session",
            json={"session": sessione},
            headers={"Authorization": f"Bearer {token}"}) as risposta:
        if risposta.status == 200:
            return True
        # Il 401 e' la risposta NORMALE a una sessione che non esiste: non
        # si registra come guasto, o il registro si riempirebbe a ogni
        # biscotto scaduto in un browser lasciato aperto.
        if risposta.status != 401:
            logger.warning(
                "ingress: il Supervisor ha risposto %s alla verifica "
                "della sessione — rifiuto", risposta.status)
        return False
