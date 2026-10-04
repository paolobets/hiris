"""Le primitive del canale di configurazione: nude, e il rifiuto porta il motivo.

Dal Task 12 della Tappa 2 girano sul client VERO (`scripts/casa_finta.py`):
prima sostituivano la sessione HTTP con una `FintaSessione` scritta qui, e
`_ws_send` coi costruttori di `tests/_ha_fakes.py`, uscito con loro. La casa finta registra in
`calls` il metodo e il percorso -- tolto l'indirizzo della casa, che una
richiesta deve portare o non e' servita -- e risponde nella forma di Home
Assistant (`json_message`, `components/config/view.py`, tag `2026.9.4`).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import SILENT, CasaFinta, Refused

from tests._casa_sintetica import synthetic_inputs

CONFIG = "/api/config/"


def _house(**answers) -> CasaFinta:
    """`answers` per metodo: `post`, `get`, `delete` (l'esito della rotta di
    configurazione) e `validate` (il `result` di `validate_config`)."""
    routes = {"post": f"POST {CONFIG}", "get": CONFIG, "delete": f"DELETE {CONFIG}",
              "validate": "validate_config"}
    return CasaFinta(synthetic_inputs(), answers={
        routes[name]: answer for name, answer in answers.items()})


@pytest.mark.asyncio
async def test_salva_compone_la_rotta_dell_editor():
    house = _house(post=lambda path, body: {"result": "ok"})
    esito = await house.save_configuration("automation", "1771346155970", {"alias": "X"})
    assert house.calls == [("POST /api/config/automation/config/1771346155970",
                            {"alias": "X"})]
    assert esito == {"salvato": True}


@pytest.mark.asyncio
async def test_il_rifiuto_di_home_assistant_torna_col_motivo_non_come_eccezione():
    """Il 400 di HA E' il valore di prodotto (spec §2.5): non si solleva, si legge."""
    house = _house(post=lambda path, body: Refused(
        400, "Message malformed: required key not provided @ data['triggers']"))
    esito = await house.save_configuration("automation", "123", {})
    assert "salvato" not in esito
    assert "triggers" in esito["errore"]


@pytest.mark.asyncio
async def test_una_chiave_ostile_non_arriva_mai_nell_url():
    house = _house(post=lambda path, body: {"result": "ok"})
    esito = await house.save_configuration("automation", "../../core/config", {})
    assert house.calls == []
    assert "chiave" in esito["errore"]


@pytest.mark.asyncio
async def test_un_dominio_fuori_dai_tre_non_si_scrive():
    house = _house(post=lambda path, body: {"result": "ok"})
    esito = await house.save_configuration("light", "x", {})
    assert house.calls == []
    assert "light" in esito["errore"]


@pytest.mark.asyncio
async def test_leggi_restituisce_il_corpo():
    house = _house(get=lambda path: {"id": "123", "alias": "Tapparelle"})
    assert (await house.read_configuration("automation", "123"))["corpo"]["alias"] == "Tapparelle"
    assert house.calls == [("/api/config/automation/config/123", None)]


@pytest.mark.asyncio
async def test_leggi_distingue_il_non_c_e_dal_non_ho_potuto_leggere():
    """«Assente» e «errore» non sono la stessa cosa: chi genera un id nuovo usa
    questa differenza per non scrivere sopra un'automazione esistente quando
    Home Assistant sta rispondendo male."""
    house = _house(get=lambda path: Refused(404, "Resource not found"))
    assert await house.read_configuration("automation", "999") == {"assente": True}
    house = _house(get=lambda path: Refused(500, "boom"))
    esito = await house.read_configuration("automation", "999")
    assert esito == {"errore": "boom", "causa": "rifiuto", "codice": 500}


@pytest.mark.asyncio
async def test_leggi_una_chiave_ostile_e_una_richiesta_con_la_busta_intera():
    """La lettura della configurazione ha la busta di ogni altra lettura
    (fondamenta 3): una chiave che non ha la forma ammessa si ferma prima
    della rete, con `causa: richiesta`, come `history` su un entity_id
    malformato."""
    house = _house(get=lambda path: {"id": "x"})
    esito = await house.read_configuration("automation", "../../core/config")
    assert house.calls == []
    assert esito["causa"] == "richiesta"
    assert esito["codice"] is None
    assert "chiave" in esito["errore"]
    esito = await house.read_configuration("light", "x")
    assert esito["causa"] == "richiesta"
    assert "light" in esito["errore"]


@pytest.mark.asyncio
async def test_le_scritture_fermate_prima_della_rete_hanno_la_stessa_busta():
    """Il rifiuto di `_config_route` e' uno solo, condiviso dalle tre
    primitive: anche le due scritture lo rendono con la busta intera. Il
    rifiuto di Home Assistant su una scrittura resta invece `{"errore"}`
    (Tappa 7): lo dichiara il docstring di `_failure`."""
    house = _house(post=lambda path, body: {"result": "ok"},
                   delete=lambda path, body: {"result": "ok"})
    for esito in (await house.save_configuration("automation", "a/b", {}),
                  await house.delete_configuration("light", "x")):
        assert esito["causa"] == "richiesta"
        assert "codice" in esito
    assert house.calls == []


@pytest.mark.asyncio
async def test_cancella_usa_il_metodo_delete():
    house = _house(delete=lambda path, body: {"result": "ok"})
    esito = await house.delete_configuration("script", "buonanotte")
    assert [what for what, _body in house.calls] == [
        "DELETE /api/config/script/config/buonanotte"]
    assert esito == {"cancellato": True}


@pytest.mark.asyncio
async def test_valida_manda_solo_le_chiavi_presenti_e_riporta_l_esito():
    house = _house(validate=lambda extra: {
        "triggers": {"valid": False, "error": "Unknown trigger 'quando'"}})
    esito = await house.validate_config(triggers=[{"trigger": "quando"}])
    assert house.calls == [("validate_config", {"triggers": [{"trigger": "quando"}]})]
    assert esito["triggers"]["valid"] is False


@pytest.mark.asyncio
async def test_valida_senza_risposta_non_dichiara_valido():
    """Il silenzio di HA non e' un «va bene»: e' un errore dichiarato."""
    house = _house(validate=lambda extra: SILENT)
    esito = await house.validate_config(actions=[{"action": "light.turn_on"}])
    assert esito["causa"] == "silenzio"
    assert "valid" not in str(esito.get("actions", ""))
