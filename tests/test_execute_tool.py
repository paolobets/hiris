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

    async def execute(self, chiamata, *, actor, subject=None):
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


def test_l_unico_costruttore_del_dispatcher_passa_l_istantanea_dei_giudizi():
    """Fix round 1 (revisione Fable), rilievo MINOR 4: stessa domanda del
    test sopra sulla porta, per l'istantanea dei giudizi (Task 5). Se
    `create_tool_dispatcher` non la inoltra, ogni turno di chat costruirebbe
    un `ToolDispatcher` che ricade silenziosamente sul solo seme
    (`REPO_JUDGMENTS`) anche quando `app["type_judgments"]` porta una
    correzione viva del proprietario -- lo stesso guasto silenzioso del test
    sopra, sull'istantanea invece che sulla porta.

    Mutazione ESEGUITA: cambiato `judgments=app.get("type_judgments")` in
    `judgments=app.get("nome_sbagliato")` nella chiamata `ToolDispatcher(`
    dentro `create_tool_dispatcher` -- rossa; ripristinato con l'editor.
    """
    from hiris.app.api.handlers_chat import create_tool_dispatcher

    giudizi_finti = object()
    d = create_tool_dispatcher({"type_judgments": giudizi_finti})
    assert d._judgments is giudizi_finti


def test_un_app_SENZA_la_chiave_costruisce_il_dispatcher_sul_SOLO_SEME():
    """Giro di correzioni 1, punto 5: la ricaduta si SCEGLIE e si fissa.

    `create_tool_dispatcher` legge `app.get("type_judgments")`, e
    `ToolDispatcher.__init__` con `None` ricade su `REPO_JUDGMENTS`: la prova
    strutturale D3 (`tests/test_judgments_passed_in_production.py`) guarda il
    **keyword**, non il valore, quindi quella ricaduta non era fissata da
    nessuna prova. In produzione non scatta mai -- l'avvio scrive sempre la
    chiave, anche quando il sapere non si apre (`server._open_knowledge` mette
    il solo seme, spec §8) -- ma il `.get` esiste perche' le prove costruiscono
    `app` a mano, e **questa e' la prova che dichiara cosa deve fare**: il solo
    seme del repo, mai `None`, mai un `KeyError`.

    L'alternativa scartata era `app["type_judgments"]` secco: farebbe esplodere
    un percorso di prova legittimo per difendersi da un ramo che la produzione
    non raggiunge.

    Mutazione ESEGUITA: `app["type_judgments"]` al posto del `.get` --
    rossa (`KeyError: 'type_judgments'`); ripristinato con l'editor.
    """
    from hiris.app.api.handlers_chat import create_tool_dispatcher
    from hiris.app.home_space.type_vocabulary import REPO_JUDGMENTS

    d = create_tool_dispatcher({})
    assert d._judgments is REPO_JUDGMENTS


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
