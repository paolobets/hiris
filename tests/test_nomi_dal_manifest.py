"""Il nome di un'integrazione dal manifest (B-50, F1 della Chiusura,
13/10/2026).

Fino a quel giorno il nome era dedotto dallo slug (`hydrawise` ->
«Hydrawise», `zha` -> «Zha»): misurato sulla casa il 13/10/2026, per 12 delle
15 integrazioni del registro degli errori che il manifest conosce il nome
dedotto era diverso da quello vero. Il manifest (`manifest/list`) entra
nell'anagrafe come tabella `manifesti`, e le tre porte che nominano
un'integrazione da un logger -- la storia degli errori, il resoconto, lo
scope -- lo leggono da li' (`log_source.manifest_of`). Anche il nome di una libreria:
il manifest dichiara nei `loggers` i nomi con cui scrivono le librerie di
un'integrazione (N151b-1).
"""
from __future__ import annotations

import copy

import pytest

from hiris.app.home_space import house_history as hh
from hiris.app.home_space.log_source import (
    Manifest,
    integration_name,
    integration_of,
    manifest_of,
)
from hiris.app.home_space.reader import build_home_space
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.mind.view import _with_integration
from tests.test_history_tool import _COMPORTAMENTO, _history_house, _history_mirror
from tests.test_house_history import T0, _q
from tests.test_house_reads_module import _ha
from tests.test_knowledge_tools import _semina_casa

_NOMI = Manifest(
    names={"hydrawise": "Hunter Hydrawise", "zha": "Zigbee Home Automation",
           "homeassistant": "Home Assistant Core Integration",
           "alexa_devices": "Alexa Devices"},
    # `alexa_devices` porta `"loggers": ["aioamazondevices"]` nel suo
    # manifest (Core `2026.10.1`); il secondo e' un logger piu' lungo dello
    # stesso albero, per la regola del piu' lungo.
    loggers={"aioamazondevices": "alexa_devices", "aioamazondevices.ws": "zha"})


def test_il_nome_e_quello_del_manifest():
    """Mutazione ESEGUITA: in `integration_name` tolto il ramo `if slug in
    names` -- rossa («Hydrawise», il nome dedotto)."""
    assert integration_name("homeassistant.components.hydrawise", _NOMI) == "Hunter Hydrawise"
    assert integration_of("zha.core", _NOMI) == ("Zigbee Home Automation", "zha")


def test_il_nucleo_resta_home_assistant():
    """Un logger `homeassistant.helpers` e' il prodotto, non l'integrazione
    `homeassistant`, che il manifest chiama «Home Assistant Core
    Integration» (letto nel sorgente, tag `2026.10.1`,
    `components/homeassistant/manifest.json`)."""
    assert integration_name("homeassistant.helpers.entity", _NOMI) == "Home Assistant"


def test_la_riga_di_una_libreria_e_dell_integrazione_che_la_dichiara():
    """N151b-1: `loggers` del manifest. Il logger dichiarato fa da prefisso
    solo seguito da un punto (`aioamazondevicesx` non e' suo), e vince il piu'
    lungo. Mutazione ESEGUITA: in `log_source._owner` tolto il ramo dei
    `loggers` -- rossa («Aioamazondevices», `aioamazondevices`)."""
    assert integration_of("aioamazondevices.api", _NOMI) == ("Alexa Devices", "alexa_devices")
    assert integration_of("aioamazondevices", _NOMI) == ("Alexa Devices", "alexa_devices")
    assert integration_of("aioamazondevices.ws.client", _NOMI)[1] == "zha"
    assert integration_of("aioamazondevicesx", _NOMI)[1] == "aioamazondevicesx"


def test_cio_che_il_manifest_non_conosce_ripiega_sullo_slug():
    """Un logger che nessun manifest caricato dichiara, e un'integrazione non
    caricata (senza argomenti `manifest/list` rende le sole caricate)."""
    assert integration_of("pysenzapadre.client", _NOMI) == ("Pysenzapadre", "pysenzapadre")
    assert integration_name("custom_components.alarmo.x", Manifest()) == "Alarmo"


def test_un_logger_di_due_integrazioni_non_e_di_nessuna():
    """La riga non dice quale delle due l'abbia scritta. Mutazione ESEGUITA:
    in `manifest_of` tolto `if len(slugs) == 1` -- rossa (`uno` o `due`)."""
    manifest = manifest_of({"manifesti": [
        {"dominio": "uno", "nome": "Uno", "loggers": ["condivisa", "solo_uno"]},
        {"dominio": "due", "nome": "Due", "loggers": ["condivisa"]}]})
    assert manifest.loggers == {"solo_uno": "uno"}
    assert integration_of("condivisa.x", manifest) == ("Condivisa", "condivisa")


def test_i_nomi_si_leggono_dall_anagrafe():
    """La riga del manifest come Home Assistant la manda (le chiavi misurate
    il 13/10/2026) -> la tabella `manifesti` -> i nomi per slug. Una voce
    senza `domain` non entra; una senza nome non da' un nome."""
    anagrafe = build_home_space({"manifesti": [
        {"domain": "zha", "name": "Zigbee Home Automation", "codeowners": [],
         "documentation": None, "iot_class": "local_polling", "is_built_in": True,
         "loggers": ["zigpy", "bellows"], "overwrites_built_in": False,
         "requirements": []},
        {"domain": "senza_nome", "name": None, "loggers": None},
        {"name": "Senza dominio"}]})
    assert anagrafe["manifesti"] == [
        {"dominio": "zha", "nome": "Zigbee Home Automation", "loggers": ["zigpy", "bellows"]},
        {"dominio": "senza_nome", "nome": None, "loggers": []}]
    assert manifest_of(anagrafe) == Manifest(
        names={"zha": "Zigbee Home Automation"},
        loggers={"zigpy": "zha", "bellows": "zha"})
    assert manifest_of({}) == Manifest()


def test_gli_errori_di_alexa_devices_trovano_le_righe_della_libreria():
    """Il filtro per integrazione della storia degli errori (`error_rows`,
    `query.who.platform`) ritrova la riga scritta da `aioamazondevices`.
    Mutazione ESEGUITA: in `log_source._owner` tolto il ramo dei `loggers` --
    rossa (nessuna voce)."""
    registro = [{"name": "aioamazondevices.api", "level": "ERROR", "message": ["giu'"],
                 "source": ["api.py", 7], "timestamp": T0 - 60,
                 "first_occurred": T0 - 60, "count": 1}]
    voci = hh.error_rows(_q(cosa="errori", integrazione="alexa_devices"), registro, _NOMI)["voci"]
    assert [voce["integrazione"] for voce in voci] == [
        {"id": "alexa_devices", "nome": "Alexa Devices"}]


def _house_with_manifest():
    casa = copy.deepcopy(_history_house())
    casa["manifesti"] = [{"dominio": "hydrawise", "nome": "Hunter Hydrawise"}]
    return casa


@pytest.mark.asyncio
async def test_la_storia_degli_errori_nomina_col_manifest(tmp_path):
    """`history(cosa="errori")` dalla chat: il nome dell'integrazione e'
    quello dell'anagrafe, senza costruire la casa del turno (gli errori non
    la guardano). Mutazione ESEGUITA: in `ToolDispatcher._history`
    `manifest_of({})` al posto di `manifest_of(known)` -- rossa
    («Hydrawise»)."""
    store = _semina_casa(tmp_path, casa=_house_with_manifest(), comportamento=_COMPORTAMENTO)
    dispatcher = ToolDispatcher(store, None, cache=_history_mirror(), ha=_ha())
    answer = await dispatcher.dispatch("history", {"cosa": "errori"})
    assert answer["voci"][0]["integrazione"] == {"id": "hydrawise", "nome": "Hunter Hydrawise"}
    assert dispatcher._house is None


@pytest.mark.asyncio
async def test_senza_anagrafe_gli_errori_ripiegano_sullo_slug():
    answer = await ToolDispatcher(None, None, ha=_ha()).dispatch("history", {"cosa": "errori"})
    assert answer["voci"][0]["integrazione"] == {"id": "hydrawise", "nome": "Hydrawise"}


def test_lo_scope_nomina_col_manifest():
    """La rotta dello scope (`MindView.watching`) raggruppa i soggetti tecnici
    con la stessa regola."""
    lines = _with_integration([{"soggetto": "log:homeassistant.components.zha@x.py:1"},
                               {"soggetto": "log:aioamazondevices.api@api.py:7"}], _NOMI)
    assert [(line["integrazione"], line["nome"]) for line in lines] == [
        ("zha", "Zigbee Home Automation"), ("alexa_devices", "Alexa Devices")]


def test_il_resoconto_nomina_col_manifest():
    """Il resoconto della pagina (`report.as_page`): una voce di sistema senza
    nome lo prende dal `dominio`, col manifest."""
    from hiris.app.mind.report import as_page
    from tests.test_mind_report_page import _giudizi, _guasto, _resoconto
    page = as_page(_resoconto(_guasto("log:x@a.py:1", cosa="ERROR",
                                      dominio="homeassistant.components.zha.core")),
                   judgments=_giudizi(), manifest=_NOMI)
    assert page["cronaca"][0]["nome"] == "Zigbee Home Automation"


_REGISTRI = {"piani": [], "aree": [], "dispositivi": [], "entita": [], "etichette": [],
             "categorie": [], "integrazioni": [],
             "manifesti": [{"domain": "zha", "name": "Zigbee Home Automation"}]}


@pytest.mark.asyncio
async def test_la_pagina_non_conta_il_manifest(aiohttp_client, tmp_path):
    """Il manifest e' una tabella interna (`reader.INTERNAL_TABLES`): la home
    non ne fa una tessera (`ux-ui-specialist`, 13/10/2026: 163 integrazioni
    caricate contro 39 configurate, «ne ho 163 o 39?»). Mutazione ESEGUITA:
    `conteggi` di nuovo su tutta l'anagrafe -- rossa."""
    from aiohttp import web

    from hiris.app.api.handlers_home_space import handle_get_home_space
    from hiris.app.home_space.reader import HomeSpace
    store = HomeSpace(str(tmp_path))
    store.hold_registries(copy.deepcopy(_REGISTRI))
    app = web.Application()
    app["home_space_store"] = store
    app.router.add_get("/api/home-space", handle_get_home_space)
    body = await (await (await aiohttp_client(app)).get("/api/home-space")).json()
    assert "manifesti" not in body["conteggi"] and "aree" in body["conteggi"]
    assert manifest_of(store.read()).names == {"zha": "Zigbee Home Automation"}


def test_un_manifest_caduto_tiene_i_nomi_e_non_si_dichiara(tmp_path):
    """Un `manifest/list` che non risponde: i nomi restano quelli di prima
    (come ogni tabella caduta, A-10), e la pagina non dichiara un registro
    caduto che non mostra. Mutazione ESEGUITA: tolto il filtro delle tabelle
    interne da `hold_registries` -- rossa (`["manifesti"]`)."""
    from hiris.app.home_space.reader import HomeSpace
    store = HomeSpace(str(tmp_path))
    store.hold_registries(copy.deepcopy(_REGISTRI))
    store.hold_registries({**copy.deepcopy(_REGISTRI), "manifesti": []}, ["manifesti"])
    assert store.unavailable() == []
    assert manifest_of(store.read()).names == {"zha": "Zigbee Home Automation"}
