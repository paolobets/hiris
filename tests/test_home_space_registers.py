"""I registri della casa, letti dal client vero sulla casa finta.

Fino alla Tappa 2 (Task 12) queste prove sostituivano `HAClient._ws_send` con
un `AsyncMock` che rendeva liste di messaggi scritte a mano, accoppiate ai
comandi per POSIZIONE. Ora girano su `scripts/casa_finta.py::CasaFinta`, che
risponde dagli ingressi coi messaggi grezzi di Home Assistant: cio' che il
client ha chiesto si legge in `house.calls`.

Resta sul trasporto finto una prova sola, `test_un_ambito_di_categorie_caduto_
si_dice_quale`: tace UN ambito delle categorie e non gli altri, cioe' lo
stesso comando (`config/category_registry/list`) con argomenti diversi -- e
`silence=` della casa finta vale per comando, non per argomento.
"""
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

#: I comandi dei registri, chiesti alla tabella del client: chi li ricopiasse
#: qui dovrebbe tenerli allineati a mano.
_REGISTRY_COMMANDS = [msg_type for _key, msg_type, _extra in HAClient._REGISTRIES]
_FLOORS = "config/floor_registry/list"


def _house(**kwargs) -> CasaFinta:
    return CasaFinta(synthetic_inputs(), **kwargs)


def _msg(risultato):
    return {"id": 1, "type": "result", "success": True, "result": risultato}


@pytest.mark.asyncio
async def test_leggi_registri_chiede_tutti_i_registri_in_un_colpo():
    house = _house()
    registri, _ = await house.read_registries()
    # Una connessione per tutti i registri, poi una per gli alias delle entita'.
    assert house.connections[0] == ("ws", tuple(_REGISTRY_COMMANDS))
    assert [command for command, _ in house.calls[:len(_REGISTRY_COMMANDS)]] == [
        "config/floor_registry/list",
        "config/area_registry/list",
        "config/device_registry/list",
        "config/entity_registry/list",
        "config/label_registry/list",
        "config_entries/get",
        "config/category_registry/list",
        "config/category_registry/list",
        "config/category_registry/list",
        "config/category_registry/list",
    ]
    assert set(registri) == {"piani", "aree", "dispositivi", "entita",
                             "etichette", "categorie", "integrazioni"}


@pytest.mark.asyncio
async def test_un_registro_mancante_diventa_lista_vuota_non_un_guasto():
    """Un HA senza piani risponde comunque: il resto dell'anagrafe deve reggere."""
    registri, _ = await _house(silence={_FLOORS}).read_registries()
    assert registri["piani"] == []
    assert registri["aree"] == synthetic_inputs()["registries"]["aree"]


@pytest.mark.asyncio
async def test_un_registro_caduto_si_distingue_da_uno_vuoto():
    """La casa senza piani e il registro dei piani caduto danno la stessa lista
    vuota: solo `non_disponibili` dice quale dei due e' successo."""
    inputs = synthetic_inputs()
    inputs["registries"]["aree"] = []
    registri, non_disponibili = await CasaFinta(
        inputs, silence={_FLOORS}).read_registries()
    assert registri["piani"] == [] and registri["aree"] == []
    assert "piani" in non_disponibili
    assert "aree" not in non_disponibili


@pytest.mark.asyncio
async def test_una_casa_sana_non_ha_registri_non_disponibili():
    _, non_disponibili = await _house().read_registries()
    assert non_disponibili == []


@pytest.mark.asyncio
async def test_le_categorie_si_chiedono_per_tutti_gli_ambiti():
    house = _house()
    await house.read_registries()
    ambiti = [extra["scope"] for tipo, extra in house.calls
              if tipo == "config/category_registry/list"]
    assert ambiti == ["automation", "script", "scene", "helpers"]


@pytest.mark.asyncio
async def test_ogni_categoria_porta_il_proprio_ambito():
    """Gli ingressi portano ogni categoria col suo `ambito`; la casa finta lo
    toglie (Home Assistant non lo manda) e serve a ogni comando le sole righe
    del suo `scope`: e' il client a rimettercelo."""
    inputs = synthetic_inputs()
    inputs["registries"]["categorie"] = [
        {"category_id": f"c{i}", "name": f"C{i}", "ambito": scope}
        for i, scope in enumerate(["automation", "script", "scene", "helpers"])]
    registri, _ = await CasaFinta(inputs).read_registries()
    assert [(c["category_id"], c["ambito"]) for c in registri["categorie"]] == [
        ("c0", "automation"), ("c1", "script"), ("c2", "scene"), ("c3", "helpers")]


@pytest.mark.asyncio
async def test_un_ambito_di_categorie_caduto_si_dice_quale():
    # Resta sul trasporto finto: vedi il docstring del modulo.
    risposte = [_msg([]) for _ in range(6)]
    risposte += [_msg([]), None, _msg([]), _msg([])]
    with patch.object(HAClient, "_ws_send", AsyncMock(return_value=risposte)):
        _, non_disponibili = await HAClient(base_url="http://ha.test",
                                            token="t").read_registries()
    assert non_disponibili == ["categorie:script"]


# Task B6: un registro che non risponde deve dire PERCHE', non solo che e'
# caduto. `_ws_send` restituisce il messaggio INTERO (il suo docstring lo
# dichiara): {success, result, error}, oppure None se il comando non ha mai
# avuto risposta. Sono tre guasti diversi con la stessa faccia in
# `non_disponibili` -- ma il log deve poterli distinguere. La casa finta li
# produce tutti e tre sul registro dei piani: `refuse=` e' il rifiuto vero di
# Home Assistant, `answers=` con un `result` che non e' una lista e' la forma
# inattesa SENZA errore, `silence=` e' il comando senza risposta.

@pytest.mark.asyncio
async def test_registro_rifiutato_il_log_porta_il_motivo_di_ha(caplog):
    """HA risponde ma rifiuta il comando: c'e' un `error` vero. Il log deve
    portare il motivo di HA, non il nome del comando che gia' sapevamo."""
    house = _house(refuse={_FLOORS: {"code": "not_found", "message": "Unknown command."}})
    with caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"):
        _, non_disponibili = await house.read_registries()
    assert non_disponibili == ["piani"]
    righe = [r.getMessage() for r in caplog.records]
    assert any("Unknown command." in r for r in righe), caplog.text


@pytest.mark.asyncio
async def test_registro_forma_inattesa_il_log_lo_dice(caplog):
    """HA risponde, non c'e' nessun `error`, ma `result` non e' una lista:
    guasto diverso dal rifiuto, e il log deve dirlo in modo diverso."""
    house = _house(answers={_FLOORS: lambda extra: "non-sono-una-lista"})
    with caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"):
        _, non_disponibili = await house.read_registries()
    assert non_disponibili == ["piani"]
    righe = [r.getMessage() for r in caplog.records]
    assert any("non-sono-una-lista" in r for r in righe), caplog.text
    assert not any("rifiutat" in r for r in righe), caplog.text


@pytest.mark.asyncio
async def test_registro_mai_partito_il_log_lo_dice(caplog):
    """Il comando non ha avuto risposta (connessione non aperta): `_ws_send`
    restituisce `None` per lui. Terzo guasto, terza dicitura -- non quella del
    rifiuto, non quella della forma inattesa."""
    house = _house(silence={_FLOORS})
    with caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"):
        _, non_disponibili = await house.read_registries()
    assert non_disponibili == ["piani"]
    righe = [r.getMessage() for r in caplog.records]
    assert any("nessuna risposta" in r for r in righe), caplog.text
    assert not any("rifiutat" in r for r in righe), caplog.text
    assert not any("non-sono-una-lista" in r for r in righe), caplog.text


# fetta E3 Task 11: test_il_monitor_di_salute_filtra_da_se_gli_errori e'
# cancellato -- importava `errori_di_integrazione` da
# `hiris.app.proxy.health_monitor`, cancellato per intero insieme
# all'HealthMonitor (il suo unico lettore rimasto). Verificato che cade per
# costruzione: `ModuleNotFoundError: No module named
# 'hiris.app.proxy.health_monitor'`, prima della cancellazione. Nessun
# successore: quel filtro non ha piu' alcun consumatore.
#
# fetta E3 Task 12: test_get_config_entries_restituisce_tutto_non_solo_gli_
# errori e' cancellato -- testava `HAClient.get_config_entries()` in
# isolamento, un metodo diverso da `read_registries()` sopra (che chiede
# "config/config_entries/get_entries" direttamente nel proprio batch WS, non
# passando da `get_config_entries`). `get_config_entries` era gia' ORFANO
# DICHIARATO dal Task 11 (l'HealthMonitor che lo leggeva e' uscito):
# verificato che cade per costruzione (`AttributeError: 'HAClient' object
# has no attribute 'get_config_entries'`), poi cancellato insieme al metodo.
