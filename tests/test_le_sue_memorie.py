"""Le sue memorie e `can_configure` (spec 2026-09-27 §4, security-constraints
«Task 3» 3.1-3.10 e ruling R-2.24).

Si prova con l'app VERA e il confine acceso, come `test_admission.py`: con le
valvole della suite accese un soggetto `sviluppo` vedrebbe tutto e ogni prova
sarebbe verde senza provare niente.

La prima sezione sono i PIN: cio' che un amministratore, un servizio firmato e
lo sviluppo ricevono da `GET /api/memories`, `GET /api/pending` e
`GET /api/chat-settings`, scritti e visti verdi sul codice di partenza
(416d8e36) prima di cambiare qualunque cosa.
"""
import os

import pytest
import pytest_asyncio

from conftest import firma, servizio_approvato
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.api.handlers_settings import _payload
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.keeper.store import AgendaStore
from tests.test_admission import _compose, _persona


@pytest.fixture(autouse=True)
def confine_vero(monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    yield
    close_all_stores()


#: Le impostazioni della chat delle prove: nomi e valori non di difetto, cosi'
#: una risposta che li perde o li scambia si vede.
SETTINGS = ChatSettings(name="Casa", system_prompt="sii breve", max_chat_turns=7)


@pytest_asyncio.fixture
async def casa(aiohttp_client, tmp_path):
    """L'opzione accesa, con gli archivi che `/api/pending` legge."""
    app = _compose(tmp_path, access=True)
    app["chat_settings"] = SETTINGS
    app["agenda"] = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    app["constructions"] = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    client = await aiohttp_client(app)
    yield client
    for store in ("memory_store", "servizi", "agenda", "constructions"):
        app[store].close()


def _semina(store):
    """Tre autori: Marta, l'amministratore e nessuno (un orfano)."""
    store.remember("la caldaia fa rumore", said_by="persona:u-marta")
    store.remember("il cane dorme in cucina", said_by="persona:u-admin")
    store.remember("un ricordo senza autore")
    store.remember("Marta preferisce 20 gradi", said_by="persona:u-marta")


_TUTTI = ["Marta preferisce 20 gradi", "il cane dorme in cucina",
          "la caldaia fa rumore", "un ricordo senza autore"]


# --- PIN: il comportamento di prima (verdi su 416d8e36) ----------------------

@pytest.mark.asyncio
async def test_PIN_l_amministratore_vede_ogni_ricordo_e_il_TOTALE_della_casa(casa):
    """3.6: tutti i ricordi, orfani compresi, i piu' recenti prima, e `total`
    e' il conto dell'archivio intero."""
    _semina(casa.app["memory_store"])

    corpo = await (await casa.get("/api/memories", headers=_persona("u-admin"))).json()

    assert [m["testo"] for m in corpo["memories"]] == [
        "Marta preferisce 20 gradi", "un ricordo senza autore",
        "il cane dorme in cucina", "la caldaia fa rumore"]
    assert (corpo["available"], corpo["total"], corpo["shown"]) == (True, 4, 4)


@pytest.mark.asyncio
async def test_PIN_oltre_il_taglio_l_amministratore_vede_il_TOTALE_vero(casa):
    """Il taglio dei 200 e il totale della casa: 250 + 5 + 250."""
    store = casa.app["memory_store"]
    for i in range(250):
        store.remember(f"vecchio {i}", said_by="persona:u-admin")
    for i in range(5):
        store.remember(f"di Marta {i}", said_by="persona:u-marta")
    for i in range(250):
        store.remember(f"nuovo {i}", said_by="persona:u-admin")

    corpo = await (await casa.get("/api/memories", headers=_persona("u-admin"))).json()

    assert (corpo["total"], corpo["shown"], len(corpo["memories"])) == (505, 200, 200)
    assert corpo["memories"][0]["testo"] == "nuovo 249"


@pytest.mark.asyncio
async def test_PIN_un_servizio_firmato_vede_ogni_ricordo(casa):
    """I servizi firmati non passano dal cancello: la lettura resta quella di
    prima, qualunque ruolo abbiano (il rischio del servizio `utente` e'
    dichiarato, security-constraints 5.9)."""
    _semina(casa.app["memory_store"])
    privata, pubblica = servizio_approvato(casa.app, "utente")

    risposta = await casa.get("/api/memories",
                              headers=firma(privata, pubblica, "GET", "/api/memories"))
    corpo = await risposta.json()

    assert sorted(m["testo"] for m in corpo["memories"]) == _TUTTI
    assert corpo["total"] == 4


@pytest.mark.asyncio
async def test_PIN_lo_sviluppo_vede_ogni_ricordo(casa, monkeypatch):
    _semina(casa.app["memory_store"])
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")

    corpo = await (await casa.get("/api/memories")).json()

    assert sorted(m["testo"] for m in corpo["memories"]) == _TUTTI
    assert corpo["total"] == 4


@pytest.mark.asyncio
async def test_PIN_i_pallini_dell_amministratore(casa):
    """I tre valori che l'amministratore riceve da `/api/pending`."""
    corpo = await (await casa.get("/api/pending", headers=_persona("u-admin"))).json()

    assert {k: corpo[k] for k in ("agenda_unread", "constructions_pending", "can_build")} \
        == {"agenda_unread": 0, "constructions_pending": 0, "can_build": True}


@pytest.mark.asyncio
async def test_PIN_le_impostazioni_dell_amministratore_sono_TUTTE(casa):
    """R-2.24, lato amministratore: la pagina Impostazioni riceve ogni campo,
    il prompt di default compreso."""
    corpo = await (await casa.get("/api/chat-settings", headers=_persona("u-admin"))).json()

    assert corpo == _payload(SETTINGS)
    assert set(corpo) == {"name", "system_prompt", "response_mode", "thinking_budget",
                          "max_chat_turns", "restrict_to_home", "retention_days",
                          "response_modes", "default_system_prompt"}
