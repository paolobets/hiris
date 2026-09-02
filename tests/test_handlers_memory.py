"""GET/PATCH/DELETE /api/memories: cio' che HIRIS sa, in chiaro e correggibile.

Convenzione seguita: quella di `tests/test_handlers_casa.py` -- handler
`async def` semplice, app costruita a mano nel test, nessun `registra_rotte_*`.
"""
import json

import pytest
from aiohttp import web

from hiris.app.api.handlers_memory import (
    handle_delete_memory,
    handle_get_memories,
    handle_patch_memory,
)
from hiris.app.home_space.store import HomeSpaceStore
from hiris.app.memory.store import MemoryStore

_PHRASE = "d'inverno la sala da pranzo la preferisco fra 19 e 20 gradi quando sono a casa"


def _app(archivio_memoria=None, archivio_casa=None) -> web.Application:
    app = web.Application()
    app["archivio_memoria"] = archivio_memoria
    app["archivio_casa"] = archivio_casa
    app.router.add_get("/api/memories", handle_get_memories)
    app.router.add_patch("/api/memories/{id}", handle_patch_memory)
    app.router.add_delete("/api/memories/{id}", handle_delete_memory)
    return app


@pytest.mark.asyncio
async def test_api_memoria_mostra_la_frase_e_cosa_hiris_ha_capito(aiohttp_client, tmp_path):
    home_space = HomeSpaceStore(str(tmp_path / "casa.db"))
    home_space.replace({
        "piani": [], "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [],
        "aree": [{"area_id": "sala_pranzo", "name": "Sala da pranzo"}],
    })
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    memory.remember(
        _PHRASE, detto_da="paolo",
        # `nome_visto` e' quello che l'utente ha scritto ALLORA ("sala"): la
        # risposta deve mostrare il nome che l'anagrafe conosce OGGI
        # ("Sala da pranzo"), non questo testo congelato.
        ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"},
                # Un'ancora il cui identificatore non esiste (piu') nell'anagrafe:
                # la vista deve dichiararlo, non tacerlo ne' fingere che non ci sia.
                {"tipo": "area", "riferimento": "area_rimossa", "nome_visto": "veranda"}],
        conditions=[{"tipo": "stagione", "valore": "inverno"},
                    {"tipo": "presenza", "valore": "casa"}],
        modality="preferenza", grandezza="temperature", minimum=19.0, maximum=20.0, unit="°C",
    )
    app = _app(archivio_memoria=memory, archivio_casa=home_space)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memories")
    assert resp.status == 200
    body = await resp.json()
    assert body["available"] is True
    r = body["memories"][0]
    assert r["testo"] == _PHRASE
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

    assert body["total"] == 1
    assert body["shown"] == 1

    home_space.close()
    memory.close()


@pytest.mark.asyncio
async def test_api_memoria_senza_archivio_risponde_lo_stesso(aiohttp_client):
    """Senza archivio: 200 e vuota, non 500 -- «non c'e' ancora niente» e
    «e' rotto» devono restare distinguibili, e non lo sono se la risposta
    afferma "zero ricordi" come un fatto accertato."""
    app = _app(archivio_memoria=None, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memories")
    assert resp.status == 200
    body = await resp.json()
    assert body["available"] is False
    assert body["memories"] == []


@pytest.mark.asyncio
async def test_correggere_cambia_l_interpretazione_e_non_il_testo(aiohttp_client, tmp_path):
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember(_PHRASE, detto_da="paolo", modality="fatto", maximum=25.0)
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}",
                               json={"forza": "preferenza", "minimo": 19.0, "massimo": 20.0})
    assert resp.status == 200

    r = memory.fetch()[0]
    assert r["testo"] == _PHRASE                     # il testo non lo tocca nessuno
    assert r["forza"] == "preferenza"
    assert (r["minimo"], r["massimo"]) == (19.0, 20.0)
    assert r["corretto_da_utente"] == 1

    memory.close()


@pytest.mark.asyncio
async def test_una_correzione_con_un_ancora_inesistente_viene_rifiutata(aiohttp_client, tmp_path):
    home_space = HomeSpaceStore(str(tmp_path / "casa.db"))
    home_space.replace({
        "piani": [], "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [], "aree": [{"area_id": "cucina", "name": "Cucina"}],
    })
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember("mi piace il caffe' forte", detto_da="paolo")
    app = _app(archivio_memoria=memory, archivio_casa=home_space)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}", json={
        "ancore": [{"tipo": "area", "riferimento": "area_che_non_esiste",
                    "nome_visto": "veranda"}],
    })
    assert resp.status == 400
    body = await resp.json()
    assert body["error"]        # la ragione, non un rifiuto muto

    r = memory.fetch()[0]
    assert r["ancore"] == []      # il ricordo resta com'era: nessuna scrittura a meta'

    home_space.close()
    memory.close()


@pytest.mark.asyncio
async def test_il_taglio_a_200_ricordi_e_dichiarato(aiohttp_client, tmp_path):
    """La pagina si chiama "cio' che HIRIS sa": un ricordo oltre il taglio
    e' invisibile se nessuno dichiara che c'era un taglio."""
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    for i in range(5):
        memory.remember(f"ricordo numero {i}", detto_da="paolo")
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memories")
    body = await resp.json()
    assert body["total"] == 5
    assert body["shown"] == 5
    assert len(body["memories"]) == 5

    memory.close()


@pytest.mark.asyncio
async def test_correggere_un_id_inesistente_risponde_404(aiohttp_client, tmp_path):
    """Correggere un ricordo che non esiste (cancellato da un'altra scheda,
    per esempio) non e' un successo: 404, non 200 `ok: true` su nulla."""
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch("/api/memories/9999", json={"forza": "preferenza"})
    assert resp.status == 404
    body = await resp.json()
    assert body["error"]

    memory.close()


@pytest.mark.asyncio
async def test_una_correzione_con_ancore_e_anagrafe_mai_letta_dice_la_ragione_vera(
        aiohttp_client, tmp_path):
    """Con `archivio_casa` presente ma mai riletto (`aggiornata_il() is
    None` -- Home Assistant non ancora pronto all'avvio), il rifiuto resta
    fail-closed, ma la ragione non deve essere "non esiste nell'anagrafe":
    e' falso, non si e' potuto nemmeno guardare."""
    home_space = HomeSpaceStore(str(tmp_path / "casa.db"))       # mai .sostituisci()-ata
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember("mi piace il caffe' forte", detto_da="paolo")
    app = _app(archivio_memoria=memory, archivio_casa=home_space)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}", json={
        "ancore": [{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}],
    })
    assert resp.status == 400
    body = await resp.json()
    assert any("non si puo' verificare" in p for p in body["problemi"])
    assert not any("non esiste nell'anagrafe" in p for p in body["problemi"])

    home_space.close()
    memory.close()


@pytest.mark.asyncio
async def test_get_con_anagrafe_mai_letta_non_dichiara_le_ancore_sparite(
        aiohttp_client, tmp_path):
    """Stessa distinzione della PATCH, sul GET: un'ancora d'una casa mai
    letta deve restare `esiste: None` ("non ho potuto controllare"), non
    `False` ("ho controllato, non c'e' piu'") -- altrimenti ogni avvio in
    cui Home Assistant non era ancora pronto farebbe sparire ogni ancora."""
    home_space = HomeSpaceStore(str(tmp_path / "casa.db"))       # mai .sostituisci()-ata
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    memory.remember(_PHRASE, detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                             "nome_visto": "sala"}])
    app = _app(archivio_memoria=memory, archivio_casa=home_space)
    client = await aiohttp_client(app)

    resp = await client.get("/api/memories")
    assert resp.status == 200
    body = await resp.json()
    tether = body["memories"][0]["ancore"][0]
    assert tether["esiste"] is None
    assert tether["nome_attuale"] is None

    home_space.close()
    memory.close()


@pytest.mark.asyncio
async def test_una_condizione_senza_valore_viene_rifiutata(aiohttp_client, tmp_path):
    """`condizioni.valore` e' `NOT NULL` in archivio: una condizione senza
    valore deve essere scartata e dichiarata dal cancello, non arrivare
    fino alla scrittura e spaccarla con un IntegrityError (500)."""
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember("mi piace il caffe' forte", detto_da="paolo")
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}", json={
        "condizioni": [{"tipo": "ora"}],   # manca `valore`
    })
    assert resp.status == 400
    body = await resp.json()
    assert body["error"]

    r = memory.fetch()[0]
    assert r["condizioni"] == []          # nessuna scrittura a meta'

    memory.close()


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
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember(_PHRASE, detto_da="paolo", minimum=19.0, maximum=20.0)
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}", json={"minimo": 25})
    assert resp.status == 200
    body = await resp.json()
    assert body["correzioni"]                            # e non in silenzio

    r = memory.fetch()[0]
    assert (r["minimo"], r["massimo"]) == (20.0, 25.0)    # raddrizzato, non (25, 20)

    memory.close()


@pytest.mark.asyncio
async def test_una_correzione_parziale_coerente_scrive_solo_quel_capo(aiohttp_client, tmp_path):
    """Una correzione parziale che RESTA coerente con l'altro capo
    archiviato deve passare, e scrivere l'intervallo corretto."""
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember(_PHRASE, detto_da="paolo", minimum=19.0, maximum=20.0)
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}", json={"minimo": 18})
    assert resp.status == 200

    r = memory.fetch()[0]
    assert (r["minimo"], r["massimo"]) == (18.0, 20.0)

    memory.close()


@pytest.mark.asyncio
async def test_correggere_i_campi_non_correggibili_viene_dichiarato(aiohttp_client, tmp_path):
    """Il testo resta giustamente intatto -- ma il PATCH deve DIRLO, non
    rispondere `ok: true` come se avesse applicato tutto quanto chiesto."""
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember(_PHRASE, detto_da="paolo")
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}",
                               json={"testo": "riscritto!", "forza": "fatto"})
    assert resp.status == 200
    body = await resp.json()
    assert body["ignorati"] == ["testo"]

    r = memory.fetch()[0]
    assert r["testo"] == _PHRASE
    assert r["forza"] == "fatto"

    memory.close()


@pytest.mark.asyncio
async def test_correggere_la_grandezza_ridedduce_l_unita(aiohttp_client, tmp_path):
    """Correggere `grandezza` senza toccare `unita` non deve lasciare
    l'unita' vecchia: "umidita' 19-20 °C" sarebbe la stessa deriva che le
    ancore evitano gia'."""
    home_space = HomeSpaceStore(str(tmp_path / "casa.db"))
    home_space.replace({
        "piani": [], "dispositivi": [], "etichette": [], "categorie": [], "integrazioni": [],
        "aree": [{"area_id": "sala_pranzo", "name": "Sala da pranzo"}],
        "entita": [{"entity_id": "sensor.umidita_sala", "name": "Umidita' sala",
                    "area_id": "sala_pranzo", "device_class": "humidity",
                    "unit_of_measurement": "%"}],
    })
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember(
        _PHRASE, detto_da="paolo",
        ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}],
        grandezza="temperature", unit="°C", minimum=19.0, maximum=20.0)
    app = _app(archivio_memoria=memory, archivio_casa=home_space)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memories/{ident}", json={"grandezza": "humidity"})
    assert resp.status == 200

    r = memory.fetch()[0]
    assert r["grandezza"] == "humidity"
    assert r["unita"] == "%"          # rideddotta, non piu' "°C"

    home_space.close()
    memory.close()


@pytest.mark.asyncio
async def test_dimenticare_toglie_il_ricordo(aiohttp_client, tmp_path):
    memory = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memory.remember("il modulo meteo esterno e' guasto", detto_da="paolo")
    app = _app(archivio_memoria=memory, archivio_casa=None)
    client = await aiohttp_client(app)

    resp = await client.delete(f"/api/memories/{ident}")
    assert resp.status == 204
    assert memory.fetch() == []

    memory.close()


@pytest.mark.asyncio
async def test_senza_archivio_le_rotte_dichiarano_il_guasto_con_la_chiave_del_confine():
    """Le tre rotte della memoria, senza archivio, rispondono 503 -- e la chiave
    del corpo si chiama `error`, non `errore`.

    Nasce da una mutazione sfuggita: `{"error": ...}` rimesso a `{"errore":
    ...}` in questo ramo lasciava verdi tutti e quattro i cancelli, perche' i
    test che nominano `error` coprono solo i rami 400. Il ramo 503 non era
    nominato da nessuno, e `memory-route.js` legge `esito.json.error`.
    """
    from aiohttp import web

    from hiris.app.api.handlers_memory import (
        handle_delete_memory,
        handle_get_memories,
        handle_patch_memory,
    )

    app = web.Application()

    def richiesta():
        return type("R", (), {"app": app, "match_info": {"id": "1"}, "query": {}})()

    # Le due che SCRIVONO dichiarano il guasto con 503 e la chiave `error`.
    for handler in (handle_patch_memory, handle_delete_memory):
        risposta = await handler(richiesta())
        assert risposta.status == 503, handler.__name__
        assert set(json.loads(risposta.body)) == {"error"}, handler.__name__

    # La LETTURA no, ed e' una distinzione voluta (vedi la docstring del
    # modulo, punto 3): risponde 200 e DICHIARA `available: false`, invece di
    # affermare «zero ricordi» come se fosse un fatto accertato. Si pinza qui
    # perche' e' l'unico posto in cui le due forme si vedono accanto.
    risposta = await handle_get_memories(richiesta())
    assert risposta.status == 200
    assert json.loads(risposta.body) == {"available": False, "memories": []}
