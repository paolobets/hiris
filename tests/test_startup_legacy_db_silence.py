"""Il silenzio dichiarato su `chatbots.json`: l'unico rimasto.

Un «silenzio dichiarato» e' una riga di registro che l'avvio scrive quando
incontra un file di un'installazione precedente che nessun codice legge piu'.
Erano dodici. Undici riguardavano gli archivi dismessi, e dal 23/09/2026
`cancella_residui` quei file li cancella: i loro annunci dicevano «il file
resta su disco, intatto» subito prima della cancellazione, o stavano dopo e
non giravano mai. Sono usciti il 02/10/2026 con le ventidue prove che li
fissavano; che l'avvio non prometta piu' cio' che non mantiene lo prova
`tests/test_residui_cancellati.py`, eseguendo l'avvio vero.

Resta `chatbots.json` (con il suo predecessore `agents.json`): non e' fra i
residui che si cancellano, per decisione del proprietario, e il suo annuncio
dice il vero.

Il blocco si estrae dal sorgente REALE di `_on_startup` (`inspect.getsource`)
invece di tenerne una copia a mano che potrebbe divergere in silenzio dal
codice spedito.
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
    assert not caplog.records, (
        "ne' chatbots.json ne' agents.json sul disco -- nessun log deve uscire"
    )
