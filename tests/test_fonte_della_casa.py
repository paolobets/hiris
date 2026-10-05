"""LA FONTE (R11; Tappa 3, Task 8, B-25; D6 «sette stati»): perche' una fonte
tace, chiesto a `House.source(id)`.

Fino al 04/10/2026 il dato si perdeva nel lettore e nessuno poteva
chiederlo: «spenta dal proprietario» e «spenta dall'integrazione» erano lo
stesso `1`, l'entita' non sapeva che la sua integrazione non era caricata
(`config_entry_id` scritto e mai letto, trovato 1), `restored` arrivava nello
specchio e nessuno lo leggeva, e «senza statistiche» era una differenza di
insiemi che mescolava disabilitate, sparite e vive.

La casa e' scritta a mano nella FORMA delle righe di Home Assistant
(`config/entity_registry/list`, `config_entries/get`,
`config/device_registry/list`, gli stati), e passa dal lettore vero e da
`_to_minimal` -- come la monta il prodotto.

Mutazioni ESEGUITE (04/10/2026), ognuna ripristinata e verificata con
`git status`, tutte ROSSE per la ragione giusta:
- `source` decide dal booleano `disabilitata` invece che dalla causa --
  `sensor.mai_attivata` esce «spenta_dal_proprietario»;
- tolta la catena verso il dispositivo, e (a parte) il lettore che butta di
  nuovo `disabled_by` dell'istanza -- le spente col dispositivo o con
  l'istanza escono «spenta_da_home_assistant»;
- `restored` ignorato -- `light.ricreata` esce con la causa `unavailable`;
- `briefing._unreliable_state` torna al letterale `unknown` -- la casa tutta
  `unavailable` si dichiara guardata;
- il guasto delle statistiche orarie torna a non portare motivo (`None`);
- la porta non passa la casa alla verifica -- il rifiuto torna «non esiste in
  questa casa»;
- il motivo delle ricette ignora la fonte -- una disabilitata riceve il motivo
  del dominio.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from hiris.app import server
from hiris.app.action.actuator import ActionActuator
from hiris.app.action.verification import verification
from hiris.app.home_space.briefing import _unreliable_state
from hiris.app.home_space.house import SOURCE_STATES, House
from hiris.app.home_space.reader import build_home_space
from hiris.app.home_space.topology import Mirror, live_mirror
from hiris.app.mind.operations import CAUSES
from hiris.app.mind.recipes import silent_entities
from hiris.app.proxy.entity_cache import _to_minimal
from tests._casa_sintetica import synthetic_inputs
from tests.test_action_actuator import FintaCache, _asked, _registro_pronto

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta, Refused

#: Le istanze: una caricata, una spenta dal proprietario (in Home Assistant
#: `ConfigEntryDisabler` ha un valore solo, `user`), una che ritenta.
ENTRIES = [
    {"entry_id": "e_ok", "domain": "hue", "title": "Hue", "state": "loaded",
     "source": "user", "disabled_by": None},
    {"entry_id": "e_spenta", "domain": "lifx", "title": "Lifx",
     "state": "not_loaded", "source": "user", "disabled_by": "user"},
    {"entry_id": "e_ritenta", "domain": "tuya", "title": "Tuya",
     "state": "setup_retry", "source": "user", "disabled_by": None},
]

DEVICES = [
    {"id": "d_spento", "name": "Lampada", "disabled_by": "user"},
    {"id": "d_acceso", "name": "Sensore", "disabled_by": None},
]


def _entity(entity_id, entry="e_ok", **extra):
    return {"entity_id": entity_id, "platform": "hue", "config_entry_id": entry,
            "disabled_by": None, "hidden_by": None, **extra}


ENTITIES = [
    _entity("light.viva"),
    _entity("light.del_proprietario", disabled_by="user"),
    _entity("sensor.mai_attivata", disabled_by="integration"),
    _entity("light.di_istanza_spenta", entry="e_spenta", disabled_by="config_entry"),
    _entity("light.di_dispositivo_spento", device_id="d_spento", disabled_by="device"),
    _entity("light.di_istanza_che_ritenta", entry="e_ritenta"),
    _entity("light.ricreata"),
    _entity("light.irraggiungibile"),
    _entity("sensor.senza_valore"),
    _entity("light.sparita"),
    _entity("sensor.con_statistiche"),
]

STATES = [
    {"entity_id": "light.viva", "state": "on", "attributes": {}},
    # Home Assistant scrive `unavailable` con `restored: true` per un'entita'
    # del registro che nessuna integrazione ha aggiunto
    # (`RegistryEntry.write_unavailable_state`).
    {"entity_id": "light.di_istanza_che_ritenta", "state": "unavailable",
     "attributes": {"restored": True}},
    {"entity_id": "light.ricreata", "state": "unavailable",
     "attributes": {"restored": True}},
    {"entity_id": "light.irraggiungibile", "state": "unavailable", "attributes": {}},
    {"entity_id": "sensor.senza_valore", "state": "unknown", "attributes": {}},
    {"entity_id": "sensor.con_statistiche", "state": "21.5",
     "attributes": {"state_class": "measurement"}},
    # Un'entita' senza `unique_id` non entra nel registro
    # (`helpers/entity_platform.py`, ramo `entity.unique_id is None`): e' viva.
    {"entity_id": "sun.sun", "state": "above_horizon", "attributes": {}},
]


def _house(statistic_ids=None, states=STATES, readable=True) -> House:
    registries = {"entita": ENTITIES, "integrazioni": ENTRIES, "dispositivi": DEVICES}
    mirror = live_mirror([_to_minimal(row) for row in states])
    if not readable:
        mirror = Mirror(readable=False)
    return House(build_home_space(registries), mirror,
                 statistic_ids=statistic_ids)


@pytest.mark.parametrize("entity_id, stato, causa", [
    ("light.viva", "viva", None),
    ("light.del_proprietario", "spenta_dal_proprietario", "user"),
    ("sensor.mai_attivata", "spenta_da_home_assistant", "integration"),
    ("light.di_istanza_che_ritenta", "integrazione_ferma", "setup_retry"),
    ("light.ricreata", "non_disponibile", "restored"),
    ("light.irraggiungibile", "non_disponibile", "unavailable"),
    ("sensor.senza_valore", "senza_valore", "unknown"),
    ("light.sparita", "sparita", None),
    ("sun.sun", "viva", None),
])
def test_ogni_stato_della_fonte_con_la_sua_causa(entity_id, stato, causa):
    fonte = _house().source(entity_id)
    assert (fonte["stato"], fonte["causa"]) == (stato, causa)


def test_spenta_dal_proprietario_e_da_home_assistant_non_sono_lo_stesso_fatto():
    """Il difetto che il lettore aveva: `disabled_by` ridotto a 1/0. Le due
    risposte devono differire."""
    house = _house()
    assert (house.source("light.del_proprietario")["stato"]
            != house.source("sensor.mai_attivata")["stato"])


@pytest.mark.parametrize("entity_id, causa", [
    ("light.di_istanza_spenta", "config_entry"),
    ("light.di_dispositivo_spento", "device"),
])
def test_spenta_con_la_sua_istanza_o_il_suo_dispositivo_e_del_proprietario(entity_id, causa):
    """`config_entry` e `device` non dicono CHI: dicono che la decisione e'
    stata presa sopra. Home Assistant la propaga
    (`entity_registry.async_config_entry_disabled_by_changed`), e
    `ConfigEntryDisabler` ha un valore solo, `user`. Misurato sulla casa il
    04/10/2026: 69 entita' su 69 `config_entry` stanno su un'istanza spenta
    dal proprietario, 22 su 22 `device` su un dispositivo spento da lui."""
    fonte = _house().source(entity_id)
    assert fonte["stato"] == "spenta_dal_proprietario"
    assert fonte["causa"] == causa
    assert fonte["spenta_da"] == "user"


def test_l_istanza_viaggia_con_la_fonte():
    """Atomicita': chi riceve «integrazione ferma» sa quale, e in che stato."""
    fonte = _house().source("light.di_istanza_che_ritenta")
    assert fonte["istanza"] == {"id": "e_ritenta", "dominio": "tuya",
                                "stato": "setup_retry", "disabilitata_da": None}
    assert _house().source("light.di_istanza_spenta")["istanza"]["disabilitata_da"] == "user"


def test_nel_registro_e_negli_stati():
    house = _house()
    assert (house.source("light.sparita")["nel_registro"],
            house.source("light.sparita")["negli_stati"]) == (True, False)
    assert (house.source("sun.sun")["nel_registro"],
            house.source("sun.sun")["negli_stati"]) == (False, True)


def test_un_id_che_nessuno_conosce_non_ha_fonte():
    assert _house().source("light.inventata") is None


def test_statistiche_vere_false_o_non_lette():
    """`None` = l'elenco di Home Assistant non e' stato letto: non si afferma
    niente (ne' «si'» con la regola, ne' «no»)."""
    letto = _house(statistic_ids={"sensor.con_statistiche"})
    assert letto.source("sensor.con_statistiche")["statistiche"] is True
    assert letto.source("light.viva")["statistiche"] is False
    assert _house().source("sensor.con_statistiche")["statistiche"] is None


def test_con_lo_specchio_non_letto_lo_stato_vivo_tace():
    """Uno specchio che non si e' potuto leggere non fa «sparita» nessuno.
    Cio' che il registro sa resta: la disabilitata e' disabilitata."""
    cieca = _house(readable=False)
    assert cieca.source("light.viva")["stato"] is None
    assert cieca.source("light.viva")["negli_stati"] is None
    assert cieca.source("light.del_proprietario")["stato"] == "spenta_dal_proprietario"


def test_il_lettore_tiene_chi_ha_spento_l_istanza_e_il_dispositivo():
    """Il dato si perdeva nel lettore: `_integration` buttava `disabled_by`,
    `_device` lo riduceva a 1/0."""
    home_space = build_home_space({"integrazioni": ENTRIES, "dispositivi": DEVICES})
    istanze = {i["entry_id"]: i for i in home_space["integrazioni"]}
    dispositivi = {d["id"]: d for d in home_space["dispositivi"]}
    assert istanze["e_spenta"]["disabilitata_da"] == "user"
    assert istanze["e_ok"]["disabilitata_da"] is None
    assert dispositivi["d_spento"]["disabilitato_da"] == "user"


# -- il motivo delle ricette dice la causa (B-26; trovato 7; attori, Task 1.2) --


#: La ricetta di un dispositivo che nomina quattro entita' della casa sopra.
RICETTA = {"why": "prova", "steps": [
    {"name": f"m{i}", "operation": "somma_periodo", "inputs": [f"@{eid}"],
     "params": {"unit": "h"}}
    for i, eid in enumerate(("light.del_proprietario", "sensor.mai_attivata",
                             "light.viva", "sensor.senza_valore"))]}


def test_gli_stati_della_fonte_sono_quelli_che_source_produce():
    """`SOURCE_STATES` e' il vocabolario che le cause delle misure riusano
    (B-26): deve essere ESATTAMENTE cio' che `source` produce. Si chiede a
    `source` su ogni id della casa di prova, che li tocca tutti e sette."""
    house = _house()
    ids = {e["entity_id"] for e in ENTITIES} | {s["entity_id"] for s in STATES}
    produced = {house.source(eid)["stato"] for eid in ids}
    assert len(produced) == 7, "la casa di prova non tocca piu' tutti gli stati"
    assert produced == set(SOURCE_STATES)


def _house_with(entities=(), states=(), statistic_ids=frozenset()) -> House:
    """La casa di prova con qualche entita' in piu', solo per questa prova."""
    registries = {"entita": ENTITIES + list(entities), "integrazioni": ENTRIES,
                  "dispositivi": DEVICES}
    mirror = live_mirror([_to_minimal(row) for row in STATES + list(states)])
    return House(build_home_space(registries), mirror, statistic_ids=statistic_ids)


#: Un sensor ricreato (`restored: true`) e uno vivo che non dichiara lo
#: `state_class`: le due cause che fino al 04/10/2026 uscivano col motivo unico.
_IN_PIU = ([_entity("sensor.ricreato"), _entity("sensor.senza_classe")],
           [{"entity_id": "sensor.ricreato", "state": "unavailable",
             "attributes": {"restored": True, "state_class": "total_increasing"}},
            {"entity_id": "sensor.senza_classe", "state": "12", "attributes": {}}])


@pytest.mark.parametrize("entity_id, causa, frase", [
    ("light.del_proprietario", "spenta_dal_proprietario", "spenta dal proprietario"),
    ("sensor.mai_attivata", "spenta_da_home_assistant", "disabled_by: integration"),
    ("light.di_istanza_che_ritenta", "integrazione_ferma", "non e' caricata"),
    ("light.sparita", "sparita", "non ha uno stato"),
    ("sensor.ricreato", "non_disponibile", "restored"),
    ("light.inventata", "assente", "ne' nel registro ne' negli stati"),
    ("light.viva", "senza_statistiche", "solo per i `sensor`"),
    ("sensor.senza_classe", "senza_statistiche", "non dichiara uno `state_class`"),
])
def test_ogni_entita_muta_porta_la_sua_causa_e_la_frase_giusta(entity_id, causa, frase):
    """B-26: fino al 04/10/2026 ogni entita' fuori dall'elenco delle
    statistiche riceveva lo stesso motivo -- «le tiene solo per le entita' che
    dichiarano uno `state_class`» -- anche spenta, sparita o ricreata. Il Task
    8 ha corretto la frase; qui la causa diventa un CAMPO dal vocabolario
    chiuso (`operations.CAUSES`), che chi legge puo' contare senza leggere la
    prosa. Solo chi non ha statistiche per la regola dello `state_class` lo
    nomina."""
    entities, states = _IN_PIU
    muta = silent_entities(_house_with(entities, states), [entity_id])[entity_id]
    assert muta.cause == causa
    assert muta.cause in CAUSES
    assert frase in muta.reason
    if entity_id != "sensor.senza_classe":
        assert "non dichiara uno `state_class`" not in muta.reason


def test_le_cause_della_fonte_sono_le_parole_della_fonte():
    """Un vocabolario, non due: dove la misura tace per la fonte, la causa e'
    lo STATO che `House.source` da' -- la stessa parola."""
    entities, states = _IN_PIU
    house = _house_with(entities, states)
    for entity_id in ("light.del_proprietario", "light.sparita", "sensor.ricreato",
                      "light.di_istanza_che_ritenta", "sensor.mai_attivata"):
        assert (silent_entities(house, [entity_id])[entity_id].cause
                == house.source(entity_id)["stato"])


def test_chi_ha_statistiche_non_tace():
    motivi = silent_entities(_house(statistic_ids={"sensor.con_statistiche"}),
                             ["light.viva", "sensor.con_statistiche"])
    assert "sensor.con_statistiche" not in motivi


def test_senza_l_elenco_delle_statistiche_non_si_afferma_niente():
    assert silent_entities(_house(), ["light.viva"]) is None


class _Store:
    def __init__(self, home_space):
        self._home_space = home_space

    def read(self):
        return self._home_space

    def unavailable(self):
        return []


#: La domanda delle statistiche orarie (`HAClient.hourly_statistics`).
_STATISTICS = "recorder/statistics_during_period"


async def _ingredients(answer, statistic_ids):
    """`answer`: cio' che la casa finta risponde alle statistiche orarie --
    un risultato, o `Refused(...)` per il guasto. Il client e' quello vero."""
    registries = {"entita": ENTITIES, "integrazioni": ENTRIES, "dispositivi": DEVICES
                  + [{"id": "d_ricetta", "name": "Ricetta"}]}
    app = {"knowledge": object(),
           "home_space_store": _Store(build_home_space(registries)),
           "entity_cache": None}

    async def _stat_ids(_app, _ha, **_kw):
        return statistic_ids

    with mock.patch.object(server.recipe_turn, "recipes",
                           lambda _k: {"d_ricetta": RICETTA}), \
            mock.patch.object(server, "statistic_ids_for_round", _stat_ids):
        house = CasaFinta(synthetic_inputs(), answers={_STATISTICS: lambda _extra: answer})
        return await server._report_ingredients(app, house, giorno="2026-10-03",
                                                timezone="Europe/Rome")


@pytest.mark.asyncio
async def test_un_guasto_delle_statistiche_non_si_scrive_come_serie_vuota():
    """Trovato 7 (S-28): il commento accanto al ramo prometteva «ogni misura
    esce non calcolabile con la sua ragione», e la ragione era «la serie e'
    vuota». Ora ogni entita' della ricetta porta il guasto."""
    _ricette, serie, _nomi, silent = await _ingredients(
        Refused("unknown_error", "timeout"), set())
    assert serie == {}
    assert silent is not None, "il guasto e' tornato a essere «niente da dire»"
    assert set(silent) == {"light.del_proprietario", "sensor.mai_attivata",
                           "light.viva", "sensor.senza_valore"}
    assert all("non si sono potute leggere" in m.reason and "timeout" in m.reason
               for m in silent.values())
    assert {m.cause for m in silent.values()} == {"statistiche_non_lette"}


@pytest.mark.asyncio
async def test_il_resoconto_riceve_la_causa_dalla_casa_del_giro():
    _ricette, _serie, _nomi, silent = await _ingredients({}, {"sensor.senza_valore"})
    assert "spenta dal proprietario" in silent["light.del_proprietario"].reason
    assert silent["light.del_proprietario"].cause == "spenta_dal_proprietario"
    assert "sensor.senza_valore" not in silent


# -- il rifiuto del comando dice la causa (D8; B-04, trovato 2, S-27) ----------


SPEGNI = {"servizio": "light.turn_off", "bersaglio": {"entita": ["light.del_proprietario"]}}


@pytest.mark.asyncio
async def test_la_verifica_dice_perche_un_entita_nominata_non_ha_stato():
    """La regola resta («ha uno stato»: Home Assistant tocca solo cio' che e'
    nella macchina degli stati); il motivo dice la causa. Fino al 04/10/2026
    un'entita' disabilitata riceveva «non esiste in questa casa»."""
    registro = await _registro_pronto()
    stati = {"light.viva": {"id": "light.viva", "state": "on"}}
    house = _house()
    no = verification(SPEGNI, registro, stati, source=house.source)
    assert not no.ok
    assert "spenta dal proprietario" in no.reason
    assert "non esiste" not in no.reason
    ferma = verification({**SPEGNI, "bersaglio": {"entita": ["light.di_istanza_che_ritenta"]}},
                         registro, stati, source=house.source)
    assert "integrazione non e' caricata" in ferma.reason
    inventata = verification({**SPEGNI, "bersaglio": {"entita": ["light.inventata"]}},
                             registro, stati, source=house.source)
    assert "non esiste in questa casa" in inventata.reason


@pytest.mark.asyncio
async def test_la_porta_chiede_la_causa_alla_casa_e_non_tocca_niente():
    registries = {"entita": ENTITIES, "integrazioni": ENTRIES, "dispositivi": DEVICES}
    client = CasaFinta(synthetic_inputs())
    porta = ActionActuator(client, await _registro_pronto(),
                           FintaCache({"light.viva": "on"}),
                           home_space_store=_Store(build_home_space(registries)))
    esito = await porta.execute(SPEGNI, actor="chat")
    assert esito["eseguito"] is False
    assert "spenta dal proprietario" in esito["errore"]
    assert _asked(client) == []


# -- «ho guardato» contro «non ho guardato» (B-08) -----------------------------

def test_una_casa_tutta_non_disponibile_non_e_una_casa_tranquilla():
    """Fino al 04/10/2026 `_unreliable_state` contava solo `unknown`: una casa
    in cui ogni integrazione e' caduta (tutto `unavailable`) si dichiarava
    guardata. Ora chiede i due «non lo so» al vocabolario."""
    home_space = build_home_space({"entita": [_entity("light.a"), _entity("light.b")]})
    assert _unreliable_state(home_space, {"light.a": "unavailable",
                                          "light.b": "unknown"}, True) is True
    assert _unreliable_state(home_space, {"light.a": "unavailable",
                                          "light.b": "on"}, True) is False
