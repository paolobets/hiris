"""Snapshot delle config Lovelace prima di una sostituzione.

Una proposta ha_dashboard in mode 'replace' riscrive INTERAMENTE la plancia.
La sicurezza non sta nell'attrito (niente OTP) ma nella reversibilita': prima
di sovrascrivere si salva qui la config precedente, cosi' un overwrite
sbagliato si annulla con un click. Bounded: solo gli ultimi N per plancia."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_PATH = "dashboard_backups.json"
MAX_BACKUPS_PER_DASHBOARD = 3


def _file(data_dir: str) -> str:
    return os.path.join(data_dir, _PATH)


def _read_store(data_dir: str) -> dict | None:
    """Legge il file dello store, distinguendo 'assente' da 'illeggibile'.

    Ritorna una mappa url_path -> lista di {"config": {...}, "saved_at": "..."},
    dalla piu' vecchia alla piu' recente. Il campo "saved_at" e' stato aggiunto
    dopo: gli snapshot scritti prima ne sono privi e valgono come 'istante
    sconosciuto', mai come errore. Casi:
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


def _write_store(data_dir: str, data: dict) -> bool:
    """Riscrive l'intero store in modo atomico (file temporaneo + os.replace).

    Il file e' condiviso fra tutte le plance: una scrittura interrotta a meta'
    non deve troncare i backup delle altre. Non solleva mai verso il chiamante,
    riporta solo True/False: questa e' una rete di sicurezza, se cede deve
    cedere in silenzio lasciando traccia nei log."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        tmp = _file(data_dir) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _file(data_dir))
        return True
    except Exception:
        logger.exception("dashboard_backups: scrittura dello store fallita")
        return False


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
    # L'istante serve all'interfaccia per distinguere un undo appena fatto da un
    # ripristino storico. La deduplica qui sopra confronta solo il campo
    # "config", quindi l'aggiunta non la disturba.
    entries.append({"config": config, "saved_at": datetime.now(timezone.utc).isoformat()})
    data[url_path] = entries[-MAX_BACKUPS_PER_DASHBOARD:]
    return _write_store(data_dir, data)


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


def discard_latest_backup(data_dir: str, url_path: str, config: dict) -> bool:
    """Consuma lo snapshot piu' recente di una plancia, ma solo se e'
    ancora quello che il chiamante ha appena riapplicato.

    Serve dopo un ripristino riuscito: quella config e' tornata a essere lo
    stato corrente della plancia, quindi continuare a offrirla come "annulla"
    sarebbe un'operazione a vuoto. Toglierla dal ring e' l'unico modo perche'
    l'elenco degli snapshot dica la verita' anche dopo un refresh del browser,
    senza chiedere all'interfaccia di ricordarsi cosa ha gia' ripristinato.

    Il consumo e' per IDENTITA', non per posizione: fra il `latest_backup` che
    ha letto la config e questa chiamata c'e' la scrittura verso Home Assistant,
    che e' un `await`. In quella finestra un altro percorso (un apply 'replace'
    da un secondo tab, o dal gateway MCP) puo' appendere un nuovo snapshot per
    la stessa plancia: togliere "l'ultimo per posizione" cancellerebbe proprio
    la rete di sicurezza appena creata da quella sostituzione concorrente,
    lasciandola senza via di ritorno. Percio' `config` e' la config che ci si
    aspetta di rimuovere: se l'ultima entry non coincide non si tocca nulla e
    si ritorna False, tracciando il motivo lato server.

    Ne toglie UNO solo: le versioni ancora precedenti restano ripristinabili,
    e le altre plance non vengono toccate. Se la plancia resta senza snapshot
    la sua voce esce dalla mappa, altrimenti `list_backups` potrebbe elencarla
    con zero versioni. Come il resto del modulo: scrittura atomica, mai
    un'eccezione verso il chiamante, esito booleano perche' chi chiama possa
    distinguere "rimosso" da "non e' stato possibile"."""
    data = _read_store(data_dir)
    if data is None:
        # Stesso fail-closed di save_backup: riscrivere un file che non
        # sappiamo leggere cancellerebbe gli snapshot delle altre plance.
        logger.error(
            "dashboard_backups: il file degli snapshot (%s) non e' leggibile o e' corrotto; "
            "lo snapshot ripristinato non e' stato consumato e restera' elencato.",
            _file(data_dir),
        )
        return False
    entries = data.get(url_path)
    if not isinstance(entries, list) or not entries:
        # Niente da consumare: non si riscrive nulla, cosi' un restore su una
        # plancia senza snapshot non tocca il file degli altri.
        return False
    last = entries[-1]
    if not isinstance(last, dict) or last.get("config") != config:
        # Fail-closed sull'identita': l'ultima entry non e' quella riapplicata.
        # Rimuoverla vorrebbe dire buttare via lo snapshot di qualcun altro;
        # meglio lasciare una voce di troppo nell'elenco, che si consuma da se'
        # al prossimo ripristino. Solo lato server: al chiamante torna False.
        logger.warning(
            "dashboard_backups: lo snapshot piu' recente di '%s' non e' quello appena "
            "ripristinato (probabile salvataggio concorrente durante la scrittura verso "
            "Home Assistant); non viene consumato nulla per non cancellare la via di "
            "ritorno di quella sostituzione.",
            url_path,
        )
        return False
    restanti = entries[:-1]
    if restanti:
        data[url_path] = restanti
    else:
        data.pop(url_path, None)
    return _write_store(data_dir, data)


def list_backups(data_dir: str) -> list[dict]:
    """Metadati degli snapshot esistenti, dal piu' recente al piu' vecchio.

    Una voce per plancia che ha almeno uno snapshot ripristinabile: url_path,
    istante dello snapshot piu' recente ("saved_at", None se quella voce e'
    anteriore all'introduzione del campo) e quanti snapshot ci sono ("count").

    Solo metadati: le config restano dentro lo store, non escono di qui.
    L'interfaccia le usa per decidere se mostrare l'undo in modo prominente o
    discreto; la soglia (recente vs storico) e' una scelta di presentazione e
    resta al frontend, qui si espone solo il quando.

    Permissiva come `latest_backup`: store assente o corrotto vale come
    'nessun backup', mai un'eccezione verso il chiamante."""
    voci = []
    for url_path, entries in _load(data_dir).items():
        if not isinstance(entries, list) or not entries:
            continue
        last = entries[-1]
        # Stesso criterio di `latest_backup`, di proposito: questo elenco alimenta
        # il pulsante Annulla e non deve promettere un undo che il restore poi nega.
        if not isinstance(last, dict) or not isinstance(last.get("config"), dict):
            continue
        saved_at = last.get("saved_at")
        if not isinstance(saved_at, str) or not saved_at:
            saved_at = None
        # Stesso criterio di ripristinabilita' usato qui sopra, non "quante
        # entry ci sono": un elenco che deve dire la verita' non puo' contare
        # versioni che il ripristino scarterebbe. Il frontend usa questo numero
        # per capire se, dopo un Annulla, resta qualcosa di ancora precedente.
        count = sum(
            1 for e in entries
            if isinstance(e, dict) and isinstance(e.get("config"), dict)
        )
        voci.append({"url_path": url_path, "saved_at": saved_at, "count": count})
    # Gli istanti sono ISO 8601 UTC ("+00:00" fisso): l'ordine lessicografico
    # coincide con quello cronologico. Le voci senza istante vanno in fondo:
    # precedono l'introduzione del campo, quindi sono le piu' vecchie che ci sono.
    con_istante = [v for v in voci if v["saved_at"] is not None]
    senza_istante = [v for v in voci if v["saved_at"] is None]
    con_istante.sort(key=lambda v: v["saved_at"], reverse=True)
    senza_istante.sort(key=lambda v: v["url_path"])
    return con_istante + senza_istante
