"""Helper e etichetta: il secondo canale, e la paternita' che sta in casa di HA.

Dal Task 12 della Tappa 2 sul client VERO (`scripts/casa_finta.py`): prima
`_ws_send` era sostituito coi costruttori di `tests/_ha_fakes.py`, uscito con loro. Cio' che
parte si legge in `house.calls`; i rifiuti sono quelli di Home Assistant
(`Refused`), il comando senza risposta e' `SILENT`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import SILENT, CasaFinta, Refused

from tests._casa_sintetica import synthetic_inputs


def _house(results: dict) -> CasaFinta:
    """`results` e' `{comando: result}` -- o un esito (`Refused`, `SILENT`)."""
    return CasaFinta(synthetic_inputs(), answers={
        command: (lambda extra, outcome=outcome: outcome)
        for command, outcome in results.items()})


@pytest.mark.asyncio
async def test_crea_helper_usa_il_comando_del_dominio():
    house = _house({"input_boolean/create": {"id": "modalita_notte",
                                             "name": "Modalita notte"}})
    esito = await house.create_helper("input_boolean", {"name": "Modalita notte"})
    assert house.calls == [("input_boolean/create", {"name": "Modalita notte"})]
    assert esito["helper"]["id"] == "modalita_notte"


@pytest.mark.asyncio
async def test_un_dominio_che_non_e_un_helper_non_si_crea():
    house = _house({})
    esito = await house.create_helper("light", {"name": "X"})
    assert house.calls == []
    assert "light" in esito["errore"]


@pytest.mark.asyncio
async def test_cancella_helper_nomina_la_chiave_del_dominio():
    """`input_boolean/delete` vuole `input_boolean_id`, non `id`: la chiave porta
    il nome del dominio (StorageCollectionWebsocket di Home Assistant)."""
    house = _house({"timer/delete": None})
    esito = await house.delete_helper("timer", "cottura")
    assert house.calls == [("timer/delete", {"timer_id": "cottura"})]
    assert esito == {"cancellato": True}


@pytest.mark.asyncio
async def test_un_comando_ws_fallito_non_diventa_un_successo():
    house = _house({"counter/create": Refused("invalid_format", "name is required")})
    esito = await house.create_helper("counter", {})
    assert "helper" not in esito
    assert "name is required" in esito["errore"]
    assert esito["codice"] == "invalid_format"


@pytest.mark.asyncio
async def test_l_etichetta_si_crea_e_si_elenca():
    house = _house({
        "config/label_registry/list": [{"label_id": "hiris", "name": "HIRIS"}],
        "config/label_registry/create": {"label_id": "hiris", "name": "HIRIS"},
    })
    assert (await house.read_registry("etichette"))["etichette"][0]["label_id"] == "hiris"
    assert (await house.create_label("HIRIS"))["etichetta"]["label_id"] == "hiris"
    assert house.calls[1] == ("config/label_registry/create", {"name": "HIRIS"})


@pytest.mark.asyncio
async def test_applicare_l_etichetta_non_cancella_quelle_dell_utente():
    """`config/entity_registry/update` SOSTITUISCE la lista: si legge prima e si
    unisce, o le etichette che l'utente aveva messo a mano spariscono."""
    house = _house({
        "config/entity_registry/get": {"entity_id": "automation.tapparelle",
                                       "labels": ["casa", "mattina"]},
        "config/entity_registry/update": {},
    })
    esito = await house.add_label_to("automation.tapparelle", "hiris")
    command, extra = house.calls[1]
    assert command == "config/entity_registry/update"
    assert sorted(extra["labels"]) == ["casa", "hiris", "mattina"]
    assert esito == {"applicata": True}


@pytest.mark.asyncio
async def test_se_non_si_riesce_a_leggere_le_etichette_non_si_sovrascrive():
    """Non aver letto non e' «non ce n'erano»: si rinuncia e si dichiara."""
    house = _house({"config/entity_registry/get": SILENT})
    esito = await house.add_label_to("automation.x", "hiris")
    assert [command for command, _ in house.calls] == ["config/entity_registry/get"]
    assert "errore" in esito
