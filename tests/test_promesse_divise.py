"""Le promesse sono di chi le chiede (fetta «il seguito delle chat divise», Task 2).

Spec `docs/design/2026-09-26-il-seguito-delle-chat-divise.md` §2: una promessa
porta il filo di chi l'ha chiesta; `agenda`, `cancel`, le rotte degli Impegni,
la cronaca di un'esecuzione legata a una promessa e il pallino vedono e
toccano SOLO quel filo; un id di un altro filo risponde come uno inesistente.
Il recapito non lo sceglie piu' il modello. Le promesse di prima si adottano
col proprietario, come la cronologia.

Il confine vero qui non c'e': lo sostituisce `_finto_confine`, che scrive
`soggetto`/`auth_via` come fa `middleware_internal_auth`, leggendo CHI
dall'intestazione di prova `X-Chi`. Le prove guardano il fatto: lo status, il
corpo byte per byte, cio' che sta nell'archivio.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

import pytest
import pytest_asyncio
from aiohttp import web

from hiris.app.action.journal import Journal
from hiris.app.api.handlers_agenda import (
    handle_delete_promise,
    handle_get_agenda,
    handle_get_execution,
    handle_mark_read,
)
from hiris.app.api.handlers_chat_history import handle_get_chat_history
from hiris.app.api.handlers_pending import handle_get_pending
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.chat_thread import ChatThread
from hiris.app.home_space.tools import PROMISE_TOOL_DEF, ToolDispatcher
from hiris.app.keeper import promise as promise_module
from hiris.app.keeper.recipient import _REASON_LINK_PERSON
from hiris.app.keeper.store import AgendaStore
from tests.test_mcp_chat_thread import rotta as rotta_chat  # noqa: F401

PAOLO = ChatThread("persona:paolo", "pannello")
MARTA = ChatThread("persona:marta", "pannello")
PAOLO_SOGGETTO = {"specie": "persona", "id": "paolo", "nome": "Paolo", "utente": "paolo"}
MARTA_SOGGETTO = {"specie": "persona", "id": "marta", "nome": "Marta", "utente": "marta"}


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


@pytest.fixture()
def archivio(tmp_path):
    a = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _chiedi(n: int = 0, *, adesso: float) -> dict:
    return {"specie": "chiedi", "frase": f"promessa {n}",
            "quando_ts": adesso + 3600 + n, "domanda": "e' aumentata?"}


def _crea(archivio, thread, n: int = 0, *, adesso: float | None = None) -> str:
    adesso = time.time() if adesso is None else adesso
    esito = archivio.create(_chiedi(n, adesso=adesso), thread=thread, now=adesso)
    assert "errore" not in esito, esito
    return esito["promessa"]["id"]


def _semina_orfana(archivio, *, adesso: float, recapito: str | None = None) -> str:
    """Una promessa di PRIMA delle promesse divise: senza filo, come le lascia
    la migrazione. Scritta col SQL perche' `create` non sa piu' farla nascere
    cosi' -- ed e' giusto."""
    archivio._conn.execute(
        "INSERT INTO promesse(id,specie,frase,quando_ts,domanda,recapito,stato,"
        "nata_ts) VALUES('vecchia','chiedi','detta prima',?,'?',?,'in_attesa',?)",
        (adesso + 3600, recapito, adesso))
    archivio._conn.commit()
    return "vecchia"


# ---------------------------------------------------------------------------
# L'archivio
# ---------------------------------------------------------------------------

def test_ognuno_vede_solo_le_sue(archivio):
    adesso = time.time()
    paolo_id = _crea(archivio, PAOLO, 0, adesso=adesso)
    marta_id = _crea(archivio, MARTA, 1, adesso=adesso)

    assert [p["id"] for p in archivio.list(thread=PAOLO)] == [paolo_id]
    assert [p["id"] for p in archivio.list(thread=MARTA, solo_in_sospeso=True)] == [marta_id]
    assert archivio.read(paolo_id)["thread"] == PAOLO


def test_lo_stesso_soggetto_da_un_altro_ingresso_e_un_altro_filo(archivio):
    """Il filo e' la COPPIA (soggetto, ingresso), come per la chat."""
    _crea(archivio, PAOLO, adesso=time.time())
    assert archivio.list(thread=ChatThread("persona:paolo", "firma")) == []


def test_un_soggetto_con_l_apice_non_rompe_la_query(archivio):
    """2.14: il filo entra nella SQL come parametro, mai incollato nel testo."""
    strano = ChatThread("persona:o'brien\") OR 1=1 --", "pannello")
    ident = _crea(archivio, strano, adesso=time.time())
    _crea(archivio, PAOLO, 1, adesso=time.time())
    assert [p["id"] for p in archivio.list(thread=strano)] == [ident]


def test_create_non_scrive_mai_il_recapito(archivio):
    """2.4: la colonna resta nello schema per le righe vecchie, ma non si
    scrive piu' -- nemmeno se qualcuno la mette nei dati."""
    adesso = time.time()
    dati = {**_chiedi(adesso=adesso), "recapito": "notify.mobile_app_x"}
    ident = archivio.create(dati, thread=PAOLO, now=adesso)["promessa"]["id"]
    riga = archivio._conn.execute(
        "SELECT recapito FROM promesse WHERE id=?", (ident,)).fetchone()
    assert riga[0] is None


def test_il_tetto_delle_cinquanta_e_per_filo(archivio):
    """2.6: Paolo pieno non ferma Marta."""
    adesso = time.time()
    for n in range(promise_module.CEILING_IN_SOSPESO):
        _crea(archivio, PAOLO, n, adesso=adesso)

    oltre = archivio.create(_chiedi(99, adesso=adesso), thread=PAOLO, now=adesso)
    assert "errore" in oltre
    assert str(promise_module.CEILING_IN_SOSPESO) in oltre["errore"]
    assert archivio.count_pending(PAOLO) == promise_module.CEILING_IN_SOSPESO

    assert "errore" not in archivio.create(_chiedi(0, adesso=adesso),
                                           thread=MARTA, now=adesso)


def test_il_tetto_della_casa_regge_qualunque_numero_di_fili(archivio):
    """2.6 (ruling): il totale e' limitato anche con mille fili diversi."""
    adesso = time.time()
    tetto = promise_module.HOUSE_CEILING_IN_SOSPESO
    for n in range(tetto):
        _crea(archivio, ChatThread(f"persona:p{n}", "pannello"), n, adesso=adesso)

    oltre = archivio.create(_chiedi(0, adesso=adesso),
                            thread=ChatThread("persona:nuovo", "pannello"), now=adesso)
    assert "errore" in oltre
    assert str(tetto) in oltre["errore"]
    totale = archivio._conn.execute("SELECT count(*) FROM promesse").fetchone()[0]
    assert totale == tetto


def test_disdire_una_promessa_altrui_e_come_disdirne_una_inesistente(archivio):
    """2.1: stesso corpo, e la promessa di Paolo resta in attesa."""
    adesso = time.time()
    ident = _crea(archivio, PAOLO, adesso=adesso)

    altrui = archivio.cancel(ident, thread=MARTA, now=adesso)
    inesistente = archivio.cancel("mai-esistita", thread=MARTA, now=adesso)

    assert altrui == inesistente
    assert "errore" in altrui
    assert archivio.read(ident)["stato"] == "in_attesa"
    assert archivio.cancel(ident, thread=PAOLO, now=adesso)["promessa"]["stato"] == "disdetta"


def test_segnare_letti_gli_esiti_altrui_non_tocca_niente(archivio):
    adesso = time.time()
    ident = _crea(archivio, PAOLO, adesso=adesso)
    archivio.concludi(ident, state="mantenuta", now=adesso + 1)

    assert archivio.count_unread(MARTA) == 0
    assert archivio.count_unread(PAOLO) == 1
    assert archivio.mark_read([ident], thread=MARTA, now=adesso + 2) == 0
    assert archivio.read(ident)["esito_letto_ts"] is None
    assert archivio.mark_read([ident], thread=PAOLO, now=adesso + 2) == 1


def test_le_orfane_sono_invisibili_finche_non_si_adottano(archivio):
    adesso = time.time()
    orfana = _semina_orfana(archivio, adesso=adesso)

    assert archivio.has_orphans()
    assert archivio.list(thread=PAOLO) == []
    assert archivio.count_pending(PAOLO) == 0
    assert "errore" in archivio.cancel(orfana, thread=PAOLO, now=adesso)
    assert archivio.read(orfana)["thread"] is None

    assert archivio.adopt_orphans(PAOLO) == 1
    assert not archivio.has_orphans()
    assert [p["id"] for p in archivio.list(thread=PAOLO)] == [orfana]
    assert archivio.adopt_orphans(MARTA) == 0, "una volta sola"


def test_un_archivio_di_prima_si_apre_e_le_sue_righe_restano_orfane(tmp_path):
    """La migrazione aggiunge le due colonne; le righe esistenti restano senza
    filo, quindi invisibili finche' il proprietario non le adotta."""
    percorso = os.path.join(str(tmp_path), "promesse.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE promesse (
            id TEXT PRIMARY KEY, specie TEXT NOT NULL, frase TEXT NOT NULL,
            quando_ts REAL NOT NULL, quando_detto TEXT, fuso TEXT,
            chiamata_json TEXT, domanda TEXT, istantanea_json TEXT,
            recapito TEXT, stato TEXT NOT NULL DEFAULT 'in_attesa', motivo TEXT,
            esecuzione_id TEXT, testo TEXT, avvisare INTEGER,
            nata_ts REAL NOT NULL, risvegliata_ts REAL, esito_letto_ts REAL,
            entities_at_birth INTEGER);
        INSERT INTO promesse(id,specie,frase,quando_ts,domanda,stato,nata_ts)
            VALUES('vecchia','chiedi','x',9999999999,'?','in_attesa',1);
        PRAGMA user_version = 3;
    """)
    conn.commit()
    conn.close()

    a = AgendaStore(percorso)
    try:
        assert a.has_orphans()
        assert a.list(thread=PAOLO) == []
        colonne = {r[1] for r in a._conn.execute("PRAGMA table_info(promesse)")}
        assert {"subject_key", "entry_point"} <= colonne
    finally:
        a.close()


# ---------------------------------------------------------------------------
# Gli strumenti
# ---------------------------------------------------------------------------

def _fra(minuti: int) -> str:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) + timedelta(minutes=minuti)).isoformat()


class _HaSenzaPersona:
    """Home Assistant in cui nessuna `person` porta l'utente di chi parla:
    la persona non e' collegata (Marta sulla casa vera, 25/09/2026)."""

    async def get_states(self, _ids):
        return [{"entity_id": "sun.sun", "state": "above_horizon", "attributes": {}}]


def _dispatcher(archivio, thread, soggetto=None, **extra):
    return ToolDispatcher(None, None, agenda=archivio, thread=thread,
                          subject=soggetto, **extra)


def _chiedi_argomenti(**altro) -> dict:
    return {"specie": "chiedi", "frase": "fra un'ora dimmi la temperatura",
            "quando": _fra(60), "domanda": "quanti gradi?", **altro}


@pytest.mark.asyncio
async def test_la_promessa_di_paolo_e_nell_agenda_di_paolo_e_non_in_quella_di_marta(archivio):
    paolo = _dispatcher(archivio, PAOLO, PAOLO_SOGGETTO)
    marta = _dispatcher(archivio, MARTA, MARTA_SOGGETTO)

    creata = await paolo.dispatch("promise", _chiedi_argomenti())
    assert "errore" not in creata, creata
    ident = creata["promessa"]["id"]
    assert "thread" not in creata["promessa"], "il filo non attraversa il confine"

    paolo_rows = (await paolo.dispatch("agenda", {}))["promesse"]
    assert [p["id"] for p in paolo_rows] == [ident]
    assert all("thread" not in p for p in paolo_rows)
    assert (await marta.dispatch("agenda", {"tutte": True}))["promesse"] == []

    altrui = await marta.dispatch("cancel", {"id": ident})
    inesistente = await marta.dispatch("cancel", {"id": "mai-esistita"})
    assert altrui == inesistente
    assert archivio.read(ident)["stato"] == "in_attesa"

    disdetta = await paolo.dispatch("cancel", {"id": ident})
    assert disdetta["promessa"]["stato"] == "disdetta"
    assert "thread" not in disdetta["promessa"]


@pytest.mark.asyncio
async def test_un_recapito_mandato_dal_modello_e_rifiutato_e_nominato(archivio):
    """2.4: il recapito non lo sceglie piu' il modello -- e non lo si ignora
    in silenzio: la chiamata intera si rifiuta, nominandolo."""
    esito = await _dispatcher(archivio, PAOLO, PAOLO_SOGGETTO).dispatch(
        "promise", _chiedi_argomenti(recapito="notify.mobile_app_x"))
    assert "errore" in esito
    assert "«recapito»" in esito["errore"]
    assert archivio.list(thread=PAOLO, solo_in_sospeso=False) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("chiave", ["thread", "subject_key", "entry_point", "filo"])
async def test_il_filo_non_si_passa_come_argomento(archivio, chiave):
    """2.3: il filo viene dal confine, mai dal modello."""
    esito = await _dispatcher(archivio, PAOLO, PAOLO_SOGGETTO).dispatch(
        "promise", _chiedi_argomenti(**{chiave: "persona:marta"}))
    assert "errore" in esito
    assert archivio.list(thread=MARTA) == []
    assert archivio.list(thread=PAOLO) == []


def test_lo_schema_di_promise_non_conosce_il_recapito():
    """Pin (6): ne' fra i parametri ne' nella descrizione."""
    assert "recapito" not in PROMISE_TOOL_DEF["input_schema"]["properties"]
    assert "recapito" not in PROMISE_TOOL_DEF["description"]
    assert "notify" not in PROMISE_TOOL_DEF["description"]


@pytest.mark.asyncio
async def test_chi_non_ha_una_strada_se_lo_sente_dire_alla_nascita(archivio):
    """§2 «Nascita»: la promessa nasce, e il risultato dice perche' non ci
    sara' una notifica -- il testo di `Recipients.reason`."""
    esito = await _dispatcher(archivio, MARTA, MARTA_SOGGETTO,
                              ha=_HaSenzaPersona()).dispatch(
        "promise", _chiedi_argomenti())
    assert "errore" not in esito, esito
    assert _REASON_LINK_PERSON in esito["avviso"]
    assert archivio.list(thread=MARTA)


@pytest.mark.asyncio
async def test_un_fai_senza_il_permesso_di_comandare_non_nasce(archivio):
    """2.7 (ruling): il soffitto di chi chiede vale anche per l'azione
    rimandata -- stesso `perche`. Un `chiedi` resta permesso."""
    soffitto = {"leggere": True, "comandare": False, "costruire": False,
                "ruolo": "lettore", "perche": "questa utenza legge e basta"}
    d = _dispatcher(archivio, MARTA, MARTA_SOGGETTO, soffitto=soffitto)

    fai = await d.dispatch("promise", {
        "specie": "fai", "frase": "alle 17 accendi lo studio", "quando": _fra(60),
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert fai == {"errore": "questa utenza legge e basta"}
    assert archivio.list(thread=MARTA) == []

    chiedi = await d.dispatch("promise", _chiedi_argomenti())
    assert "errore" not in chiedi, chiedi


@pytest.mark.asyncio
async def test_senza_filo_nessuna_promessa_nasce_ne_si_legge(archivio):
    """Un turno senza nessuno che l'abbia aperto non ha di chi fare una
    promessa: si rifiuta e lo si dice, invece di farla nascere orfana."""
    d = ToolDispatcher(None, None, agenda=archivio)
    esito = await d.dispatch("promise", _chiedi_argomenti())
    assert "errore" in esito
    assert "errore" in await d.dispatch("agenda", {})
    assert "errore" in await d.dispatch("cancel", {"id": "x"})
    assert not archivio._conn.execute("SELECT count(*) FROM promesse").fetchone()[0]


# ---------------------------------------------------------------------------
# Le rotte
# ---------------------------------------------------------------------------

def _persona(pid):
    return {"specie": "persona", "id": pid, "nome": (pid or "").title() or None,
            "utente": pid}


@web.middleware
async def _finto_confine(request, handler):
    chi = request.headers.get("X-Chi", "")
    if chi == "anonimo":
        request["auth_via"] = "ingress"
        request["soggetto"] = _persona(None)
    elif chi == "paolo-firma":
        request["auth_via"] = "canale"
        request["soggetto"] = _persona("paolo")
    else:
        request["auth_via"] = "ingress"
        request["soggetto"] = _persona(chi)
    return await handler(request)


class _UtentiHA:
    """`paolo` proprietario e amministratore, `marta` utente."""

    async def users(self):
        return {"utenti": [
            {"id": "paolo", "amministratore": True, "proprietario": True},
            {"id": "marta", "amministratore": False, "proprietario": False},
        ]}


class _CostruzioniVuote:
    def count_pending(self, *, now):
        return 0


@pytest_asyncio.fixture
async def rotte(aiohttp_client, tmp_path):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    app = web.Application(middlewares=[_finto_confine])
    app["agenda"] = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    app["journal"] = Journal(os.path.join(str(tmp_path), "azioni.db"))
    app["constructions"] = _CostruzioniVuote()
    app["data_dir"] = data_dir
    app["chat_settings"] = ChatSettings(name="t", system_prompt="Sei HIRIS.")
    app["ha_client"] = _UtentiHA()
    app["ruoli"] = {"quando": 0.0, "per_id": {}}
    app.router.add_get("/api/agenda", handle_get_agenda)
    app.router.add_delete("/api/agenda/{id}", handle_delete_promise)
    app.router.add_post("/api/agenda/read", handle_mark_read)
    app.router.add_get("/api/executions/{id}", handle_get_execution)
    app.router.add_get("/api/pending", handle_get_pending)
    app.router.add_get("/api/chat/history", handle_get_chat_history)
    client = await aiohttp_client(app)
    yield client
    app["agenda"].close()
    app["journal"].close()


def _chi(nome):
    return {"X-Chi": nome}


@pytest.mark.asyncio
async def test_l_amministratore_vede_solo_le_sue(rotte):
    """Pin (1) e 2.2: gli amministratori NON sono esenti."""
    agenda = rotte.app["agenda"]
    paolo_id = _crea(agenda, PAOLO, 0)
    marta_id = _crea(agenda, MARTA, 1)

    paolo = await (await rotte.get("/api/agenda?all=1", headers=_chi("paolo"))).json()
    marta = await (await rotte.get("/api/agenda?all=1", headers=_chi("marta"))).json()

    assert [p["id"] for p in paolo["agenda"]] == [paolo_id]
    assert [p["id"] for p in marta["agenda"]] == [marta_id]
    assert all("thread" not in p for p in paolo["agenda"] + marta["agenda"])


@pytest.mark.asyncio
async def test_delete_di_una_promessa_altrui_e_il_404_di_una_inesistente(rotte):
    agenda = rotte.app["agenda"]
    ident = _crea(agenda, PAOLO)

    altrui = await rotte.delete(f"/api/agenda/{ident}", headers=_chi("marta"))
    inesistente = await rotte.delete("/api/agenda/mai-esistita", headers=_chi("marta"))

    assert altrui.status == inesistente.status == 404
    assert await altrui.read() == await inesistente.read()
    assert agenda.read(ident)["stato"] == "in_attesa"

    propria = await rotte.delete(f"/api/agenda/{ident}", headers=_chi("paolo"))
    assert propria.status == 200
    corpo = await propria.json()
    assert corpo["promessa"]["stato"] == "disdetta"
    assert "thread" not in corpo["promessa"]


@pytest.mark.asyncio
async def test_segnare_letti_gli_esiti_altrui_da_la_rotta_non_segna_niente(rotte):
    agenda = rotte.app["agenda"]
    ident = _crea(agenda, PAOLO)
    agenda.concludi(ident, state="mantenuta", now=time.time())

    risposta = await rotte.post("/api/agenda/read", json={"ids": [ident]},
                                headers=_chi("marta"))
    assert (await risposta.json())["marked"] == 0
    assert agenda.read(ident)["esito_letto_ts"] is None


@pytest.mark.asyncio
async def test_il_pallino_conta_solo_gli_esiti_del_proprio_filo(rotte):
    """2.13."""
    agenda = rotte.app["agenda"]
    for n in range(2):
        agenda.concludi(_crea(agenda, PAOLO, n), state="mantenuta", now=time.time())
    agenda.concludi(_crea(agenda, MARTA, 5), state="fallita", now=time.time())

    paolo = await (await rotte.get("/api/pending", headers=_chi("paolo"))).json()
    marta = await (await rotte.get("/api/pending", headers=_chi("marta"))).json()
    assert paolo["agenda_unread"] == 2
    assert marta["agenda_unread"] == 1


@pytest.mark.asyncio
async def test_la_cronaca_di_una_promessa_altrui_e_il_404_di_una_inesistente(rotte):
    """Pin (2): `GET /api/executions/{id}` legato a una promessa."""
    agenda, journal = rotte.app["agenda"], rotte.app["journal"]
    ident = _crea(agenda, PAOLO)
    esecuzione = journal.log(actor="schedulatore", service="light.turn_on",
                             entity=["light.studio"], executed=True, now=time.time())
    agenda.concludi(ident, state="mantenuta", now=time.time(), execution_id=esecuzione)

    altrui = await rotte.get(f"/api/executions/{esecuzione}", headers=_chi("marta"))
    inesistente = await rotte.get("/api/executions/mai-esistita", headers=_chi("marta"))
    assert altrui.status == inesistente.status == 404
    assert await altrui.read() == await inesistente.read()

    propria = await rotte.get(f"/api/executions/{esecuzione}", headers=_chi("paolo"))
    assert propria.status == 200
    assert (await propria.json())["execution"]["id"] == esecuzione


@pytest.mark.asyncio
async def test_la_cronaca_non_legata_a_una_promessa_resta_leggibile(rotte):
    """Cio' che la spec non tocca non cambia: un'esecuzione della chat non e'
    una promessa, e la rotta la serve come prima."""
    journal = rotte.app["journal"]
    esecuzione = journal.log(actor="chat", service="light.turn_on",
                             entity=["light.studio"], executed=True, now=time.time())
    risposta = await rotte.get(f"/api/executions/{esecuzione}", headers=_chi("marta"))
    assert risposta.status == 200


# --- le orfane --------------------------------------------------------------

@pytest.mark.asyncio
async def test_le_promesse_di_prima_vanno_al_proprietario_e_a_nessun_altro(rotte):
    agenda = rotte.app["agenda"]
    orfana = _semina_orfana(agenda, adesso=time.time())

    marta = await (await rotte.get("/api/agenda", headers=_chi("marta"))).json()
    assert marta["agenda"] == []
    assert agenda.has_orphans(), "una non proprietaria non adotta nulla"

    paolo = await (await rotte.get("/api/agenda", headers=_chi("paolo"))).json()
    assert [p["id"] for p in paolo["agenda"]] == [orfana]
    assert not agenda.has_orphans()
    assert agenda.read(orfana)["thread"] == PAOLO


@pytest.mark.asyncio
async def test_le_promesse_di_prima_si_adottano_con_la_cronologia(rotte):
    """Stesso momento, stessa regola: la prima pagina che il proprietario apre
    e' la chat, e da li' passano sia la cronologia sia le promesse."""
    agenda = rotte.app["agenda"]
    _semina_orfana(agenda, adesso=time.time())
    risposta = await rotte.get("/api/chat/history", headers=_chi("paolo"))
    assert risposta.status == 200
    assert not agenda.has_orphans()
    assert len(agenda.list(thread=PAOLO)) == 1


@pytest.mark.asyncio
async def test_un_anonimo_non_adotta_le_promesse_di_prima(rotte):
    """Pin (8): `persona:-` dal pannello non e' il proprietario."""
    agenda = rotte.app["agenda"]
    _semina_orfana(agenda, adesso=time.time())
    corpo = await (await rotte.get("/api/agenda", headers=_chi("anonimo"))).json()
    assert corpo["agenda"] == []
    assert agenda.has_orphans()


@pytest.mark.asyncio
async def test_il_proprietario_da_un_altro_ingresso_non_adotta_le_promesse(rotte):
    agenda = rotte.app["agenda"]
    _semina_orfana(agenda, adesso=time.time())
    corpo = await (await rotte.get("/api/agenda", headers=_chi("paolo-firma"))).json()
    assert corpo["agenda"] == []
    assert agenda.has_orphans()


@pytest.mark.asyncio
async def test_delete_non_adotta_prima_di_disdire(rotte):
    """2.11: una DELETE su un'orfana, prima di qualunque lettura, e' un 404 --
    anche per il proprietario."""
    agenda = rotte.app["agenda"]
    orfana = _semina_orfana(agenda, adesso=time.time())
    risposta = await rotte.delete(f"/api/agenda/{orfana}", headers=_chi("paolo"))
    assert risposta.status == 404
    assert agenda.read(orfana)["stato"] == "in_attesa"
    assert agenda.has_orphans()


# ---------------------------------------------------------------------------
# Il ponte
# ---------------------------------------------------------------------------

@pytest.fixture
def col_token_del_piano(monkeypatch):
    from hiris.app.model_resolution import SUBSCRIPTION_TOKEN_VAR
    monkeypatch.setenv(SUBSCRIPTION_TOKEN_VAR, "un-token-qualunque")


@pytest.mark.asyncio
async def test_il_job_del_ponte_di_una_promessa_porta_il_filo(tmp_path, col_token_del_piano):
    """Pin (5): `_enqueue_to_bridge` accoda col filo della promessa (§2.4), e
    il contesto non guadagna ne' il soggetto ne' chiavi di chat (2.8)."""
    from hiris.app.keeper.exchange import interpreta_promise
    from hiris.app.reasoning.queue import ReasoningQueue

    archivio = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    coda = ReasoningQueue(os.path.join(str(tmp_path), "reasoning.db"))
    try:
        ident = _crea(archivio, PAOLO)
        app = {"bridge_active": True, "reasoning_queue": coda,
               "models_config": {"ponte": {"tetto_giornaliero": 150, "scadenza_min": 10}}}
        esito = await interpreta_promise(app, archivio.read(ident))
        assert esito == {"accodata": True}

        job = coda.latest("promessa")
        assert job["thread"] == PAOLO
        riga = coda._conn.execute(
            "SELECT context_json FROM reasoning_jobs WHERE job_id=?",
            (job["job_id"],)).fetchone()
        contesto = json.loads(riga[0])
        assert "soggetto" not in contesto
        assert not ({"chat", "thread", "subject_key"} & set(contesto))
        assert coda.has_pending_chat(PAOLO) is False, (
            "2.10: un job di promessa non e' una chat in volo")
    finally:
        archivio.close()
        coda.close()


# --- i pin sul codice di partenza (verdi prima, e una mutazione li fa rossi) ---

@pytest.mark.asyncio
async def test_un_anonimo_non_adotta_la_cronologia_di_prima(rotte):
    """Pin (8), sulla meta' che esisteva gia': la cronologia. Mutazione
    eseguita: `is_owner` che risponde `True` a un soggetto senza id fa
    diventare rosso questo test."""
    from hiris.app.chat_store import has_orphans
    from tests.test_chat_divise import _semina_orfane

    data_dir = rotte.app["data_dir"]
    _semina_orfane(data_dir)
    corpo = await (await rotte.get("/api/chat/history", headers=_chi("anonimo"))).json()
    assert corpo["messages"] == []
    assert has_orphans(data_dir)


@pytest.mark.asyncio
async def test_il_job_di_una_promessa_col_filo_non_vale_come_chat(rotta_chat):
    """Pin (7) e 2.9: i job di promessa ora portano `subject_key`; un
    `X-HIRIS-Chat` con l'id di uno di loro resta un'intestazione non valida,
    perche' `claimed_chat` filtra `kind='chat'` nella SQL. Mutazione eseguita:
    togliere quel filtro fa diventare rosso questo test."""
    from tests.test_mcp_chat_thread import _confirm, _proposta

    client, coda, archivio, casa_ha = rotta_chat
    proposta = await _proposta(client)
    adesso = time.time()
    ident = coda.enqueue("promessa", {"promessa_id": "p1"}, {"promessa_id": "p1"},
                         adesso + 300, now=adesso, thread=PAOLO)
    assert coda.claim(adesso + 1)["job_id"] == ident

    esito = await _confirm(client, proposta, chat=ident)

    assert "non è più valido" in (esito.get("errore") or ""), esito
    assert casa_ha.salvate == []
    assert archivio.read(proposta)["stato"] == "in_attesa"
