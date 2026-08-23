"""Le quattro rotte: guardare, guardarne una, confermare, rimettere com'era."""
import os

import pytest
import pytest_asyncio
from aiohttp import web

from hiris.app.api.handlers_costruzioni import (
    handle_conferma_costruzione, handle_get_costruzione, handle_get_costruzioni,
    handle_ripristina_costruzione)
from hiris.app.azione.costruzione.officina import Officina
from hiris.app.azione.costruzione.versioni import ArchivioCostruzioni
from hiris.app.azione.cronaca import Cronaca
from hiris.app.server import create_app
from tests.test_costruzione_officina import FintoHA
# Fixture generica (annulla la valvola `HIRIS_ALLOW_NO_CSRF` che conftest.py
# mette per l'intera suite), senza niente di specifico alle impostazioni:
# stesso riuso cross-file gia' praticato da `test_promesse_api.py`.
from tests.test_impostazioni_api import csrf_stretto  # noqa: F401


class FintoArchivio:
    def __init__(self, righe=None):
        self._righe = righe or []
        self.scadenze_chieste = 0

    def scadi(self, adesso):
        self.scadenze_chieste += 1
        return 0

    def elenca(self, *, solo_in_attesa=False, limite=200):
        if solo_in_attesa:
            return [r for r in self._righe if r["stato"] == "in_attesa"]
        return list(self._righe)

    def leggi(self, ident):
        for r in self._righe:
            if r["id"] == ident:
                return r
        return None


class FintaOfficina:
    def __init__(self, esito):
        self.esito = esito
        self.chiamate = []

    async def applica(self, proposta_id, *, origine, turno, adesso):
        self.chiamate.append(("applica", proposta_id, origine, turno))
        return self.esito

    async def ripristina(self, costruzione_id, *, origine, turno, adesso):
        self.chiamate.append(("ripristina", costruzione_id, origine, turno))
        return self.esito


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


@pytest.mark.asyncio
async def test_l_elenco_di_default_da_tutto_e_col_filtro_solo_le_aperte():
    righe = [{"id": "a", "stato": "in_attesa"}, {"id": "b", "stato": "applicata"}]
    archivio = FintoArchivio(righe)
    app = _app(archivio)
    tutte = await handle_get_costruzioni(FintaRichiesta(app))
    assert b'"b"' in tutte.body
    aperte = await handle_get_costruzioni(FintaRichiesta(app, query={"in_attesa": "1"}))
    assert b'"b"' not in aperte.body
    # La pagina non deve mai mostrare come «da approvare» una proposta che
    # l'officina rifiuterebbe perche' scaduta.
    assert archivio.scadenze_chieste == 2


@pytest.mark.asyncio
async def test_senza_archivio_si_dichiara_indisponibile_e_non_si_finge_vuoto():
    risposta = await handle_get_costruzioni(FintaRichiesta(_app()))
    assert risposta.status == 503


@pytest.mark.asyncio
async def test_una_costruzione_che_non_esiste_da_404():
    app = _app(FintoArchivio([]))
    risposta = await handle_get_costruzione(FintaRichiesta(app, ident="zzz"))
    assert risposta.status == 404


@pytest.mark.asyncio
async def test_confermare_dalla_pagina_dichiara_l_origine_umana():
    """La pagina E' un umano che ha cliccato: nessun turno da distinguere."""
    officina = FintaOfficina({"applicata": True, "esecuzione_id": "e1"})
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]), officina)
    risposta = await handle_conferma_costruzione(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 200
    _, proposta_id, origine, turno = officina.chiamate[0]
    assert (proposta_id, origine, turno) == ("p1", "pagina", None)


@pytest.mark.asyncio
async def test_una_conferma_rifiutata_non_risponde_200():
    officina = FintaOfficina({"errore": "quella proposta e' gia' applicata."})
    app = _app(FintoArchivio([{"id": "p1", "stato": "applicata"}]), officina)
    risposta = await handle_conferma_costruzione(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 409


@pytest.mark.asyncio
async def test_ripristinare_passa_dall_officina():
    officina = FintaOfficina({"applicata": True, "esecuzione_id": "e2"})
    app = _app(FintoArchivio([{"id": "c1", "stato": "applicata"}]), officina)
    risposta = await handle_ripristina_costruzione(FintaRichiesta(app, ident="c1"))
    assert risposta.status == 200
    assert officina.chiamate[0][0] == "ripristina"


@pytest.mark.asyncio
async def test_confermare_senza_officina_da_503():
    """Il ramo 503 di `_agisci` non aveva un test proprio -- era coperto
    solo dal lato GET (`handle_get_costruzioni`/`handle_get_costruzione`).
    Un archivio presente ma un'officina assente non e' un caso remoto: e'
    esattamente la finestra fra la creazione dell'app e il momento in cui
    `_on_startup` monta `app["officina"]`."""
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]))
    risposta = await handle_conferma_costruzione(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 503
    assert b"officina non disponibile" in risposta.body


# ---------------------------------------------------------------------------
# Integrazione: l'applicazione VERA (`create_app`), non le finte sopra.
#
# I test sopra chiamano gli handler direttamente con una `FintaRichiesta`
# costruita a mano: scavalcano il router di aiohttp, la popolazione di
# `match_info` e TUTTI i middleware, CSRF compreso. Che le due POST siano
# protette dal CSRF lo sappiamo perche' lo si e' letto nel sorgente di
# `middleware_csrf.py` -- non perche' un test lo dica. Senza un test che
# passi per davvero dal router e dallo stack di middleware, una futura
# esenzione aggiunta per errore (o una registrazione della rotta prima del
# middleware) lascerebbe la suite verde. Stessa ragione, stessa forma di
# `tests/test_promesse_api.py::test_delete_senza_x_requested_with_e_403_e_non_disdice`.
# ---------------------------------------------------------------------------

ADESSO_HTTP = 1_756_100_000.0


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app["costruzioni"] = ArchivioCostruzioni(
        os.path.join(str(tmp_path), "costruzioni_http.db"))
    app["cronaca"] = Cronaca(os.path.join(str(tmp_path), "azioni_http.db"))
    ha = FintoHA()
    app["officina"] = Officina(ha, app["costruzioni"], app["cronaca"])
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
    ident = archivio.proponi(
        gesto="crea", dominio="automation", chiave="tapparelle_csrf",
        origine="chat", turno="turno-1", frase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], anteprima="anteprima",
        adesso=ADESSO_HTTP)["id"]

    risposta = await client.post("/api/costruzioni/%s/conferma" % ident)
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    # La meta' che conta: un 403 non deve aver toccato ne' l'archivio ne'
    # Home Assistant.
    assert archivio.leggi(ident)["stato"] == "in_attesa"
    assert client.app["_ha_finta"].salvate == []


@pytest.mark.asyncio
async def test_conferma_con_x_requested_with_applica_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.proponi(
        gesto="crea", dominio="automation", chiave="tapparelle_csrf_ok",
        origine="chat", turno="turno-1", frase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], anteprima="anteprima",
        adesso=ADESSO_HTTP)["id"]

    risposta = await client.post("/api/costruzioni/%s/conferma" % ident,
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.leggi(ident)["stato"] == "applicata"
    assert client.app["_ha_finta"].salvate


@pytest.mark.asyncio
async def test_ripristina_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.proponi(
        gesto="modifica", dominio="automation", chiave="tapparelle_rip",
        origine="chat", turno="turno-1", frase="modifica",
        prima={"alias": "Prima"}, dopo={"alias": "Dopo"}, helper=[],
        anteprima="anteprima", adesso=ADESSO_HTTP)["id"]
    archivio.segna_applicata(ident, adesso=ADESSO_HTTP, esecuzione_id="e-test")

    risposta = await client.post("/api/costruzioni/%s/ripristina" % ident)
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    assert client.app["_ha_finta"].salvate == []
    # Nessuna nuova proposta di ripristino deve essere nata: quella originale
    # resta l'unica riga dell'archivio.
    assert len(archivio.elenca(limite=200)) == 1


@pytest.mark.asyncio
async def test_ripristina_con_x_requested_with_ripristina_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app["costruzioni"]
    ident = archivio.proponi(
        gesto="modifica", dominio="automation", chiave="tapparelle_rip_ok",
        origine="chat", turno="turno-1", frase="modifica",
        prima={"alias": "Prima"}, dopo={"alias": "Dopo"}, helper=[],
        anteprima="anteprima", adesso=ADESSO_HTTP)["id"]
    archivio.segna_applicata(ident, adesso=ADESSO_HTTP, esecuzione_id="e-test")

    risposta = await client.post("/api/costruzioni/%s/ripristina" % ident,
                                 headers={"X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert client.app["_ha_finta"].salvate
