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
SLUG_SHAPE = re.compile(r"^[a-z0-9_]+$")

#: Il tetto dell'intera sincronia. Non e' una misura: e' quanto si accetta di
#: lasciare un compito appeso dietro un Home Assistant che non risponde. Il
#: Supervisor avvia l'add-on anche prima del nucleo (`startup: services`).
SYNC_CEILING_S = 60


def parse_access_flag(raw: str | None) -> bool:
    """Solo «true» apre. `bashio::config` di un `bool` scrive `true`/`false`;
    non si usa `env_util.env_bool`, che accetta anche `yes`/`1`/`on`: su
    un'opzione che allarga l'accesso ogni forma inattesa resta chiusa."""
    return (raw or "").strip().lower() == "true"


async def read_own_slug(token: str) -> dict:
    """`{"slug": ...}` oppure `{"errore": ...}`.

    `GET /addons/self/info` risolve l'add-on che chiama (Supervisor 2026.09.2,
    `api/apps.py::get_app_for_request`, verificato il 27/09/2026) e risponde
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
    if not isinstance(slug, str) or not SLUG_SHAPE.match(slug):
        return {"errore": "il Supervisor non ha dato uno slug di forma attesa"}
    return {"slug": slug}


async def sync_panel_visibility(app) -> None:
    """Allinea la voce di menu all'opzione. Non solleva mai."""
    try:
        await asyncio.wait_for(_sync(app), timeout=SYNC_CEILING_S)
    except TimeoutError:
        logger.warning("voce di menu: Home Assistant non ha risposto entro %d s, "
                       "la voce resta com'era", SYNC_CEILING_S)
    except Exception as exc:
        logger.warning("voce di menu: sincronia non riuscita (%s)", type(exc).__name__)


async def _sync(app) -> None:
    accesso = app["non_admin_access"]
    own = await read_own_slug(os.environ.get("SUPERVISOR_TOKEN", ""))
    if "errore" in own:
        logger.warning("voce di menu: non tocco niente, manca lo slug di HIRIS: %s",
                       own["errore"])
        return
    slug = own["slug"]
    ha = app["ha_client"]
    # Spenta si manda `None` e non `True`: toglie l'override e torna il
    # predefinito di Home Assistant (il manifest: `panel_admin`) senza tracce.
    esito = await ha.update_panel(slug, False if accesso else None)
    if esito.get("codice") == "unknown_command":
        logger.warning(
            "voce di menu: questo Home Assistant non conosce frontend/update_panel "
            "(arriva con la 2026.3), quindi la voce resta ai soli amministratori; "
            "chi può entrare lo decide comunque HIRIS (non_admin_access=%s)", accesso)
    elif "errore" in esito:
        logger.warning("voce di menu: Home Assistant ha rifiutato l'override di %s "
                       "(non_admin_access=%s): %s", slug, accesso, esito["errore"])
    await _log_real_state(ha, slug, accesso)


async def _log_real_state(ha, slug: str, accesso: bool) -> None:
    """Lo stato si rilegge, non si deduce dal comando mandato. Solo la voce di
    HIRIS: gli altri pannelli della casa non finiscono nel registro."""
    letti = await ha.panels()
    if "errore" in letti:
        logger.warning("voce di menu: stato di %s non riletto: %s", slug, letti["errore"])
        return
    pannello = letti["pannelli"].get(slug)
    if not isinstance(pannello, dict):
        logger.warning("voce di menu: %s non è fra i pannelli di Home Assistant", slug)
        return
    chi = ("ai soli amministratori" if pannello.get("require_admin")
           else "a tutti gli utenti")
    barra = "" if pannello.get("show_in_sidebar", True) else ", nascosta dalla barra laterale"
    logger.info("voce di menu: %s è visibile %s%s (non_admin_access=%s)",
                slug, chi, barra, accesso)
