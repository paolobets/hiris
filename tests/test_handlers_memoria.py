"""GET/PATCH/DELETE /api/memoria: cio' che HIRIS sa, in chiaro e correggibile.

Convenzione seguita: quella di `tests/test_handlers_casa.py` -- handler
`async def` semplice, app costruita a mano nel test, nessun `registra_rotte_*`.
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_memoria import (
    handle_get_memoria, handle_patch_memoria, handle_delete_memoria,
)
from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.memoria.archivio import ArchivioMemoria

_FRASE = "d'inverno la sala da pranzo la preferisco fra 19 e 20 gradi quando sono a casa"


def _app(archivio_memoria=None, archivio_casa=None) -> web.Application:
    app = web.Application()
    app["archivio_memoria"] = archivio_memoria
    app["archivio_casa"] = archivio_casa
    app.router.add_get("/api/memoria", handle_get_memoria)
    app.router.add_patch("/api/memoria/{id}", handle_patch_memoria)
    app.router.add_delete("/api/memoria/{id}", handle_delete_memoria)
    return app


@pytest.mark.asyncio
async def test_api_memoria_mostra_la_frase_e_cosa_hiris_ha_capito(aiohttp_client, tmp_path):
    casa = ArchivioCasa(str(tmp_path / "casa.db"))
    casa.sostituisci({
        "piani": [], "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [],
        "aree": [{"area_id": "sala_pranzo", "name": "Sala da pranzo"}],
    })
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    memoria.ricorda(
        _FRASE, detto_da="paolo",
        # `nome_visto` e' quello che l'utente ha scritto ALLORA ("sala"): la
        # risposta deve mostrare il nome che l'anagrafe conosce OGGI
        # ("Sala da pranzo"), non questo testo congelato.
        ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"},
                # Un'ancora il cui identificatore non esiste (piu') nell'anagrafe:
                # la vista deve dichiararlo, non tacerlo ne' fingere che non ci sia.
                {"tipo": "area", "riferimento": "area_rimossa", "nome_visto": "veranda"}],
        condizioni=[{"tipo": "stagione", "valore": "inverno"},
                    {"tipo": "presenza", "valore": "casa"}],
        forza="preferenza", grandezza="temperature", minimo=19.0, massimo=20.0, unita="°C",
    )
    app = _app(archivio_memoria=memoria, archivio_casa=casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memoria")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["disponibile"] is True
    r = corpo["ricordi"][0]
    assert r["testo"] == _FRASE
    assert r["detto_da"] == "paolo"
    assert r["forza"] == "preferenza"
    assert (r["minimo"], r["massimo"], r["unita"]) == (19.0, 20.0, "°C")
    assert {c["tipo"] for c in r["condizioni"]} == {"stagione", "presenza"}
    assert r["corretto_da_utente"] is False

    per_riferimento = {a["riferimento"]: a for a in r["ancore"]}
    viva = per_riferimento["sala_pranzo"]
    assert viva["nome_attuale"] == "Sala da pranzo"   # il nome DELL'ANAGRAFE, non "sala"
    assert viva["esiste"] is True

    rimossa = per_riferimento["area_rimossa"]
    assert rimossa["esiste"] is False
    assert rimossa["nome_attuale"] is None

    casa.chiudi()
    memoria.chiudi()


@pytest.mark.asyncio
async def test_api_memoria_senza_archivio_risponde_lo_stesso(aiohttp_client):
    """Senza archivio: 200 e vuota, non 500 -- «non c'e' ancora niente» e
    «e' rotto» devono restare distinguibili, e non lo sono se la risposta
    afferma "zero ricordi" come un fatto accertato."""
    app = _app(archivio_memoria=None, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memoria")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["disponibile"] is False
    assert corpo["ricordi"] == []


@pytest.mark.asyncio
async def test_correggere_cambia_l_interpretazione_e_non_il_testo(aiohttp_client, tmp_path):
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda(_FRASE, detto_da="paolo", forza="fatto", massimo=25.0)
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}",
                               json={"forza": "preferenza", "minimo": 19.0, "massimo": 20.0})
    assert resp.status == 200

    r = memoria.richiama()[0]
    assert r["testo"] == _FRASE                     # il testo non lo tocca nessuno
    assert r["forza"] == "preferenza"
    assert (r["minimo"], r["massimo"]) == (19.0, 20.0)
    assert r["corretto_da_utente"] == 1

    memoria.chiudi()


@pytest.mark.asyncio
async def test_una_correzione_con_un_ancora_inesistente_viene_rifiutata(aiohttp_client, tmp_path):
    casa = ArchivioCasa(str(tmp_path / "casa.db"))
    casa.sostituisci({
        "piani": [], "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [], "aree": [{"area_id": "cucina", "name": "Cucina"}],
    })
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda("mi piace il caffe' forte", detto_da="paolo")
    app = _app(archivio_memoria=memoria, archivio_casa=casa)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}", json={
        "ancore": [{"tipo": "area", "riferimento": "area_che_non_esiste",
                    "nome_visto": "veranda"}],
    })
    assert resp.status == 400
    corpo = await resp.json()
    assert corpo["errore"]        # la ragione, non un rifiuto muto

    r = memoria.richiama()[0]
    assert r["ancore"] == []      # il ricordo resta com'era: nessuna scrittura a meta'

    casa.chiudi()
    memoria.chiudi()


@pytest.mark.asyncio
async def test_dimenticare_toglie_il_ricordo(aiohttp_client, tmp_path):
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda("il modulo meteo esterno e' guasto", detto_da="paolo")
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.delete(f"/api/memoria/{ident}")
    assert resp.status == 204
    assert memoria.richiama() == []

    memoria.chiudi()
