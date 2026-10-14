"""GET /api/home-space: la casa si vede in sola lettura, anche quando l'archivio manca.

Convenzione seguita: quella vera del repo (vedi `hiris/app/server.py`,
`create_app()`) -- un handler `async def` semplice, registrato con
`app.router.add_get(...)` dentro `create_app()`. Nessun `registra_rotte_*`:
il repo non lo usa da nessun'altra parte, e introdurlo qui sarebbe esattamente
il secondo modo di fare la stessa cosa che questo refactor vuole eliminare.
"""
import json
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.handlers_home_space import handle_get_briefing, handle_get_home_space
from hiris.app.api.soffitto import consente
from hiris.app.home_space.reader import HomeSpace
from hiris.app.memory.store import MemoryStore
from hiris.app.proxy.entity_cache import EntityCache
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte
from casa_finta import CasaFinta


class _CacheFinta:
    """Sostituto minimo di `EntityCache` per i test: stessa forma di
    `all_states()` (lista di dict con chiave "id", non "entity_id") e
    stessa bandiera `loaded` che governa `inventory_is_readable()`."""

    def __init__(self, stati: list[dict], *, pronta: bool = True) -> None:
        self._stati = stati
        self.loaded = pronta

    def all_states(self) -> list[dict]:
        return self._stati


@pytest.mark.asyncio
async def test_api_casa_restituisce_la_gerarchia(aiohttp_client, tmp_path):
    archivio = HomeSpace(str(tmp_path))
    archivio.hold_registries({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [{"domain": "mqtt", "titolo": "MQTT", "state": "loaded"}],
    })
    app = web.Application()
    app["home_space_store"] = archivio
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)

    resp = await client.get("/api/home-space")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["piani"][0]["nome"] == "Piano terra"
    assert corpo["piani"][0]["aree"][0]["nome"] == "Cucina"
    assert corpo["conteggi"]["aree"] == 1
    assert corpo["anagrafe_letta_il"] is not None
    assert corpo["non_disponibili"] == []


@pytest.mark.asyncio
async def test_api_casa_senza_anagrafe_risponde_lo_stesso(aiohttp_client):
    """L'anagrafe puo' essere vuota se HA non era pronto all'avvio: 200 e vuota,
    non 500 -- chi guarda deve poter distinguere «vuota» da «rotta»."""
    app = web.Application()
    app["home_space_store"] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)

    resp = await client.get("/api/home-space")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["piani"] == []
    assert corpo["anagrafe_letta_il"] is None
    # Stesso principio applicato al comportamento: senza archivio, un
    # "senza_corpo" a zero affermerebbe "conosco tutto" -- resta `None`,
    # non un fatto finto. `conteggi` e' un contenitore naturale.
    assert corpo["comportamento"] == {
        "letto_il": None, "conteggi": {}, "senza_corpo": None,
        "problemi": None, "corpi_non_letti": None, "conservato": None,
    }
    assert corpo["plance"] == {"lette_il": None, "non_disponibili": None,
                               "conservato": None, "voci": []}


@pytest.mark.asyncio
async def test_api_casa_mostra_il_comportamento_e_quanto_non_sa(aiohttp_client, tmp_path):
    archivio = HomeSpace(str(tmp_path))
    archivio.hold_behavior(
        [
            {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
             "corpo": {"trigger": []}, "origine": "file"},
            {"id": "automation.a_mano", "tipo": "automazione", "nome": "A mano",
             "corpo": None, "origine": "solo_stato"},
            {"id": "script.vuoto", "tipo": "script", "nome": "Vuoto",
             "corpo": {}, "origine": "file"},
        ],
        problems=["automations.yaml: id 42 usato da 2 voci"],
        # La forma di `behavior.reread`: una voce archiviata senza corpo e'
        # anche in `unread_bodies`, per id (fino al 12/10/2026 qui c'era la
        # chiave di un file, la forma di prima del 10/09/2026; N118-2).
        unread_bodies={"automation.a_mano": "configurazione non letta da Home Assistant"},
    )
    app = web.Application()
    app["home_space_store"] = archivio
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)

    resp = await client.get("/api/home-space")
    assert resp.status == 200
    corpo = await resp.json()
    comportamento = corpo["comportamento"]
    # Data propria della sezione, diversa da `anagrafe_letta_il`.
    assert comportamento["letto_il"] is not None
    assert comportamento["conteggi"] == {"automazione": 2, "script": 1}
    # Solo "a_mano" e' senza corpo: "vuoto" un corpo ce l'ha, e' solo vuoto --
    # le due cose non sono la stessa cosa e non vanno confuse.
    assert comportamento["senza_corpo"] == 1
    # Le voci col corpo non escono (Tappa 9, F5, D3): nessuna pagina le
    # legge, e il corpo la chat lo chiede a `search`.
    assert "voci" not in comportamento
    # Le dichiarazioni costruite da comportamento.compose()/reread() devono
    # arrivare fin qui, non morire in un log (Important 3).
    assert comportamento["problemi"] == ["automations.yaml: id 42 usato da 2 voci"]
    assert comportamento["corpi_non_letti"] == {
        "automation.a_mano": "configurazione non letta da Home Assistant"}


@pytest.mark.asyncio
async def test_api_casa_mostra_le_plance_compresa_la_predefinita(aiohttp_client, tmp_path):
    archivio = HomeSpace(str(tmp_path))
    archivio.hold_dashboards([
        {"percorso": None, "titolo": "Principale"},
        {"percorso": "cucina", "titolo": "Cucina"},
    ])
    app = web.Application()
    app["home_space_store"] = archivio
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)

    resp = await client.get("/api/home-space")
    assert resp.status == 200
    corpo = await resp.json()
    sezione = corpo["plance"]
    # Data propria della sezione: `replace_dashboards` l'ha appena scritta,
    # non e' `aggiornata_il`/`anagrafe_letta_il`.
    assert sezione["lette_il"] is not None
    assert sezione["non_disponibili"] == []
    plance = sezione["voci"]
    assert len(plance) == 2
    # Di ogni plancia escono titolo e percorso, quelli che la pagina mostra
    # (Tappa 9, F5, D3).
    assert plance == [{"percorso": None, "titolo": "Principale"},
                      {"percorso": "cucina", "titolo": "Cucina"}]


@pytest.mark.asyncio
async def test_api_nucleo_mostra_il_testo_e_il_riepilogo(aiohttp_client, tmp_path):
    """`/api/briefing` mostra il testo ESATTO che il modello ha davanti, e il
    riepilogo (caratteri, troncato, ricordi esclusi) e' coerente col testo."""
    archivio_casa = HomeSpace(str(tmp_path))
    archivio_casa.hold_registries({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [],
        "entita": [{"entity_id": "light.cucina", "name": "Faretti", "area_id": "cucina"}],
        "etichette": [], "categorie": [], "integrazioni": [],
    })
    archivio_memoria = MemoryStore(str(tmp_path / "memoria.db"))
    archivio_memoria.remember("d'inverno la sala la preferisco fra 19 e 20 gradi",
                              detto_da="paolo")
    app = web.Application()
    app["home_space_store"] = archivio_casa
    app["memory_store"] = archivio_memoria
    app["entity_cache"] = _CacheFinta([{"id": "light.cucina", "state": "on"}])
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    resp = await client.get("/api/briefing")
    assert resp.status == 200
    corpo = await resp.json()
    testo = corpo["text"]
    riepilogo = corpo["summary"]
    assert "Cucina" in testo
    # Lo stato del momento non entra (29/09/2026): la luce accesa si chiede.
    assert "Notevole adesso" not in testo
    assert "fra 19 e 20 gradi" in testo            # i ricordi entrano interi
    # Il riepilogo non puo' mentire su cio' che il testo contiene davvero.
    assert riepilogo["chars"] == len(testo)
    assert riepilogo["truncated"] is False
    assert riepilogo["excluded_memories"] == 0
    archivio_memoria.close()


@pytest.mark.asyncio
async def test_api_nucleo_senza_archivi_non_afferma_di_sapere(aiohttp_client):
    """Senza archivio della casa e senza inventario vivo, il nucleo deve
    dichiarare "non ho potuto guardare" -- MAI un nucleo vuoto spacciato per
    una casa vuota. 200 comunque: e' una lacuna dichiarata, non un guasto."""
    app = web.Application()
    app["home_space_store"] = None
    app["memory_store"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    resp = await client.get("/api/briefing")
    assert resp.status == 200
    corpo = await resp.json()
    testo = corpo["text"]
    riepilogo = corpo["summary"]
    # Il nucleo dice "non ho guardato", non "va tutto bene".
    assert "non si è potuto guardare" in testo or "non si e’ potuto guardare" in testo
    assert any("non è stato letto" in a or "non attendibile" in a for a in riepilogo["notices"])


@pytest.mark.asyncio
async def test_api_nucleo_propaga_i_registri_non_disponibili(aiohttp_client, tmp_path):
    """Il difetto sbagliato tre volte su questo ramo: un registro caduto
    (qui "aree") deve comparire sia nella sezione "La casa" (che NON deve
    dire "Senza area", un'affermazione che non abbiamo il diritto di fare)
    sia nel riepilogo -- mai inghiottito da un modulo che lo riceve e non
    lo passa oltre."""
    archivio_casa = HomeSpace(str(tmp_path))
    archivio_casa.hold_registries({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [], "dispositivi": [],
        "entita": [{"entity_id": "light.orfana", "name": "Orfana", "area_id": None}],
        "etichette": [], "categorie": [], "integrazioni": [],
    }, unavailable=["aree"])
    app = web.Application()
    app["home_space_store"] = archivio_casa
    app["memory_store"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    resp = await client.get("/api/briefing")
    assert resp.status == 200
    corpo = await resp.json()
    sezione_casa = corpo["text"].split("## La casa")[1].split("\n## ")[0]
    assert "Aree non lette" in sezione_casa
    assert "Senza area" not in sezione_casa
    assert any("aree" in a and "non hanno risposto" in a for a in corpo["summary"]["notices"])


@pytest.mark.asyncio
async def test_api_nucleo_non_tronca_i_ricordi_al_default_di_richiama(aiohttp_client, tmp_path):
    """CRITICAL ①: il default di `MemoryStore.fetch()` e' `limit=20`.
    Con 200 ricordi veri, il vecchio handler ne passava a `compose()` solo
    20 -- il primo ricordo ("d'inverno la sala...") spariva PRIMA ancora di
    arrivare al taglio, e il riepilogo giurava `ricordi_esclusi: 0` su una
    casa con 180 ricordi invisibili. Qui si verifica che TUTTI i ricordi
    arrivino a `compose()` (usando `count()`), lasciando al taglio -- che
    dichiara sempre -- decidere cosa non entra."""
    archivio_casa = HomeSpace(str(tmp_path))
    archivio_casa.hold_registries({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "entita": [], "etichette": [], "categorie": [], "integrazioni": [],
    })
    archivio_memoria = MemoryStore(str(tmp_path / "memoria.db"))
    primo_ricordo = "d'inverno la sala la preferisco fra 19 e 20 gradi"
    archivio_memoria.remember(primo_ricordo, detto_da="paolo")  # il PIU' VECCHIO (id piu' basso)
    for i in range(200):
        archivio_memoria.remember(f"ricordo numero {i}: qualcosa che qualcuno ha detto",
                                  detto_da="paolo")
    app = web.Application()
    app["home_space_store"] = archivio_casa
    app["memory_store"] = archivio_memoria
    app["entity_cache"] = None
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    resp = await client.get("/api/briefing")
    assert resp.status == 200
    corpo = await resp.json()
    riepilogo = corpo["summary"]
    n_righe_ricordo = corpo["text"].count('" (detto da')
    # 201 ricordi in tutto: il taglio (non l'handler) decide quanti entrano,
    # e dichiara sempre il resto -- MAI un default silenzioso a 20.
    assert n_righe_ricordo + riepilogo["excluded_memories"] == 201
    assert riepilogo["excluded_memories"] > 0  # con 201 ricordi lunghi, il tetto di default taglia
    # Il PIU' VECCHIO (il primo scritto) e' anche il primo a saltare per la
    # regola "il piu' vecchio prima" -- ma la sua assenza deve essere
    # CONTATA in ricordi_esclusi, mai un'invisibilita' gratuita come prima.
    archivio_memoria.close()


@pytest.mark.asyncio
async def test_api_nucleo_riceve_i_problemi_e_i_corpi_non_letti_del_comportamento(
        aiohttp_client, tmp_path):
    """`/api/home-space` espone gia' `problemi`/`corpi_non_letti` del
    comportamento, ma `compose()` non aveva un parametro per riceverli -- e il
    PERCHE' non arrivava mai al modello attraverso `/api/briefing`.

    Dal 10/09/2026 il soggetto non e' piu' un file ma l'ENTITA' di cui non si
    conosce il corpo: l'avviso dice quante sono, non quali file mancano. E non
    c'e' piu' un caso da escludere -- un corpo non letto nasconde sempre cio'
    che quell'automazione fa."""
    archivio_casa = HomeSpace(str(tmp_path))
    archivio_casa.hold_registries({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "entita": [], "etichette": [], "categorie": [], "integrazioni": [],
    })
    archivio_casa.hold_behavior(
        [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
          "corpo": {"trigger": []}}],
        problems=["automations.yaml: id 42 usato da 2 voci"],
        unread_bodies={"script.muto": "configurazione non letta da Home Assistant"},
    )
    app = web.Application()
    app["home_space_store"] = archivio_casa
    app["memory_store"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    resp = await client.get("/api/briefing")
    assert resp.status == 200
    corpo = await resp.json()
    avvisi = corpo["summary"]["notices"]
    assert any("problema" in a and "comportamento" in a for a in avvisi)
    assert any("non conosco il corpo" in a for a in avvisi)


@pytest.mark.asyncio
async def test_pagina_e_nucleo_contano_gli_stessi_corpi_mancanti(aiohttp_client, tmp_path):
    """N118-2 (giro 118): «quante voci senza corpo» e' un fatto solo, e lo
    contano tutte e due le porte con `behavior.without_body`. Una voce che sta
    solo in `unread_bodies` conta per la pagina come per il nucleo.

    Rossa prima: la pagina contava solo i corpi `None` (0), il nucleo
    l'unione (1)."""
    archivio_casa = HomeSpace(str(tmp_path))
    archivio_casa.hold_registries({
        "piani": [], "aree": [], "dispositivi": [], "entita": [], "etichette": [],
        "categorie": [], "integrazioni": [],
    })
    archivio_casa.hold_behavior(
        [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
          "corpo": {"trigger": []}}],
        unread_bodies={"script.muto": "configurazione non letta da Home Assistant"},
    )
    app = web.Application()
    app["home_space_store"] = archivio_casa
    app["memory_store"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    pagina = await (await client.get("/api/home-space")).json()
    nucleo = await (await client.get("/api/briefing")).json()
    avviso = next(a for a in nucleo["summary"]["notices"] if "non conosco il corpo" in a)
    assert pagina["comportamento"]["senza_corpo"] == 1
    assert avviso.startswith("di 1 fra"), avviso


@pytest.mark.asyncio
async def test_le_etichette_escono_col_nome_sull_entita_non_in_una_mappa(aiohttp_client,
                                                                         tmp_path):
    """Fino al 12/10/2026 l'albero portava i soli `label_id` e, a parte, la
    mappa id -> nome (e quella delle categorie, per ambito), che la pagina
    applicava da se'. Dalla Tappa 9 (F5, D1) l'entita' e' la resa media: le
    etichette arrivano col nome, nella forma della chat (`Nome (id: X)`), e
    le due mappe non escono piu'. L'area non porta alias ne' etichette (D3).

    Rossa prima di F5: `etichette` della voce era `["da_controllare"]`."""
    casa = HomeSpace(str(tmp_path))
    casa.hold_registries({
        "aree": [{"area_id": "cucina", "name": "Cucina", "labels": ["da_controllare"],
                  "aliases": ["Angolo cottura"]}],
        "etichette": [{"label_id": "da_controllare", "name": "Da controllare"}],
        "entita": [{"entity_id": "light.cucina", "area_id": "cucina",
                    "labels": ["da_controllare"], "aliases": ["Lampadario"],
                    "platform": "hue", "translation_key": "ceiling"}],
    }, [])
    app = web.Application()
    app["home_space_store"] = casa
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)

    corpo = await (await client.get("/api/home-space")).json()
    assert "etichette" not in corpo and "categorie" not in corpo
    area = corpo["piani"][0]["aree"][0]
    assert "etichette" not in area and "alias" not in area
    luce = area["entita"][0]
    assert luce["etichette"] == ["Da controllare (id: da_controllare)"]
    assert luce["alias"] == ["Lampadario"]
    assert luce["translation_key"] == "ceiling"
    assert luce["integrazione"] == {"id": "hue", "nome": "hue"}
    # Il ramo e' l'area: non si ripete sull'entita'; le ceste dello stato non
    # le disegna nessuno.
    assert "area" not in luce and "attributi" not in luce


@pytest.mark.asyncio
async def test_l_albero_non_porta_gli_attributi_dello_stato(tmp_path):
    """Gli `attributi` restano fuori dall'albero (`_TREE_DROPS`). Non e' solo
    il peso: questa porta non passa dal filtro di riservatezza
    (`privacy.redact_row`, che applica solo `query_house`) e la leggono anche
    i servizi firmati «lettore» e «utente». Con le ceste, la posizione di una
    persona uscirebbe di qui (N135-1, giro 135).

    Mutazione ESEGUITA: `_TREE_DROPS = ("area",)` -- rossa (le ceste della
    persona escono, con `latitude`)."""
    specchio = EntityCache()
    await specchio.load(CasaFinta({"states": [
        {"entity_id": "person.inquilino", "state": "Lavoro",
         "attributes": {"friendly_name": "Inquilino", "latitude": 45.1,
                        "longitude": 9.2, "gps_accuracy": 10}}]}))
    casa = HomeSpace(str(tmp_path))
    casa.hold_registries({
        "aree": [{"area_id": "ingresso", "name": "Ingresso"}],
        "entita": [{"entity_id": "person.inquilino", "area_id": "ingresso"}],
    }, [])
    app = web.Application()
    app["home_space_store"] = casa
    app["entity_cache"] = specchio
    risposta = await handle_get_home_space(
        make_mocked_request("GET", "/api/home-space", app=app))
    corpo = json.loads(risposta.text)
    persona = corpo["piani"][0]["aree"][0]["entita"][0]
    assert persona["id"] == "person.inquilino"
    assert "attributi" not in persona, persona
    assert "latitude" not in risposta.text and "45.1" not in risposta.text


@pytest.mark.asyncio
async def test_l_entita_dell_albero_e_quella_di_search(tmp_path):
    """Fondamenta 3: la stessa entita' ha la stessa forma dalla pagina e dalla
    chat. L'albero e' la resa media meno il ramo (`area`) e le ceste
    (`attributi`), con lo stato in parole della stessa tabella.

    Mutazione ESEGUITA: `_tree_entity` alla corta -- rossa (mancano `classe` e
    `integrazione`)."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        risposta = await handle_get_home_space(
            make_mocked_request("GET", "/api/home-space", app=app))
        corpo = json.loads(risposta.text)
        albero = {e["id"]: e for piano in corpo["piani"] for area in piano["aree"]
                  for e in area.get("entita") or []}
        dispatcher = create_tool_dispatcher(app, soffitto=consente(None, ruolo="amministratore"))
        ricerca = await dispatcher.dispatch("search", {"dominio": "sensor"})
    assert ricerca["profondita"] == "media", ricerca["profondita"]
    confrontate = 0
    for voce in ricerca["voci"]:
        attesa = {k: v for k, v in voce.items() if k not in ("area", "attributi")}
        assert albero[voce["id"]] == attesa, voce["id"]
        confrontate += 1
    assert confrontate >= 2


# -- il corpo delle automazioni solo a chi amministra (3.73.1) ---------------

def _app_with_behavior(tmp_path, soggetto):
    archivio = HomeSpace(str(tmp_path))
    archivio.hold_registries({"piani": [], "aree": [], "dispositivi": [], "entita": [],
                              "etichette": [], "categorie": [], "integrazioni": []})
    archivio.hold_behavior([
        {"tipo": "automazione", "id": "a1", "nome": "Luci", "corpo": {"triggers": [1]}},
        {"tipo": "automazione", "id": "a2", "nome": "Senza corpo", "corpo": None},
        {"tipo": "script", "id": "s1", "nome": "Buonanotte", "corpo": {"sequence": [1]}},
    ])

    @web.middleware
    async def confine(request, handler):
        # Un servizio firmato, come lo lascia `middleware_internal_auth`.
        request["auth_via"] = "canale"
        request["soggetto"] = soggetto
        return await handler(request)

    app = web.Application(middlewares=[confine])
    app["home_space_store"] = archivio
    app.router.add_get("/api/home-space", handle_get_home_space)
    return app


def _servizio(ruolo):
    return {"specie": "servizio", "id": "un servizio", "nome": "un servizio",
            "utente": None, "ruolo": ruolo}


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo", ["lettore", "utente", "amministratore", None])
async def test_il_corpo_delle_automazioni_non_esce_da_questa_porta(aiohttp_client, tmp_path,
                                                                   ruolo):
    """Dalla 3.73.1 la rotta copriva il corpo a chi non amministra. Dalla
    Tappa 9 (F5, D3) le voci non escono per nessuno: nessuna pagina le
    leggeva, e il corpo la chat lo chiede a `search`, con la stessa regola
    (`privacy.cover_reserved_body`). Un ruolo per caso: un corpo rimesso
    nella risposta per chi amministra (come la 3.73.1) arrossisce il suo."""
    app = _app_with_behavior(tmp_path, _servizio(ruolo))
    client = await aiohttp_client(app)
    risposta = await (await client.get("/api/home-space")).json()
    assert "voci" not in risposta["comportamento"]
    assert "triggers" not in str(risposta) and "sequence" not in str(risposta)


@pytest.mark.asyncio
async def test_senza_corpo_conta_cio_che_HIRIS_non_sa_non_cio_che_copre(aiohttp_client, tmp_path):
    """`senza_corpo` e' «quante voci HIRIS conosce solo di nome», anche per
    chi non amministra.

    Mutazione ESEGUITA il 12/10/2026 (Tappa 9, chiusura): `senza_corpo`
    come numero di tutte le voci -- rossa (3 invece di 1). Quella di prima
    («contato dopo la copertura») non si puo' piu' costruire: dalla F5 la
    rotta non copre piu' niente, perche' le voci non escono."""
    app = _app_with_behavior(tmp_path, _servizio("lettore"))
    client = await aiohttp_client(app)
    risposta = await (await client.get("/api/home-space")).json()
    assert risposta["comportamento"]["senza_corpo"] == 1


@pytest.mark.asyncio
async def test_la_replica_conservata_esce_dalle_due_porte_nella_stessa_forma(
        aiohttp_client, tmp_path):
    """G-16 (Tappa 8, Task 10): il segno della replica conservata si chiede a
    `/api/home-space` (l'oggetto, per il comportamento e per le plance) e
    arriva al nucleo di `/api/briefing` (a parole, con la data). Mutazione
    eseguita: non passare `behavior_kept` a `compose` -> rossa sull'avviso."""
    archivio = HomeSpace(str(tmp_path))
    archivio.hold_behavior([{"id": "automation.sveglia", "tipo": "automazione",
                             "nome": "Sveglia", "corpo": {"trigger": []}}])
    archivio.keep_behavior("Home Assistant non le ha ancora caricate")
    archivio.keep_dashboards("nessuna plancia leggibile", unavailable=["principale"])
    app = web.Application()
    app["home_space_store"] = archivio
    app["memory_store"] = None
    app["entity_cache"] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    casa = await (await client.get("/api/home-space")).json()
    nucleo = await (await client.get("/api/briefing")).json()

    assert casa["comportamento"]["conservato"] == {
        "motivo": "Home Assistant non le ha ancora caricate",
        "letto_il": casa["comportamento"]["letto_il"]}
    assert casa["plance"]["conservato"] == {"motivo": "nessuna plancia leggibile",
                                           "letto_il": None}
    assert casa["plance"]["non_disponibili"] == ["principale"]
    assert any("replica letta" in a and "non le ha ancora caricate" in a
               for a in nucleo["summary"]["notices"])


@pytest.mark.asyncio
async def test_api_casa_una_classe_che_non_c_e_non_si_scrive_null(aiohttp_client, tmp_path):
    """C-63 (regola dell'assenza, D1 della Tappa 4): la classe e l'unita' vive
    entrano nella riga solo quando ci sono. Fino all'11/10/2026
    `_with_live_kind` scriveva `classe: None` e `unita: None` su ogni entita'
    senza, mentre `render_entity` lascia mancare la chiave: lo stesso fatto in
    due forme da due porte.

    Mutazione ESEGUITA: `_with_live_kind` che torna a scrivere i `None` --
    rossa (la luce porta `classe`)."""
    archivio = HomeSpace(str(tmp_path))
    archivio.hold_registries({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "etichette": [], "categorie": [], "integrazioni": [],
        "entita": [{"entity_id": "light.cucina", "name": "Faretti", "area_id": "cucina"},
                   {"entity_id": "sensor.frigo", "name": "Frigo", "area_id": "cucina"}],
    })
    app = web.Application()
    app["home_space_store"] = archivio
    app["entity_cache"] = _CacheFinta([
        {"id": "light.cucina", "state": "on", "name": "Faretti"},
        {"id": "sensor.frigo", "state": "4", "name": "Frigo", "unit": "°C",
         "device_class": "temperature"}])
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)

    corpo = await (await client.get("/api/home-space")).json()
    per_id = {e["id"]: e for e in corpo["piani"][0]["aree"][0]["entita"]}
    assert "classe" not in per_id["light.cucina"], per_id["light.cucina"]
    assert "unita" not in per_id["light.cucina"], per_id["light.cucina"]
    assert per_id["sensor.frigo"]["classe"] == "temperature"
    assert per_id["sensor.frigo"]["unita"] == "°C"
