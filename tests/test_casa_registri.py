import logging
from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.proxy.ha_client import HAClient


def _client():
    return HAClient(base_url="http://ha.test", token="t")


def _msg(risultato):
    return {"id": 1, "type": "result", "success": True, "result": risultato}


def _msg_errore(codice, messaggio):
    """Un messaggio HA che rifiuta il comando: il modo in cui `error` si
    presenta davvero -- {success: False, error: {code, message}}, non un
    `result` mancante e basta."""
    return {"id": 1, "type": "result", "success": False,
            "error": {"code": codice, "message": messaggio}}


@pytest.mark.asyncio
async def test_leggi_registri_chiede_tutti_i_registri_in_un_colpo():
    client = _client()
    finto = AsyncMock(return_value=[_msg([{"a": 1}]) for _ in range(10)])
    with patch.object(HAClient, "_ws_batch", finto):
        registri, _ = await client.leggi_registri()
    (comandi,), _ = finto.call_args
    tipi = [t for t, _ in comandi]
    assert tipi == [
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
    risposte = [None] + [_msg([{"a": 1}]) for _ in range(9)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri, _ = await _client().leggi_registri()
    assert registri["piani"] == []
    assert registri["aree"] == [{"a": 1}]


@pytest.mark.asyncio
async def test_un_registro_caduto_si_distingue_da_uno_vuoto():
    """La casa senza piani e il registro dei piani caduto danno la stessa lista
    vuota: solo `non_disponibili` dice quale dei due e' successo."""
    risposte = [None] + [_msg([]) for _ in range(9)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri, non_disponibili = await _client().leggi_registri()
    assert registri["piani"] == []
    assert "piani" in non_disponibili
    assert "aree" not in non_disponibili


@pytest.mark.asyncio
async def test_una_casa_sana_non_ha_registri_non_disponibili():
    with patch.object(HAClient, "_ws_batch",
                      AsyncMock(return_value=[_msg([{"a": 1}]) for _ in range(10)])):
        _, non_disponibili = await _client().leggi_registri()
    assert non_disponibili == []


@pytest.mark.asyncio
async def test_le_categorie_si_chiedono_per_tutti_gli_ambiti():
    finto = AsyncMock(return_value=[_msg([]) for _ in range(10)])
    with patch.object(HAClient, "_ws_batch", finto):
        await _client().leggi_registri()
    (comandi,), _ = finto.call_args
    ambiti = [extra["scope"] for tipo, extra in comandi
              if tipo == "config/category_registry/list"]
    assert ambiti == ["automation", "script", "scene", "helpers"]


@pytest.mark.asyncio
async def test_ogni_categoria_porta_il_proprio_ambito():
    risposte = [_msg([]) for _ in range(6)]                       # i sei registri non-categoria
    risposte += [_msg([{"category_id": f"c{i}", "name": f"C{i}"}]) for i in range(4)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri, _ = await _client().leggi_registri()
    assert [c["ambito"] for c in registri["categorie"]] == [
        "automation", "script", "scene", "helpers"]


@pytest.mark.asyncio
async def test_un_ambito_di_categorie_caduto_si_dice_quale():
    risposte = [_msg([]) for _ in range(6)]
    risposte += [_msg([]), None, _msg([]), _msg([])]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        _, non_disponibili = await _client().leggi_registri()
    assert non_disponibili == ["categorie:script"]


# Task B6: un registro che non risponde deve dire PERCHE', non solo che e'
# caduto. `_ws_batch` restituisce il messaggio INTERO (il suo docstring lo
# dichiara): {success, result, error}, oppure None se il comando non ha mai
# avuto risposta. Sono tre guasti diversi con la stessa faccia in
# `non_disponibili` -- ma il log deve poterli distinguere. Le tre finte sotto
# imitano ognuno dei tre modi in cui HA (o la connessione) mente davvero:
# _msg_errore produce un `error` vero, _msg con un `result` non-lista imita
# una forma inattesa SENZA errore, e `None` imita il comando mai partito.
# Tutte e tre puntano al registro "piani" (primo di _REGISTRI, comando
# "config/floor_registry/list") apposta: quel comando non cambia in questo
# task, cosi' i test restano validi a prescindere dalla correzione del nome
# del comando "integrazioni" fatta piu' sotto nell'implementazione.

@pytest.mark.asyncio
async def test_registro_rifiutato_il_log_porta_il_motivo_di_ha(caplog):
    """HA risponde ma rifiuta il comando: c'e' un `error` vero. Il log deve
    portare il motivo di HA, non il nome del comando che gia' sapevamo."""
    risposte = [_msg_errore("not_found", "Unknown command.")] + [_msg([]) for _ in range(9)]
    with (
        patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)),
        caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"),
    ):
        _, non_disponibili = await _client().leggi_registri()
    assert "piani" in non_disponibili
    righe = [r.getMessage() for r in caplog.records]
    assert any("Unknown command." in r for r in righe), caplog.text


@pytest.mark.asyncio
async def test_registro_forma_inattesa_il_log_lo_dice(caplog):
    """HA risponde, non c'e' nessun `error`, ma `result` non e' una lista:
    guasto diverso dal rifiuto, e il log deve dirlo in modo diverso."""
    risposte = [_msg("non-sono-una-lista")] + [_msg([]) for _ in range(9)]
    with (
        patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)),
        caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"),
    ):
        _, non_disponibili = await _client().leggi_registri()
    assert "piani" in non_disponibili
    righe = [r.getMessage() for r in caplog.records]
    assert any("non-sono-una-lista" in r for r in righe), caplog.text
    assert not any("rifiutat" in r for r in righe), caplog.text


@pytest.mark.asyncio
async def test_registro_mai_partito_il_log_lo_dice(caplog):
    """Il batch non e' mai partito (connessione non aperta): `_ws_batch`
    restituisce `None` per il comando. Terzo guasto, terza dicitura -- non
    quella del rifiuto, non quella della forma inattesa."""
    risposte = [None] + [_msg([]) for _ in range(9)]
    with (
        patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)),
        caplog.at_level(logging.DEBUG, logger="hiris.app.proxy.ha_client"),
    ):
        _, non_disponibili = await _client().leggi_registri()
    assert "piani" in non_disponibili
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
# isolamento, un metodo diverso da `leggi_registri()` sopra (che chiede
# "config/config_entries/get_entries" direttamente nel proprio batch WS, non
# passando da `get_config_entries`). `get_config_entries` era gia' ORFANO
# DICHIARATO dal Task 11 (l'HealthMonitor che lo leggeva e' uscito):
# verificato che cade per costruzione (`AttributeError: 'HAClient' object
# has no attribute 'get_config_entries'`), poi cancellato insieme al metodo.
