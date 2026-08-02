from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..security.semaphore import DANGEROUS_DOMAINS

CHECK_IDS = {
    "entity_unavailable", "low_battery", "automation_broken",
    "dangerous_domain_green", "entity_no_area",
    "addon_down", "disk_space", "updates_available",
}

# Identificativo del controllo e prefisso del titolo delle segnalazioni di
# batteria scarica. Il briefing quotidiano (brain/briefing.py) rilegge queste
# segnalazioni dallo store invece di ricalcolare le batterie per conto suo, e
# prende il nome del dispositivo dall'evidenza. Il prefisso resta condiviso
# solo per il RIPIEGO sulle righe salvate prima che l'evidenza portasse il
# campo `name`: lo store e' persistente, quelle righe esistono davvero.
CHECK_BATTERIA = "low_battery"
BATTERIA_TITOLO_PREFISSO = "Batteria scarica: "

# Soglia predefinita di carica residua sotto la quale una batteria e' scarica.
# UNICA in tutto il prodotto: la Sentinella parte dallo stesso numero
# (watcher/policy.py DEFAULT_POLICY, watcher/detectors.detect_low_battery), e
# un test lo verifica. I due meccanismi restano pero' distinti e questo e'
# voluto, non un residuo:
#   - questo controllo gira a ogni scansione del Brain su TUTTE le batterie
#     della casa e produce una segnalazione persistente: e' igiene, sempre
#     attiva, e la sua soglia non e' configurabile perche' non e' una
#     preferenza ma un valore di buon senso;
#   - `detectors.battery` e' un rilevatore in tempo reale che l'utente
#     abilita su entita' SCELTE, con la propria `min_pct` regolabile: chi lo
#     accende sta chiedendo una sorveglianza piu' stretta su quelle poche
#     entita', e abbassare o alzare quel numero deve restare possibile senza
#     spostare l'igiene di tutta la casa.
# Cio' che NON deve accadere e' che i due partano da numeri diversi: a meta'
# strada fra 10 e 15 l'utente si sentirebbe dire "scarica" da un meccanismo e
# nulla dall'altro sulla stessa entita'. Da qui il valore condiviso.
SOGLIA_BATTERIA_PCT = 15

# Da quanti giorni una entita' deve essere assente perche' il Brain ne faccia
# una segnalazione. Vedi `check_entity_unavailable` per il rapporto con lo
# snapshot istantaneo di proxy/health_monitor.py.
GIORNI_NON_DISPONIBILE = 2

# Stati con cui Home Assistant dice "non ho un valore per questa entita'".
STATI_NON_DISPONIBILI = ("unavailable", "unknown")

# Formato degli istanti scritti nelle voci: UTC al secondo, ordinabile come
# stringa. Lo stesso di proxy/health_monitor._TS_FMT, cosi' snapshot e
# segnalazioni citano la stessa caduta con la stessa scrittura.
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Soglie di spazio libero sul disco dell'host, in percentuale. "Sotto" e'
# stretto: esattamente al 10% si resta in avviso, esattamente al 20% non si
# segnala nulla.
DISCO_LIBERO_PCT_ALTO = 10.0
DISCO_LIBERO_PCT_AVVISO = 20.0

# Quanti aggiornamenti elencare nell'evidenza. L'evidenza finisce nel prompt
# dell'LLM: il conteggio totale e' sempre presente, l'elenco e' un campione.
MAX_UPDATES_EVIDENZA = 10

# Stati del Supervisor che indicano un add-on non in esecuzione, con la
# severita' associata. `error` e' un guasto; `stopped` puo' essere una scelta
# deliberata dell'utente, quindi vale un avviso e non un allarme.
ADDON_STATI_FERMI = {"error": "high", "stopped": "warn"}


def _parse_iso(v):
    if not v or not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def entita_non_disponibili(states):
    """Entita' che NON rispondono adesso, dalla lista completa degli stati.

    Unica derivazione del fatto "questa entita' non risponde" in tutto il
    prodotto. La usano entrambi i luoghi che di quel fatto parlano:

    - `proxy/health_monitor.HealthMonitor`, che tiene lo snapshot di chi non
      risponde ADESSO (rigenerato a ogni refresh da questa funzione e
      mantenuto fra un refresh e l'altro dagli eventi WebSocket, sempre
      passando da qui);
    - `check_entity_unavailable` qui sotto, che di quella stessa lista tiene
      solo le assenze che durano da giorni.

    `since` viene da `last_changed` (o `last_updated`) normalizzato a UTC:
    la durata dell'assenza e' quella di Home Assistant, non l'istante in cui
    HIRIS se n'e' accorto. Vale None quando HA non porta un istante
    leggibile -- l'entita' non risponde lo stesso, ma da quanto non si sa.

    Funzione pura: nessun I/O, nessuna scrittura, mai solleva su voci
    malformate.
    """
    out = []
    for s in states or []:
        if not isinstance(s, dict):
            continue
        if s.get("state") not in STATI_NON_DISPONIBILI:
            continue
        eid = s.get("entity_id") or ""
        if not eid:
            continue
        ts = _parse_iso(s.get("last_changed") or s.get("last_updated"))
        attributi = s.get("attributes")
        nome = (attributi or {}).get("friendly_name") if isinstance(attributi, dict) else None
        out.append({
            "entity_id": eid,
            "domain": eid.split(".", 1)[0] if "." in eid else "",
            "since": ts.astimezone(timezone.utc).strftime(_TS_FMT) if ts else None,
            "state": s.get("state"),
            "name": nome or eid,
        })
    return out


def check_entity_unavailable(states, *, now: datetime,
                             days: int = GIORNI_NON_DISPONIBILE):
    """Segnalazioni per le entita' assenti da almeno `days` giorni.

    NON e' un secondo calcolo di chi non risponde: e' un FILTRO PER DURATA
    sopra `entita_non_disponibili`, l'unica derivazione del fatto. Le due
    letture che l'utente incontra rispondono percio' a due domande diverse
    sopra lo stesso fatto, e non possono contraddirsi:

    - «cosa non risponde adesso?» -> lo snapshot di `proxy/health_monitor.py`,
      sezione `unavailable`, che il Chatbot legge con `get_ha_health`;
    - «cosa e' rotto per davvero?» -> queste segnalazioni, che ignorano le
      assenze brevi (riavvio di HA, wifi che salta) perche' segnalarle
      sarebbe rumore.

    L'insieme segnalato qui e' sempre un sottoinsieme di quello: il titolo
    dichiara la durata, cosi' chi vede le due liste di lunghezza diversa
    capisce perche'. Un'entita' senza istante leggibile resta nello snapshot
    ma non viene segnalata: non si puo' affermare che manchi da giorni.
    """
    cutoff = now - timedelta(days=days)
    durata = "un giorno" if days == 1 else f"{days} giorni"
    out = []
    for voce in entita_non_disponibili(states):
        ts = _parse_iso(voce["since"])
        if ts is None or ts > cutoff:
            continue
        eid = voce["entity_id"]
        out.append({
            "check_id": "entity_unavailable", "severity": "warn",
            "title": f"{voce['name']} non disponibile da più di {durata}",
            "evidence": {"entity_id": eid, "since": voce["since"],
                         "state": voce["state"]},
            "suggested_fix": "Controlla il dispositivo o l'integrazione.",
            "fix_kind": "manual",
            "source_ref": f"entity_unavailable:{eid}",
        })
    return out


def check_low_battery(states, *, threshold: int = SOGLIA_BATTERIA_PCT):
    out = []
    for e in states or []:
        eid = e.get("id", "")
        if not eid.startswith("sensor."):
            continue
        dc = e.get("device_class")
        unit = e.get("unit") or ""
        name = e.get("name") or ""
        is_batt = dc == "battery" or (unit == "%" and "batter" in name.lower())
        if not is_batt:
            continue
        try:
            pct = float(e.get("state"))
        except (TypeError, ValueError):
            continue
        if pct < threshold:
            out.append({
                "check_id": CHECK_BATTERIA, "severity": "warn",
                "title": f"{BATTERIA_TITOLO_PREFISSO}{name or eid}",
                # Il nome amichevole sta nell'evidenza, accanto alla carica
                # residua: e' un dato, e chi rilegge la segnalazione (il
                # briefing quotidiano) lo prende da qui invece di spellare
                # all'indietro il titolo, che e' testo per l'utente.
                "evidence": {"entity_id": eid, "name": name or eid, "pct": pct},
                "suggested_fix": "Sostituisci le pile.",
                "fix_kind": "manual",
                "source_ref": f"{CHECK_BATTERIA}:{eid}",
            })
    return out


def check_automation_broken(automations):
    out = []
    for a in automations or []:
        st = a.get("state")
        if st not in ("off", "unavailable"):
            continue
        eid = a.get("entity_id", "")
        name = (a.get("attributes") or {}).get("friendly_name") or eid
        if st == "unavailable":
            sev, reason = "high", "non disponibile"
        else:
            sev, reason = "warn", "disabilitata"
        out.append({
            "check_id": "automation_broken", "severity": sev,
            "title": f"Automazione {reason}: {name}",
            "evidence": {"entity_id": eid, "state": st},
            "suggested_fix": "Verifica o ri-abilita l'automazione in Home Assistant.",
            "fix_kind": "manual",
            "source_ref": f"automation_broken:{eid}",
        })
    return out


def check_dangerous_domain_green(tiers: dict, entity_tiers: dict):
    out = []
    for dom in sorted(DANGEROUS_DOMAINS):
        if (tiers or {}).get(dom) == "green":
            out.append({
                "check_id": "dangerous_domain_green", "severity": "high",
                "title": f"Dominio pericoloso eseguibile senza conferma: {dom}",
                "evidence": {"domain": dom, "tier": "green"},
                "suggested_fix": "Alza il livello del semaforo per questo dominio nel Gateway.",
                "fix_kind": "hiris_config",
                "source_ref": f"dangerous_domain_green:domain:{dom}",
            })
    for eid, lvl in (entity_tiers or {}).items():
        dom = eid.split(".", 1)[0] if "." in eid else ""
        if lvl == "green" and dom in DANGEROUS_DOMAINS:
            out.append({
                "check_id": "dangerous_domain_green", "severity": "high",
                "title": f"Entità pericolosa eseguibile senza conferma: {eid}",
                "evidence": {"entity_id": eid, "tier": "green"},
                "suggested_fix": "Alza il livello del semaforo per questa entità nel Gateway.",
                "fix_kind": "hiris_config",
                "source_ref": f"dangerous_domain_green:entity:{eid}",
            })
    return out


def check_entity_no_area(no_area_ids):
    ids = list(no_area_ids or [])
    if not ids:
        return []
    return [{
        "check_id": "entity_no_area", "severity": "info",
        "title": f"{len(ids)} entità senza area assegnata",
        "evidence": {"count": len(ids), "entities": ids[:50]},
        "suggested_fix": "Assegna un'area alle entità in Home Assistant.",
        "fix_kind": "manual",
        "source_ref": "entity_no_area:all",
    }]


def _numero(v):
    """Converte in float solo numeri veri: `None`, stringhe e bool restano fuori."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def check_addon_down(addons):
    """Add-on installati che non sono in esecuzione.

    Il Supervisor non espone, nell'elenco degli add-on, se l'avvio automatico
    e' abilitato: l'unico segnale disponibile e' lo stato. `error` significa
    guasto ed e' severita' alta; `stopped` puo' essere un add-on che l'utente
    ha spento di proposito, quindi resta un avviso per non trasformare una
    scelta legittima in un allarme. Gli stati transitori (`startup`) e quelli
    ignoti non producono nulla.
    """
    out = []
    for addon in addons or []:
        if not isinstance(addon, dict):
            continue
        stato = addon.get("state")
        if not isinstance(stato, str):
            continue
        severita = ADDON_STATI_FERMI.get(stato)
        if severita is None:
            continue
        slug = addon.get("slug")
        if not slug:
            continue
        nome = addon.get("name") or slug
        motivo = "in errore" if stato == "error" else "fermo"
        out.append({
            "check_id": "addon_down", "severity": severita,
            "title": f"Add-on {motivo}: {nome}",
            "evidence": {"slug": slug, "state": stato},
            "suggested_fix": "Controlla l'add-on in Home Assistant: log, avvio e avvio automatico.",
            "fix_kind": "manual",
            "source_ref": f"addon_down:{slug}",
        })
    return out


def check_disk_space(host_info):
    """Spazio libero sul disco dell'host, dal Supervisor.

    I valori arrivano in GB. Se `disk_free` manca si ricava da totale meno
    usato. Dati assenti, non numerici o incoerenti non producono nulla.
    """
    if not isinstance(host_info, dict):
        return []
    totale = _numero(host_info.get("disk_total"))
    libero = _numero(host_info.get("disk_free"))
    if libero is None:
        usato = _numero(host_info.get("disk_used"))
        if totale is not None and usato is not None:
            libero = totale - usato
    if totale is None or libero is None or totale <= 0 or libero < 0:
        return []

    # Confronto sul rapporto grezzo: arrotondare prima del confronto puo'
    # spostare un valore appena sotto una soglia (es. 9.96%) dalla parte
    # sbagliata (9.96 -> 10.0 arrotondato degraderebbe "grave" ad "avviso").
    # L'arrotondamento resta solo per il titolo e l'evidenza mostrati
    # all'utente.
    pct_grezza = libero / totale * 100
    if pct_grezza < DISCO_LIBERO_PCT_ALTO:
        severita = "high"
    elif pct_grezza < DISCO_LIBERO_PCT_AVVISO:
        severita = "warn"
    else:
        return []
    pct = round(pct_grezza, 1)
    return [{
        "check_id": "disk_space", "severity": severita,
        "title": f"Spazio su disco quasi esaurito: {pct}% libero",
        "evidence": {"free_pct": pct, "free_gb": round(libero, 1),
                     "total_gb": round(totale, 1)},
        "suggested_fix": "Libera spazio: vecchi backup, snapshot e log sono i primi candidati.",
        "fix_kind": "manual",
        "source_ref": "disk_space:host",
    }]


def check_updates_available(updates):
    """Aggiornamenti disponibili per core, OS, Supervisor e add-on.

    Una sola voce aggregata di severita' informativa: sono una condizione
    permanente, non un evento, e una voce per aggiornamento sarebbe rumore.
    L'evidenza porta il totale e un campione limitato dei nomi.
    """
    voci = [u for u in (updates or []) if isinstance(u, dict)]
    if not voci:
        return []
    nomi = []
    for u in voci[:MAX_UPDATES_EVIDENZA]:
        nome = u.get("name") or u.get("update_type") or "sconosciuto"
        versione = u.get("version_latest")
        nomi.append(f"{nome} {versione}" if versione else str(nome))
    quanti = len(voci)
    titolo = ("1 aggiornamento disponibile" if quanti == 1
              else f"{quanti} aggiornamenti disponibili")
    return [{
        "check_id": "updates_available", "severity": "info",
        "title": titolo,
        "evidence": {"count": len(voci), "items": nomi},
        "suggested_fix": "Rivedi e installa gli aggiornamenti dalle impostazioni di Home Assistant.",
        "fix_kind": "manual",
        "source_ref": "updates_available:all",
    }]
