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
import json
import os
import re
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp.test_utils import make_mocked_request

from conftest import credenziale_ponte, firma, servizio_approvato
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.api.handlers_memory import handle_get_memories
from hiris.app.api.handlers_settings import _payload
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.chat_thread import subject_key_for
from hiris.app.keeper.store import AgendaStore
from hiris.app.memory.store import MemoryStore
from hiris.app.server import create_app
from tests.test_admission import _compose, _persona, live_routes


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


# --- le sue memorie (spec §4, security-constraints 3.1-3.8) ------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("utente,vede", [
    ("u-marta", ["Marta preferisce 20 gradi", "la caldaia fa rumore"]),
    ("u-lettore", []),
])
async def test_chi_non_amministra_vede_SOLO_i_suoi_ricordi(casa, utente, vede):
    """3.3, 3.4: il corpo porta solo le sue righe -- non quelle
    dell'amministratore, non gli orfani -- e il conto e' il suo (3.2)."""
    _semina(casa.app["memory_store"])

    risposta = await casa.get("/api/memories", headers=_persona(utente))
    corpo = await risposta.json()

    assert risposta.status == 200
    assert [m["testo"] for m in corpo["memories"]] == vede
    assert (corpo["available"], corpo["total"], corpo["shown"]) == (True, len(vede), len(vede))


@pytest.mark.asyncio
async def test_il_filtro_sta_PRIMA_del_taglio_e_il_totale_e_il_suo(casa):
    """3.1, 3.2: 250 dell'amministratore, 5 di Marta, 250 dell'amministratore.
    Filtrati dopo un `fetch(limit=200)` i suoi sparirebbero sotto il taglio, e
    un `total` della casa direbbe quanti ricordi hanno gli altri."""
    store = casa.app["memory_store"]
    for i in range(250):
        store.remember(f"vecchio {i}", said_by="persona:u-admin")
    for i in range(5):
        store.remember(f"di Marta {i}", said_by="persona:u-marta")
    for i in range(250):
        store.remember(f"nuovo {i}", said_by="persona:u-admin")

    corpo = await (await casa.get("/api/memories", headers=_persona("u-marta"))).json()

    assert [m["testo"] for m in corpo["memories"]] == [f"di Marta {i}" for i in range(4, -1, -1)]
    assert (corpo["total"], corpo["shown"]) == (5, 5)


def test_l_archivio_filtra_per_AUTORE_prima_del_limite(tmp_path):
    """3.1 sull'archivio: `said_by` nel WHERE, il limite dopo; `count` conta
    lo stesso insieme. Un autore che non ha scritto niente ha zero ricordi."""
    store = MemoryStore(str(tmp_path / "memoria.db"))
    try:
        for i in range(250):
            store.remember(f"vecchio {i}", said_by="persona:u-admin")
        for i in range(5):
            store.remember(f"di Marta {i}", said_by="persona:u-marta")
        store.remember("orfano")
        for i in range(250):
            store.remember(f"nuovo {i}", said_by="persona:u-admin")

        suoi = store.fetch(limit=200, said_by="persona:u-marta")

        assert [r["testo"] for r in suoi] == [f"di Marta {i}" for i in range(4, -1, -1)]
        assert store.count(said_by="persona:u-marta") == 5
        assert store.fetch(limit=3, said_by="persona:u-marta")[-1]["testo"] == "di Marta 2"
        assert store.fetch(said_by="persona:u-nessuno") == []
        assert store.count(said_by="persona:u-nessuno") == 0
        assert store.count() == 506
    finally:
        store.close()


@pytest.mark.asyncio
async def test_la_QUERY_non_allarga_il_filtro(casa):
    """3.7: il filtro lo decide il ruolo, mai la richiesta."""
    _semina(casa.app["memory_store"])

    corpo = await (await casa.get("/api/memories?all=1&said_by=persona:u-admin",
                                  headers=_persona("u-marta"))).json()

    assert [m["testo"] for m in corpo["memories"]] == [
        "Marta preferisce 20 gradi", "la caldaia fa rumore"]
    assert corpo["total"] == 2


def _richiesta(app, *, ruolo, soggetto):
    """Una richiesta come il cancello la lascia: per provare cio' che il
    cancello, dal vivo, non fa arrivare al gestore (un ruolo ignoto, una
    persona senza id)."""
    request = make_mocked_request("GET", "/api/memories", app=app)
    request["auth_via"] = "ingress"
    request["soggetto"] = soggetto
    request["ruolo"] = ruolo
    request["ruolo_letto"] = True
    return request


async def _memorie_dirette(tmp_path, *, ruolo, soggetto, extra=()):
    app = _compose(tmp_path, access=True)
    _semina(app["memory_store"])
    for testo, autore in extra:
        app["memory_store"].remember(testo, said_by=autore)
    try:
        risposta = await handle_get_memories(_richiesta(app, ruolo=ruolo, soggetto=soggetto))
        return json.loads(risposta.body)
    finally:
        app["memory_store"].close()
        app["servizi"].close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo", [None, "utente", "lettore", "sconosciuto"])
async def test_un_ruolo_che_non_e_AMMINISTRATORE_filtra(tmp_path, ruolo):
    """3.7: ogni ruolo che non e' `amministratore`, ignoto compreso, filtra."""
    corpo = await _memorie_dirette(
        tmp_path, ruolo=ruolo, soggetto={"specie": "persona", "id": "u-marta"})

    assert [m["testo"] for m in corpo["memories"]] == [
        "Marta preferisce 20 gradi", "la caldaia fa rumore"]


@pytest.mark.asyncio
async def test_una_persona_SENZA_ID_non_vede_nessun_ricordo(tmp_path):
    """3.3: la chiave di un soggetto senza id e' `persona:-`, e un ricordo
    scritto con quella chiave non e' di nessuno -- filtrare per lei darebbe a
    chiunque arrivi senza id i ricordi di tutti gli altri senza id."""
    corpo = await _memorie_dirette(
        tmp_path, ruolo="utente", soggetto={"specie": "persona", "id": None},
        extra=[("scritto senza id", "persona:-")])

    assert (corpo["memories"], corpo["total"], corpo["shown"]) == ([], 0, 0)


@pytest.mark.asyncio
async def test_il_ricordo_scritto_in_chat_e_quello_che_la_pagina_mostra(casa):
    """3.8: la chiave che il filtro confronta e' quella che scrive `remember`
    dello strumento (`subject_key_for` del soggetto del turno, in chat e dal
    ponte): un ricordo nato da Marta in chat lo ritrova Marta sulla pagina."""
    casa.app["memory_store"].remember(
        "la tapparella della sala si blocca",
        said_by=subject_key_for({"specie": "persona", "id": "u-marta"}))

    corpo = await (await casa.get("/api/memories", headers=_persona("u-marta"))).json()

    assert [m["testo"] for m in corpo["memories"]] == ["la tapparella della sala si blocca"]


def test_nessuna_rotta_per_il_SINGOLO_ricordo_in_lettura():
    """3.5: la pagina non legge un ricordo per id, e una rotta che lo facesse
    sarebbe un oracolo sull'esistenza dei ricordi altrui."""
    rotte = live_routes(create_app())

    assert ("GET", "/api/memories/{id}") not in rotte
    assert ("PATCH", "/api/memories/{id}") in rotte


# --- can_configure (spec §4, security-constraints 3.9-3.10) -------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("utente,puo", [
    ("u-admin", True), ("u-marta", False), ("u-lettore", False)])
async def test_can_configure_e_VERO_solo_per_l_amministratore(casa, utente, puo):
    corpo = await (await casa.get("/api/pending", headers=_persona(utente))).json()

    assert corpo["can_configure"] is puo
    assert corpo["can_build"] is puo


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo,puo", [
    ("amministratore", True), ("utente", False), ("lettore", False)])
async def test_can_configure_per_un_SERVIZIO_viene_dalla_sua_approvazione(casa, ruolo, puo):
    privata, pubblica = servizio_approvato(casa.app, ruolo)

    risposta = await casa.get("/api/pending",
                              headers=firma(privata, pubblica, "GET", "/api/pending"))

    assert (await risposta.json())["can_configure"] is puo


@pytest.mark.asyncio
async def test_can_configure_per_il_PONTE_e_falso(casa):
    """Un turno servito dal ponte non e' nessuno che configuri."""
    risposta = await casa.get("/api/pending",
                              headers=credenziale_ponte(casa.app, "segreto-di-turno"))

    assert (await risposta.json())["can_configure"] is False


@pytest.mark.asyncio
async def test_can_configure_nello_SVILUPPO_e_vero(casa, monkeypatch):
    """Lo sviluppo non si restringe per ruolo (ruling del Task 2, `denies`):
    con l'autenticazione spenta le pagine di configurazione restano quelle di
    oggi."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")

    corpo = await (await casa.get("/api/pending")).json()

    assert corpo["can_configure"] is True


@pytest.mark.asyncio
async def test_il_ruolo_si_legge_UNA_volta_per_richiesta(casa):
    """Extra 1: il ruolo lo legge il cancello, e `/api/pending` lo prende
    dalla richiesta. Con la copia dei ruoli scaduta ad ogni lettura, una
    seconda domanda nel gestore farebbe due letture per richiesta."""
    app = casa.app
    app["ha_client"].users.reset_mock()
    ruoli = app["ruoli"]

    class _SempreScaduta(dict):
        def __getitem__(self, key):
            return 0.0 if key == "quando" else super().__getitem__(key)

    app["ruoli"] = _SempreScaduta(ruoli)
    try:
        risposta = await casa.get("/api/pending", headers=_persona("u-marta"))
    finally:
        app["ruoli"] = ruoli

    assert risposta.status == 200
    assert app["ha_client"].users.await_count == 1


# --- le impostazioni della chat (ruling R-2.24) -------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("utente", ["u-marta", "u-lettore"])
async def test_a_chi_non_amministra_solo_cio_che_la_CHAT_usa(casa, utente):
    """R-2.24: `chat/agents.js::loadSettings` legge `name` e
    `max_chat_turns`, e nient'altro. Il prompt di sistema, quello di difetto,
    la conservazione e il resto restano alla pagina Impostazioni."""
    corpo = await (await casa.get("/api/chat-settings", headers=_persona(utente))).json()

    assert corpo == {"name": "Casa", "max_chat_turns": 7}


@pytest.mark.asyncio
async def test_un_servizio_firmato_riceve_le_impostazioni_come_prima(casa):
    """Il cancello e la riduzione valgono per le persone dall'ingress: i
    servizi hanno le loro regole (security-constraints 5.9, dichiarato)."""
    privata, pubblica = servizio_approvato(casa.app, "utente")

    risposta = await casa.get("/api/chat-settings",
                              headers=firma(privata, pubblica, "GET", "/api/chat-settings"))

    assert await risposta.json() == _payload(SETTINGS)


def test_la_riduzione_e_cio_che_la_CHAT_legge():
    """Il corpo ridotto e' cio' che la chat legge davvero: se `agents.js`
    comincia a leggere un campo in piu', questa prova lo dice prima che la
    chat di chi non amministra lo trovi vuoto. Si leggono gli accessi a
    `data.` dentro `loadSettings`, la sola funzione che chiama la rotta."""
    from hiris.app.api.handlers_settings import CHAT_PAGE_FIELDS

    agents = (Path(__file__).parents[1] / "hiris/app/static/chat/agents.js").read_text(
        encoding="utf-8")
    corpo = agents[agents.index("async function loadSettings"):]
    corpo = corpo[:corpo.index("\n  }\n")]

    assert "api/chat-settings" in corpo
    assert set(re.findall(r"\bdata\.(\w+)", corpo)) == set(CHAT_PAGE_FIELDS)
