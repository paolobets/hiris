"""Persone e dispositivi che le seguono non arrivano al modello col loro nome
(decisione 12 della spec «Una fonte sola di verita'», approvata dal
proprietario; Tappa 6, Task 6).

Misurato sul commit di partenza `5bce65d`: `observer.house_lines` scriveva
`person.paolo · Paolo` e `device_tracker.iphone_di_paolo · iPhone di Paolo`
nella domanda dell'osservatore, cioe' a un modello esterno. Il nome sta anche
nell'IDENTIFICATORE, quindi togliere il solo nome non basta: la riga porta un
segnaposto (`person.#1`) e la risposta si riporta all'id vero dentro HIRIS.

Chi e' «persona» non e' una lista di questa prova ne' dell'osservatore: e'
`home_space/privacy.MOVING_DOMAINS`, il genere «presenza» del vocabolario dei
tipi. Le prove lo CHIEDONO, e una lo confronta con cio' che Home Assistant
dichiara (`person` e `device_tracker`, Core 2026.9.3).

Mutazioni ESEGUITE (05/10/2026), ciascuna poi ripristinata e verificata con
`git status`:
- tolto il segnaposto in `house_lines` (la riga torna con id e nome): rosse le
  prove delle righe, della domanda sulla catena e del turno del ponte, col nome
  della persona nel messaggio;
- `apply_answer` senza il ritorno dal segnaposto all'id: rossa la prova della
  decisione (il segnaposto finiva fra le ignorate, e la persona veniva
  annotata come «guardata e non giudicata»).
"""
import os

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.privacy import MOVING_DOMAINS
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import observer
from hiris.app.mind.store import ObservationsStore

#: I nomi che non devono arrivare al modello, in ogni forma in cui la casa li
#: porta: il nome mostrato e l'object_id.
_NAMES = ("paolo", "giulia")


def _row(entity_id, name, **extra):
    row = {"id": entity_id, "nome": name, "classe": None, "unita": None,
           "translation_key": None, "categoria": None, "disabilitata": 0,
           "nascosta": 0, "area_id": None, "piattaforma": "x"}
    row.update(extra)
    return row


def _house():
    rows = [
        _row("climate.camera_t", "Termostato Camera", area_id="camera"),
        _row("person.paolo", "Paolo"),
        _row("person.giulia", "Giulia"),
        _row("device_tracker.iphone_di_paolo", "iPhone di Paolo",
             area_id="camera", piattaforma="mobile_app"),
    ]
    return House({"entita": rows, "aree": [{"id": "camera", "nome": "Camera"}]},
                 Mirror())


@pytest.fixture
def archivio(tmp_path):
    store = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield store
    store.close()


def _without_names(text: str) -> None:
    for name in _NAMES:
        assert name not in text.lower(), (
            f"il nome «{name}» arriva al modello:\n{text}")


def test_la_lista_delle_presenze_e_quella_che_Home_Assistant_dichiara():
    """`person` (components/person, `DOMAIN = "person"`) e i
    `device_tracker` che una persona segue (`ATTR_DEVICE_TRACKERS`, validati
    con `cv.entities_domain("device_tracker")`): letti nel sorgente di Home
    Assistant Core 2026.9.3 il 05/10/2026. Se il vocabolario dei tipi
    cambiasse il genere «presenza», questa prova lo direbbe prima che i nomi
    tornino nella domanda."""
    assert MOVING_DOMAINS == {"person", "device_tracker"}


def test_le_righe_non_portano_NE_nome_NE_identificatore_di_una_persona():
    lines = observer.house_lines(_house())
    _without_names("\n".join(lines))
    assert any(line.startswith("climate.camera_t · Termostato Camera")
               for line in lines), "le altre entita' restano come prima"
    handles = sorted(line.split(" · ", 1)[0] for line in lines
                     if not line.startswith("climate."))
    assert handles == ["device_tracker.#1", "person.#1", "person.#2"]


def test_il_segnaposto_non_puo_essere_un_entity_id_vero():
    """Home Assistant ammette nell'object_id solo `[\\da-z_]`
    (`homeassistant/core.py`, `_OBJECT_ID`, Core 2026.9.3, letto il
    05/10/2026): un segnaposto con `#` non puo' collidere con un'entita'
    vera."""
    import re
    object_id = re.compile(r"^(?!_)[\da-z_]+(?<!_)$")
    for handle in observer.presence_handles(["person.paolo"]).values():
        assert not object_id.match(handle.split(".", 1)[1])


class _Model:
    def __init__(self, answer="[]"):
        self.answer = answer
        self.questions = []

    async def chat(self, *, user_message, system_prompt="", model="auto",
                   agent_type="chat", max_tokens=0, **kw):
        self.questions.append(user_message + "\n" + system_prompt)
        return self.answer


@pytest.mark.asyncio
async def test_sulla_CATENA_la_domanda_non_porta_i_nomi_e_la_decisione_torna_all_id(archivio):
    model = _Model('[{"id": "person.#1", "dentro": true, '
                   '"motivo": "la presenza spiega il riscaldamento"}]')
    outcome = await observer.reconsider(model, archivio, _house(), reason="prova",
                                        now=1000.0)
    _without_names(model.questions[0])
    assert outcome["decise"] == 1, outcome
    # person.#1 e' la prima persona in ordine d'id: giulia.
    assert archivio.scope()["person.giulia"]["dentro"] is True
    assert "person.#1" not in archivio.scope()


def test_sul_PONTE_il_turno_non_porta_i_nomi_e_la_raccolta_torna_all_id(archivio):
    turn = observer.bridge_turn(archivio, _house())
    _without_names(turn["history"][0]["content"] + turn["system_prompt"]
                   + turn["istruzione"])
    lotto = set(observer.watched_ids(_house()))
    outcome = observer.apply_answer(
        archivio, _house(),
        '[{"id": "device_tracker.#1", "dentro": false, "motivo": "ripete la persona"}]',
        reason="il ponte ha risposto", asked=lotto, now=1000.0)
    assert outcome["decise"] == 1, outcome
    assert archivio.scope()["device_tracker.iphone_di_paolo"]["dentro"] is False


def test_una_casa_SENZA_persone_ha_la_domanda_di_prima():
    """Pura sostituzione dove non ci sono persone: nessuna frase in piu'."""
    house = House({"entita": [_row("climate.camera_t", "Termostato Camera")],
                   "aree": []}, Mirror())
    lines = observer.house_lines(house)
    assert lines == ["climate.camera_t · Termostato Camera"]
    assert "segnaposto" not in observer.build_house_question("x", lines)
