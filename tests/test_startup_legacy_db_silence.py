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
        "advisory_db_path", "from .brain.portrait_store import PortraitStore",
    )
    (tmp_path / "advisory.db").write_text("x")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_advisory_silence"))
    assert any("advisory.db" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_advisory_db_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "advisory_db_path", "from .brain.portrait_store import PortraitStore",
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
        "dashboard_backups_path", '_apprise_raw = os.environ.get("APPRISE_URLS"',
    )
    (tmp_path / "dashboard_backups.json").write_text("{}")
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_dashboard_backups_silence"))
    assert any("dashboard_backups.json" in rec.message and "installazione precedente" in rec.message
               for rec in caplog.records)


def test_dashboard_backups_json_silent_when_file_absent(tmp_path, caplog):
    check = _load_silence_check(
        "dashboard_backups_path", '_apprise_raw = os.environ.get("APPRISE_URLS"',
    )
    with caplog.at_level("INFO"):
        check(str(tmp_path), __import__("os"), logging.getLogger("test_dashboard_backups_silence"))
    assert not caplog.records, "nessun dashboard_backups.json sul disco -- nessun log deve uscire"
