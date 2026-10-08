"""fetta "Modelli" (2.0), Task 12: la potatura notturna (`conservazione.nightly`,
cron alle 3; fino alla Tappa 8 `server.py::_run_retention`) e' il PRIMO dei due lettori di
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

Dal 03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'») la prova
non ritaglia piu' il blocco dal sorgente di `_on_startup` per eseguirlo: avvia
l'app davvero (`fotografia_porte.mounted`) e fa girare il lavoro
`hiris_retention` che lo schedulatore ha registrato. Un blocco spostato non la
rompe piu'; un lavoro che non pota, si'.

Dalla Tappa 8 (Task 6, D-27) l'archivio della chat e' `app["chat_store"]`, e
la finestra la chiede alle impostazioni a ogni potatura (`read_retention_days`)."""
import sys
from datetime import UTC
from pathlib import Path

import pytest

from hiris.app.chat_settings import ChatSettings
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte


@pytest.mark.asyncio
async def test_la_potatura_legge_i_giorni_dall_archivio_non_da_una_costante_fissa(tmp_path):
    """Il PUT che cambia `giorni_conservazione` a caldo riassegna
    `app["chat_settings"]` (handlers_settings.py): la potatura di
    stanotte deve vedere QUEL valore, non uno catturato all'avvio.

    Mutazione ESEGUITA (03/10/2026): i giorni letti una volta sola all'avvio,
    fuori da `_run_retention` -- rossa. Rieseguita l'08/10/2026 sul codice
    nuovo: `read_retention_days` costruito col valore dell'avvio invece che
    con la lettura di `app["chat_settings"]` -- rossa."""
    from datetime import datetime, timedelta

    from hiris.app.chat_store import append_messages, close_all_stores, load_history
    from hiris.app.chat_thread import ChatThread

    # La potatura e' della casa, non di un filo (spec §3): qui un filo solo
    # basta a vedere che cosa resta.
    T = ChatThread("persona:paolo", "pannello")

    close_all_stores()
    data_dir = str(tmp_path)
    append_messages([{"role": "user", "content": "vecchio"}], data_dir, thread=T)

    # Il messaggio "vecchio" e' scritto adesso (append_messages timestampa col
    # `now`): lo si retrodata a mano, cosi' la potatura ha davvero qualcosa da
    # potare quando i giorni configurati sono pochi.
    from hiris.app.chat_store import _get_store
    store = _get_store(data_dir)
    vecchio_ts = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute("UPDATE chat_messages SET timestamp = ?", (vecchio_ts,))
    store._conn.commit()

    async with fotografia_porte.mounted(synthetic_inputs(), data_dir) as app:
        run_retention = app["scheduler"].get_job("hiris_retention").func
        app["chat_settings"] = ChatSettings(retention_days=5)
        await run_retention()
        assert load_history(data_dir, thread=T) == [], (
            "5 giorni: il messaggio di 10 giorni fa doveva sparire")

        # Ora lo stesso oggetto app, ma con la chiave riassegnata a un valore che
        # NON pota niente (com'e' dopo un PUT che alza la soglia): la potatura
        # deve vederlo, non un 5 catturato alla costruzione della chiusura.
        append_messages([{"role": "user", "content": "recente"}], data_dir, thread=T)
        store2 = _get_store(data_dir)
        vecchio_ts2 = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store2._conn.execute(
            "UPDATE chat_messages SET timestamp = ? WHERE content = ?",
            (vecchio_ts2, "recente"),
        )
        store2._conn.commit()
        app["chat_settings"] = ChatSettings(retention_days=0)
        await run_retention()
        assert load_history(data_dir, thread=T) == [{"role": "user", "content": "recente"}], (
            "0: la potatura non deve aver toccato niente"
        )
    close_all_stores()
