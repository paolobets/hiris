"""GET /api/casa: la casa si vede in sola lettura, anche quando l'archivio manca.

Convenzione seguita: quella vera del repo (vedi `hiris/app/server.py`,
`create_app()`) -- un handler `async def` semplice, registrato con
`app.router.add_get(...)` dentro `create_app()`. Nessun `registra_rotte_*`:
il repo non lo usa da nessun'altra parte, e introdurlo qui sarebbe esattamente
il secondo modo di fare la stessa cosa che questo refactor vuole eliminare.
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_casa import handle_get_casa, handle_get_nucleo
from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.memoria.archivio import ArchivioMemoria


class _CacheFinta:
    """Sostituto minimo di `EntityCache` per i test: stessa forma di
    `all_states()` (lista di dict con chiave "id", non "entity_id") e
    stessa bandiera `loaded` che governa `inventario_leggibile()`."""

    def __init__(self, stati: list[dict], *, pronta: bool = True) -> None:
        self._stati = stati
        self.loaded = pronta

    def all_states(self) -> list[dict]:
        return self._stati


@pytest.mark.asyncio
async def test_api_casa_restituisce_la_gerarchia(aiohttp_client, tmp_path):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [{"domain": "mqtt", "title": "MQTT", "state": "loaded"}],
    })
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["piani"][0]["nome"] == "Piano terra"
    assert corpo["piani"][0]["aree"][0]["nome"] == "Cucina"
    assert corpo["conteggi"]["aree"] == 1
    assert corpo["anagrafe_letta_il"] is not None
    assert corpo["non_disponibili"] == []
    archivio.chiudi()


@pytest.mark.asyncio
async def test_api_casa_senza_anagrafe_risponde_lo_stesso(aiohttp_client):
    """L'anagrafe puo' essere vuota se HA non era pronto all'avvio: 200 e vuota,
    non 500 -- chi guarda deve poter distinguere «vuota» da «rotta»."""
    app = web.Application()
    app["archivio_casa"] = None
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["piani"] == []
    assert corpo["anagrafe_letta_il"] is None
    # Stesso principio applicato al comportamento: senza archivio, un
    # "senza_corpo" a zero affermerebbe "conosco tutto" -- resta `None`,
    # non un fatto finto. `conteggi`/`voci` sono contenitori naturali.
    assert corpo["comportamento"] == {
        "letto_il": None, "conteggi": {}, "senza_corpo": None,
        "problemi": None, "file_non_letti": None, "voci": [],
    }
    assert corpo["plance"] == {"lette_il": None, "non_disponibili": None, "voci": []}


@pytest.mark.asyncio
async def test_api_casa_mostra_il_comportamento_e_quanto_non_sa(aiohttp_client, tmp_path):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci_comportamento(
        [
            {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
             "corpo": {"trigger": []}, "origine": "file"},
            {"id": "automation.a_mano", "tipo": "automazione", "nome": "A mano",
             "corpo": None, "origine": "solo_stato"},
            {"id": "script.vuoto", "tipo": "script", "nome": "Vuoto",
             "corpo": {}, "origine": "file"},
        ],
        problemi=["automations.yaml: id 42 usato da 2 voci"],
        file_non_letti={"scripts.yaml": "assente"},
    )
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    comportamento = corpo["comportamento"]
    # Data propria della sezione, diversa da `anagrafe_letta_il`.
    assert comportamento["letto_il"] is not None
    assert comportamento["conteggi"] == {"automazione": 2, "script": 1}
    # Solo "a_mano" e' senza corpo: "vuoto" un corpo ce l'ha, e' solo vuoto --
    # le due cose non sono la stessa cosa e non vanno confuse.
    assert comportamento["senza_corpo"] == 1
    assert len(comportamento["voci"]) == 3
    # Le dichiarazioni costruite da comportamento.componi()/rileggi() devono
    # arrivare fin qui, non morire in un log (Important 3).
    assert comportamento["problemi"] == ["automations.yaml: id 42 usato da 2 voci"]
    assert comportamento["file_non_letti"] == {"scripts.yaml": "assente"}
    per_id = {v["id"]: v for v in comportamento["voci"]}
    assert per_id["automation.a_mano"]["corpo"] is None
    assert per_id["script.vuoto"]["corpo"] == {}
    archivio.chiudi()


@pytest.mark.asyncio
async def test_api_casa_mostra_le_plance_compresa_la_predefinita(aiohttp_client, tmp_path):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci_plance([
        {"url_path": None, "title": "Principale", "mode": "storage",
         "config": {"views": []}, "entita": ["light.cucina"]},
        {"url_path": "cucina", "title": "Cucina", "mode": "storage",
         "config": None, "entita": []},
    ])
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    sezione = corpo["plance"]
    # Data propria della sezione: `sostituisci_plance` l'ha appena scritta,
    # non e' `aggiornata_il`/`anagrafe_letta_il`.
    assert sezione["lette_il"] is not None
    assert sezione["non_disponibili"] == []
    plance = sezione["voci"]
    assert len(plance) == 2
    principale = next(p for p in plance if p["percorso"] is None)
    assert principale["titolo"] == "Principale"
    assert principale["entita"] == ["light.cucina"]
    cucina = next(p for p in plance if p["percorso"] == "cucina")
    # Una plancia in modalita' YAML non si legge: `config: None` e' un fatto
    # diverso da "plancia senza viste" e non va appiattito.
    assert cucina["config"] is None
    archivio.chiudi()


@pytest.mark.asyncio
async def test_api_nucleo_mostra_il_testo_e_il_riepilogo(aiohttp_client, tmp_path):
    """`/api/nucleo` mostra il testo ESATTO che il modello ha davanti, e il
    riepilogo (caratteri, troncato, ricordi esclusi) e' coerente col testo."""
    archivio_casa = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio_casa.sostituisci({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [],
        "entita": [{"entity_id": "light.cucina", "name": "Faretti", "area_id": "cucina"}],
        "etichette": [], "categorie": [], "integrazioni": [],
    })
    archivio_memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    archivio_memoria.ricorda("d'inverno la sala la preferisco fra 19 e 20 gradi", "paolo")
    app = web.Application()
    app["archivio_casa"] = archivio_casa
    app["archivio_memoria"] = archivio_memoria
    app["entity_cache"] = _CacheFinta([{"id": "light.cucina", "state": "on"}])
    app.router.add_get("/api/nucleo", handle_get_nucleo)
    client = await aiohttp_client(app)

    resp = await client.get("/api/nucleo")
    assert resp.status == 200
    corpo = await resp.json()
    testo = corpo["testo"]
    riepilogo = corpo["riepilogo"]
    assert "Cucina" in testo
    assert "Faretti" in testo                     # accesa: e' notevole
    assert "fra 19 e 20 gradi" in testo            # i ricordi entrano interi
    # Il riepilogo non puo' mentire su cio' che il testo contiene davvero.
    assert riepilogo["caratteri"] == len(testo)
    assert riepilogo["troncato"] is False
    assert riepilogo["ricordi_esclusi"] == 0
    archivio_casa.chiudi()
    archivio_memoria.chiudi()


@pytest.mark.asyncio
async def test_api_nucleo_senza_archivi_non_afferma_di_sapere(aiohttp_client):
    """Senza archivio della casa e senza inventario vivo, il nucleo deve
    dichiarare "non ho potuto guardare" -- MAI un nucleo vuoto spacciato per
    una casa vuota. 200 comunque: e' una lacuna dichiarata, non un guasto."""
    app = web.Application()
    app["archivio_casa"] = None
    app["archivio_memoria"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/nucleo", handle_get_nucleo)
    client = await aiohttp_client(app)

    resp = await client.get("/api/nucleo")
    assert resp.status == 200
    corpo = await resp.json()
    testo = corpo["testo"]
    riepilogo = corpo["riepilogo"]
    # "Notevole adesso" dice "non ho guardato", non "niente di notevole".
    assert "non si e' potuto guardare" in testo or "non si e’ potuto guardare" in testo
    assert any("non e' stato letto" in a or "non attendibile" in a for a in riepilogo["avvisi"])


@pytest.mark.asyncio
async def test_api_nucleo_propaga_i_registri_non_disponibili(aiohttp_client, tmp_path):
    """Il difetto sbagliato tre volte su questo ramo: un registro caduto
    (qui "aree") deve comparire sia nella sezione "La casa" (che NON deve
    dire "Senza area", un'affermazione che non abbiamo il diritto di fare)
    sia nel riepilogo -- mai inghiottito da un modulo che lo riceve e non
    lo passa oltre."""
    archivio_casa = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio_casa.sostituisci({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [], "dispositivi": [],
        "entita": [{"entity_id": "light.orfana", "name": "Orfana", "area_id": None}],
        "etichette": [], "categorie": [], "integrazioni": [],
    }, non_disponibili=["aree"])
    app = web.Application()
    app["archivio_casa"] = archivio_casa
    app["archivio_memoria"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/nucleo", handle_get_nucleo)
    client = await aiohttp_client(app)

    resp = await client.get("/api/nucleo")
    assert resp.status == 200
    corpo = await resp.json()
    sezione_casa = corpo["testo"].split("## Notevole adesso")[0]
    assert "Aree non lette" in sezione_casa
    assert "Senza area" not in sezione_casa
    assert any("aree" in a and "non hanno risposto" in a for a in corpo["riepilogo"]["avvisi"])
    archivio_casa.chiudi()
