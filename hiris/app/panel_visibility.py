"""La voce di menu di HIRIS segue l'opzione `non_admin_access` (spec
2026-09-27 §2).

All'avvio: lo slug si chiede al Supervisor, l'override si scrive in Home
Assistant, lo stato si rilegge e si dice nel registro. **La voce di menu non
e' un controllo d'accesso** (spec §1): il cancello vero legge
`app["non_admin_access"]` e il ruolo da Home Assistant, mai l'esito di questo
modulo. Per questo qui un guasto si dice e basta: nessun ritentare, nessuna
eccezione che fermi l'avvio.
"""
import asyncio
import logging
import os
import re

import aiohttp

logger = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"

#: La forma di uno slug del Supervisor (`6354e165_hiris` sulla casa, 27/09/2026).
#: Tutto il resto non diventa un `url_path`: lo slug arriva da una risposta
#: HTTP, e un valore strano deve fermare il comando, non viaggiare fino a HA.
#: Si usa con `fullmatch`, non con `match` e `^...$`: `$` accetta anche un
#: a-capo finale, e `"6354e165_hiris\n"` passerebbe.
SLUG_SHAPE = re.compile(r"[a-z0-9_]+")

#: Il tetto dell'intera sincronia, attesa del nucleo compresa. Non e' una
#: misura: e' una scelta. Il Supervisor avvia l'add-on prima del nucleo
#: (`startup: services`), e dopo un riavvio della macchina il nucleo puo'
#: metterci minuti; oltre questo tetto la voce resta com'era, e lo si dice.
SYNC_CEILING_S = 600


def parse_access_flag(raw: str | None) -> bool:
    """Solo «true» apre. `bashio::config` di un `bool` scrive `true`/`false`;
    `yes`, `1` e `on` non valgono: su un'opzione che allarga l'accesso ogni
    forma inattesa resta chiusa."""
    return (raw or "").strip().lower() == "true"


async def read_own_slug(token: str) -> dict:
    """`{"slug": ...}` oppure `{"errore": ...}`.

    `GET /addons/self/info` risolve l'add-on che chiama (Supervisor 2026.09.2,
    `supervisor/api/apps.py::get_app_for_request`, verificato il 27/09/2026) e risponde
    `{"result": "ok", "data": {...}}`. **Il corpo non si scrive mai nel
    registro**: `data` porta anche le opzioni dell'add-on, chiavi API comprese.
    Nell'errore vanno solo lo stato HTTP o il nome dell'eccezione.
    """
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)) as session, session.get(
                f"{SUPERVISOR_URL}/addons/self/info",
                headers={"Authorization": f"Bearer {token}"}) as resp:
            if resp.status != 200:
                return {"errore": f"il Supervisor ha risposto {resp.status}"}
            body = await resp.json(content_type=None)
    except Exception as exc:
        return {"errore": f"il Supervisor non ha risposto ({type(exc).__name__})"}
    data = body.get("data") if isinstance(body, dict) else None
    slug = data.get("slug") if isinstance(data, dict) else None
    if not isinstance(slug, str) or not SLUG_SHAPE.fullmatch(slug):
        return {"errore": "il Supervisor non ha dato uno slug di forma attesa"}
    return {"slug": slug}


async def sync_panel_visibility(app) -> None:
    """Allinea la voce di menu all'opzione. Non solleva mai."""
    try:
        await _sync(app)
    except Exception as exc:
        logger.warning("voce di menu: sincronia non riuscita (%s)", type(exc).__name__)


async def _sync(app) -> None:
    access = app["non_admin_access"]
    # Senza token non c'e' un Supervisor (sviluppo locale, `.smoke-test`):
    # chiamarlo costerebbe fino a dieci secondi e un avviso sullo slug a ogni
    # avvio, per un guasto che non c'e'. Lo si dice una volta, a livello info.
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        logger.info("nessun Supervisor: la voce di menu non si tocca")
        return
    own = await read_own_slug(token)
    if "errore" in own:
        logger.warning("voce di menu: non tocco niente, manca lo slug di HIRIS: %s",
                       own["errore"])
        return
    ha = app["ha_client"]
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
