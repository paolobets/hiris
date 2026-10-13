"""Cio' che l'add-on scrive in Home Assistant per installarsi e disinstallarsi.

La terza porta di scrittura (Tappa 7, D1; finita con la Chiusura, F5): la voce
di menu dell'add-on e la disinstallazione della vecchia card Lovelace. Non sono
servizi (`action/actuator.py`) e non sono la configurazione di automazioni,
script e scene (`action/construction/workshop.py`).

**Tutto passa da `HAClient`** (E-01, E-06): lo slug dal Supervisor
(`own_slug`), l'override della voce (`update_panel`) e la sua rilettura
(`panels`), le risorse Lovelace (`lovelace_resources`,
`delete_lovelace_resource`). Fino alla Chiusura la logica della voce viveva in
`panel_visibility.py`, con un client suo verso il Supervisor, e la
disinstallazione apriva una sessione WebSocket sua: tre client verso lo stesso
sistema, con tre timeout e tre forme d'errore.

**Avviene in un compito a parte, dopo l'avvio** (`start_installation`):
l'add-on parte prima del nucleo (`startup: services`), e una Home Assistant che
non risponde non deve tenere chiuso HIRIS. Fino alla Chiusura la
disinstallazione della card stava dentro `_on_startup` e lo teneva fermo fino a
35 secondi a ogni avvio (M-41).
"""
import asyncio
import logging
import os
from datetime import UTC, datetime

from aiohttp import web

from ..background import spawn as _spawn
from ..home_space.redaction import home_assistant_folder

logger = logging.getLogger(__name__)


# fetta E5 Task 5: la card Lovelace esce per intero -- il file
# `static/hiris-chat-card.js`, la sua copia dentro Home Assistant, il file di
# scoperta dell'ingress che solo lei leggeva e la registrazione della risorsa.
# Tornera' riscritta da zero quando il prodotto sara' completo.
#
# Con lei escono `_deploy_card_to_www` (copiava il JS in <config-ha>/www/{slug}/),
# `_write_ingress_config` (scriveva `hiris-ingress.json` accanto alla card: il
# suo unico lettore era la card, `hiris-chat-card.js:565`) e
# `_register_lovelace_card` (registrava la risorsa e migrava gli URL stantii).
#
# Al loro posto resta questa **disinstallazione**, perche' quelle tre funzioni
# non scrivevano dentro l'add-on: scrivevano nella configurazione dell'utente.
# Cancellare il solo codice lascerebbe in piedi una risorsa Lovelace che punta
# a un file che non esiste piu' -- un errore visibile nella dashboard, che
# l'utente dovrebbe togliere a mano senza sapere perche'. Chi ha installato
# disinstalla.
#
# Le tre regole che questa funzione rispetta, e che i test pinnano:
#  1. **tocca solo cio' che ha messo lei**: gli unici URL riconosciuti sono i
#     due che `_register_lovelace_card` sapeva creare -- il vecchio URL ingress
#     e qualunque `/local/{slug}/hiris-chat-card.js` (nudo o con `?v=`).
#     Qualsiasi altra risorsa Lovelace dell'utente resta dov'e';
#  2. **e' idempotente**: al secondo avvio non trova niente e non fa niente;
#  3. **non fa cadere l'avvio e non lo appende**: gira nel compito
#     dell'installazione, dopo l'avvio, e se Home Assistant non risponde, o
#     la cartella di configurazione non e' montata, registra e torna. E se la
#     deregistrazione fallisce lo **dice**: ogni
#     risorsa rimasta col proprio URL, piu' una riga di riepilogo con
#     l'elenco completo. Una traccia lasciata in silenzio nella configurazione
#     dell'utente sarebbe indistinguibile da un'assenza di problemi -- e un
#     elenco monco lo sarebbe altrettanto, perche' l'utente toglierebbe cio'
#     che ha letto e resterebbe con il resto.
_LOCAL_CARD_URL = "/local/{slug}/hiris-chat-card.js"
_URL_CARD_INGRESS = "/api/hassio_ingress/{slug}/static/hiris-chat-card.js"
# I due file che l'add-on copiava dentro <config-ha>/www/{slug}/. Nient'altro
# di quella cartella e' suo: se l'utente ci ha messo roba propria, resta.
_FILE_CARD = ("hiris-chat-card.js", "hiris-ingress.json")


#: La cartella in cui il vecchio installatore copiava la card, e lo slug dei
#: suoi URL. Era `HIRIS_SLUG`, una variabile d'ambiente che `run.sh` non ha
#: mai esportato -- di fatto questa costante (F-10). NON e' lo slug del
#: Supervisor (`HAClient.own_slug`), che serve alla voce di menu.
CARD_FOLDER = "hiris"

#: Il segno che la card e' disinstallata, in `/data`: la condizione d'uscita
#: che mancava (M-41). Si scrive solo dopo un passaggio pulito -- nessuna
#: risorsa rimasta, nessun file rimasto -- e da li' in poi la disinstallazione
#: non chiede piu' niente a Home Assistant. Chi ha installato disinstalla, una
#: volta.
CARD_UNINSTALLED_MARK = "card_lovelace_disinstallata"

def _e_risorsa_della_card(url: str, slug: str) -> bool:
    """Vero SOLO per le tre forme di URL che l'add-on sapeva registrare.

    fix round 1, Critical. Prima questa funzione chiudeva con
    `url.startswith(locale)`, che di forme ne riconosceva infinite: erano
    "sue" anche `/local/hiris/hiris-chat-card.js.bak`,
    `/local/hiris/hiris-chat-card.js-mio.js` e `/local/hiris/hiris-chat-card.json`.
    Un utente con un proprio fork della card dal nome derivato se lo sarebbe
    visto deregistrare dall'add-on, con un log che diceva "rimossa" e nessun
    modo di capire che era suo. Il vincolo e' l'opposto: mai toccare risorse
    che non ha installato lui. Le tre forme, e nient'altro:
      - il vecchio URL ingress;
      - `/local/{slug}/hiris-chat-card.js` nudo (add-on vecchi);
      - lo stesso con la query di versione, `?v=...`.
    """
    local = _LOCAL_CARD_URL.format(slug=slug)
    return (
        url == _URL_CARD_INGRESS.format(slug=slug)
        or url == local
        or url.startswith(local + "?")
    )


async def _deregistra_risorsa_card(ha, slug: str) -> bool:
    """Toglie da Lovelace TUTTE le risorse della card. Torna False se ne resta.

    `False` = "qualcosa e' rimasto nella configurazione dell'utente", oppure
    "non lo so" (Home Assistant non ha risposto), e a quel punto il log l'ha
    gia' detto: ogni risorsa non tolta col proprio URL, piu' una riga di
    riepilogo con l'elenco completo. Non solleva.
    """
    listed = await ha.lovelace_resources()
    if "errore" in listed:
        if listed["causa"] == "rifiuto":
            # Lovelace in modalita' YAML: le risorse non si gestiscono da
            # qui, e in quella modalita' l'add-on non ne aveva mai
            # registrata una (la registrazione usciva dallo stesso ramo).
            logger.info(
                "card HIRIS: risorse Lovelace non gestibili via WebSocket "
                "(%s) — se avevi aggiunto la card a mano, toglila dal tuo "
                "lovelace.yaml", listed["errore"])
            return True
        logger.warning(
            "card HIRIS: Home Assistant non ha risposto (%s) — se nella tua "
            "dashboard resta la risorsa %s, toglila da Impostazioni -> Dashboard "
            "-> Risorse", listed["errore"], _LOCAL_CARD_URL.format(slug=slug))
        return False

    # fix round 1, Important 2: una delete rifiutata NON interrompe il ciclo.
    # Chi aggiorna da una versione vecchia ha tipicamente DUE risorse della
    # card (l'URL nudo e quello versionato): si tenta ognuna, si nomina
    # ognuna, e l'esito complessivo torna in fondo.
    tolte: list[str] = []
    rimaste: list[str] = []
    for risorsa in listed["risorse"]:
        url = risorsa.get("url", "") if isinstance(risorsa, dict) else ""
        if not _e_risorsa_della_card(url, slug):
            continue
        outcome = await ha.delete_lovelace_resource(risorsa.get("id"))
        if "errore" not in outcome:
            tolte.append(url)
            logger.info(
                "card HIRIS: risorsa Lovelace rimossa (%s) — la card e' "
                "uscita dal prodotto, tornera' riscritta", url)
        else:
            rimaste.append(url)
            logger.warning(
                "card HIRIS: non ho potuto togliere la risorsa Lovelace "
                "%s (%s) — toglila a mano da Impostazioni -> Dashboard "
                "-> Risorse", url, outcome["errore"])
    if rimaste:
        # Il riepilogo: chi legge il log deve trovare in UNA riga l'elenco
        # COMPLETO di cio' che gli e' rimasto da togliere.
        logger.warning(
            "card HIRIS: %d risorse Lovelace rimosse, %d rimaste da "
            "togliere a mano: %s", len(tolte), len(rimaste), ", ".join(rimaste))
    return not rimaste


def _rimuovi_file_card(slug: str) -> bool:
    """Toglie i due file della card da <config-ha>/www/{slug}/, se ci sono.
    Torna False se un file e' rimasto."""
    ha_config = home_assistant_folder()
    if ha_config is None:
        # Senza cartella montata non c'e' niente da togliere e niente da dire:
        # non e' un guasto, e' una installazione che la copia non l'ha mai
        # ricevuta.
        return True
    folder = os.path.join(ha_config, "www", slug)
    clean = True
    for name in _FILE_CARD:
        path = os.path.join(folder, name)
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info("card HIRIS: rimosso %s", path)
        except Exception as exc:
            clean = False
            logger.warning(
                "card HIRIS: non ho potuto rimuovere %s (%s) — puoi cancellarlo "
                "a mano", path, exc)
    # La cartella si toglie SOLO se e' rimasta vuota: se l'utente ci ha messo
    # qualcosa di suo, quella roba non e' dell'add-on e non si tocca.
    try:
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
            logger.info("card HIRIS: rimossa la cartella vuota %s", folder)
    except Exception as exc:
        logger.debug("card HIRIS: cartella %s non rimossa (%s)", folder, exc)
    return clean


async def disinstalla_card_lovelace(ha, data_dir: str,
                                    slug: str = CARD_FOLDER) -> None:
    """Disinstalla la card Lovelace dalla configurazione di Home Assistant,
    una volta: dopo un passaggio pulito scrive il segno
    (`CARD_UNINSTALLED_MARK`) e dagli avvii successivi non fa piu' niente.

    Prima la risorsa, poi i file: al contrario si lascerebbe -- proprio nella
    finestra in cui Home Assistant non risponde -- una risorsa registrata che
    punta a un file gia' cancellato, cioe' l'errore che questa funzione esiste
    per evitare. Se la deregistrazione fallisce i file si tolgono lo stesso
    (il JS non esiste piu' nell'immagine: quella copia e' un residuo di una
    versione precedente), ma il fallimento e' gia' stato dichiarato nel log
    con l'URL da togliere a mano, e il segno non si scrive: al prossimo avvio
    si riprova.
    """
    mark = os.path.join(data_dir, CARD_UNINSTALLED_MARK)
    if os.path.exists(mark):
        return
    resources_clean = await _deregistra_risorsa_card(ha, slug)
    files_clean = _rimuovi_file_card(slug)
    if not (resources_clean and files_clean):
        return
    _write_mark(mark)


def _write_mark(mark: str) -> None:
    """Il segno porta cosa dice e quando: chi apre `/data` lo legge da solo."""
    try:
        with open(mark, "w", encoding="utf-8") as handle:
            handle.write("La vecchia card Lovelace di HIRIS e' disinstallata: "
                         "nessuna risorsa e nessun file rimasti, "
                         f"{datetime.now(UTC).isoformat(timespec='seconds')}.\n")
    except OSError as exc:
        logger.warning("card HIRIS: disinstallata, ma il segno %s non si scrive (%s): "
                       "al prossimo avvio si ricontrolla", mark, exc)


# ── La voce di menu (spec 2026-09-27 §2) ────────────────────────────────────
#
# All'avvio: lo slug si chiede al Supervisor, l'override si scrive in Home
# Assistant, lo stato si rilegge e si dice nel registro. **La voce di menu non
# e' un controllo d'accesso** (spec §1): il cancello vero legge
# `app["non_admin_access"]` e il ruolo da Home Assistant, mai l'esito di questa
# parte. Per questo qui un guasto si dice e basta: nessun ritentare, nessuna
# eccezione che fermi l'avvio.

#: Il tetto dell'intera sincronia, attesa del nucleo compresa. Non e' una
#: misura: e' una scelta. Il Supervisor avvia l'add-on prima del nucleo
#: (`startup: services`), e dopo un riavvio della macchina il nucleo puo'
#: metterci minuti; oltre questo tetto la voce resta com'era, e lo si dice.
SYNC_CEILING_S = 600

#: Quanto si aspetta lo slug dal Supervisor. Una scelta, non una misura: era
#: il tetto del client suo di `panel_visibility.read_own_slug`, e la domanda
#: e' una sola, all'avvio, a un servizio della stessa macchina.
SLUG_CEILING_S = 10


async def sync_panel_visibility(app) -> None:
    """Allinea la voce di menu all'opzione. Non solleva mai."""
    try:
        await _sync(app)
    except Exception as exc:
        logger.warning("voce di menu: sincronia non riuscita (%s)", type(exc).__name__)


async def _sync(app) -> None:
    access = app["non_admin_access"]
    ha = app["ha_client"]
    try:
        own = await asyncio.wait_for(ha.own_slug(), timeout=SLUG_CEILING_S)
    except TimeoutError:
        own = {"errore": f"il Supervisor non ha risposto entro {SLUG_CEILING_S} s"}
    if "errore" in own:
        logger.warning("voce di menu: non tocco niente, manca lo slug di HIRIS: %s",
                       own["errore"])
        return
    try:
        await asyncio.wait_for(_apply(ha, own["slug"], access), timeout=SYNC_CEILING_S)
    except TimeoutError:
        if not ha.ws_ready.is_set():
            logger.warning("voce di menu: Home Assistant non si è collegato entro %d s, "
                           "nessun comando mandato: la voce resta com'era "
                           "(non_admin_access=%s)", SYNC_CEILING_S, access)
        else:
            logger.warning("voce di menu: Home Assistant non ha risposto entro %d s, "
                           "la voce resta com'era (non_admin_access=%s)",
                           SYNC_CEILING_S, access)


async def _apply(ha, slug: str, access: bool) -> None:
    """UNA chiamata, dopo che il WebSocket di HIRIS si e' autenticato: prima il
    nucleo potrebbe non esserci ancora, e la chiamata fallirebbe per certo.
    Poi lo stato si rilegge, e tutto si dice in UNA riga del registro."""
    await ha.ws_ready.wait()
    # Spenta si manda `None` e non `True`: toglie l'override e torna il
    # predefinito di Home Assistant (il manifest: `panel_admin`) senza tracce.
    outcome = await ha.update_panel(slug, False if access else None)
    if outcome.get("codice") == "unknown_command":
        failure = ("questo Home Assistant non conosce frontend/update_panel (arriva "
                   "con la 2026.3), quindi la voce resta ai soli amministratori; chi "
                   "può entrare lo decide comunque HIRIS")
    elif "errore" in outcome:
        failure = f"Home Assistant ha rifiutato l'override: {outcome['errore']}"
    else:
        failure = None
    state = await _real_state(ha, slug)
    if failure:
        logger.warning("voce di menu %s: %s; %s (non_admin_access=%s)",
                       slug, failure, state, access)
    else:
        logger.info("voce di menu %s: %s (non_admin_access=%s)", slug, state, access)


async def _real_state(ha, slug: str) -> str:
    """Lo stato si rilegge, non si deduce dal comando mandato. Solo la voce di
    HIRIS: gli altri pannelli della casa non finiscono nel registro."""
    read = await ha.panels()
    if "errore" in read:
        return f"stato non riletto: {read['errore']}"
    panel = read["pannelli"].get(slug)
    if not isinstance(panel, dict):
        return "non è fra i pannelli di Home Assistant"
    who = ("ai soli amministratori" if panel.get("require_admin")
           else "a tutti gli utenti")
    sidebar = "" if panel.get("show_in_sidebar", True) else ", nascosta dalla barra laterale"
    return f"visibile {who}{sidebar}"


# ── Il compito dell'installazione ───────────────────────────────────────────

async def install(app) -> None:
    """La voce di menu, poi la card. Non solleva mai.

    Senza token non c'e' un Supervisor (sviluppo locale, `.smoke-test`):
    chiamarlo costerebbe un avviso sullo slug a ogni avvio, per un guasto che
    non c'e'. Lo si dice una volta, a livello info.

    La card aspetta il nucleo come la voce di menu, sotto lo stesso tetto: le
    risorse Lovelace le sa solo Home Assistant.
    """
    if not os.environ.get("SUPERVISOR_TOKEN", ""):
        logger.info("nessun Supervisor: la voce di menu e la card non si toccano")
        return
    await sync_panel_visibility(app)
    ha = app["ha_client"]
    try:
        await asyncio.wait_for(ha.ws_ready.wait(), timeout=SYNC_CEILING_S)
    except TimeoutError:
        logger.warning("card HIRIS: Home Assistant non si è collegato entro %d s, "
                       "la disinstallazione si riprova al prossimo avvio",
                       SYNC_CEILING_S)
        return
    try:
        await disinstalla_card_lovelace(ha, app["data_dir"])
    except Exception as exc:
        logger.warning("card HIRIS: disinstallazione non riuscita (%s)",
                       type(exc).__name__)


async def start_installation(app: web.Application) -> None:
    # Il compito si tiene in `app`: il tetto della sincronia e' di dieci
    # minuti, e un arresto durante l'attesa del nucleo lo lascerebbe pendente
    # a chiusura. `_on_cleanup` lo ferma.
    app["installation_task"] = _spawn(install(app), name="installation")
