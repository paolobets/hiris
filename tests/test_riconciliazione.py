"""La riconciliazione: scope e sapere seguono la casa (Tappa 8, Task 1, D1).

Dopo ogni ricostruzione dell'anagrafe, cio' che Home Assistant non conosce piu'
esce dagli archivi del cervello -- e solo quello: le entita' spente, mute o
sparite dagli stati ma ancora nel registro restano, perche' possono tornare;
un dispositivo con tutte le entita' spente e' ancora nel registro, e le sue
risposte del sapere restano.

Le guardie non sono soglie: sono le quattro condizioni senza le quali una casa
letta a meta' si leggerebbe come una casa svuotata (`mind/reconciliation.py`).

Mutazioni ESEGUITE (08/10/2026):
- tolta la guardia sull'anagrafe letta (`read_at is None`) -- rossa
  `test_all_avvio_con_l_anagrafe_mai_letta_non_esce_niente`;
- invertita la guardia sui registri caduti (`if not fallen`) -- rosse
  `test_un_registro_caduto_ferma_tutto` e le prove dove i registri ci sono;
- tolta la guardia su Home Assistant avviato -- rossa
  `test_home_assistant_non_avviato_ferma_tutto`.
"""
from __future__ import annotations

import logging

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.reader import HomeSpace, build_home_space
from hiris.app.home_space.topology import Mirror, ha_running, live_mirror
from hiris.app.mind.knowledge import Fact, KnowledgeStore
from hiris.app.mind.recipe_turn import ANSWER_FIELDS, DECLINED_FIELD
from hiris.app.mind.reconciliation import reconcile, what_to_forget
from hiris.app.mind.store import ObservationsStore
from hiris.app.proxy.entity_cache import _to_minimal

READ_AT = "2026-10-08T06:00:00+00:00"

DEVICES = [
    {"id": "d_vivo", "name": "Termostato"},
    # Tutte le sue entita' spente dal proprietario: e' ancora nel registro.
    {"id": "d_spento", "name": "Presa spenta"},
]
ENTITIES = [
    {"entity_id": "climate.soggiorno", "device_id": "d_vivo"},
    {"entity_id": "switch.presa", "device_id": "d_spento", "disabled_by": "user"},
    # Nel registro, non negli stati: «sparita», non «non esiste piu'».
    {"entity_id": "sensor.sparita", "device_id": "d_vivo"},
]
STATES = [
    {"entity_id": "climate.soggiorno", "state": "heat", "attributes": {}},
    # Senza `unique_id`: mai nel registro, viva negli stati.
    {"entity_id": "sun.sun", "state": "above_horizon", "attributes": {}},
]
REGISTRIES = {"entita": ENTITIES, "dispositivi": DEVICES}

#: Lo scope: dentro e fuori, entita' e soggetti di sistema.
SCOPE = ["climate.soggiorno", "switch.presa", "sensor.sparita", "sun.sun",
         "light.tolta", "sensor.tolta_fuori", "log:homeassistant.core"]


def _house(*, unavailable=(), readable=True) -> House:
    mirror = live_mirror([_to_minimal(row) for row in STATES])
    if not readable:
        mirror = Mirror(readable=False)
    return House(build_home_space(REGISTRIES), mirror, unavailable)


def _plan(house=None, *, read_at=READ_AT, started=True,
          devices=("d_vivo", "d_spento", "d_tolto")):
    return what_to_forget(house or _house(), read_at=read_at, ha_started=started,
                          scope_subjects=SCOPE, answered_devices=devices)


def test_esce_solo_cio_che_ne_il_registro_ne_gli_stati_conoscono():
    plan = _plan()
    assert plan.stopped is None
    assert plan.scope == ("light.tolta", "sensor.tolta_fuori")


def test_le_entita_che_possono_tornare_restano():
    resta = set(SCOPE) - set(_plan().scope)
    # spenta dal proprietario, sparita dagli stati ma nel registro, senza
    # `unique_id` e viva, e un soggetto di sistema che non e' un'entita'.
    assert {"switch.presa", "sensor.sparita", "sun.sun",
            "log:homeassistant.core", "climate.soggiorno"} <= resta


def test_un_dispositivo_tolto_perde_le_risposte_uno_con_le_entita_spente_no():
    assert _plan().devices == ("d_tolto",)


def test_all_avvio_con_l_anagrafe_mai_letta_non_esce_niente():
    plan = _plan(House({}, live_mirror([])), read_at=None)
    assert (plan.scope, plan.devices) == ((), ())
    assert plan.stopped == "anagrafe non ancora letta"


@pytest.mark.parametrize("fallen", ["entita", "dispositivi"])
def test_un_registro_caduto_ferma_tutto(fallen):
    plan = _plan(_house(unavailable=(fallen,)))
    assert (plan.scope, plan.devices) == ((), ())
    assert fallen in plan.stopped


def test_un_registro_che_non_serve_non_ferma():
    assert _plan(_house(unavailable=("aree", "entita:alias"))).scope


def test_lo_specchio_illeggibile_ferma_tutto():
    plan = _plan(_house(readable=False))
    assert (plan.scope, plan.devices) == ((), ())
    assert plan.stopped is not None


def test_home_assistant_non_avviato_ferma_tutto():
    plan = _plan(started=False)
    assert (plan.scope, plan.devices) == ((), ())
    assert plan.stopped is not None


class _Client:
    def __init__(self, config):
        self._config = config

    async def get_config(self):
        return self._config


@pytest.mark.asyncio
@pytest.mark.parametrize("config, expected", [
    ({"state": "RUNNING"}, True),
    ({"state": "STARTING"}, False),
    ({"state": "NOT_RUNNING"}, False),
    ({"errore": "Home Assistant non ha risposto", "causa": "rete"}, False),
])
async def test_avviato_si_legge_da_get_config(config, expected):
    assert await ha_running(_Client(config)) is expected


@pytest.mark.asyncio
async def test_senza_client_non_e_avviato():
    assert await ha_running(None) is False


class _Cache:
    """Uno specchio caricato, con le righe nella forma di `all_states`."""
    loaded = True

    def all_states(self):
        return [_to_minimal(row) for row in STATES]


@pytest.fixture
def archivi(tmp_path):
    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    knowledge = KnowledgeStore(str(tmp_path / "sapere.db"))
    home_space = HomeSpace(str(tmp_path))
    home_space.hold_registries({**REGISTRIES, "piani": [], "aree": [], "etichette": [],
                                "categorie": [], "integrazioni": []})
    for i, subject in enumerate(SCOPE):
        store.decide_scope(subject, inside=i % 2 == 0, reason="perche' si'",
                           author="observer", when_ts=1_000.0)
    for device in ("d_vivo", "d_spento", "d_tolto"):
        knowledge.write(Fact(
            subject_kind="dispositivo", subject=device, field=DECLINED_FIELD,
            value="niente da misurare", provenance="dedotto",
            evidence="il modello ha risposto", who="prova", when_ts=1_000.0))
    yield store, knowledge, home_space
    store.close()
    knowledge.close()


@pytest.mark.asyncio
async def test_la_riconciliazione_scrive_sugli_archivi_e_lo_dice(archivi, caplog):
    store, knowledge, home_space = archivi
    app = {"observations": store, "knowledge": knowledge, "home_space_store": home_space,
           "entity_cache": _Cache(), "ha_client": _Client({"state": "RUNNING"})}

    with caplog.at_level(logging.INFO, logger="hiris.app.mind.reconciliation"):
        await reconcile(app)

    assert set(SCOPE) - set(store.scope()) == {"light.tolta", "sensor.tolta_fuori"}
    assert set(knowledge.device_answers(ANSWER_FIELDS)) == {"d_vivo", "d_spento"}
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 1, lines
    assert "2 righe dello scope" in lines[0] and "light.tolta" in lines[0]
    assert "1 risposte del sapere" in lines[0] and "d_tolto" in lines[0]


@pytest.mark.asyncio
async def test_a_casa_non_avviata_gli_archivi_restano_e_il_log_dice_perche(archivi, caplog):
    store, knowledge, home_space = archivi
    app = {"observations": store, "knowledge": knowledge, "home_space_store": home_space,
           "entity_cache": _Cache(), "ha_client": _Client({"state": "STARTING"})}

    with caplog.at_level(logging.INFO, logger="hiris.app.mind.reconciliation"):
        await reconcile(app)

    assert set(store.scope()) == set(SCOPE)
    assert len(knowledge.device_answers(ANSWER_FIELDS)) == 3
    assert [r.getMessage() for r in caplog.records] == [
        "riconciliazione: niente tolto, Home Assistant non si e' dichiarato avviato"]


def test_forget_scope_toglie_dentro_e_fuori_e_conta(archivi):
    store, _knowledge, _home_space = archivi
    assert store.forget_scope(["climate.soggiorno", "switch.presa", "mai.vista"]) == 2
    assert store.forget_scope([]) == 0
    assert "climate.soggiorno" not in store.scope()
