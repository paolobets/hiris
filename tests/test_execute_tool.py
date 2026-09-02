"""Il quinto strumento: `execute`, e il fatto che si propaghi da solo.

Il punto di questo file non e' che `execute` funzioni -- il lavoro vero
(verifica, chiamata, rilettura, registro) e' in `action/actuator.py` e ha i suoi
test. Qui si pinnano tre cose che nessun altro test copre:

1. `execute` sta nel catalogo UNICO, e da li' arriva da solo a `mcp_names()`
   (l'argv del ponte) e a `mcp_catalog()` (la rotta MCP). Se uno di quei due
   test cade, qualcuno ha ricopiato i nomi a mano da qualche parte;
2. il dispatcher passa alla porta e DICHIARA l'origine (`"chat"`): la porta
   non sa chi la chiama, e domani lo schedulatore passera' un'altra origine
   dalla stessa firma;
3. `dispatch()` ora attende i gestori che sono coroutine -- e i quattro che
   NON lo sono continuano a funzionare: e' l'unica modifica invasiva del task.
"""
import inspect

import pytest

from hiris.app.action.actuator import ActionActuator
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS, ToolDispatcher
from tests._contracts import assert_stessa_firma


class FintaPorta:
    def __init__(self, esito=None):
        self.chiamate = []
        self.esito = esito or {"eseguito": True, "servizio": "light.turn_off",
                               "entita": ["light.salotto"], "cambiato": ["light.salotto"]}

    async def execute(self, chiamata, *, actor):
        self.chiamate.append((chiamata, actor))
        return self.esito


def test_la_finta_porta_combacia_con_la_firma_vera():
    """Se `ActionActuator.execute` cambia firma, questo test cade invece
    di lasciare che il finto imiti un contratto che non esiste piu'."""
    assert_stessa_firma(ActionActuator.execute, FintaPorta.execute, nome="execute")


def test_esegui_e_nel_catalogo_unico():
    nomi = [d["name"] for d in KNOWLEDGE_TOOLS]
    assert "execute" in nomi
    assert len(nomi) == len(set(nomi)), "nessun nome duplicato nel catalogo"


def test_esegui_si_propaga_ai_nomi_mcp():
    from hiris.app.agent.runner import mcp_names
    assert "mcp__hiris__execute" in mcp_names(), (
        "i nomi MCP si DERIVANO dal catalogo: se questo cade, "
        "qualcuno ha scritto i nomi a mano da qualche parte")


def test_esegui_si_propaga_al_catalogo_del_ponte():
    from hiris.app.api.handlers_mcp import mcp_catalog
    assert "execute" in [d["name"] for d in mcp_catalog()]


@pytest.mark.asyncio
async def test_dispatch_passa_alla_porta_e_dichiara_l_origine():
    actuator = FintaPorta()
    d = ToolDispatcher(None, None, cache=None, actuator=actuator)
    esito = await d.dispatch("execute", {"servizio": "light.turn_off",
                                        "bersaglio": {"entita": ["light.salotto"]}})
    assert esito["eseguito"] is True
    chiamata, actor = actuator.chiamate[0]
    assert chiamata["servizio"] == "light.turn_off"
    assert actor == "chat"


@pytest.mark.asyncio
async def test_senza_porta_lo_dichiara_invece_di_rompersi():
    d = ToolDispatcher(None, None, cache=None, actuator=None)
    esito = await d.dispatch("execute", {"servizio": "light.turn_off",
                                        "bersaglio": {"entita": ["light.salotto"]}})
    assert "errore" in esito
    assert "Home Assistant" in esito["errore"]


@pytest.mark.asyncio
async def test_gli_altri_quattro_restano_sincroni_e_funzionanti():
    """La modifica a dispatch() non deve rompere i gestori che non sono coroutine."""
    d = ToolDispatcher(None, None, cache=None, actuator=None)
    esito = await d.dispatch("search", {"testo": "salotto"})
    assert "errore" in esito  # niente archivio casa: errore dichiarato, non eccezione


# -- il cablaggio: la porta arriva davvero fin qui --------------------------
# I due test sopra provano che il dispatcher USA la porta se ce l'ha. Questi
# due provano che ce l'ha: senza, `execute` sarebbe nel catalogo, il modello lo
# chiamerebbe, e riceverebbe per sempre «il collegamento con Home Assistant
# non e' disponibile» -- un guasto silenzioso che nessun test di unita'
# avrebbe visto, perche' ogni finta passa la porta a mano.


@pytest.mark.asyncio
async def test_l_unico_costruttore_del_dispatcher_passa_la_porta():
    """`create_tool_dispatcher` e' l'UNICO punto di costruzione del
    dispatcher (chat sincrona e rotta `/api/mcp` chiamano lui): se la porta non
    passa di qui non passa da nessuna parte, e per entrambi i percorsi
    insieme."""
    from hiris.app.api.handlers_chat import create_tool_dispatcher

    actuator = FintaPorta()
    d = create_tool_dispatcher({"action_actuator": actuator})

    esito = await d.dispatch("execute", {"servizio": "light.turn_off",
                                        "bersaglio": {"entita": ["light.salotto"]}})
    assert esito["eseguito"] is True
    assert actuator.chiamate, "il dispatcher costruito dall'app non ha la porta"


def test_la_porta_nasce_nell_app_e_dopo_lo_specchio_dello_stato():
    """Pin sorgente sull'aggancio in `_on_startup` (stessa tecnica di
    `tests/test_action_registry.py::test_il_registro_e_agganciato_all_app`).

    Due cose in un test solo perche' sono una: la riga deve esserci **e**
    deve stare DOPO `app["entity_cache"]`. Il brief la collocava accanto a
    `registro_servizi`, dove pero' la cache non esiste ancora: `app.get(
    "entity_cache")` avrebbe dato `None`, e una porta senza specchio rifiuta
    OGNI azione con «non vedo lo stato di questa casa» (guardia (b) di
    `action/actuator.py`) -- per sempre, e senza che nulla sollevi. E' il tipo di
    difetto che si vede solo sulla casa vera: qui lo si vede subito."""
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'app["action_actuator"] = ActionActuator(' in src
    assert src.index('app["entity_cache"] = entity_cache') < src.index(
        'app["action_actuator"] = ActionActuator('), (
        "la porta si costruisce PRIMA dello specchio dello stato: nascerebbe "
        "con cache=None e rifiuterebbe ogni azione")
