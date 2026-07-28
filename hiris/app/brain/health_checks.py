from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..security.semaphore import DANGEROUS_DOMAINS

CHECK_IDS = {
    "entity_unavailable", "low_battery", "automation_broken",
    "dangerous_domain_green", "entity_no_area",
}


def _parse_iso(v):
    if not v or not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_entity_unavailable(states, *, now: datetime, days: int = 2):
    cutoff = now - timedelta(days=days)
    out = []
    for s in states or []:
        if s.get("state") not in ("unavailable", "unknown"):
            continue
        ts = _parse_iso(s.get("last_changed") or s.get("last_updated"))
        if ts is None or ts > cutoff:
            continue
        eid = s.get("entity_id", "")
        name = (s.get("attributes") or {}).get("friendly_name") or eid
        out.append({
            "check_id": "entity_unavailable", "severity": "warn",
            "title": f"{name} non disponibile da giorni",
            "evidence": {"entity_id": eid, "since": s.get("last_changed"),
                         "state": s.get("state")},
            "suggested_fix": "Controlla il dispositivo o l'integrazione.",
            "fix_kind": "manual",
            "source_ref": f"entity_unavailable:{eid}",
        })
    return out


def check_low_battery(states, *, threshold: int = 15):
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
                "check_id": "low_battery", "severity": "warn",
                "title": f"Batteria scarica: {name or eid}",
                "evidence": {"entity_id": eid, "pct": pct},
                "suggested_fix": "Sostituisci le pile.",
                "fix_kind": "manual",
                "source_ref": f"low_battery:{eid}",
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
