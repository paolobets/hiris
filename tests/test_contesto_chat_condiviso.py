"""Task 1 della fetta "il ponte riceve il nucleo" (parita' A): una
composizione sola del contesto della chat -- estratta, non duplicata.

`compose_chat_context(app, data_dir)` (hiris/app/api/handlers_chat.py)
assorbe invariato il blocco che prima viveva solo dentro `handle_chat` (il
ramo sincrono): sessioni precedenti + nucleo (col suo degrado dichiarato) in
un'unica stringa. Il Task 2 mettera' la STESSA stringa nel job del ponte
(chat via abbonamento) -- se la ricopiasse invece di chiamarla, i due
percorsi avrebbero due composizioni destinate a divergere.

Questi test chiamano `compose_chat_context` DIRETTAMENTE, senza HTTP --
tests/test_chat_briefing.py gia' verifica lo stesso comportamento passando
per `POST /api/chat` (e resta verde, invariato: e' la prova che lo
spostamento non ha cambiato nulla per il ramo sincrono). Qui si verifica la
funzione condivisa in se', cosi' che il Task 2 possa fidarsene senza dover
rifare il giro HTTP.
"""
from datetime import UTC, datetime

import pytest

from hiris.app.api.handlers_chat import compose_chat_context
from hiris.app.chat_store import _TS_FMT, _get_store, close_all_stores
from tests.test_chat_briefing import _semina_casa


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


def _semina_sessione_chiusa(data_dir: str, riepilogo: str) -> None:
    """Stesso pattern di test_chat_briefing.py: una sessione GIA' chiusa
    (summary non nullo) inserita direttamente nella ChatStore del data_dir."""
    ts = datetime.now(UTC).strftime(_TS_FMT)
    store = _get_store(data_dir)
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, summary) "
        "VALUES(?,?,?,?)",
        ("closed-1", ts, ts, riepilogo),
    )
    store._conn.commit()


# ---------------------------------------------------------------------------
# ① Con archivi seminati, il contesto contiene sia il nucleo sia le sessioni
# precedenti -- le due fonti restano indipendenti (Task 3 di
# test_chat_briefing.py), qui verificato sulla funzione condivisa.
# ---------------------------------------------------------------------------

def test_con_archivi_seminati_contiene_nucleo_e_sessioni_precedenti(tmp_path):
    archivio_casa = _semina_casa(tmp_path)
    data_dir = str(tmp_path)
    _semina_sessione_chiusa(data_dir, "parlato di irrigazione del giardino")

    app = {"archivio_casa": archivio_casa}
    contesto = compose_chat_context(app, data_dir)

    assert "## La casa" in contesto
    assert "Cucina" in contesto
    assert "## Sessioni precedenti" in contesto
    assert "irrigazione del giardino" in contesto

    archivio_casa.close()


# ---------------------------------------------------------------------------
# ② Un `archivio_casa` che solleva (guasto, non semplicemente assente) non
# fa sollevare `compose_chat_context`: restituisce il testo di guasto,
# copiato alla lettera dal blocco pre-estrazione (stesso principio di
# test_chat_briefing.py::test_un_archivio_guasto_non_fa_rispondere_500_alla_chat).
# ---------------------------------------------------------------------------

def test_archivio_guasto_non_solleva_e_restituisce_il_testo_di_guasto(tmp_path):
    archivio_casa = _semina_casa(tmp_path)
    archivio_casa.close()  # la connessione sotto e' chiusa: ogni query solleva
    data_dir = str(tmp_path)

    app = {"archivio_casa": archivio_casa}
    contesto = compose_chat_context(app, data_dir)  # non deve sollevare

    assert "nucleo non si e' potuto comporre" in contesto
    assert "Non e' una casa vuota -- e' un guasto" in contesto


# ---------------------------------------------------------------------------
# ③ L'invariante su cui il Task 2 costruisce: mai la stringa vuota, nemmeno
# con un'app completamente vuota (nessun archivio wired) -- una stringa
# vuota il modello la leggerebbe come "casa vuota", non come "non ho potuto
# guardare".
# ---------------------------------------------------------------------------

def test_non_restituisce_mai_la_stringa_vuota_con_app_vuota(tmp_path):
    app: dict = {}
    contesto = compose_chat_context(app, str(tmp_path))

    assert contesto != ""
    # E' il nucleo degradato-ma-dichiarato (nessun archivio wired), non il
    # testo di guasto del test ②: qui l'archivio manca, non e' rotto.
    assert "Nessun piano registrato." in contesto
