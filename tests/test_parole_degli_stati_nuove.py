"""Le parole degli stati si seminano solo quando sono NUOVE (A-22, Tappa 8,
Task 9, 08/10/2026).

Il giro dei cinque minuti (`hiris_state_translations`) rileggeva le
traduzioni dalla cache e rifaceva `seed` nel sapere: non scriveva niente dopo
la prima volta, ma ricalcolava tutto e faceva avanzare la versione del
sapere, che svuotava la cache degli attributi dell'osservatore
(`Watcher._wanted_attributes`) ogni cinque minuti.

Nessun evento di Home Assistant dice «le traduzioni sono cambiate» (letto in
`helpers/translation.py` al tag 2026.9.4): il giro resta a intervallo, per la
prima lettura fallita.

Mutazioni ESEGUITE:
- `prime_state_translations` che semina senza guardare `appena_lette` --
  rossa `test_il_giro_sulla_tabella_in_cache_non_tocca_il_sapere`;
- `KnowledgeStore.seed` che fa avanzare la versione anche senza scritture --
  rossa `test_un_seme_che_non_scrive_non_fa_avanzare_la_versione` (la prova
  del giro resta verde: sulla tabella in cache il seme non si chiama affatto).
"""
import pytest

from hiris.app.mind.knowledge import Fact, KnowledgeStore
from hiris.app.mind.state_words import prime_state_translations
from hiris.app.proxy.state_translations import StateTranslations

_RISORSE = {"component.binary_sensor.entity_component.gas.name": "Gas"}


class _Client:
    def __init__(self):
        self.reads = 0

    async def get_translations(self, language, *, category):
        self.reads += 1
        return {"risorse": dict(_RISORSE)}


class _Casa:
    def reference_frame(self):
        return {"versione_ha": "2026.9.4", "lingua": "it"}


@pytest.fixture
def sapere(tmp_path):
    k = KnowledgeStore(str(tmp_path / "sapere.db"))
    yield k
    k.close()


@pytest.mark.asyncio
async def test_la_cache_dice_se_la_tabella_e_appena_letta():
    client = _Client()
    cache = StateTranslations(client)
    first = await cache.read(ha_version="2026.9.4", language="it")
    second = await cache.read(ha_version="2026.9.4", language="it")
    assert (first["appena_lette"], second["appena_lette"]) == (True, False)
    assert client.reads == 1
    third = await cache.read(ha_version="2026.10.0", language="it")
    assert third["appena_lette"] is True


@pytest.mark.asyncio
async def test_il_giro_sulla_tabella_in_cache_non_tocca_il_sapere(sapere):
    app = {"knowledge": sapere, "home_space_store": _Casa(),
           "state_translations": StateTranslations(_Client())}

    await prime_state_translations(app)
    assert sapere.get("tipo", "binary_sensor.gas", "significato").value == "Gas"
    version = sapere.version()

    calls = []
    seed = sapere.seed
    sapere.seed = lambda *a, **k: calls.append(1) or seed(*a, **k)
    await prime_state_translations(app)

    assert calls == []
    assert sapere.version() == version


def test_un_seme_che_non_scrive_non_fa_avanzare_la_versione(sapere):
    fact = Fact(subject_kind="tipo", subject="binary_sensor.gas", field="significato",
                value="Gas", provenance="importato", who="prova", when_ts=1_000.0,
                source="Home Assistant 2026.9.4, it")
    assert sapere.seed([fact]) == 1
    version = sapere.version()
    assert sapere.seed([fact]) == 0
    assert sapere.version() == version
