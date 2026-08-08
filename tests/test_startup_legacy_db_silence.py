"""fetta E3 Task 9 (rilievo 3 della review indipendente sul blocco 5-8):
`server.py:1169-1177` (`advisory.db`) e `server.py:1224-1232` (`sentinel.db`)
sono due "silenzi dichiarati" -- un log esplicito quando un file di
un'installazione precedente non ha piu' nessun lettore/scrittore -- ma
nessun test li difendeva: grep su `tests/` trovava zero riferimenti a
"advisory.db"/"sentinel.db" prima di questo file. Cancellarli lasciava la
suite verde.

Come `test_reasoning_sweep_chat_skip.py` fa per `_reasoning_sweep`, questo
file estrae il sorgente REALE di `_on_startup` via `inspect.getsource` invece
di mantenere una copia a mano che potrebbe divergere in silenzio dal codice
spedito. A differenza di `_reasoning_sweep` (gia' una funzione nidificata),
i due blocchi qui sono istruzioni inline dentro `_on_startup`: li isoliamo
per marcatore di testo e li incapsuliamo in una funzione sintetica minima
che riceve `data_dir`/`os`/`logger` dall'esterno -- il corpo eseguito e'
comunque quello vero, non una parafrasi.

fetta E3 Task 10: le proposte escono per intero e lasciano lo stesso genere
di silenzio dichiarato per `proposals.db` e `dashboard_backups.json`
(`server.py`, appena dopo dove viveva la ProposalStore) -- pinnato qui con
lo stesso metodo, invece di un nuovo file.

fetta E3 Task 11: l'HealthMonitor esce (col SupervisorClient, suo ultimo
lettore) e lascia lo stesso genere di silenzio dichiarato per
`ha_health.json` (`server.py`, dove viveva la costruzione dell'HealthMonitor)
-- pinnato qui con lo stesso metodo.

fetta E3 Task 12: il ritratto esce per intero (portrait.py, portrait_store.py,
il job schedulato "hiris_portrait_observe") e lascia lo stesso genere di
silenzio dichiarato per `portrait.db` (`server.py`, dove viveva la
costruzione di PortraitStore) -- pinnato qui con lo stesso metodo. Il marcatore
di chiusura del blocco advisory.db (`next_marker`) cambia di conseguenza: non
punta piu' all'import di PortraitStore (uscito), ma all'inizio del nuovo
blocco portrait.db.
"""
import inspect
import logging
import textwrap

from hiris.app import server


def _load_silence_check(path_literal: str, next_marker: str):
    """Estrae dal sorgente vero di `_on_startup` il blocco che controlla
    `os.path.exists(..., "<path_literal>")` e logga se presente, fino a
    (esclusa) `next_marker`. Lo incapsula in `def _check(data_dir, os,
    logger): ...` cosi' da poterlo eseguire isolato."""
    src = inspect.getsource(server._on_startup)
    start = src.index(f'    _{path_literal}')
    end = src.index(next_marker, start)
    body = textwrap.dedent(src[start:end])
    func_src = "def _check(data_dir, os, logger):\n" + textwrap.indent(body, "    ")
    namespace: dict = {}
    exec(compile(func_src, f"<_on_startup {path_literal} silence check>", "exec"), namespace)
    return namespace["_check"]


def test_advisory_db_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "advisory_db_path", '_portrait_db_path = os.path.join(data_dir, "portrait.db")',
    )
    (tmp_path / "advisory.db").write_text("x")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_advisory_silence"))
    assert any("advisory.db" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_advisory_db_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "advisory_db_path", '_portrait_db_path = os.path.join(data_dir, "portrait.db")',
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_advisory_silence"))
    assert not caplog.records, "nessun advisory.db sul disco -- nessun log deve uscire"


def test_sentinel_db_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "sentinel_db_path", "# ── Ponte push (Piano A, fetta 3):",
    )
    (tmp_path / "sentinel.db").write_text("x")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_sentinel_silence"))
    assert any("sentinel.db" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_sentinel_db_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "sentinel_db_path", "# ── Ponte push (Piano A, fetta 3):",
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_sentinel_silence"))
    assert not caplog.records, "nessun sentinel.db sul disco -- nessun log deve uscire"


# fetta E3 Task 10: le proposte escono per intero (ProposalStore,
# proxy/proposta_config.py, proxy/dashboard_backups.py, le rotte
# /api/proposals*, /api/dashboards*). Stessa disciplina di advisory.db/
# sentinel.db: un proposals.db o un dashboard_backups.json ereditati da
# un'installazione precedente non vengono cancellati (mai dati utente in
# /data) ma il loro incontro va dichiarato nel log, non muto.


def test_proposals_db_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "proposals_db_path",
        '_dashboard_backups_path = os.path.join(data_dir, "dashboard_backups.json")',
    )
    (tmp_path / "proposals.db").write_text("x")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_proposals_silence"))
    assert any("proposals.db" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_proposals_db_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "proposals_db_path",
        '_dashboard_backups_path = os.path.join(data_dir, "dashboard_backups.json")',
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_proposals_silence"))
    assert not caplog.records, "nessun proposals.db sul disco -- nessun log deve uscire"


def test_dashboard_backups_json_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "dashboard_backups_path", 'app["theme"] = os.environ.get("THEME"',
    )
    (tmp_path / "dashboard_backups.json").write_text("{}")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_dashboard_backups_silence"))
    assert any("dashboard_backups.json" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_dashboard_backups_json_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "dashboard_backups_path", 'app["theme"] = os.environ.get("THEME"',
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_dashboard_backups_silence"))
    assert not caplog.records, "nessun dashboard_backups.json sul disco -- nessun log deve uscire"


# fetta E3 Task 11: l'HealthMonitor esce (col SupervisorClient, suo ultimo
# lettore rimasto) e lascia lo stesso genere di silenzio dichiarato per
# `ha_health.json`.


def test_ha_health_json_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "ha_health_path", "# fetta E3 Task 10: le proposte escono per intero",
    )
    (tmp_path / "ha_health.json").write_text("{}")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_ha_health_silence"))
    assert any("ha_health.json" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_ha_health_json_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "ha_health_path", "# fetta E3 Task 10: le proposte escono per intero",
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_ha_health_silence"))
    assert not caplog.records, "nessun ha_health.json sul disco -- nessun log deve uscire"


# fetta E3 Task 12: il ritratto esce per intero (portrait.py,
# portrait_store.py, il job schedulato "hiris_portrait_observe") e lascia lo
# stesso genere di silenzio dichiarato per `portrait.db`.


def test_portrait_db_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "portrait_db_path", "# fetta E3 Task 7 (",
    )
    (tmp_path / "portrait.db").write_text("x")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_portrait_silence"))
    assert any("portrait.db" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_portrait_db_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "portrait_db_path", "# fetta E3 Task 7 (",
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_portrait_silence"))
    assert not caplog.records, "nessun portrait.db sul disco -- nessun log deve uscire"


# Review finale fetta E3, Minor: `tasks.json` (Task 9, il TaskEngine) aveva la
# stessa forma di silenzio degli altri sei file ma la nota diceva "nessun log
# e' possibile" -- falso, corretto aggiungendo lo stesso genere di silenzio
# dichiarato, pinnato qui con lo stesso metodo.


def test_tasks_json_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "tasks_json_path", 'api_key = os.environ.get("CLAUDE_API_KEY"',
    )
    (tmp_path / "tasks.json").write_text("{}")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_tasks_json_silence"))
    assert any("tasks.json" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_tasks_json_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "tasks_json_path", 'api_key = os.environ.get("CLAUDE_API_KEY"',
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_tasks_json_silence"))
    assert not caplog.records, "nessun tasks.json sul disco -- nessun log deve uscire"


# fetta E4 Task 4 ("un bot solo"): l'entita' Chatbot esce per intero
# (chatbot_engine.py, cancellato) sostituita dalle impostazioni della chat
# (impostazioni_chat.py). Un chatbots.json (o il suo predecessore
# agents.json, la stessa coppia che ChatbotEngine._load migrava) di
# un'installazione precedente non ha piu' nessun lettore/scrittore -- stessa
# disciplina degli altri sette file sopra, pinnata qui con lo stesso metodo.


def test_chatbots_json_presence_logged_when_file_exists(tmp_path, caplog):
    check = _load_silence_check(
        "chatbots_json_path", "scheduler = AsyncIOScheduler()",
    )
    (tmp_path / "chatbots.json").write_text("{}")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_chatbots_json_silence"))
    assert any("chatbots.json" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_agents_json_legacy_presence_logged_when_file_exists(tmp_path, caplog):
    """Il predecessore di chatbots.json (prima della rinomina SP-4 Fase A)
    deve dichiararsi anche da solo, senza che chatbots.json esista."""
    check = _load_silence_check(
        "chatbots_json_path", "scheduler = AsyncIOScheduler()",
    )
    (tmp_path / "agents.json").write_text("{}")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_agents_json_legacy_silence"))
    assert any("chatbots.json" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_chatbots_json_silent_when_both_files_absent(tmp_path, caplog):
    check = _load_silence_check(
        "chatbots_json_path", "scheduler = AsyncIOScheduler()",
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_chatbots_json_silence"))
    assert not caplog.records, "ne' chatbots.json ne' agents.json sul disco -- nessun log deve uscire"
