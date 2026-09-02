"""Le cinque rotte: guardare, guardarne una, confermare, rimettere com'era, rifiutare."""
import os

import pytest
import pytest_asyncio
from aiohttp import web

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.journal import Journal
from hiris.app.api.handlers_constructions import (
    handle_confirm_construction,
    handle_get_construction,
    handle_get_constructions,
    handle_reject_construction,
    handle_restore_construction,
)
from hiris.app.server import create_app
from tests._contratti import assert_stessa_firma
from tests.test_costruzione_officina import FintoHA

# Fixture generica (annulla la valvola `HIRIS_ALLOW_NO_CSRF` che conftest.py
# mette per l'intera suite), senza niente di specifico alle impostazioni:
# stesso riuso cross-file gia' praticato da `test_agenda_api.py`.
from tests.test_impostazioni_api import csrf_stretto  # noqa: F401


class FintoArchivio:
    def __init__(self, righe=None, esito_disdetta=None):
        self._righe = righe or []
        self.scadenze_chieste = 0
        self.disdette = []
        self._esito_disdetta = esito_disdetta

    def scadi(self, now):
        self.scadenze_chieste += 1
        return 0

    def list(self, *, pending_only=False, limit=200):
        if pending_only:
            return [r for r in self._righe if r["stato"] == "in_attesa"]
        return list(self._righe)

    def read(self, ident):
        for r in self._righe:
            if r["id"] == ident:
                return r
        return None

    def mark_cancelled(self, ident, *, now):
        self.disdette.append(ident)
        return self._esito_disdetta or {"id": ident, "stato": "disdetta"}


class FintaOfficina:
    def __init__(self, esito):
        self.esito = esito
        self.chiamate = []

    async def apply(self, proposta_id, *, actor, exchange, now):
        self.chiamate.append(("apply", proposta_id, actor, exchange))
        return self.esito

    async def restore(self, costruzione_id, *, actor, exchange, now):
        self.chiamate.append(("restore", costruzione_id, actor, exchange))
        return self.esito


def test_i_finti_combaciano_con_la_firma_vera():
    """Se `ConstructionStore`/`Workshop` cambiano firma, questo test cade
    invece di lasciare che i finti imitino un contratto che non esiste
    piu'."""
    assert_stessa_firma(ConstructionStore.list, FintoArchivio.list, nome="list")
    assert_stessa_firma(ConstructionStore.read, FintoArchivio.read, nome="read")
    assert_stessa_firma(ConstructionStore.scadi, FintoArchivio.scadi, nome="scadi")
    assert_stessa_firma(ConstructionStore.mark_cancelled, FintoArchivio.mark_cancelled,
                        nome="mark_cancelled")
    assert_stessa_firma(Workshop.apply, FintaOfficina.apply, nome="apply")
    assert_stessa_firma(Workshop.restore, FintaOfficina.restore, nome="restore")


def _app(archivio=None, officina=None):
    app = web.Application()
    if archivio is not None:
        app["costruzioni"] = archivio
    if officina is not None:
        app["officina"] = officina
    return app


class FintaRichiesta:
    def __init__(self, app, ident=None, query=None):
        self.app = app
        self.match_info = {"id": ident} if ident else {}
        self.query = query or {}


def _corpo(risposta) -> dict:
    """Il corpo PARSATO, non la sua serializzazione.

    Questo aiutante nasce da un difetto vero, e la genealogia va scritta perche'
    non torni. Prima si asseriva `b'"b"' in risposta.body`: una SOTTOSTRINGA
    del corpo serializzato, che vede gli id dentro l'elenco e **non vede il nome
    dell'involucro che li contiene**. Provato per mutazione durante la review
    della fetta «la rinomina»: rinominato l'involucro di questa rotta da
    `constructions` a `costruzioni`, tutti e quattro i cancelli restavano verdi
    (ruff, 3001 test, npm 300/300, oxlint) mentre la pagina non sapeva piu'
    leggere la risposta.

    L'altro lato non poteva prenderlo: la finta di `tests/js/
    costruzioni-route.test.mjs` fornisce quella chiave DA SE', quindi nessuno
    dei due lati la pinzava. Da qui in poi la pinza questo.
    """
    import json
    return json.loads(risposta.body)


@pytest.mark.asyncio
async def test_l_elenco_di_default_da_tutto_e_col_filtro_solo_le_aperte():
    righe = [{"id": "a", "stato": "in_attesa"}, {"id": "b", "stato": "applicata"}]
    archivio = FintoArchivio(righe)
    app = _app(archivio)
    tutte = _corpo(await handle_get_constructions(FintaRichiesta(app)))
    # L'INVOLUCRO, per nome: e' il contratto che la pagina legge
    # (`static/config/constructions-route.js::dati.constructions`), e nessun
    # altro test di questa rotta lo nomina.
    assert set(tutte) == {"constructions"}
    assert [c["id"] for c in tutte["constructions"]] == ["a", "b"]
    aperte = _corpo(await handle_get_constructions(
        FintaRichiesta(app, query={"pending_only": "1"})))
    assert set(aperte) == {"constructions"}
    assert [c["id"] for c in aperte["constructions"]] == ["a"]
    # La pagina non deve mai mostrare come «da approvare» una proposta che
    # l'officina rifiuterebbe perche' scaduta.
    assert archivio.scadenze_chieste == 2


@pytest.mark.asyncio
async def test_senza_archivio_si_dichiara_indisponibile_e_non_si_finge_vuoto():
    risposta = await handle_get_constructions(FintaRichiesta(_app()))
    assert risposta.status == 503


@pytest.mark.asyncio
async def test_una_costruzione_che_non_esiste_da_404():
    app = _app(FintoArchivio([]))
    risposta = await handle_get_construction(FintaRichiesta(app, ident="zzz"))
    assert risposta.status == 404


@pytest.mark.asyncio
async def test_una_costruzione_che_esiste_esce_nel_suo_involucro():
    """Il caso RIUSCITO di `GET /api/constructions/{id}`, che non era coperto.

    Aveva solo il test del 404: il ramo che risponde 200 non era esercitato da
    nessuno, e l'involucro `construction` (singolare, distinto da
    `constructions` della lista) non era nominato da nessuna parte. Misurato
    con una batteria di mutazioni a fine fetta «la rinomina»: rimesso a
    `costruzione`, tutti e quattro i cancelli restavano verdi.

    **Questa rotta non ha lettori nel frontend** (`constructions-route.js` prende
    l'elenco intero e filtra in locale), quindi non c'e' una pagina che possa
    andare rossa al posto suo: questo test e' l'unica cosa che pinza il suo
    contratto. E' anche il motivo per cui la rotta e' nella tabella del debito.
    """
    import json

    riga = {"id": "p1", "stato": "in_attesa", "gesto": "crea"}
    app = _app(FintoArchivio([riga]))
    risposta = await handle_get_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 200
    corpo = json.loads(risposta.body)
    assert set(corpo) == {"construction"}
    assert corpo["construction"]["id"] == "p1"


@pytest.mark.asyncio
async def test_confermare_dalla_pagina_dichiara_l_origine_umana():
    """La pagina E' un umano che ha cliccato: nessun turno da distinguere."""
    officina = FintaOfficina({"applicata": True, "esecuzione_id": "e1"})
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]), officina)
    risposta = await handle_confirm_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 200
    _, proposta_id, origine, turno = officina.chiamate[0]
    assert (proposta_id, origine, turno) == ("p1", "pagina", None)


@pytest.mark.asyncio
async def test_una_conferma_rifiutata_non_risponde_200():
    officina = FintaOfficina({"errore": "quella proposta e' gia' applicata."})
    app = _app(FintoArchivio([{"id": "p1", "stato": "applicata"}]), officina)
    risposta = await handle_confirm_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 409


@pytest.mark.asyncio
async def test_un_guasto_di_rete_dell_officina_da_503_non_409():
    """Ondata finale, punto 7 (terza pulizia): `_act` appiattiva ogni
    errore dell'officina su 409 -- anche un guasto di Home Assistant, che
    dalla GET sarebbe un 503. `Workshop._fallita`/`_rete` marcano un guasto
    di trasporto con `guasto_rete: True`; questa rotta lo deve leggere."""
    officina = FintaOfficina({"errore": "Home Assistant non ha risposto: timeout",
                              "guasto_rete": True})
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]), officina)
    risposta = await handle_confirm_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 503
    # Il flag e' interno: non deve trapelare nel corpo della risposta.
    assert b"guasto_rete" not in risposta.body


@pytest.mark.asyncio
async def test_ripristinare_passa_dall_officina():
    officina = FintaOfficina({"applicata": True, "esecuzione_id": "e2"})
    app = _app(FintoArchivio([{"id": "c1", "stato": "applicata"}]), officina)
    risposta = await handle_restore_construction(FintaRichiesta(app, ident="c1"))
    assert risposta.status == 200
    assert officina.chiamate[0][0] == "restore"


@pytest.mark.asyncio
async def test_confermare_senza_officina_da_503():
    """Il ramo 503 di `_act` non aveva un test proprio -- era coperto
    solo dal lato GET (`handle_get_constructions`/`handle_get_construction`).
    Un archivio presente ma un'officina assente non e' un caso remoto: e'
    esattamente la finestra fra la creazione dell'app e il momento in cui
    `_on_startup` monta `app["officina"]`."""
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]))
    risposta = await handle_confirm_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 503
    assert b"officina non disponibile" in risposta.body


@pytest.mark.asyncio
async def test_rifiutare_dalla_pagina_non_tocca_home_assistant():
    """Il no non passa dall'officina: non c'e' niente da scrivere."""
    officina = FintaOfficina({"applicata": True})
    archivio = FintoArchivio([{"id": "p1", "stato": "in_attesa"}])
    app = _app(archivio, officina)
    risposta = await handle_reject_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 200
    assert officina.chiamate == [], "il rifiuto non deve passare dall'officina"
    assert archivio.disdette == ["p1"]


@pytest.mark.asyncio
async def test_rifiutare_cio_che_non_e_piu_in_attesa_da_409():
    archivio = FintoArchivio([{"id": "p1", "stato": "applicata"}],
                             esito_disdetta={"errore": "quella proposta non e' piu' in attesa"})
    risposta = await handle_reject_construction(
        FintaRichiesta(_app(archivio, FintaOfficina({})), ident="p1"))
    assert risposta.status == 409


# ---------------------------------------------------------------------------
# Integrazione: l'applicazione VERA (`create_app`), non le finte sopra.
#
# I test sopra chiamano gli handler direttamente con una `FintaRichiesta`
# costruita a mano: scavalcano il router di aiohttp, la popolazione di
# `match_info` e TUTTI i middleware, CSRF compreso. Le POST protette dal CSRF
# sono TRE -- conferma, ripristina, rifiuta -- e ciascuna ha qui sotto il suo
# test che passa per davvero dal router e dallo stack di middleware: senza di
# loro, una futura esenzione aggiunta per errore (o una registrazione della
# rotta prima del middleware) lascerebbe la suite verde. Stessa ragione,
# stessa forma di
# `tests/test_agenda_api.py::test_delete_senza_x_requested_with_e_403_e_non_disdice`.
# ---------------------------------------------------------------------------

ADESSO_HTTP = 1_756_100_000.0


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app["costruzioni"] = ConstructionStore(
        os.path.join(str(tmp_path), "costruzioni_http.db"))
    app["cronaca"] = Journal(os.path.join(str(tmp_path), "azioni_http.db"))
    ha = FintoHA()
    app["officina"] = Workshop(ha, app["costruzioni"], app["cronaca"])
    # Solo per i test: leggere cosa e' stato scritto DAVVERO su Home
    # Assistant, senza toccare l'attributo privato dell'officina.
    app["_ha_finta"] = ha
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app["costruzioni"].close()
    app["cronaca"].close()


@pytest.mark.asyncio
async def test_conferma_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_csrf",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/confirm")
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    # La meta' che conta: un 403 non deve aver toccato ne' l'archivio ne'
    # Home Assistant.
    assert archivio.read(ident)["stato"] == "in_attesa"
    assert client.app["_ha_finta"].salvate == []


@pytest.mark.asyncio
async def test_conferma_con_x_requested_with_applica_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_csrf_ok",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/confirm",
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.read(ident)["stato"] == "applicata"
    assert client.app["_ha_finta"].salvate


@pytest.mark.asyncio
async def test_ripristina_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.propose(
        operation="modifica", domain="automation", key="tapparelle_rip",
        actor="chat", exchange="turno-1", phrase="modifica",
        prima={"alias": "Prima"}, dopo={"alias": "Dopo"}, helper=[],
        preview="anteprima", now=ADESSO_HTTP)["id"]
    archivio.mark_applied(ident, now=ADESSO_HTTP, execution_id="e-test")

    risposta = await client.post(f"/api/constructions/{ident}/restore")
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    assert client.app["_ha_finta"].salvate == []
    # Nessuna nuova proposta di ripristino deve essere nata: quella originale
    # resta l'unica riga dell'archivio.
    assert len(archivio.list(limit=200)) == 1


@pytest.mark.asyncio
async def test_ripristina_con_x_requested_with_ripristina_anche_a_csrf_stretto(
    client, csrf_stretto
):
    archivio = client.app["costruzioni"]
    ident = archivio.propose(
        operation="modifica", domain="automation", key="tapparelle_rip_ok",
        actor="chat", exchange="turno-1", phrase="modifica",
        prima={"alias": "Prima"}, dopo={"alias": "Dopo"}, helper=[],
        preview="anteprima", now=ADESSO_HTTP)["id"]
    archivio.mark_applied(ident, now=ADESSO_HTTP, execution_id="e-test")

    risposta = await client.post(f"/api/constructions/{ident}/restore",
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert client.app["_ha_finta"].salvate


@pytest.mark.asyncio
async def test_rifiuta_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    """Punto 9 (residuo): `/reject` era l'unica delle tre POST senza questa
    prova end-to-end, nel file il cui stesso commento argomenta perche' serve.
    Non tocca Home Assistant (vedi `handlers_constructions.py`), quindi la meta'
    che conta qui non e' `salvate == []` ma lo stato della proposta."""
    archivio = client.app["costruzioni"]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_rifiuta_csrf",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/reject")
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    # La meta' che conta: sul 403 la proposta resta `in_attesa`.
    assert archivio.read(ident)["stato"] == "in_attesa"


@pytest.mark.asyncio
async def test_rifiuta_con_x_requested_with_rifiuta_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_rifiuta_csrf_ok",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/reject",
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.read(ident)["stato"] == "disdetta"
