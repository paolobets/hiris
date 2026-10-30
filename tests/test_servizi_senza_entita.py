"""Chi non amministra chiama solo i servizi che si rivolgono a un'entita'
(Fase S, S.4, scelta del proprietario il 30/10/2026).

HIRIS chiama Home Assistant col proprio token di amministratore, e Home
Assistant non dice da nessuna API quali servizi riserva agli amministratori.
Misurato il 30/10/2026 sul sorgente: nel nucleo 2026.10.4 nessun servizio
riservato dichiara un `target`; in Spook v5.11.1, quello installato in casa,
14 dei 17 riservati che la porta lascerebbe passare non lo dichiarano, e 9 di
loro cancellano un aiutante. La regola si chiede quindi alla definizione del
servizio (`verification.touches_no_entity`), non a una lista.

Le definizioni qui sotto sono nella forma di `/api/services`; i servizi di
Spook senza `target` (`delete`, `zone.delete`) e con `target`
(`input_number.set_range`) sono quelli letti nel suo sorgente al tag v5.11.1.
"""
import os
import sys
from pathlib import Path

import pytest

from hiris.app.action.registry import ServiceRegistry
from hiris.app.action.verification import touches_no_entity
from hiris.app.api.soffitto import (
    ADMIN_SERVICES_REFUSAL,
    NO_ENTITY_SERVICES_REFUSAL,
    consente,
)
from hiris.app.chat_thread import ChatThread
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.keeper.store import AgendaStore
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

_SERVIZI = [
    {"domain": "input_boolean", "services": {
        "turn_on": {"fields": {}, "target": {"entity": [{"domain": ["input_boolean"]}]}},
        "delete": {"fields": {"entity_id": {}}}}},
    {"domain": "zone", "services": {
        "delete": {"fields": {"entity_id": {}}}}},
    {"domain": "input_number", "services": {
        "set_range": {"fields": {"minimum": {}, "maximum": {}},
                      "target": {"entity": [{"domain": ["input_number"]}]}}}},
    {"domain": "notify", "services": {
        "mobile_app_x": {"fields": {"message": {}, "title": {}}}}},
    {"domain": "homeassistant", "services": {
        "update_entity": {"fields": {"entity_id": {}}},
        "turn_on": {"fields": {}, "target": {}}}},
]

_PERSONA = {"specie": "persona", "id": "u-persona"}
_FILO = ChatThread("persona:u-persona", "pannello")


class _Porta:
    """La porta finta: dice soltanto se la chiamata le e' arrivata."""

    def __init__(self):
        self.eseguite = []
        self.verificate = []

    async def execute(self, arguments, *, actor, subject):
        self.eseguite.append(arguments["servizio"])
        return {"esito": "fatto"}

    async def verify(self, call, *, resolve=True, actor="verifica"):
        self.verificate.append(call["servizio"])
        return {"errore": "fermata qui dalla prova"}


def _casa() -> CasaFinta:
    inputs = synthetic_inputs()
    inputs["services"] = _SERVIZI
    return CasaFinta(inputs)


def _chat(ruolo, *, porta, registro=None, ha=None, agenda=None):
    ha = _casa() if ha is None else ha
    return ToolDispatcher(None, None, ha=ha, actuator=porta,
                          registry=ServiceRegistry() if registro is None else registro,
                          agenda=agenda, thread=_FILO,
                          soffitto=consente(_PERSONA, ruolo=ruolo), subject=_PERSONA)


def _esegui(servizio, entita):
    return {"servizio": servizio, "bersaglio": {"entita": [entita]}}


@pytest.mark.asyncio
@pytest.mark.parametrize("servizio,entita", [
    ("input_boolean.delete", "input_boolean.ospiti"),
    ("zone.delete", "zone.lavoro"),
])
async def test_chi_non_amministra_non_chiama_un_servizio_senza_entita(servizio, entita):
    """Mutazione ESEGUITA: tolta dalla riga di `execute` la
    `Permission("amministrare", applies=_service_without_entity)` -- rossa,
    la chiamata arriva alla porta."""
    porta = _Porta()

    esito = await _chat("utente", porta=porta).dispatch("execute", _esegui(servizio, entita))

    assert esito == {"errore": NO_ENTITY_SERVICES_REFUSAL}
    assert porta.eseguite == []


@pytest.mark.asyncio
@pytest.mark.parametrize("servizio,entita", [
    ("input_boolean.turn_on", "input_boolean.ospiti"),
    # Il rischio dichiarato nel BACKLOG: un servizio riservato di Spook che
    # dichiara un `target` passa, perche' la regola non lo distingue.
    ("input_number.set_range", "input_number.soglia"),
    ("notify.mobile_app_x", "notify.mobile_app_x"),
    # `update_entity` non dichiara un `target`, ed e' concesso: il dominio
    # `homeassistant` lo decide `privacy.HA_CORE_USER_SERVICES`.
    ("homeassistant.update_entity", "sensor.temperatura"),
    ("homeassistant.turn_on", "light.salotto"),
])
async def test_chi_non_amministra_chiama_i_servizi_su_un_entita(servizio, entita):
    """Mutazione ESEGUITA: `touches_no_entity` senza l'esenzione dei recapiti
    -- rossa su `notify.mobile_app_x` (e su `test_la_regola_chiede_la_definizione`)."""
    porta = _Porta()

    esito = await _chat("utente", porta=porta).dispatch("execute", _esegui(servizio, entita))

    assert esito == {"esito": "fatto"}
    assert porta.eseguite == [servizio]


@pytest.mark.asyncio
async def test_chi_amministra_chiama_anche_i_servizi_senza_entita():
    """Mutazione ESEGUITA: in `_refusal` la domanda sulla chiamata prima del
    soffitto -- rossa, il soffitto scalda il registro anche per chi
    amministra."""
    porta = _Porta()
    ha = _casa()

    await _chat("amministratore", porta=porta, ha=ha).dispatch(
        "execute", _esegui("zone.delete", "zone.lavoro"))

    assert porta.eseguite == ["zone.delete"]
    # A chi il gesto e' concesso la domanda non serve: il registro lo scalda
    # la porta, non il soffitto.
    assert ha.calls == []


@pytest.mark.asyncio
async def test_il_registro_freddo_si_scalda_prima_di_rispondere():
    """Il registro si carica alla prima azione: freddo non conosce nessun
    servizio, e la domanda direbbe «non riservato» a tutto.

    Mutazione ESEGUITA: tolto `await dispatcher._ensure_registry_fresh()` da
    `_service_without_entity` -- rossa, `zone.delete` arriva alla porta (e la
    promessa di `zone.delete` alla verifica)."""
    porta, registro, ha = _Porta(), ServiceRegistry(), _casa()
    assert registro.empty()

    esito = await _chat("utente", porta=porta, registro=registro, ha=ha).dispatch(
        "execute", _esegui("zone.delete", "zone.lavoro"))

    assert esito == {"errore": NO_ENTITY_SERVICES_REFUSAL}
    assert [path for path, _extra in ha.calls] == ["/api/services"]


@pytest.mark.asyncio
async def test_un_servizio_che_il_registro_non_conosce_lo_rifiuta_la_porta():
    """Non e' il soffitto a dire «non esiste»: la porta lo dice con la sua
    ragione, a chiunque."""
    porta = _Porta()

    await _chat("utente", porta=porta).dispatch(
        "execute", _esegui("light.inventato", "light.salotto"))

    assert porta.eseguite == ["light.inventato"]


@pytest.fixture()
def agenda(tmp_path):
    archivio = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    yield archivio
    archivio.close()


def _prometti(servizio, entita):
    return {"specie": "fai", "frase": "fra un'ora", "quando": "2099-01-01T00:00:00+00:00",
            "chiamata": _esegui(servizio, entita)}


@pytest.mark.asyncio
@pytest.mark.parametrize("servizio,entita,rifiuto", [
    ("zone.delete", "zone.lavoro", NO_ENTITY_SERVICES_REFUSAL),
    # Fino al 30/10/2026 la promessa chiedeva solo `comandare`: un `fai` di
    # `homeassistant.restart` nasceva, e lo schedulatore lo eseguiva senza
    # nessun soffitto da guardare.
    ("homeassistant.restart", "light.salotto", ADMIN_SERVICES_REFUSAL),
])
async def test_una_promessa_non_rimanda_cio_che_la_chat_non_farebbe(
        agenda, servizio, entita, rifiuto):
    """Mutazione ESEGUITA: tolte dalla riga di `promise` le due
    `Permission("amministrare", applies=_on_promised_call(...))` -- rosse
    entrambe, la chiamata arriva alla verifica della porta."""
    porta = _Porta()

    esito = await _chat("utente", porta=porta, agenda=agenda).dispatch(
        "promise", _prometti(servizio, entita))

    assert esito == {"errore": rifiuto}
    assert porta.verificate == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo,servizio,entita", [
    ("utente", "input_boolean.turn_on", "input_boolean.ospiti"),
    ("amministratore", "zone.delete", "zone.lavoro"),
])
async def test_una_promessa_concessa_arriva_alla_verifica(agenda, ruolo, servizio, entita):
    porta = _Porta()

    await _chat(ruolo, porta=porta, agenda=agenda).dispatch(
        "promise", _prometti(servizio, entita))

    assert porta.verificate == [servizio]


def test_la_regola_chiede_la_definizione():
    assert touches_no_entity("zone", {"fields": {}}) is True
    assert touches_no_entity("zone", {"fields": {}, "target": None}) is True
    assert touches_no_entity("input_number", {"target": {}}) is False
    assert touches_no_entity("notify", {"fields": {}}) is False
    assert touches_no_entity("persistent_notification", {"fields": {}}) is False
