"""GET/PATCH/DELETE /api/memoria: cio' che HIRIS sa, in chiaro e correggibile.

Convenzione seguita: quella di `tests/test_handlers_casa.py` -- handler
`async def` semplice, app costruita a mano nel test, nessun `registra_rotte_*`.
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_memoria import (
    handle_delete_memoria,
    handle_get_memoria,
    handle_patch_memoria,
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

    assert corpo["totale"] == 1
    assert corpo["mostrati"] == 1

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
async def test_il_taglio_a_200_ricordi_e_dichiarato(aiohttp_client, tmp_path):
    """La pagina si chiama "cio' che HIRIS sa": un ricordo oltre il taglio
    e' invisibile se nessuno dichiara che c'era un taglio."""
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    for i in range(5):
        memoria.ricorda(f"ricordo numero {i}", detto_da="paolo")
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memoria")
    corpo = await resp.json()
    assert corpo["totale"] == 5
    assert corpo["mostrati"] == 5
    assert len(corpo["ricordi"]) == 5

    memoria.chiudi()


@pytest.mark.asyncio
async def test_correggere_un_id_inesistente_risponde_404(aiohttp_client, tmp_path):
    """Correggere un ricordo che non esiste (cancellato da un'altra scheda,
    per esempio) non e' un successo: 404, non 200 `ok: true` su nulla."""
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch("/api/memoria/9999", json={"forza": "preferenza"})
    assert resp.status == 404
    corpo = await resp.json()
    assert corpo["errore"]

    memoria.chiudi()


@pytest.mark.asyncio
async def test_una_correzione_con_ancore_e_anagrafe_mai_letta_dice_la_ragione_vera(
        aiohttp_client, tmp_path):
    """Con `archivio_casa` presente ma mai riletto (`aggiornata_il() is
    None` -- Home Assistant non ancora pronto all'avvio), il rifiuto resta
    fail-closed, ma la ragione non deve essere "non esiste nell'anagrafe":
    e' falso, non si e' potuto nemmeno guardare."""
    casa = ArchivioCasa(str(tmp_path / "casa.db"))       # mai .sostituisci()-ata
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda("mi piace il caffe' forte", detto_da="paolo")
    app = _app(archivio_memoria=memoria, archivio_casa=casa)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}", json={
        "ancore": [{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}],
    })
    assert resp.status == 400
    corpo = await resp.json()
    assert any("non si puo' verificare" in p for p in corpo["problemi"])
    assert not any("non esiste nell'anagrafe" in p for p in corpo["problemi"])

    casa.chiudi()
    memoria.chiudi()


@pytest.mark.asyncio
async def test_get_con_anagrafe_mai_letta_non_dichiara_le_ancore_sparite(
        aiohttp_client, tmp_path):
    """Stessa distinzione della PATCH, sul GET: un'ancora d'una casa mai
    letta deve restare `esiste: None` ("non ho potuto controllare"), non
    `False` ("ho controllato, non c'e' piu'") -- altrimenti ogni avvio in
    cui Home Assistant non era ancora pronto farebbe sparire ogni ancora."""
    casa = ArchivioCasa(str(tmp_path / "casa.db"))       # mai .sostituisci()-ata
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    memoria.ricorda(_FRASE, detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                             "nome_visto": "sala"}])
    app = _app(archivio_memoria=memoria, archivio_casa=casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memoria")
    assert resp.status == 200
    corpo = await resp.json()
    ancora = corpo["ricordi"][0]["ancore"][0]
    assert ancora["esiste"] is None
    assert ancora["nome_attuale"] is None

    casa.chiudi()
    memoria.chiudi()


@pytest.mark.asyncio
async def test_una_condizione_senza_valore_viene_rifiutata(aiohttp_client, tmp_path):
    """`condizioni.valore` e' `NOT NULL` in archivio: una condizione senza
    valore deve essere scartata e dichiarata dal cancello, non arrivare
    fino alla scrittura e spaccarla con un IntegrityError (500)."""
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda("mi piace il caffe' forte", detto_da="paolo")
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}", json={
        "condizioni": [{"tipo": "ora"}],   # manca `valore`
    })
    assert resp.status == 400
    corpo = await resp.json()
    assert corpo["errore"]

    r = memoria.richiama()[0]
    assert r["condizioni"] == []          # nessuna scrittura a meta'

    memoria.chiudi()


@pytest.mark.asyncio
async def test_una_correzione_parziale_non_crea_un_intervallo_rovesciato_in_silenzio(
        aiohttp_client, tmp_path):
    """«fra 19 e 20 gradi», poi `PATCH {"minimo": 25}` (refuso per 15).

    La coerenza si verifica contro il `massimo` GIA' ARCHIVIATO, non contro
    `None`: altrimenti si archivierebbe silenziosamente (25.0, 20.0).

    E l'intervallo si RADDRIZZA dichiarandolo, non si rifiuta: e' lo stesso
    comportamento che ha da sempre un intervallo mandato intero. Prima erano
    due comportamenti opposti per la stessa situazione a seconda di come
    arrivava -- il tipo di divergenza che questo refactor esiste per togliere.
    """
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda(_FRASE, detto_da="paolo", minimo=19.0, massimo=20.0)
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}", json={"minimo": 25})
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["correzioni"]                            # e non in silenzio

    r = memoria.richiama()[0]
    assert (r["minimo"], r["massimo"]) == (20.0, 25.0)    # raddrizzato, non (25, 20)

    memoria.chiudi()


@pytest.mark.asyncio
async def test_una_correzione_parziale_coerente_scrive_solo_quel_capo(aiohttp_client, tmp_path):
    """Una correzione parziale che RESTA coerente con l'altro capo
    archiviato deve passare, e scrivere l'intervallo corretto."""
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda(_FRASE, detto_da="paolo", minimo=19.0, massimo=20.0)
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}", json={"minimo": 18})
    assert resp.status == 200

    r = memoria.richiama()[0]
    assert (r["minimo"], r["massimo"]) == (18.0, 20.0)

    memoria.chiudi()


@pytest.mark.asyncio
async def test_correggere_i_campi_non_correggibili_viene_dichiarato(aiohttp_client, tmp_path):
    """Il testo resta giustamente intatto -- ma il PATCH deve DIRLO, non
    rispondere `ok: true` come se avesse applicato tutto quanto chiesto."""
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda(_FRASE, detto_da="paolo")
    app = _app(archivio_memoria=memoria, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}",
                               json={"testo": "riscritto!", "forza": "fatto"})
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["ignorati"] == ["testo"]

    r = memoria.richiama()[0]
    assert r["testo"] == _FRASE
    assert r["forza"] == "fatto"

    memoria.chiudi()


@pytest.mark.asyncio
async def test_correggere_la_grandezza_ridedduce_l_unita(aiohttp_client, tmp_path):
    """Correggere `grandezza` senza toccare `unita` non deve lasciare
    l'unita' vecchia: "umidita' 19-20 °C" sarebbe la stessa deriva che le
    ancore evitano gia'."""
    casa = ArchivioCasa(str(tmp_path / "casa.db"))
    casa.sostituisci({
        "piani": [], "dispositivi": [], "etichette": [], "categorie": [], "integrazioni": [],
        "aree": [{"area_id": "sala_pranzo", "name": "Sala da pranzo"}],
        "entita": [{"entity_id": "sensor.umidita_sala", "name": "Umidita' sala",
                    "area_id": "sala_pranzo", "device_class": "humidity",
                    "unit_of_measurement": "%"}],
    })
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    ident = memoria.ricorda(
        _FRASE, detto_da="paolo",
        ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}],
        grandezza="temperature", unita="°C", minimo=19.0, massimo=20.0)
    app = _app(archivio_memoria=memoria, archivio_casa=casa)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{ident}", json={"grandezza": "humidity"})
    assert resp.status == 200

    r = memoria.richiama()[0]
    assert r["grandezza"] == "humidity"
    assert r["unita"] == "%"          # rideddotta, non piu' "°C"

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
