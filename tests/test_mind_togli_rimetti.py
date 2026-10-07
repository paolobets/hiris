"""Togli e rimetti nello scope (strato 3 degli attori, Task 3.7, D9).

Due movimenti, due autori, la stessa regola (`mind/scope.may_overwrite`):

- il **proprietario toglie** (o rimette) dalla pagina dell'osservatore: la
  rotta `POST /api/mind/scope` scrive con autore `OWNER`;
- l'**analista rimette dentro** dalla sua risposta (`rimetti`, Task 3.5):
  quando l'analisi si archivia, `analyst.bring_back` lo scrive con autore
  `ANALYST`, e cio' che il proprietario ha tolto resta fuori -- con la
  ragione scritta accanto alla richiesta, non un silenzio.

Fino a questo task `ANALYST` e `OWNER` non avevano nessun chiamante in
produzione (M-12 del registro dei doppioni).
"""
import json

import pytest

from hiris.app.api.handlers_mind import handle_set_scope
from hiris.app.home_space.house import House
from hiris.app.mind import analyst
from hiris.app.mind.scope import ANALYST, OBSERVER, OWNER
from hiris.app.mind.store import ObservationsStore

#: Chi chiede dalla pagina: un amministratore entrato dall'ingress, come lo
#: lascia il confine (stessa premessa di `test_handlers_mind_judgment.py`).
AMMINISTRATORE = {"specie": "persona", "id": "u-admin", "nome": "Paolo"}


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(str(tmp_path / "osservazioni.db"))
    yield a
    a.close()


def _richiesta(app, corpo, *, ruolo="amministratore"):
    class _R(dict):
        def __init__(self):
            super().__init__(soggetto=AMMINISTRATORE, auth_via="ingress", ruolo=ruolo)
            app.setdefault("ruoli", {"quando": 0.0, "per_id": {}})
            self.app = app
            self.query = {}
            self.method, self.path = "POST", "/api/mind/scope"

        async def json(self):
            return corpo
    return _R()


# -- Il proprietario, dalla pagina -------------------------------------------

@pytest.mark.asyncio
async def test_il_proprietario_toglie_e_la_decisione_e_sua(archivio):
    archivio.decide_scope("sensor.vicino", inside=True, reason="pesa", author=OBSERVER,
                          when_ts=1000.0)

    r = await handle_set_scope(_richiesta({"observations": archivio}, {
        "soggetto": "sensor.vicino", "dentro": False, "motivo": "e' il sensore del vicino"}))

    assert r.status == 200
    corpo = json.loads(r.text)
    assert corpo["decisione"]["dentro"] is False
    assert corpo["decisione"]["autore"] == OWNER
    voce = archivio.scope()["sensor.vicino"]
    assert (voce["dentro"], voce["autore"], voce["motivo"]) == (
        False, OWNER, "e' il sensore del vicino")
    assert archivio.is_watched("sensor.vicino") is False


@pytest.mark.asyncio
async def test_senza_motivo_si_scrive_quello_di_ripiego(archivio):
    """`decide_scope` rifiuta una decisione senza ragione: il motivo e'
    facoltativo per chi preme il bottone, mai per l'archivio."""
    archivio.decide_scope("sensor.x", inside=True, reason="pesa", author=OBSERVER)

    r = await handle_set_scope(_richiesta({"observations": archivio}, {
        "soggetto": "sensor.x", "dentro": False, "motivo": "   "}))

    assert r.status == 200
    assert archivio.scope()["sensor.x"]["motivo"] == analyst.OWNER_REMOVED


@pytest.mark.asyncio
async def test_il_proprietario_puo_cambiare_idea(archivio):
    """La prova della mutazione del Passo 4: con `>` invece di `>=` in
    `may_overwrite` il proprietario non potrebbe piu' rimettere dentro cio'
    che lui stesso ha tolto."""
    archivio.decide_scope("sensor.x", inside=True, reason="pesa", author=OBSERVER)
    app = {"observations": archivio}
    await handle_set_scope(_richiesta(app, {"soggetto": "sensor.x", "dentro": False}))

    r = await handle_set_scope(_richiesta(app, {"soggetto": "sensor.x", "dentro": True}))

    assert r.status == 200
    voce = archivio.scope()["sensor.x"]
    assert (voce["dentro"], voce["autore"], voce["motivo"]) == (
        True, OWNER, analyst.OWNER_BROUGHT_BACK)


@pytest.mark.asyncio
async def test_si_tocca_solo_cio_su_cui_qualcuno_ha_deciso(archivio):
    """La pagina toglie e rimette righe che esistono: un soggetto mai
    giudicato e' un 404, non una riga nuova che nessun evento accendera'."""
    r = await handle_set_scope(_richiesta({"observations": archivio}, {
        "soggetto": "sensor.mai_visto", "dentro": False}))
    assert r.status == 404
    assert archivio.scope() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("corpo", [
    {"soggetto": "log:zha", "dentro": False},
    {"soggetto": "sensor.x"},
    {"soggetto": "sensor.x", "dentro": "no"},
    {"soggetto": "sensor.x", "dentro": False, "motivo": 3},
])
async def test_un_corpo_storto_e_un_400(archivio, corpo):
    archivio.decide_scope("sensor.x", inside=True, reason="pesa", author=OBSERVER)
    r = await handle_set_scope(_richiesta({"observations": archivio}, corpo))
    assert r.status == 400
    assert archivio.scope()["sensor.x"]["autore"] == OBSERVER


@pytest.mark.asyncio
async def test_chi_non_costruisce_non_toglie(archivio):
    """Una decisione `OWNER` non la scavalca nessuno: la scrive solo chi puo'
    costruire (`soffitto.require_builder`), come i giudizi sui tipi."""
    archivio.decide_scope("sensor.x", inside=True, reason="pesa", author=OBSERVER)
    r = await handle_set_scope(_richiesta({"observations": archivio}, {
        "soggetto": "sensor.x", "dentro": False}, ruolo="utente"))
    assert r.status == 403
    assert archivio.scope()["sensor.x"]["autore"] == OBSERVER


@pytest.mark.asyncio
async def test_senza_archivio_e_un_503():
    r = await handle_set_scope(_richiesta({}, {"soggetto": "sensor.x", "dentro": False}))
    assert r.status == 503


# -- L'analista, dalla risposta ----------------------------------------------

class _Anagrafe:
    """L'archivio dell'anagrafe, con le sole entita' nominate: quanto basta a
    `House.read` per sapere cosa la casa ha."""

    def __init__(self, *ids):
        self._ids = ids

    def read(self):
        return {"entita": [{"id": i} for i in self._ids], "dispositivi": [], "aree": []}

    def unavailable(self):
        return ()

    def reference_frame(self):
        return {}


def _casa(*ids):
    """La casa di adesso, con le sole entita' nominate."""
    return House.read(_Anagrafe(*ids), None)


def _analisi(*ids):
    return {"osservazioni": [],
            "rimetti": [{"id": i, "perche": "spiega il crollo"} for i in ids]}


def test_l_analista_rimette_cio_che_l_osservatore_ha_tolto(archivio):
    archivio.decide_scope("sensor.pioggia", inside=False, reason="non pesa",
                          author=OBSERVER, when_ts=1000.0)

    scritta = analyst.bring_back(archivio, _analisi("sensor.pioggia"), _casa("sensor.pioggia"),
                                 when_ts=2000.0)

    voce = archivio.scope()["sensor.pioggia"]
    assert (voce["dentro"], voce["autore"], voce["motivo"]) == (
        True, ANALYST, "spiega il crollo")
    assert scritta["rimetti"][0]["esito"] == analyst.BACK_IN
    assert "ragione" not in scritta["rimetti"][0]


def test_l_analista_non_rimette_cio_che_il_proprietario_ha_tolto(archivio):
    """Il rifiuto si dice, con la ragione, accanto alla richiesta: senza,
    l'analisi archiviata direbbe che l'analista ha chiesto e basta, e nessuno
    saprebbe perche' la cosa e' rimasta fuori."""
    archivio.decide_scope("sensor.vicino", inside=False, reason="e' del vicino",
                          author=OWNER, when_ts=1000.0)

    scritta = analyst.bring_back(archivio, _analisi("sensor.vicino"), _casa("sensor.vicino"),
                                 when_ts=2000.0)

    voce = archivio.scope()["sensor.vicino"]
    assert (voce["dentro"], voce["autore"]) == (False, OWNER)
    esito = scritta["rimetti"][0]
    assert esito["esito"] == analyst.BACK_IN_REFUSED
    assert "proprietario" in esito["ragione"]
    assert "e' del vicino" in esito["ragione"]


def test_cio_che_e_gia_dentro_non_si_riscrive(archivio):
    """L'osservatore l'aveva gia' messo dentro: il motivo e l'autore restano i
    suoi, e il «dal ...» della pagina non si sposta."""
    archivio.decide_scope("sensor.solare", inside=True, reason="pesa",
                          author=OBSERVER, when_ts=1000.0)

    scritta = analyst.bring_back(archivio, _analisi("sensor.solare"), _casa("sensor.solare"),
                                 when_ts=2000.0)

    voce = archivio.scope()["sensor.solare"]
    assert (voce["autore"], voce["quando"]) == (OBSERVER, 1000.0)
    assert scritta["rimetti"][0]["esito"] == analyst.ALREADY_INSIDE


def test_l_analista_non_rimette_cio_che_la_casa_non_ha(archivio):
    """N65-2: un id ben scritto che ne' il registro ne' gli stati conoscono
    non entra, nemmeno fuori dallo scope: il rifiuto sta accanto alla
    richiesta, con la ragione."""
    scritta = analyst.bring_back(archivio, _analisi("sensor.inventato"),
                                 _casa("sensor.pioggia"), when_ts=2000.0)

    assert archivio.scope() == {}
    assert scritta["rimetti"] == [{"id": "sensor.inventato", "perche": "spiega il crollo",
                                   "esito": analyst.BACK_IN_REFUSED,
                                   "ragione": analyst.NOT_IN_HOUSE}]


def test_un_analisi_senza_rimetti_passa_com_e(archivio):
    analisi = {"osservazioni": []}
    assert analyst.bring_back(archivio, analisi, _casa()) == analisi
    assert archivio.scope() == {}


# -- Dal giro dell'analista, per intero --------------------------------------

class _ModelloCheRimette:
    async def chat(self, **kwargs):
        return json.dumps({"osservazioni": [], "rimetti": [
            {"id": "sensor.pioggia", "perche": "spiega il crollo"},
            {"id": "sensor.vicino", "perche": "forse serve"}]})


@pytest.mark.asyncio
async def test_il_giro_dell_analista_scrive_il_rimetti_e_lo_archivia(archivio):
    """Il collegamento: senza la chiamata in `analyst_round.write_analysis` il
    `rimetti` validato dal Task 3.5 finirebbe nell'archivio e basta, e lo
    scope non cambierebbe mai."""
    from hiris.app import server
    from hiris.app.home_space import historian

    archivio.replace_report("2026-09-15", {
        "giorno": "2026-09-15", "obiettivo": None, "forme": [], "cronaca": [],
        "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                    "operazione": "somma_periodo", "valore": 1.0, "unita": "kWh",
                    "copertura": 1.0}]})
    archivio.decide_scope("sensor.pioggia", inside=False, reason="non pesa", author=OBSERVER)
    archivio.decide_scope("sensor.vicino", inside=False, reason="e' del vicino", author=OWNER)

    await server.analyst_round({"observations": archivio, "llm_router": _ModelloCheRimette(),
                                "bridge_active": False,
                                "home_space_store": _Anagrafe("sensor.pioggia", "sensor.vicino")})

    scope = archivio.scope()
    assert (scope["sensor.pioggia"]["dentro"], scope["sensor.pioggia"]["autore"]) == (
        True, ANALYST)
    assert (scope["sensor.vicino"]["dentro"], scope["sensor.vicino"]["autore"]) == (
        False, OWNER)
    oggi = historian.today(historian.house_timezone(None)).isoformat()
    esiti = {r["id"]: r["esito"] for r in archivio.analysis(oggi)["rimetti"]}
    assert esiti == {"sensor.pioggia": analyst.BACK_IN,
                     "sensor.vicino": analyst.BACK_IN_REFUSED}


class _ModelloCheInventa:
    async def chat(self, **kwargs):
        return json.dumps({"osservazioni": [], "rimetti": [
            {"id": "sensor.pioggia", "perche": "spiega il crollo"},
            {"id": "sensor.inventato", "perche": "forse serve"}]})


@pytest.mark.asyncio
async def test_il_giro_dell_analista_non_rimette_un_entita_che_la_casa_non_ha(archivio):
    """N65-2 (giro 66 del revisore): `analyst_turn._back_in` valida solo la
    FORMA dell'id, quindi un id ben scritto che la casa non ha diventava una
    riga «decisa dall'analista» che nessun evento accendera' mai. Si filtra
    sull'anagrafe di adesso, come l'osservatore con `known`, e il rifiuto si
    scrive con la ragione accanto alla richiesta.

    Mutazione ESEGUITA (07/10/2026): `bring_back` senza il filtro -- rossa
    (`sensor.inventato` entra nello scope con autore analista)."""
    from hiris.app import server
    from hiris.app.home_space import historian

    archivio.replace_report("2026-09-15", {
        "giorno": "2026-09-15", "obiettivo": None, "forme": [], "cronaca": [],
        "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                    "operazione": "somma_periodo", "valore": 1.0, "unita": "kWh",
                    "copertura": 1.0}]})
    archivio.decide_scope("sensor.pioggia", inside=False, reason="non pesa", author=OBSERVER)

    await server.analyst_round({"observations": archivio, "llm_router": _ModelloCheInventa(),
                                "bridge_active": False,
                                "home_space_store": _Anagrafe("sensor.pioggia")})

    assert "sensor.inventato" not in archivio.scope()
    assert archivio.scope()["sensor.pioggia"]["autore"] == ANALYST
    oggi = historian.today(historian.house_timezone(None)).isoformat()
    esiti = {r["id"]: r for r in archivio.analysis(oggi)["rimetti"]}
    assert esiti["sensor.pioggia"]["esito"] == analyst.BACK_IN
    assert esiti["sensor.inventato"]["esito"] == analyst.BACK_IN_REFUSED
    assert esiti["sensor.inventato"]["ragione"] == analyst.NOT_IN_HOUSE
