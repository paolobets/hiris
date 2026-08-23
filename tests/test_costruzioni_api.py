"""Le quattro rotte: guardare, guardarne una, confermare, rimettere com'era."""
import pytest
from aiohttp import web

from hiris.app.api.handlers_costruzioni import (
    handle_conferma_costruzione, handle_get_costruzione, handle_get_costruzioni,
    handle_ripristina_costruzione)


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
