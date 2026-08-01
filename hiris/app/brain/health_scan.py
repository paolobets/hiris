from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import health_checks as hc
from .advisory_store import SEVERITA_GRAVE
from .health_checks import CHECK_IDS
from ..tools.notify_tools import send_notification

logger = logging.getLogger(__name__)

# Canale della notifica: lo stesso push mobile gia' usato dal briefing e dai
# solleciti (server.py), cosi' il deep-link e il canale Android sono quelli
# che l'utente conosce.
_CANALE = "ha_push"
_TITOLO = "HIRIS: problema rilevato"

# Tetto di notifiche per singola scansione. Un guasto solo puo' aprire molte
# segnalazioni gravi in un colpo (dopo un riavvio di Home Assistant decine di
# automazioni risultano non disponibili): una raffica di push produrrebbe
# esattamente il rifiuto che questo meccanismo esiste per evitare. Oltre il
# tetto parte un unico messaggio di riepilogo; le segnalazioni restano tutte
# registrate e leggibili in HIRIS.
MAX_NOTIFICHE_PER_SCANSIONE = 5


def _iso(now: datetime | None) -> str:
    dt = now or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _messaggio(segnalazione: dict) -> str:
    """Testo della notifica: il problema e, se c'e', cosa farci."""
    titolo = (segnalazione.get("title") or "").strip()
    rimedio = (segnalazione.get("suggested_fix") or "").strip()
    return f"{titolo}\n{rimedio}".strip() if rimedio else titolo


async def _notifica_le_gravi(ha_client, esito: dict, notify_config: dict) -> None:
    """Invia una notifica per ogni segnalazione grave nuova, riaperta o
    innalzata a grave.

    Mai per un semplice aggiornamento: la scansione gira 48 volte al giorno e
    ri-notificare lo stesso problema porterebbe l'utente a disattivare le
    notifiche, perdendo anche quelle utili. Ogni invio e' isolato: uno fallito
    non ferma gli altri e non fa fallire la scansione.
    """
    da_inviare = [
        s
        for chiave in ("inserted_items", "reopened_items", "escalated_items")
        for s in (esito.get(chiave) or [])
        if s.get("severity") == SEVERITA_GRAVE
    ]

    async def _invia(messaggio: str, riferimento) -> None:
        if not messaggio:
            return
        try:
            await send_notification(ha_client, messaggio, _CANALE,
                                    notify_config, title=_TITOLO)
        except Exception:
            # La notifica e' un di piu': la scansione ha gia' registrato la
            # segnalazione, che resta visibile in chat e nella UI.
            logger.warning("health_scan: notifica non inviata per %s",
                           riferimento, exc_info=True)

    for segnalazione in da_inviare[:MAX_NOTIFICHE_PER_SCANSIONE]:
        await _invia(_messaggio(segnalazione), segnalazione.get("source_ref"))

    restanti = len(da_inviare) - MAX_NOTIFICHE_PER_SCANSIONE
    if restanti > 0:
        await _invia(
            f"Altri {restanti} problemi gravi rilevati. Aprili in HIRIS per l'elenco completo.",
            "riepilogo",
        )


async def run_health_scan(*, ha_client, entity_cache, tiers, entity_tiers, store,
                          now=None, unavailable_days: int = 2,
                          battery_pct: int = 15, supervisor_client=None,
                          notify_config: dict | None = None,
                          notify_enabled: bool = True) -> dict:
    """Scansione di sola lettura: raccoglie i dati e riconcilia le segnalazioni.

    `supervisor_client` e' opzionale: su un'installazione senza Supervisor non
    esiste affatto, e i tre controlli di sistema restano semplicemente muti.

    `notify_config` e' la configurazione di notifica gia' in uso altrove
    (`server.py`): senza, non c'e' alcun canale a cui inviare e la scansione
    resta muta esattamente come prima. `notify_enabled` e' l'opzione
    dell'add-on `brain_notify_high`, attiva per impostazione predefinita.
    """
    now = now or datetime.now(timezone.utc)

    raw_states = []
    try:
        raw_states = await ha_client.get_states([])
    except Exception:
        logger.warning("health_scan: get_states failed", exc_info=True)

    minimal = []
    try:
        if entity_cache is not None:
            minimal = entity_cache.all_states() or []
    except Exception:
        logger.warning("health_scan: cache states failed", exc_info=True)

    automations = []
    try:
        automations = await ha_client.get_automations()
    except Exception:
        logger.warning("health_scan: get_automations failed", exc_info=True)

    no_area = []
    try:
        area_map = entity_cache.get_area_map() if entity_cache is not None else None
        if area_map is None and entity_cache is not None:
            await entity_cache.load_area_registry(ha_client)
            area_map = entity_cache.get_area_map()
        no_area = (area_map or {}).get("__no_area__", [])
    except Exception:
        logger.warning("health_scan: area map failed", exc_info=True)

    addons = []
    try:
        if supervisor_client is not None:
            addons = await supervisor_client.get_addons() or []
    except Exception:
        logger.warning("health_scan: get_addons failed", exc_info=True)

    host_info = {}
    try:
        if supervisor_client is not None:
            host_info = await supervisor_client.get_host_info() or {}
    except Exception:
        logger.warning("health_scan: get_host_info failed", exc_info=True)

    updates = []
    try:
        if supervisor_client is not None:
            updates = await supervisor_client.get_available_updates() or []
    except Exception:
        logger.warning("health_scan: get_available_updates failed", exc_info=True)

    candidates = []
    candidates += hc.check_entity_unavailable(raw_states, now=now, days=unavailable_days)
    candidates += hc.check_low_battery(minimal, threshold=battery_pct)
    candidates += hc.check_automation_broken(automations)
    candidates += hc.check_dangerous_domain_green(tiers or {}, entity_tiers or {})
    candidates += hc.check_entity_no_area(no_area)
    candidates += hc.check_addon_down(addons)
    candidates += hc.check_disk_space(host_info)
    candidates += hc.check_updates_available(updates)

    esito = store.reconcile(candidates, CHECK_IDS, now=_iso(now))

    if notify_enabled and notify_config is not None:
        try:
            await _notifica_le_gravi(ha_client, esito, notify_config)
        except Exception:
            logger.warning("health_scan: invio notifiche fallito", exc_info=True)

    return esito
