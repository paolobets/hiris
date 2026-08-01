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


def _read_store(data_dir: str) -> dict | None:
    """Legge il file dello store, distinguendo 'assente' da 'illeggibile'.

    Ritorna una mappa url_path -> lista di {"config": {...}}, dalla piu'
    vecchia alla piu' recente. Casi:
      - file assente: {} (nessun backup ancora, situazione legittima);
      - file valido: il dict letto;
      - file presente ma corrotto/illeggibile: None.

    I due casi di fallimento vanno tenuti distinti: riscrivere un file
    corrotto con la sola plancia corrente cancellerebbe in silenzio gli
    snapshot di tutte le altre plance, e il chiamante procederebbe a
    sovrascrivere credendo di avere una rete di sicurezza."""
    path = _file(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        logger.warning("dashboard_backups: file illeggibile o corrotto", exc_info=True)
        return None
    if not isinstance(data, dict):
        logger.warning("dashboard_backups: contenuto del file non e' una mappa, considerato corrotto")
        return None
    return data


def _load(data_dir: str) -> dict:
    """Vista permissiva dello store per la sola lettura: un file assente o
    corrotto vale come 'nessun backup', cosi' `latest_backup` non solleva mai."""
    data = _read_store(data_dir)
    return data if data is not None else {}


def save_backup(data_dir: str, url_path: str, config: dict) -> bool:
    """Accoda uno snapshot, scartando i piu' vecchi oltre il limite.

    Scrittura atomica (file temporaneo + os.replace): il file e' condiviso
    fra tutte le plance, una scrittura interrotta a meta' non deve troncare
    i backup delle altre. Tutto avvolto nel try/except: questa e' una rete
    di sicurezza, non deve mai sollevare verso il chiamante. Ritorna True
    se lo stato precedente e' al sicuro su disco, False altrimenti: il
    chiamante (l'apply in mode 'replace') usa questo esito per decidere se
    procedere con la sovrascrittura o abortire."""
    data = _read_store(data_dir)
    if data is None:
        # Fail-closed: meglio rifiutare la sostituzione che distruggere gli
        # snapshot delle altre plance riscrivendo un file che non sappiamo
        # leggere. Il messaggio resta lato server: al chiamante torna solo False.
        logger.error(
            "dashboard_backups: il file degli snapshot (%s) esiste ma non e' leggibile o e' "
            "corrotto; salvataggio rifiutato per non cancellare i backup delle altre plance. "
            "Ispezionare il file e, se non recuperabile, rimuoverlo a mano: il prossimo "
            "salvataggio lo ricreera' da zero.",
            _file(data_dir),
        )
        return False
    entries = data.get(url_path)
    if not isinstance(entries, list):
        entries = []
    last = entries[-1] if entries else None
    if isinstance(last, dict) and last.get("config") == config:
        # Stato gia' al sicuro: non si appende un duplicato. I tentativi di
        # apply falliti (config rifiutata, errore WS) rientrano qui e non
        # devono consumare il ring espellendo le versioni realmente precedenti.
        return True
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
