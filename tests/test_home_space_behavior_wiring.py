"""Il cablaggio del lettore del comportamento.

**Sette prove di questo file sono uscite il 10/09/2026, con cio' che
difendevano**: l'impronta sull'`mtime` di `automations.yaml`/`scripts.yaml` --
«se i file non cambiano non si rilegge», «un file toccato fa rileggere»,
«forza rilegge anche se i file non sono cambiati». Quel confronto esisteva
perche' la fonte era il file e per gli script Home Assistant non emette
nessun evento di ricarica. Adesso la fonte e' Home Assistant, l'impronta di
quei file non dice piu' niente su cio' che HA ha caricato -- un'automazione
dentro un pacchetto non li tocca affatto -- e un giro costa **66 ms misurati**:
si rilegge e basta.

Restano le tre proprieta' che non dipendevano dall'impronta.
"""
import pytest

from hiris.app.home_space.reader import HomeSpace
from hiris.app.server import behavior_reader


class _Cliente:
    def __init__(self, *, solleva=False):
        self.solleva = solleva
        self.giri = 0

    async def get_states(self, entity_ids):
        self.giri += 1
        if self.solleva:
            raise RuntimeError("Home Assistant non risponde")
        return [{"entity_id": "automation.sveglia", "state": "on",
                 "attributes": {"friendly_name": "Sveglia"}}]

    async def behavior_configs(self, entity_ids):
        return {"configurazioni": {e: {"alias": "Sveglia"} for e in entity_ids}}


@pytest.fixture
def casa(tmp_path):
    a = HomeSpace(str(tmp_path / "casa.db"))
    yield a
    a.close()


@pytest.mark.asyncio
async def test_ogni_giro_rilegge(casa, tmp_path):
    """Non c'e' piu' niente da sorvegliare: due giri, due letture. Il
    contrario -- un giro che non rilegge -- vorrebbe dire una casa che tiene
    per se' un'automazione appena scritta.

    Mutazione che la uccide: rimettere un confronto che salti il secondo giro.
    """
    client = _Cliente()
    guarda = behavior_reader(client, casa, tmp_path)

    assert await guarda() is True
    assert await guarda() is True
    assert client.giri == 2


@pytest.mark.asyncio
async def test_senza_cartella_non_esplode(casa):
    """La cartella serve solo per `secrets.yaml`: senza, il comportamento si
    legge lo stesso e i corpi restano non archiviati (dichiarati). Non
    sollevare e' cio' che tiene in piedi il giro periodico."""
    guarda = behavior_reader(_Cliente(), casa, None, find_folder=lambda: None)

    assert await guarda() is True
    assert casa.behavior()[0]["corpo"] is None
    assert casa.unread_bodies()


@pytest.mark.asyncio
async def test_la_cartella_comparsa_dopo_l_avvio_si_trova(casa, tmp_path):
    """L'add-on puo' partire prima che il Supervisor abbia montato la cartella:
    risolverla una volta sola all'avvio significherebbe restare convinti per
    sempre che i segreti non si possano controllare -- e non archiviare mai
    piu' un corpo.

    Mutazione che la uccide: cercare la cartella solo alla costruzione.
    """
    import yaml
    (tmp_path / "secrets.yaml").write_text(yaml.safe_dump({"t": "x"}), encoding="utf-8")
    apparsa = {"quando": None}

    def _trova():
        return apparsa["quando"]

    guarda = behavior_reader(_Cliente(), casa, None, find_folder=_trova)
    await guarda()
    assert casa.behavior()[0]["corpo"] is None      # ancora senza cartella

    apparsa["quando"] = str(tmp_path)
    await guarda()

    assert casa.behavior()[0]["corpo"] == {"alias": "Sveglia"}
    assert casa.unread_bodies() == {}


@pytest.mark.asyncio
async def test_una_rilettura_fallita_non_blocca_le_successive(casa, tmp_path):
    """Un guasto passeggero -- Home Assistant che si riavvia -- non deve
    congelare il comportamento: si riprova al giro dopo, e lo si dice."""
    client = _Cliente(solleva=True)
    guarda = behavior_reader(client, casa, tmp_path)

    assert await guarda() is False

    client.solleva = False
    assert await guarda() is True
