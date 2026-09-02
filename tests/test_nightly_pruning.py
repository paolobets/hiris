"""fetta "Modelli" (2.0), Task 12: la potatura notturna (`server.py::
_run_retention`, cron alle 3) e' il PRIMO dei due lettori di
`giorni_conservazione` -- il secondo e' `chat_store.load_context`, pinnato
in `tests/test_chat_store.py`/`tests/test_api.py`.

Prima di questo task nessuna suite esercitava `_run_retention`: leggeva
`chat_store.HISTORY_RETENTION_DAYS`, una costante di modulo fissata
all'import, e nessun test costruiva uno scenario per verificarlo (si scopre
grep-ando `hiris_retention`/`_run_retention` nei test esistenti: zero
occorrenze prima di questo file). Il Task 12 lo rende un parametro letto da
`app["chat_settings"]` -- un valore che un PUT su
`/api/chat-settings` puo' cambiare a caldo -- ed e' proprio questo che
merita un pin: se il numero tornasse a essere catturato una volta sola
all'avvio (o a leggere una costante fissa), un utente che abbassa la
conservazione dalla pagina vedrebbe la potatura di stanotte ignorarlo.

Tecnica di `tests/test_websocket_startup.py`: si estrae dal sorgente VERO di
`_on_startup` il blocco che costruisce `_run_retention` (da
`from .chat_store import delete_old_messages as _delete_old_messages` alla
fine della funzione), isolato dal resto del boot (Supervisor/scheduler/
websocket)."""
import inspect
import textwrap
from datetime import UTC

from hiris.app import server
from hiris.app.chat_settings import ChatSettings


def _load_run_retention():
    src = inspect.getsource(server._on_startup)
    start_marker = "    from .chat_store import delete_old_messages as _delete_old_messages"
    end_marker = 'logger.info("Retention: deleted %d old chat messages", n)'
    start = src.index(start_marker)
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "def _check(app, data_dir, logger):\n" + textwrap.indent(body, "    ")
        + "\n    return _run_retention\n"
    )
    # `__package__` va dato esplicitamente: il blocco estratto contiene un
    # `from .chat_store import ...` relativo, e senza un pacchetto risolto
    # exec() lo rifiuta (KeyError su '__name__' assente da globals) prima
    # ancora di arrivare al corpo che vogliamo provare.
    namespace: dict = {"__package__": "hiris.app", "__name__": "hiris.app._test_potatura"}
    exec(compile(func_src, "<_on_startup potatura notturna>", "exec"), namespace)
    return namespace["_check"]


def test_la_potatura_legge_i_giorni_dall_archivio_non_da_una_costante_fissa(tmp_path, monkeypatch):
    """Il PUT che cambia `giorni_conservazione` a caldo riassegna
    `app["chat_settings"]` (handlers_settings.py): la potatura di
    stanotte deve vedere QUEL valore, non uno catturato all'avvio."""
    from datetime import datetime, timedelta

    from hiris.app.chat_store import append_messages, close_all_stores, load_history

    close_all_stores()
    data_dir = str(tmp_path)
    append_messages([{"role": "user", "content": "vecchio"}], data_dir)

    # Il messaggio "vecchio" e' scritto adesso (append_messages timestampa col
    # `now`): lo si retrodata a mano, cosi' la potatura ha davvero qualcosa da
    # potare quando i giorni configurati sono pochi.
    from hiris.app.chat_store import _get_store
    store = _get_store(data_dir)
    vecchio_ts = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute("UPDATE chat_messages SET timestamp = ?", (vecchio_ts,))
    store._conn.commit()

    check = _load_run_retention()
    import logging

    app = {"chat_settings": ChatSettings(retention_days=5)}
    run_retention = check(app=app, data_dir=data_dir, logger=logging.getLogger("test"))
    run_retention()
    assert load_history(data_dir) == [], "5 giorni: il messaggio di 10 giorni fa doveva sparire"

    # Ora lo stesso oggetto app, ma con la chiave riassegnata a un valore che
    # NON pota niente (com'e' dopo un PUT che alza la soglia): _run_retention
    # deve vederlo, non un 5 catturato alla costruzione della chiusura.
    append_messages([{"role": "user", "content": "recente"}], data_dir)
    store2 = _get_store(data_dir)
    vecchio_ts2 = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store2._conn.execute(
        "UPDATE chat_messages SET timestamp = ? WHERE content = ?",
        (vecchio_ts2, "recente"),
    )
    store2._conn.commit()
    app["chat_settings"] = ChatSettings(retention_days=0)
    run_retention()
    assert load_history(data_dir) == [{"role": "user", "content": "recente"}], (
        "0: la potatura non deve aver toccato niente"
    )
    close_all_stores()
