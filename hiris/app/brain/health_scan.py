from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import health_checks as hc
from .advisory_store import SEVERITA_GRAVE
from .health_checks import CHECK_IDS
from ..notifiche import send_notification

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

# Periodo di silenzio per riferimento di deduplica: dopo una notifica, lo
# stesso problema non ne produce un'altra finche' non sono trascorse queste
# ore. La regola "solo nuova o riaperta" da sola non basta, perche' si regge
# sul confronto con lo stato precedente: un valore che sfarfalla attorno a una
# soglia (il disco che scende sotto il 10% libero e risale, un add-on in ciclo
# di riavvio che alterna errore e fermo) torna "nuovo" a ogni giro e notifica
# ogni volta.
#
# Dodici ore: la scansione gira ogni 30 minuti, quindi il silenzio copre 24
# giri e assorbe qualunque oscillazione di giornata (backup notturni, riavvii,
# entita' intermittenti) con al massimo due notifiche al giorno per problema;
# nel frattempo il briefing quotidiano continua comunque a riepilogare le
# segnalazioni ancora aperte. Ed e' abbastanza corto perche' un problema che si
# ripresenta davvero giorni dopo torni a notificare come una notizia nuova.
SILENZIO_NOTIFICA_ORE = 12

# Importanza relativa dei controlli, usata SOLO quando le segnalazioni gravi
# superano il tetto per scansione. L'ordine in cui girano i controlli non e' un
# ordine di gravita': l'ordine e' questo, dal piu' urgente da sapere subito.
#
# 1. dangerous_domain_green: un dominio pericoloso (serrature, allarme) che si
#    esegue senza conferma e' un buco di sicurezza aperto, non un guasto.
# 2. disk_space: il disco che si esaurisce ferma le scritture di Home Assistant
#    e manda a vuoto i backup, cioe' proprio la rete di sicurezza.
# 3. addon_down: un servizio su cui l'utente conta e' giu'.
# 4. automation_broken: numerose e spesso transitorie subito dopo un riavvio,
#    che e' esattamente l'evento di massa che ha reso necessario il tetto.
# Gli altri controlli non producono severita' alta, ma restano elencati perche'
# il criterio non dipenda da quale severita' emettono oggi.
PRIORITA_CONTROLLO = {
    "dangerous_domain_green": 1,
    "disk_space": 2,
    "addon_down": 3,
    "automation_broken": 4,
    "entity_unavailable": 5,
    "low_battery": 6,
    "entity_no_area": 7,
    "updates_available": 8,
}
_PRIORITA_IGNOTA = 99

# Come chiamare, nel riepilogo, i problemi rimasti fuori dal tetto: singolare e
# plurale. Un conteggio nudo ("ci sono altri 36 problemi gravi") non aiuta a
# decidere se aprire l'app; sapere che sono 34 automazioni e 2 add-on si'.
ETICHETTE_CONTROLLO = {
    "dangerous_domain_green": ("comando pericoloso senza conferma",
                               "comandi pericolosi senza conferma"),
    "disk_space": ("problema di spazio su disco", "problemi di spazio su disco"),
    "addon_down": ("add-on", "add-on"),
    "automation_broken": ("automazione", "automazioni"),
    "entity_unavailable": ("entità non disponibile", "entità non disponibili"),
    "low_battery": ("batteria scarica", "batterie scariche"),
    "entity_no_area": ("entità senza area", "entità senza area"),
    "updates_available": ("aggiornamento", "aggiornamenti"),
}


def _iso(now: datetime | None) -> str:
    dt = now or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _messaggio(segnalazione: dict) -> str:
    """Testo della notifica: il problema e, se c'e', cosa farci."""
    titolo = (segnalazione.get("title") or "").strip()
    rimedio = (segnalazione.get("suggested_fix") or "").strip()
    return f"{titolo}\n{rimedio}".strip() if rimedio else titolo


def _peso(check_id: str) -> int:
    return PRIORITA_CONTROLLO.get(check_id, _PRIORITA_IGNOTA)


def _a_giro_per_importanza(segnalazioni: list[dict]) -> list[dict]:
    """Riordina a giro: prima una segnalazione per ciascun controllo, partendo
    dal piu' importante, poi la seconda di ciascuno, e cosi' via.

    Il tetto per scansione taglia la coda, quindi l'ordine decide chi viene
    notificato davvero. Prendere le voci nell'ordine in cui girano i controlli
    significherebbe, dopo un riavvio di Home Assistant, cinque automazioni non
    disponibili e il disco quasi pieno silenziato dentro il riepilogo. Il giro
    garantisce che nessun controllo sparisca del tutto e, a parita' di giro,
    che passi prima quello piu' importante.
    """
    gruppi: dict[str, list[dict]] = {}
    for s in segnalazioni:
        gruppi.setdefault(s.get("check_id") or "", []).append(s)
    ordinati = sorted(gruppi.items(), key=lambda kv: (_peso(kv[0]), kv[0]))
    piu_lungo = max((len(voci) for _, voci in ordinati), default=0)
    return [voci[giro] for giro in range(piu_lungo)
            for _, voci in ordinati if giro < len(voci)]


def _riepilogo(restanti: list[dict]) -> str:
    """Messaggio unico per i problemi rimasti fuori dal tetto, con il dettaglio
    di che tipo sono."""
    quanti = len(restanti)
    testa = ("C'è un altro problema grave" if quanti == 1
             else f"Ci sono altri {quanti} problemi gravi")
    conteggi: dict[str, int] = {}
    for s in restanti:
        cid = s.get("check_id") or ""
        conteggi[cid] = conteggi.get(cid, 0) + 1
    pezzi = []
    for cid, n in sorted(conteggi.items(), key=lambda kv: (_peso(kv[0]), kv[0])):
        etichette = ETICHETTE_CONTROLLO.get(cid)
        if etichette is None:
            continue
        pezzi.append(f"{n} {etichette[0] if n == 1 else etichette[1]}")
    dettaglio = f": {', '.join(pezzi)}" if pezzi else ""
    return f"{testa}{dettaglio}. Apri HIRIS per l'elenco completo."


async def _notifica_le_gravi(ha_client, esito: dict, notify_config: dict, *,
                             store, now: datetime) -> None:
    """Invia una notifica per ogni segnalazione grave nuova, riaperta o
    innalzata a grave, saltando quelle per cui si e' gia' avvisato di recente.

    Mai per un semplice aggiornamento: la scansione gira 48 volte al giorno e
    ri-notificare lo stesso problema porterebbe l'utente a disattivare le
    notifiche, perdendo anche quelle utili. Ogni invio e' isolato: uno fallito
    non ferma gli altri e non fa fallire la scansione.
    """
    candidate = [
        s
        for chiave in ("inserted_items", "reopened_items", "escalated_items")
        for s in (esito.get(chiave) or [])
        if s.get("severity") == SEVERITA_GRAVE
    ]
    if not candidate:
        return

    gia_notificati: set = set()
    try:
        gia_notificati = store.notificati_dopo(
            [s.get("source_ref") for s in candidate],
            _iso(now - timedelta(hours=SILENZIO_NOTIFICA_ORE)))
    except Exception:
        # Fail-open: se la memoria non e' leggibile si avvisa lo stesso. Una
        # notifica di troppo e' un fastidio, un guasto grave taciuto per
        # sempre e' il difetto peggiore di quello che si sta correggendo.
        logger.warning("health_scan: memoria delle notifiche non leggibile",
                       exc_info=True)

    da_inviare = _a_giro_per_importanza(
        [s for s in candidate if s.get("source_ref") not in gia_notificati])

    async def _invia(messaggio: str, riferimento) -> bool:
        if not messaggio:
            return False
        try:
            inviata = await send_notification(ha_client, messaggio, _CANALE,
                                              notify_config, title=_TITOLO)
        except Exception:
            # La notifica e' un di piu': la scansione ha gia' registrato la
            # segnalazione, che resta visibile in chat e nella UI.
            logger.warning("health_scan: notifica non inviata per %s",
                           riferimento, exc_info=True)
            return False
        if not inviata:
            # Rifiuto "morbido": canale non configurato o servizio di notifica
            # scritto male. Senza questa riga l'utente non riceve nulla e la
            # scansione non lascia alcuna traccia del perche'.
            logger.warning("health_scan: notifica rifiutata dal canale %s per %s "
                           "(configurazione del canale da verificare)",
                           _CANALE, riferimento)
        return bool(inviata)

    for segnalazione in da_inviare[:MAX_NOTIFICHE_PER_SCANSIONE]:
        riferimento = segnalazione.get("source_ref")
        if not await _invia(_messaggio(segnalazione), riferimento):
            # Un invio mai arrivato non vale come "gia' avvisato".
            continue
        try:
            store.registra_notifica(riferimento, now=_iso(now))
        except Exception:
            # Non annotare costa al massimo una notifica ripetuta alla prossima
            # riapertura: mai una notifica persa, e mai una scansione fallita.
            logger.warning("health_scan: memoria delle notifiche non aggiornata "
                           "per %s", riferimento, exc_info=True)

    restanti = da_inviare[MAX_NOTIFICHE_PER_SCANSIONE:]
    if restanti:
        # Le voci del riepilogo non sono state notificate singolarmente,
        # quindi non consumano il periodo di silenzio.
        await _invia(_riepilogo(restanti), "riepilogo")


async def run_health_scan(*, ha_client, entity_cache, tiers, entity_tiers, store,
                          now=None, unavailable_days: int = hc.GIORNI_NON_DISPONIBILE,
                          battery_pct: int = hc.SOGLIA_BATTERIA_PCT,
                          supervisor_client=None,
                          notify_config: dict | None = None,
                          notify_enabled: bool = True) -> dict:
    """Scansione di sola lettura: raccoglie i dati e riconcilia le segnalazioni.

    `supervisor_client` e' opzionale: su un'installazione senza Supervisor non
    esiste affatto, e i tre controlli di sistema restano semplicemente muti.

    `notify_config` e' la configurazione di notifica gia' in uso altrove
    (`server.py`): senza, non c'e' alcun canale a cui inviare e la scansione
    resta muta esattamente come prima. `notify_enabled` e' l'opzione
    dell'add-on `brain_notify_high`, attiva per impostazione predefinita.

    `store` fa anche da memoria delle notifiche gia' inviate, cosi' un problema
    che sfarfalla attorno a una soglia non torna a notificare a ogni giro
    (vedi SILENZIO_NOTIFICA_ORE).
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
            await _notifica_le_gravi(ha_client, esito, notify_config,
                                     store=store, now=now)
        except Exception:
            logger.warning("health_scan: invio notifiche fallito", exc_info=True)

    return esito
