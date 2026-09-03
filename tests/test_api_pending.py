"""`GET /api/pending` e `POST /api/agenda/read`.

`test_i_due_numeri_contano_cose_diverse` e' la prova centrale, e la mutazione
che deve uccidere e' quella che verrebbe scritta per SIMMETRIA: contare i
sospesi anche sugli Impegni. E' l'implementazione che sembra coerente ed e'
sbagliata -- un impegno in sospeso non aspetta l'utente, aspetta l'ora
(`docs/design/2026-09-03-i-menu-esecutivi.md` §4.1). Coi numeri scelti qui
sotto la versione sbagliata risponde 4 e 5 invece di 4 e 2, quindi la prova
la vede.

`test_senza_archivio_e_503` e' l'altra che porta peso, ed e' la lezione del
pallino MORTO: quello di prima contava le segnalazioni del Brain leggendo una
rotta uscita con la fetta E3, e mostrava `0` quando quella rotta rispondeva
404 (la lapide sta in `hiris-config.css:871`). Diceva «non c'e' niente da
guardare» quando la verita' era «non lo so». Chi consuma questa rotta puo'
distinguere le due cose solo se gliele distingue il codice HTTP.

Fixture `client`: l'app VERA (`create_app`), non un'app montata a mano con la
sola rotta in prova -- stesso ragionamento di `test_agenda_api.py`. La rotta
deve passare dagli stessi middleware di ogni altra, o il test non direbbe
niente su cio' che accade in produzione.
"""
import os

import pytest
import pytest_asyncio

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.chat_store import close_all_stores
from hiris.app.keeper.store import AgendaStore
from hiris.app.server import create_app

# Fixture generica (annulla la valvola `HIRIS_ALLOW_NO_CSRF` che conftest.py
# mette per l'intera suite): stesso riuso cross-file gia' praticato da
# `test_agenda_api.py` e `test_constructions_api.py`.
from tests.test_settings_api import csrf_stretto  # noqa: F401

ADESSO = 1_756_000_000.0


@pytest.fixture(autouse=True)
def reset_chat_stores():
    """Chiude le connessioni SQLite dopo ogni test (file-lock su Windows)."""
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app["agenda"] = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    app["constructions"] = ConstructionStore(
        os.path.join(str(tmp_path), "costruzioni.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app["agenda"].close()
    app["constructions"].close()


@pytest_asyncio.fixture
async def client_nudo(aiohttp_client):
    """L'app vera NUDA: i due archivi non ci sono.

    `on_startup.clear()` toglie il montaggio che li costruirebbe, quindi
    `app.get("agenda")` risponde `None` da solo: e' la stessa condizione in
    cui si trova l'add-on quando un archivio non si apre. Non si spegne un
    archivio sull'app gia' avviata -- aiohttp non lo permette, e sarebbe
    comunque una condizione che in produzione non esiste.
    """
    app = create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


def _promessa(archivio, n: int) -> str:
    return archivio.create(
        {"specie": "chiedi", "frase": f"promessa {n}",
         "quando_ts": ADESSO + 3600 + n, "domanda": "e' aumentata?"},
        now=ADESSO)["promessa"]["id"]


def _proposta(archivio, n: int) -> str:
    return archivio.propose(
        operation="crea", domain="automation", key=f"k{n}", actor="chat",
        exchange="t1", phrase="apri le tapparelle all'alba", prima=None,
        dopo={"id": f"k{n}", "alias": "Tapparelle"}, helper=[],
        preview="Creo un'automazione.", now=ADESSO)["id"]


@pytest.mark.asyncio
async def test_i_due_numeri_contano_cose_diverse(client):
    """Impegni conta gli esiti NON LETTI; Proposte conta i sospesi.

    I sette impegni sono scelti apposta perche' i due modi di contare diano
    numeri diversi: cinque restano in sospeso e due si concludono (disdette)
    senza che nessuno le legga. Chi contasse i sospesi anche qui direbbe 5.
    """
    agenda = client.app["agenda"]
    costruzioni = client.app["constructions"]

    identificatori = [_promessa(agenda, n) for n in range(7)]
    for ident in identificatori[:2]:
        agenda.cancel(ident, now=ADESSO + 1)

    for n in range(4):
        ident = _proposta(costruzioni, n)
        if n == 3:
            # `in_corso` conta come sospesa: e' rivendicata, non decisa.
            costruzioni.claim(ident, now=ADESSO + 1)

    risposta = await client.get("/api/pending")
    assert risposta.status == 200
    assert await risposta.json() == {"agenda_unread": 2, "constructions_pending": 4}


@pytest.mark.asyncio
async def test_senza_archivio_e_503(client_nudo):
    """«Non lo so» non e' «non c'e' niente»: 503, mai un 200 con degli zeri."""
    risposta = await client_nudo.get("/api/pending")
    assert risposta.status == 503
    assert "agenda_unread" not in await risposta.json()


@pytest.mark.asyncio
async def test_segna_solo_gli_id_passati(client):
    """La pagina segna cio' che ha MOSTRATO, non «tutto il non letto»."""
    agenda = client.app["agenda"]
    identificatori = [_promessa(agenda, n) for n in range(3)]
    for ident in identificatori:
        agenda.cancel(ident, now=ADESSO + 1)
    assert agenda.count_unread() == 3

    risposta = await client.post("/api/agenda/read",
                                 json={"ids": identificatori[:2]},
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert (await risposta.json())["marked"] == 2
    assert agenda.count_unread() == 1


@pytest.mark.asyncio
async def test_non_segna_una_in_sospeso(client):
    """Il segno vale sugli ESITI, non sugli impegni.

    Una promessa in sospeso ha `esito_letto_ts` NULL -- e' il suo stato
    normale, non un esito da leggere. Se `mark_read` filtrasse sul solo
    campo nullo, marcarla la toglierebbe da una sezione in cui non e' mai
    stata, e soprattutto le scriverebbe addosso un'ora di lettura falsa.
    """
    agenda = client.app["agenda"]
    ident = _promessa(agenda, 0)

    risposta = await client.post("/api/agenda/read", json={"ids": [ident]},
                                 headers={"X-Requested-With": "fetch"})
    assert (await risposta.json())["marked"] == 0
    assert agenda.read(ident)["esito_letto_ts"] is None


@pytest.mark.asyncio
async def test_una_lista_che_non_e_una_lista_e_400(client):
    """Il corpo sbagliato e' un errore d'ingresso, non un 500."""
    risposta = await client.post("/api/agenda/read", json={"ids": "p1"},
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 400


@pytest.mark.asyncio
async def test_post_senza_x_requested_with_e_403_e_non_segna(client, csrf_stretto):
    """La scrittura cross-site non passa, e non lascia traccia.

    Non basta il 403: si verifica anche che l'archivio sia intatto. Una
    rotta registrata prima del middleware risponderebbe 403 e avrebbe gia'
    scritto.
    """
    agenda = client.app["agenda"]
    ident = _promessa(agenda, 0)
    agenda.cancel(ident, now=ADESSO + 1)

    risposta = await client.post("/api/agenda/read", json={"ids": [ident]})
    assert risposta.status == 403
    assert agenda.count_unread() == 1
