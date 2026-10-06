"""Il livello delle proposte (attori, strato 4, Task 4.3; D13, approvata da
Paolo il 06/10/2026).

Quattro valori chiusi -- banale, lieve, medio, alto -- in una casa sola
(`action/construction/stakes.py`), sulle due code: le costruzioni
dell'officina e le proposte da fare a mano. `alto` lo impone il codice quando
la proposta AGISCE su serrature o allarme (la decisione del 03/10/2026); gli
altri tre li sceglie il modello, che non puo' abbassare un `alto` ne'
scriverlo da se'.

L'avviso per una proposta `alto` (D14) non e' qui: avvisa il cervello, e il
suo chiamante e' il giro del proponente (Task 4.2), che non c'e' ancora.

Mutazioni ESEGUITE (06/10/2026), una per volta, ripristino verificato con
`git status`:

- tolto `lock` da `stakes.HIGH_STAKES_DOMAINS` -> rosse le tre prove della
  serratura (azione, dispositivo, scena), col messaggio «'lieve' == 'alto'»;
- `impose` che restituisce il livello del modello anche sopra la lista ->
  rosse le cinque prove `alto`;
- `acting_part` che restituisce il corpo intero invece delle sole azioni ->
  rossa la prova dell'innesco su una serratura;
- tolto `"livello"` dall'intento di `ToolDispatcher._propose` -> rossa la
  prova di derivazione, che nomina il campo mancante.
"""
import ast
import inspect
import os
import textwrap

import pytest

from hiris.app.action.construction import stakes
from hiris.app.home_space import tools
from hiris.app.home_space.tools import PROPOSE_TOOL_DEF
from hiris.app.mind.store import ObservationsStore
from tests.test_construction_workshop import ADESSO, _intento, banco  # noqa: F401

_SERRATURA = [{"action": "lock.unlock", "target": {"entity_id": "lock.ingresso"}}]


@pytest.mark.asyncio
async def test_una_proposta_su_una_SERRATURA_e_alta_anche_se_il_modello_dice_lieve(banco):
    officina, _, archivio, _ = banco
    esito = await officina.propose(_intento(azioni=_SERRATURA, livello="lieve"),
                                   actor="chat", exchange="t1", now=ADESSO)

    assert "proposta_id" in esito, esito
    assert esito["livello"] == "alto"
    assert archivio.read(esito["proposta_id"])["livello"] == "alto"


@pytest.mark.asyncio
async def test_l_ALLARME_come_bersaglio_di_un_servizio_generico_e_alto(banco):
    """Il servizio e' di `homeassistant`, il bersaglio e' l'allarme: si
    guarda anche l'entita', non solo il nome del servizio."""
    officina, _, archivio, _ = banco
    azioni = [{"action": "homeassistant.turn_on",
               "target": {"entity_id": ["light.portico", "alarm_control_panel.casa"]}}]
    esito = await officina.propose(_intento(azioni=azioni, livello="banale"),
                                   actor="chat", exchange="t1", now=ADESSO)

    assert archivio.read(esito["proposta_id"])["livello"] == "alto"


@pytest.mark.asyncio
async def test_l_azione_di_un_DISPOSITIVO_serratura_e_alta(banco):
    officina, _, archivio, _ = banco
    azioni = [{"device_id": "abc123", "domain": "lock", "type": "unlock",
               "entity_id": "4f2e9c"}]
    esito = await officina.propose(_intento(azioni=azioni, livello="lieve"),
                                   actor="chat", exchange="t1", now=ADESSO)

    assert archivio.read(esito["proposta_id"])["livello"] == "alto"


@pytest.mark.asyncio
async def test_una_SCENA_che_chiude_la_serratura_e_alta(banco):
    officina, _, archivio, _ = banco
    esito = await officina.propose(
        _intento(dominio="scene", richiesto="scena", innesco=[], azioni=[],
                 stati=[{"entity_id": "lock.ingresso", "state": "locked"}],
                 livello="lieve"),
        actor="chat", exchange="t1", now=ADESSO)

    assert "proposta_id" in esito, esito
    assert archivio.read(esito["proposta_id"])["livello"] == "alto"


@pytest.mark.asyncio
async def test_CANCELLARE_un_automazione_che_arma_l_allarme_e_alto(banco):
    """Per `cancella` il corpo e' il «prima»: togliere l'allarme di notte
    conta quanto aggiungerlo."""
    officina, ha, archivio, _ = banco
    ha._override["leggi"] = {
        "id": "1771", "alias": "Allarme di notte",
        "triggers": [{"trigger": "time", "at": "23:00:00"}],
        "actions": [{"action": "alarm_control_panel.alarm_arm_night",
                     "target": {"entity_id": "alarm_control_panel.casa"}}]}
    esito = await officina.propose(
        _intento(gesto="cancella", chiave="1771", livello="lieve"),
        actor="chat", exchange="t1", now=ADESSO)

    assert "proposta_id" in esito, esito
    assert archivio.read(esito["proposta_id"])["livello"] == "alto"


@pytest.mark.asyncio
async def test_GUARDARE_una_serratura_non_e_agire_su_di_lei(banco):
    """Un innesco o una condizione sulla serratura guardano la casa: la
    proposta che accende la luce quando la porta si apre non tocca la
    serratura, e il suo livello lo sceglie il modello."""
    officina, _, archivio, _ = banco
    esito = await officina.propose(
        _intento(innesco=[{"trigger": "state", "entity_id": "lock.ingresso",
                           "to": "unlocked"}],
                 condizioni=[{"condition": "state", "entity_id": "lock.ingresso",
                              "state": "unlocked"}],
                 azioni=[{"action": "light.turn_on",
                          "target": {"entity_id": "light.ingresso"}}],
                 livello="lieve"),
        actor="chat", exchange="t1", now=ADESSO)

    assert archivio.read(esito["proposta_id"])["livello"] == "lieve"


@pytest.mark.asyncio
async def test_fuori_dalla_lista_vale_il_livello_del_modello_e_senza_resta_non_detto(banco):
    officina, _, archivio, _ = banco
    detto = await officina.propose(_intento(livello="medio"), actor="chat",
                                   exchange="t1", now=ADESSO)
    taciuto = await officina.propose(_intento(alias="Tapparelle al tramonto"),
                                     actor="chat", exchange="t2", now=ADESSO)

    assert archivio.read(detto["proposta_id"])["livello"] == "medio"
    assert archivio.read(taciuto["proposta_id"])["livello"] is None, (
        "un livello che nessuno ha detto non si inventa")


@pytest.mark.asyncio
async def test_il_modello_non_puo_scrivere_ALTO_da_se(banco):
    officina, ha, archivio, _ = banco
    esito = await officina.propose(_intento(livello="alto"), actor="chat",
                                   exchange="t1", now=ADESSO)

    assert "proposta_id" not in esito
    assert "lo mette il codice" in esito["errore"]
    assert archivio.list() == [] and ha.salvate == []


@pytest.mark.asyncio
async def test_un_livello_fuori_dal_vocabolario_si_rifiuta(banco):
    officina, _, archivio, _ = banco
    esito = await officina.propose(_intento(livello="urgente"), actor="chat",
                                   exchange="t1", now=ADESSO)

    assert "errore" in esito and "livello" in esito["errore"]
    assert archivio.list() == []


def test_la_proposta_da_fare_a_mano_porta_lo_stesso_campo(tmp_path):
    """Fondamenta 3: le due code, una forma del livello."""
    store = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    try:
        store.add_proposal(text="sposta l'irrigazione alle 6", perche="piove",
                           fingerprint="s|m|k|1", prova={"base": 19},
                           chi_applica="tu", stakes="medio", now_ts=100.0)
        assert store.proposals()[0]["livello"] == "medio"
    finally:
        store.close()


def test_lo_schema_di_propose_offre_al_modello_SOLO_cio_che_puo_scegliere():
    """L'enumerazione si chiede a `stakes`, non si ricopia; `alto` non c'e'."""
    field = PROPOSE_TOOL_DEF["input_schema"]["properties"]["livello"]

    assert field["enum"] == list(stakes.CHOSEN_BY_MODEL)
    assert stakes.HIGH not in field["enum"]
    assert set(stakes.CHOSEN_BY_MODEL) | {stakes.HIGH} == set(stakes.STAKES)


def test_la_chat_passa_all_officina_OGNI_campo_dello_schema_di_propose():
    """`ToolDispatcher._propose` ricompone l'intento a mano, campo per campo.
    Un campo dello schema che non arriva all'officina e' un campo che il
    modello riempie per niente: l'elenco si chiede allo schema e al
    sorgente, non si scrive qui."""
    source = textwrap.dedent(inspect.getsource(tools.ToolDispatcher._propose))
    literals = [node for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Dict)
                and any(isinstance(k, ast.Constant) and k.value == "gesto"
                        for k in node.keys)]
    assert len(literals) == 1, "non trovo l'intento composto in `_propose`"
    passed = {k.value for k in literals[0].keys if isinstance(k, ast.Constant)}
    schema = set(PROPOSE_TOOL_DEF["input_schema"]["properties"])

    assert len(schema) > 10, "la derivazione dallo schema si e' svuotata"
    assert schema - passed == set(), sorted(schema - passed)
