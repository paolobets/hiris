"""Gli alias delle entita': la parola con cui l'utente chiama le sue cose.

`config/entity_registry/list` risponde con `as_partial_dict`, che NON contiene
`aliases` (verificato sul sorgente di HA: stanno solo in `extended_dict`).
Quindi la colonna `alias` delle entita' era vuota su ogni casa, sempre — e la
«spina dorsale di `cerca`» reggeva solo per le AREE, che invece li mandano
davvero nel proprio registro.

Un utente che aveva scritto «lampada della nonna» come alias in Home Assistant
non trovava niente cercandola: HIRIS gli chiedeva di ripetere a parole cio' che
aveva gia' dichiarato una volta.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

from hiris.app.proxy.ha_client import HAClient

GET_ENTRIES = "config/entity_registry/get_entries"


def _house(aliases=None, *, silent=False):
    """Una casa con UN'entita' (`light.salotto`), e i suoi alias scritti
    nella riga del registro. `CasaFinta` risponde come Home Assistant: la
    lista (`as_partial_dict`) li toglie, `get_entries` (`extended_dict`) li
    porta. Se la casa li mettesse nella lista, la prova non potrebbe fallire
    -- ed e' esattamente cosi' che questo difetto e' passato inosservato per
    mesi. I registri sono chiesti alla tabella del client, non ricopiati."""
    registries = {key: [] for key, _msg_type, _extra in HAClient._REGISTRIES}
    row = {"entity_id": "light.salotto", "name": "Piantana"}
    if aliases is not None:
        row["aliases"] = aliases
    registries["entita"] = [row]
    return CasaFinta({"registries": registries},
                     silence={GET_ENTRIES} if silent else ())


@pytest.mark.asyncio
async def test_gli_alias_arrivano_dal_comando_esteso():
    house = _house(["lampada della nonna"])
    registri, non_disponibili = await house.read_registries()
    assert registri["entita"][0]["aliases"] == ["lampada della nonna"]
    assert non_disponibili == []
    assert [extra for command, extra in house.calls
            if command == GET_ENTRIES] == [{"entity_ids": ["light.salotto"]}]


@pytest.mark.asyncio
async def test_un_comando_esteso_fallito_si_dichiara():
    """Non si ingoia, e non si chiama `entita`: quella dicitura significa «il
    registro delle entita' non ha risposto», e farebbe credere alla casa di non
    avere entita' affatto."""
    house = _house(["lampada della nonna"], silent=True)
    _registri, non_disponibili = await house.read_registries()
    assert non_disponibili == ["entita:alias"]


@pytest.mark.asyncio
async def test_un_entita_senza_alias_non_ne_guadagna_uno_vuoto():
    registri, _ = await _house([]).read_registries()
    assert "aliases" not in registri["entita"][0]


@pytest.mark.asyncio
async def test_il_None_di_home_assistant_non_e_un_alias():
    """LA SENTINELLA, e il difetto vero trovato sull'impianto il 2026-08-18.

    Home Assistant dichiara `_serialize_aliases(...) -> list[str | None]` e
    mappa `COMPUTED_NAME` su `None` (`helpers/entity_registry.py`, verificato):
    quel `null` significa «qui va il nome calcolato», che HIRIS ha gia'
    (`original_name`). Non e' una parola che qualcuno ha scritto.

    Preso alla lettera ha riempito l'archivio -- 1030 entita' su 1223 con
    `alias: [null]` -- e ha ucciso `cerca` e `remember`, gli unici due che
    costruiscono l'indice: «'NoneType' object has no attribute 'lower'» su
    OGNI chiamata.

    E' il `carbon_monoxide` in un'altra forma: avevo verificato CHE `aliases`
    esistesse in `extended_dict`, non COSA possono contenere i suoi elementi.
    Il tipo lo diceva.
    """
    house = _house([None, "lampada della nonna", "  ", 42])
    registri, _ = await house.read_registries()
    assert registri["entita"][0]["aliases"] == ["lampada della nonna"]


@pytest.mark.asyncio
async def test_una_lista_di_sole_sentinelle_non_diventa_un_alias_vuoto():
    """`[None]` deve sparire del tutto, non diventare `[]` salvato: la chiave
    resta assente, come per un'entita' che alias non ne ha."""
    registri, _ = await _house([None]).read_registries()
    assert "aliases" not in registri["entita"][0]

