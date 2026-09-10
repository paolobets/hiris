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

    app = {"home_space_store": archivio_casa}
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

def test_un_archivio_chiuso_non_ferma_piu_il_nucleo(tmp_path):
    """**Cio' che la fetta del 10/09/2026 ha comprato, misurato qui.**

    Prima l'anagrafe viveva su disco: chiudere la connessione voleva dire
    nucleo non componibile, e la prova verificava che almeno lo DICESSE invece
    di sollevare. Adesso l'anagrafe e il comportamento si tengono a memoria, e
    un archivio chiuso -- che ormai custodisce solo le plance e la cornice --
    non ha piu' niente da rompere: il nucleo si compone lo stesso, con la casa
    dentro.

    Mutazione che la uccide: rimettere la lettura dell'anagrafe dietro
    l'archivio (il nucleo tornerebbe a essere il testo di guasto).
    """
    home_space = _semina_casa(tmp_path)
    home_space.close()  # la connessione sotto e' chiusa: ogni query SQL solleva
    data_dir = str(tmp_path)

    app = {"home_space_store": home_space}
    contesto = compose_chat_context(app, data_dir)  # non deve sollevare

    assert "nucleo non si e' potuto comporre" not in contesto
    assert "Cucina" in contesto

def test_non_restituisce_mai_la_stringa_vuota_con_app_vuota(tmp_path):
    app: dict = {}
    contesto = compose_chat_context(app, str(tmp_path))

    assert contesto != ""
    # E' il nucleo degradato-ma-dichiarato (nessun archivio wired), non il
    # testo di guasto del test ②: qui l'archivio manca, non e' rotto.
    assert "Nessun piano registrato." in contesto
