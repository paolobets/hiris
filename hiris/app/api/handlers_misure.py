"""`GET /api/misure` — i due registri, in lettura. **ROTTA TEMPORANEA.**

**Perche' esiste.** I due registri della 3.66.0 scrivono in `consumi.db`, che
vive in `/data` dentro il contenitore dell'add-on. `scripts/misure.py` vuole
quel file, e su Home Assistant non c'e' un ambiente Python in cui farlo
girare: il risultato e' che i registri scrivevano e **nessuno poteva
leggerli**. «Zero superficie di prodotto» era stato difeso come un pregio
fino a perdere il deliverable -- una misura che nessuno puo' leggere e' una
misura che non c'e'.

**TEMPORANEA, e la condizione di uscita e' scritta.** Serve alla FASE delle
misure: qualche giorno di turni sulla casa vera, poi i verdetti di
`scripts/misure.py`, poi le decisioni sulle tre leve (sottoinsieme degli
strumenti, potatura della mappa, prefisso della catena). **Quando quella fase
si chiude questa rotta ESCE** -- o sparisce, o diventa una pagina vera con un
disegno suo. Cio' che non deve fare e' restare: una rotta di servizio
dimenticata e' il modo in cui una superficie provvisoria diventa permanente.
La voce e' in `docs/BACKLOG.md`.

**Non e' una porta aperta.** Sta dietro il perimetro come tutto il resto
(`middleware_internal_auth`): ci arriva chi il proprietario ha approvato -- il
canale firmato o l'ingress. E' importante che ci resti, perche' i turni
portano `subject_json`, cioe' CHI ha chiesto.

**Non porta gli argomenti degli strumenti**, e non e' una scelta di questa
rotta: non sono nell'archivio, perche' `log_turn` non li accetta. Un `view`
porta il nome di una stanza, un `execute` un valore impostato.
"""
from __future__ import annotations

import logging
import time

from aiohttp import web

logger = logging.getLogger(__name__)

#: Quanti giorni si guardano quando il chiamante non lo dice. Sette e' la
#: finestra della domanda normale; i registri ne conservano trenta.
GIORNI_PREDEFINITI = 7

#: Il tetto di turni in una risposta. Un turno puo' avere fino a cinquanta
#: righe di carico, quindi senza tetto una casa attiva risponderebbe con
#: qualche megabyte -- e questa e' una rotta di servizio, non una pagina che
#: pagina.
TETTO_TURNI = 2000


async def handle_misure(request) -> web.Response:
    """I turni della finestra, col carico di ognuno legato al suo turno.

    **Legato, non affiancato**: due liste scollegate costringerebbero chi
    legge a rifare la giunzione, e una giunzione fatta due volte diverge. La
    specie del turno e' cio' che distingue «l'analista spende cosi'» da «la
    chat spende cosi'»: un carico senza il suo turno non risponde a niente.
    """
    archivio = request.app.get("usage")
    if archivio is None:
        # All'avvio, o su un'installazione che non ha ancora misurato. Una
        # rotta di servizio che risponde 500 manda chi la usa a cercare un
        # guasto che non c'e'.
        return web.json_response(_risposta([], {}))

    try:
        giorni = max(1, int(request.query.get("giorni", GIORNI_PREDEFINITI)))
    except (TypeError, ValueError):
        giorni = GIORNI_PREDEFINITI
    # `adesso` esiste per le PROVE, e non e' una concessione: la finestra e'
    # una proprieta' del lettore, e provarla con l'orologio vero vorrebbe dire
    # una prova che cambia esito a mezzanotte. Stessa scelta di
    # `home_space/briefing.compose`, che l'orologio lo riceve.
    try:
        adesso = float(request.query.get("adesso") or time.time())
    except (TypeError, ValueError):
        adesso = time.time()

    da_ts = adesso - giorni * 86400
    turni = [t for t in archivio.turns(limit=TETTO_TURNI) if t["ts"] >= da_ts]
    carichi = {t["id"]: archivio.payloads(t["id"]) for t in turni}
    return web.json_response(_risposta(turni, carichi))


def _risposta(turni: list, carichi: dict) -> dict:
    return {
        # **La risposta dice di se' che e' temporanea.** Chi la trova fra sei
        # mesi deve sapere che non e' un'interfaccia, e per quale fase
        # esisteva -- senza doverlo dedurre dal fatto che non c'e' una
        # pagina.
        "temporanea": ("rotta di servizio per la fase delle misure "
                       "(3.66.x): esce quando i verdetti hanno deciso le "
                       "tre leve. Vedi docs/BACKLOG.md."),
        "turni": turni,
        "carichi": carichi,
    }
