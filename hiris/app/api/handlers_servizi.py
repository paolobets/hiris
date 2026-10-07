"""Le rotte dell'ACCOPPIAMENTO dei servizi (decisione del proprietario, 22/09/2026).

Una sola di queste rotte e' speciale.

**`POST /api/services/present` e' l'unica superficie che questo prodotto non
puo' autenticare.** Deve esserlo: un servizio che non hai ancora approvato non
ha modo di autenticarsi, ed e' tutto il punto dell'accoppiamento. Invece di
difenderla -- tetti sulle righe, limiti di ritmo -- si e' scelto di **non farla
esistere**: l'esenzione dal confine vale solo nei dieci minuti in cui hai aperto
la finestra, e fuori di li' quella rotta risponde come qualunque altra, cioe'
401. Una difesa permanente invecchia; una porta chiusa no.

**Presentarsi non e' essere autorizzati.** La presentazione mette in coda una
riga con un codice di quattro cifre derivato dalla chiave pubblica. Il servizio
mostra lo stesso codice sul suo schermo; se i due coincidono, il proprietario
sta accoppiando QUEL servizio e non qualcun altro che si e' messo in mezzo.

**La chiave privata non viaggia mai**: la genera il servizio e non esce da li'.
Qui arriva solo la pubblica, che non e' un segreto -- ed e' per questo che
l'archivio dei servizi si puo' leggere per intero senza che ne esca niente.

**Aprire la finestra, approvare e revocare sono gesti da amministratore**: il
gesto `amministrare` delle loro righe in `admission.ADMISSION`, chiesto dal
confine come per le scritture verso Home Assistant -- dare a una macchina il
diritto di comandare la casa non e' meno di scriverci un'automazione. Fino al
07/10/2026 lo chiedeva qui `_solo_amministratori`, copia di
`soffitto.require_builder` con un altro testo (F-03).
"""
from __future__ import annotations

import logging
import time

from aiohttp import web

from ..chat_thread import unknown_id_text
from .boundary import error_response, json_object
from .canali import RUOLI, SERVICE_SPECIES
from .servizi import (
    apri_finestra,
    chiudi_finestra,
    finestra_aperta,
    finestra_resta,
)

logger = logging.getLogger(__name__)

#: Il percorso esente dal confine **mentre la finestra e' aperta**. Uno solo, e
#: il cancello `test_servizi_rotte.py` lo pinna: una seconda riga qui sarebbe
#: una seconda superficie non autenticata, e andrebbe decisa da una persona.
ROTTA_APERTA = "/api/services/present"

_CHIUSA = ("l’accoppiamento è chiuso. Aprilo da HIRIS, nella pagina dei "
           "servizi: resta aperto dieci minuti.")
#: Approvare e revocare cercano per chiave, non per id: la frase e' quella di
#: ogni id che non c'e' (C-07), con cio' con cui si e' cercato.
_UNKNOWN_KEY = unknown_id_text("nessun servizio", by="quella chiave")


def _archivio(request):
    return request.app.get("servizi")


async def handle_service_present(request: web.Request) -> web.Response:
    """Un servizio si fa vivo. **Non lo autorizza**: lo mette in coda.

    Non risponde niente di utile a chi non e' il servizio: né se il nome
    esiste già, né quanti ce ne sono, né chi sono. Torna il codice da
    confrontare — che chi presenta può comunque calcolarsi da solo dalla
    propria chiave, quindi non è una rivelazione.
    """
    archivio = _archivio(request)
    if archivio is None:
        return error_response(503, "archivio non disponibile")
    if not finestra_aperta(request.app.get("finestra_servizi"), adesso=time.time()):
        # Non dovrebbe arrivarci -- il confine la ferma prima -- ma una porta
        # che si difende in un posto solo e' una porta che si apre il giorno in
        # cui quel posto cambia.
        return error_response(403, _CHIUSA)

    dati = await json_object(request)
    chiave = str(dati.get("chiave") or "").strip()
    if not chiave:
        return error_response(400, "serve la tua chiave pubblica Ed25519, in base64")
    riga = archivio.presenta(nome=str(dati.get("nome") or "").strip() or "senza nome",
                             chiave=chiave,
                             indirizzo=request.remote or "?", now_ts=time.time())
    logger.info("servizi: «%s» si è presentato da %s — codice %s, stato %s",
                riga["nome"], riga["indirizzo"], riga["codice"], riga["stato"])
    return web.json_response({"codice": riga["codice"], "stato": riga["stato"]})


async def handle_services(request: web.Request) -> web.Response:
    """Chi ha chiesto, chi è vivo, chi hai revocato — e lo stato della finestra."""
    archivio = _archivio(request)
    if archivio is None:
        return error_response(503, "archivio non disponibile")
    adesso = time.time()
    finestra = request.app.get("finestra_servizi")
    return web.json_response({
        "servizi": archivio.elenco(now_ts=adesso),
        "finestra": {"aperta": finestra_aperta(finestra, adesso=adesso),
                     "resta_s": round(finestra_resta(finestra, adesso=adesso))},
        "ruoli": list(RUOLI), "specie": list(SERVICE_SPECIES)})


async def handle_open_window(request: web.Request) -> web.Response:
    """Apre l'accoppiamento per dieci minuti."""
    finestra = request.app.get("finestra_servizi")
    if finestra is None:
        return error_response(503, "finestra non disponibile")
    adesso = time.time()
    apri_finestra(finestra, adesso=adesso)
    logger.info("servizi: accoppiamento aperto per %d minuti",
                round(finestra_resta(finestra, adesso=adesso) / 60))
    return web.json_response({"aperta": True,
                              "resta_s": round(finestra_resta(finestra, adesso=adesso))})


async def handle_close_window(request: web.Request) -> web.Response:
    """La chiude subito, senza aspettare i minuti che avanzano."""
    chiudi_finestra(request.app.get("finestra_servizi") or {})
    logger.info("servizi: accoppiamento chiuso")
    return web.json_response({"aperta": False, "resta_s": 0})


async def handle_service_approve(request: web.Request) -> web.Response:
    """Il sì: il servizio è autorizzato, col ruolo e la specie che decidi tu."""
    archivio = _archivio(request)
    if archivio is None:
        return error_response(503, "archivio non disponibile")
    dati = await json_object(request)
    adesso = time.time()
    try:
        fatto = archivio.approva(str(dati.get("chiave") or ""),
                                 ruolo=str(dati.get("ruolo") or ""),
                                 specie=str(dati.get("specie") or ""),
                                 now_ts=adesso)
    except ValueError as errore:
        return error_response(400, str(errore))
    if not fatto:
        return error_response(404, _UNKNOWN_KEY)
    logger.info("servizi: approvato un servizio come «%s» (%s)",
                dati.get("ruolo"), dati.get("specie"))
    return web.json_response({"servizi": archivio.elenco(now_ts=adesso)})


async def handle_service_revoke(request: web.Request) -> web.Response:
    """Il no, o il ripensamento. Vale **subito**."""
    archivio = _archivio(request)
    if archivio is None:
        return error_response(503, "archivio non disponibile")
    dati = await json_object(request)
    adesso = time.time()
    if not archivio.revoca(str(dati.get("chiave") or ""), now_ts=adesso):
        return error_response(404, _UNKNOWN_KEY)
    logger.info("servizi: accesso revocato a un servizio")
    return web.json_response({"servizi": archivio.elenco(now_ts=adesso)})
