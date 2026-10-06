"""Lo strumento `mind`: cio' che il cervello guarda, chiedibile dalla chat
(Tappa 5, Task 8; R8 della spec «Una fonte sola di verita'»).

**Cosa difende.** Fino al 06/10/2026 lo scope, l'obiettivo, i resoconti e le
analisi li vedeva la pagina e non il modello: le composizioni che li rendono
leggibili vivevano dentro le rotte di `api/handlers_mind.py`. Ora vivono in
`mind/view.MindView`, e la rotta e lo strumento la chiamano tutte e due. La
prova principale e' la fondamenta 3: **per ogni `cosa`, lo strumento e la
rotta restituiscono lo stesso contenuto** -- l'elenco delle letture si chiede
a `MIND_READINGS`, non si scrive qui.

Mutazioni ESEGUITE il 06/10/2026, elencate sulle prove che le prendono.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.handlers_mind import handle_analysis, handle_report, handle_watching
from hiris.app.home_space import energy
from hiris.app.home_space.tools import (
    KNOWLEDGE_TOOLS,
    MIND_READINGS,
    MIND_TOOL_DEF,
    ToolDispatcher,
)
from hiris.app.mind.store import ObservationsStore
from tests.test_home_space_energy import PREFS, _Cache, _house, _store

DAY = "2026-10-04"


class _Osservatore:
    """L'osservatore dal lato di chi legge lo scope (`Watcher.watching`)."""

    def watching(self, *, house=None):
        return [{"soggetto": "climate.camera_t", "motivo": "scalda la casa",
                 "autore": "observer", "quando": 1787000000.0},
                {"soggetto": "log:homeassistant.components.zha@ERROR",
                 "motivo": "un errore che torna", "autore": "observer",
                 "quando": 1787000002.0}]


def _app(tmp_path) -> dict:
    """Un'app con l'archivio VERO del cervello, un resoconto e un'analisi."""
    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    store.decide_scope("sensor.uptime", inside=False, reason="di servizio", author="observer")
    store.replace_report(DAY, {"giorno": DAY, "misure": [
        {"soggetto": "dev_a", "misura": "consumo", "valore": 3.2}], "cronaca": []})
    store.replace_analysis(DAY, {"giorno": DAY, "osservazioni": [
        {"soggetto": "dev_a", "testo": "consuma piu' del solito"}]})
    return {"observations": store, "watcher": _Osservatore()}


class _Richiesta:
    def __init__(self, app, query=None):
        self.app = app
        self.query = query or {}


def _body(response) -> dict:
    return json.loads(response.body)


async def _route(app, what: str, day: str | None) -> dict:
    """La rotta che la pagina chiama per ogni `cosa` che ha una rotta."""
    query = {"day": day} if day else {}
    if what in ("scope", "obiettivo"):
        body = _body(await handle_watching(_Richiesta(app)))
        return body if what == "scope" else {"obiettivo": body["obiettivo"]}
    handler = {"resoconti": handle_report, "analisi": handle_analysis}[what]
    body = _body(await handler(_Richiesta(app, query)))
    return body if what == "analisi" else (body if not day else {"resoconto": body["resoconto"]})


#: Le letture SENZA rotta, con la ragione: la pagina non le chiede a una rotta
#: del cervello. Lista di ammissione: una lettura nuova senza rotta deve
#: passare di qui, scritta.
WITHOUT_ROUTE = {
    "energia": "e' un oggetto della casa (`home_space/energy.py`), non del "
               "cervello; la sua prova e' qui sotto, contro `energy_dashboard`",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("what", sorted(set(MIND_READINGS) - set(WITHOUT_ROUTE)))
async def test_lo_strumento_e_la_rotta_dicono_la_stessa_cosa(tmp_path, what):
    """Fondamenta 3: lo stesso contenuto dalle due porte, per ogni `cosa` e,
    dove vale, anche per un giorno solo.

    Mutazione ESEGUITA il 06/10/2026: in `handle_watching` un campo in piu'
    solo nella rotta (`{**scope, "extra": 1}`) -- rossa su `scope`, col campo
    nel confronto. Ripristinata, `git status` pulito."""
    app = _app(tmp_path)
    dispatcher = create_tool_dispatcher(app)
    days = [None, DAY] if MIND_READINGS[what].by_day else [None]
    for day in days:
        arguments = {"cosa": what} | ({"giorno": day} if day else {})
        answer = await dispatcher.dispatch("mind", arguments)
        assert "errore" not in answer, answer
        assert answer == await _route(app, what, day), (what, day)


def test_ogni_lettura_ha_una_rotta_o_una_ragione():
    """La parametrizzazione qui sopra si chiede a `MIND_READINGS`: una lettura
    nuova entra nel confronto da sola. Se non ha una rotta, deve essere
    ammessa per iscritto in `WITHOUT_ROUTE`; una voce di `WITHOUT_ROUTE` che
    non e' piu' una lettura e' un'ammissione orfana."""
    assert set(WITHOUT_ROUTE) <= set(MIND_READINGS), set(WITHOUT_ROUTE) - set(MIND_READINGS)
    assert len(MIND_READINGS) >= 5, MIND_READINGS


def test_lo_schema_si_chiede_alla_tabella_del_parametro():
    """L'`enum` di `cosa` e' la tabella `MIND_READINGS`: un valore scritto
    nello schema e non nella tabella sarebbe un `KeyError` nel gestore, uno
    nella tabella e non nello schema una lettura che il modello non vede.

    Mutazione ESEGUITA il 06/10/2026: una riga `"prova"` aggiunta a
    `MIND_READINGS` -- compare nell'`enum` senza toccare lo schema ne' la
    prova (`["scope", ..., "energia", "prova"]`). Ripristinata."""
    assert MIND_TOOL_DEF["input_schema"]["properties"]["cosa"]["enum"] == list(MIND_READINGS)
    assert MIND_TOOL_DEF in KNOWLEDGE_TOOLS


@pytest.mark.asyncio
async def test_un_giorno_mai_aggregato_si_dice_come_lo_dice_la_rotta(tmp_path):
    """«Quel giorno non l'abbiamo guardato» non e' «non e' successo niente»:
    la rotta risponde 404 con l'ora in cui il resoconto si scrivera', lo
    strumento un `errore` con la stessa ora."""
    app = _app(tmp_path)
    dispatcher = create_tool_dispatcher(app)
    answer = await dispatcher.dispatch("mind", {"cosa": "resoconti", "giorno": "2026-01-01"})
    page = await handle_report(_Richiesta(app, {"day": "2026-01-01"}))
    assert page.status == 404
    assert "non e' stato aggregato" in answer["errore"]
    assert answer["ora_notturna"] == _body(page)["ora_notturna"]
    answer = await dispatcher.dispatch("mind", {"cosa": "analisi", "giorno": "2026-01-01"})
    assert "non e' stato analizzato" in answer["errore"]


@pytest.mark.asyncio
async def test_giorno_con_una_lettura_che_non_ha_giorni_si_rifiuta(tmp_path):
    """Un filtro che non vale si rifiuta, non si ignora: lo stesso contratto
    di `history`. Il rifiuto nomina le letture per cui vale, chieste alla
    tabella.

    Mutazione ESEGUITA il 06/10/2026: tolto il controllo di `by_day` dal
    gestore -- `scope` con un giorno rispondeva lo scope, rossa."""
    dispatcher = create_tool_dispatcher(_app(tmp_path))
    answer = await dispatcher.dispatch("mind", {"cosa": "scope", "giorno": DAY})
    assert answer == {"errore": "«giorno» vale solo per analisi, resoconti, non per «scope»."}


@pytest.mark.asyncio
async def test_una_cosa_fuori_vocabolario_si_rifiuta_col_vocabolario(tmp_path):
    dispatcher = create_tool_dispatcher(_app(tmp_path))
    answer = await dispatcher.dispatch("mind", {"cosa": "ricordi"})
    assert "errore" in answer
    assert all(what in answer["errore"] for what in MIND_READINGS), answer


@pytest.mark.asyncio
async def test_senza_osservatore_e_senza_letture_si_dice_cosa_manca(tmp_path):
    """Un archivio assente non e' un archivio vuoto: la rotta risponde 503,
    lo strumento un `errore` che lo dice."""
    app = _app(tmp_path)
    app.pop("watcher")
    answer = await create_tool_dispatcher(app).dispatch("mind", {"cosa": "scope"})
    assert "osservatore non e' disponibile" in answer["errore"]
    assert (await handle_watching(_Richiesta(app))).status == 503

    app.pop("observations")
    answer = await create_tool_dispatcher(app).dispatch("mind", {"cosa": "resoconti"})
    assert "archivio del cervello" in answer["errore"]

    bare = ToolDispatcher(None, None)
    answer = await bare.dispatch("mind", {"cosa": "scope"})
    assert "letture del cervello non sono collegate" in answer["errore"]


@pytest.mark.asyncio
async def test_l_energia_e_la_dashboard_della_casa(tmp_path):
    """`cosa: energia` e' la dashboard Energia dell'anagrafe
    (`energy.energy_dashboard`), lo stesso oggetto che legge il giro delle
    ricette -- con `ha_statistiche` a `None`, perche' qui l'elenco delle
    statistiche non si chiede, e «non l'ho chiesto» si dice com'e'."""
    store = _store(tmp_path)
    ha = CasaFinta({"energy_prefs": PREFS})
    # Senza letture del cervello: l'energia non passa di li'.
    dispatcher = ToolDispatcher(store, None, cache=_Cache(), ha=ha)
    answer = await dispatcher.dispatch("mind", {"cosa": "energia"})
    expected = await energy.energy_dashboard(ha, store, _house(store))
    assert answer == {"energia": expected}
    assert all(role["ha_statistiche"] is None for role in answer["energia"]["ruoli"])

