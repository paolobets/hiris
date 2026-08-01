"""Snapshot delle config Lovelace prima di una sostituzione.

Una proposta ha_dashboard in mode 'replace' riscrive INTERAMENTE la plancia.
La sicurezza non sta nell'attrito (niente OTP) ma nella reversibilita': prima
di sovrascrivere si salva qui la config precedente, cosi' un overwrite
sbagliato si annulla con un click. Bounded: solo gli ultimi N per plancia."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_PATH = "dashboard_backups.json"
MAX_BACKUPS_PER_DASHBOARD = 3


def _file(data_dir: str) -> str:
    return os.path.join(data_dir, _PATH)


def _load(data_dir: str) -> dict:
    """Mappa url_path -> lista di {"config": {...}}, dalla piu' vecchia alla piu'
    recente. Un file assente o corrotto vale come 'nessun backup': questo store
    e' una rete di sicurezza, non deve mai bloccare un apply."""
    path = _file(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("dashboard_backups: file illeggibile o corrotto, ignorato", exc_info=True)
        return {}


def save_backup(data_dir: str, url_path: str, config: dict) -> bool:
    """Accoda uno snapshot, scartando i piu' vecchi oltre il limite.

    Scrittura atomica (file temporaneo + os.replace): il file e' condiviso
    fra tutte le plance, una scrittura interrotta a meta' non deve troncare
    i backup delle altre. Tutto avvolto nel try/except: questa e' una rete
    di sicurezza, non deve mai sollevare verso il chiamante. Ritorna True
    se lo snapshot e' stato scritto su disco, False altrimenti: il chiamante
    (l'apply in mode 'replace') usa questo esito per decidere se procedere
    con la sovrascrittura o abortire."""
    data = _load(data_dir)
    entries = data.get(url_path)
    if not isinstance(entries, list):
        entries = []
    entries.append({"config": config})
    data[url_path] = entries[-MAX_BACKUPS_PER_DASHBOARD:]
    try:
        os.makedirs(data_dir, exist_ok=True)
        tmp = _file(data_dir) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _file(data_dir))
        return True
    except Exception:
        logger.exception("dashboard_backups: salvataggio snapshot fallito")
        return False


def latest_backup(data_dir: str, url_path: str) -> dict | None:
    """La config salvata piu' di recente per questa plancia, o None."""
    entries = _load(data_dir).get(url_path)
    if not isinstance(entries, list) or not entries:
        return None
    last = entries[-1]
    if not isinstance(last, dict):
        return None
    cfg = last.get("config")
    return cfg if isinstance(cfg, dict) else None
