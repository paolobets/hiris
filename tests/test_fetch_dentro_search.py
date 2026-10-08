"""`fetch` e' un sottoinsieme di `search(riferimento)`? (Tappa 5, Task 4, passo 2)

La decisione 10 della spec dello sprint toglie `fetch`: il dettaglio di
`search` con `riferimento` porta gia' i ricordi ancorati
(`queries._tethered_memories`). Il piano chiede di PROVARLO prima di togliere,
oggetto per oggetto della casa sintetica: se un ricordo esce da `fetch` e non
da `search`, togliere `fetch` lo renderebbe irraggiungibile al modello.

**Misurato il 05/10/2026 su `5bce65d` + Task 0-3: la prova e' ROSSA**, e il
piano dice di fermarsi e chiedere. Su 19 oggetti, `search` -- anche con
`includi_nascoste` e `includi_servizio` -- non porta i ricordi ancorati a:

- un'entita' DISABILITATA (`sensor.sensore_d_spento`) e un dispositivo
  disabilitato (`dev_d`): `search` non li cerca (D7 della Tappa 3), quindi
  non apre il loro dettaglio;
- un'AUTOMAZIONE (`automation.automazione_uno`), ancorata come entita':
  `search` apre il dettaglio del comportamento, la cui chiave `ricordi` e'
  sempre vuota (M-32) -- e la Tappa 4 (Task 8) la toglie.

Finche' il proprietario non decide, `fetch` resta e questa prova e' un
`xfail` stretto: diventa verde da sola il giorno in cui `search` porta quei
ricordi, e allora lo `xfail` va tolto.

**Era cieca dal 07/10/2026 all'08/10/2026** (trovato dalla fetta F3 della
Tappa 9): da `ce10f64` (gli attori dichiarano il loro soffitto)
`create_tool_dispatcher` rifiuta un turno senza soffitto, e questa prova lo
costruiva senza. Lo `xfail` stretto restava «atteso» per un `ValueError`, non
per i ricordi mancanti: un rosso per la ragione sbagliata. Ora il turno porta
il soffitto di chi amministra, come le altre prove della chat
(`tests/test_mind_tool.py`), e il rosso e' di nuovo quello dei tre ricordi.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.soffitto import consente
from hiris.app.home_space.tools import TOOLS
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

_GAP = ("fetch porta i ricordi di oggetti disabilitati e di automazioni, che "
        "search(riferimento) non apre: misurato il 05/10/2026, decisione del "
        "proprietario")


@pytest.mark.xfail(strict=True, reason=_GAP)
def test_la_tabella_non_ha_fetch():
    assert "fetch" not in {tool.name for tool in TOOLS}


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=_GAP)
async def test_i_ricordi_di_fetch_escono_anche_da_search(tmp_path):
    """Un ricordo per ogni area, entita' e dispositivo della casa sintetica,
    ancorato a lui; poi, per ognuno, i ricordi di `fetch(riferimento)` contro
    quelli del dettaglio di `search(riferimento)`, con le nascoste e quelle di
    servizio incluse. Gli oggetti si chiedono all'anagrafe, non si elencano."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        home_space, memory = app["home_space_store"].read(), app["memory_store"]
        objects = ([("area", a["id"]) for a in home_space["aree"]]
                   + [("entita", e["id"]) for e in home_space["entita"]]
                   + [("dispositivo", d["id"]) for d in home_space["dispositivi"]])
        assert len(objects) >= 10, objects
        for kind, ident in objects:
            memory.remember(f"un ricordo su {ident}",
                            ancore=[{"tipo": kind, "riferimento": ident}])
        dispatcher = create_tool_dispatcher(app, soffitto=consente(None, ruolo="amministratore"))
        missing = {}
        for _kind, ident in objects:
            fetched = await dispatcher.dispatch("fetch", {"riferimento": ident})
            searched = await dispatcher.dispatch("search", {
                "riferimento": ident, "includi_nascoste": True, "includi_servizio": True})
            from_fetch = {m["id"] for m in fetched["ricordi"]}
            from_search = {m["id"] for entry in searched.get("voci") or []
                           for m in entry.get("ricordi") or []}
            if not from_fetch <= from_search:
                missing[ident] = sorted(from_fetch - from_search)
        assert missing == {}
