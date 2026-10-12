"""Ogni ricordo ancorato a una parte della casa esce dalla sua scheda di
`search(riferimento)` (Tappa 9, F6; D-20).

Fino al 12/10/2026 i ricordi ancorati li dava anche lo strumento `fetch`, e
la decisione 10 della spec dello sprint lo toglieva solo dopo averlo PROVATO:
se un ricordo usciva da `fetch` e non da `search`, togliere `fetch` lo
rendeva irraggiungibile al modello. La prova di equivalenza e' stata rossa
dal 05/10 all'08/10/2026 per le automazioni (M-32, chiuso nella F3) e fino al
12/10/2026 per entita' e dispositivi disabilitati, che `search` non apriva
(D7 della Tappa 3). Il proprietario ha scelto «Sì, per id esatto»
(`house_query._disabled_by_reference`): la prova e' diventata verde, e
`fetch` e' uscito.

Resta la proprieta' che quella prova difendeva, sulla porta che resta: per
ogni area, entita' e dispositivo della casa sintetica -- disabilitati e
nascosti compresi -- il ricordo ancorato a lui esce dalla sua scheda.

Mutazione ESEGUITA: senza il ramo del disabilitato in `house_query._select`
-- rossa, coi due disabilitati della casa sintetica fra i mancanti.
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


def test_la_tabella_non_ha_fetch():
    assert "fetch" not in {tool.name for tool in TOOLS}


@pytest.mark.asyncio
async def test_ogni_ricordo_ancorato_esce_dalla_scheda(tmp_path):
    """Gli oggetti si chiedono all'anagrafe, non si elencano: un ricordo per
    ognuno, ancorato a lui, e la sua scheda di `search(riferimento)` -- con
    le nascoste e quelle di servizio incluse -- deve portarlo."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        home_space, memory = app["home_space_store"].read(), app["memory_store"]
        objects = ([("area", a["id"]) for a in home_space["aree"]]
                   + [("entita", e["id"]) for e in home_space["entita"]]
                   + [("dispositivo", d["id"]) for d in home_space["dispositivi"]])
        assert len(objects) >= 10, objects
        assert any(d["disabilitato"] for d in home_space["dispositivi"]), \
            "la casa sintetica non ha piu' un dispositivo disabilitato: la prova non guarda"
        wanted = {ident: memory.remember(f"un ricordo su {ident}",
                                         ancore=[{"tipo": kind, "riferimento": ident}])
                  for kind, ident in objects}
        dispatcher = create_tool_dispatcher(app, soffitto=consente(None, ruolo="amministratore"))
        missing = []
        for _kind, ident in objects:
            searched = await dispatcher.dispatch("search", {
                "riferimento": ident, "includi_nascoste": True, "includi_servizio": True})
            found = {m["id"] for entry in searched.get("voci") or []
                     for m in entry.get("ricordi") or []}
            if wanted[ident] not in found:
                missing.append(ident)
        assert missing == []
