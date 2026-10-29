"""Il tetto di turni al giorno per chi non amministra (Fase S, S.2, 29/10/2026).

Scelta del proprietario: un valore solo per chi non amministra, in turni al
giorno, spento di fabbrica. Si contano i turni nell'archivio dei consumi
(`UsageStore.count_turns`), chat e promesse insieme, nel giorno della casa.
Chi amministra non ha tetto.
"""
from __future__ import annotations

import json
import os

import pytest
import pytest_asyncio

from hiris.app.agent.runner import _turn_subject
from hiris.app.api.handlers_settings import Rejection, validate
from hiris.app.chat_settings import CHAT_SETTINGS_KEY, ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.chat_thread import ChatThread, new_subject
from hiris.app.home_space.historian import day_boundaries, local_date
from hiris.app.keeper import exchange
from hiris.app.steering import daily_turns_refusal
from hiris.app.usage.store import USAGE_KEY, UsageStore
from tests.test_admission import _compose, _persona

MARTA = new_subject("persona", ident="u-marta", nome="Marta")
PAOLO = new_subject("persona", ident="u-admin", nome="Paolo")
#: Mezzogiorno UTC del 29/10/2026: lontano da ogni mezzanotte.
ADESSO = 1_793_275_200.0


def _turno(usage, chi, ts, specie="chat"):
    usage.log_turn(species=specie, provider="claude", model="m", channel="catena",
                   duration_ms=1, iterations=1, tools=[], outcome="ok", now=ts,
                   subject=chi)


@pytest.fixture
def usage(tmp_path):
    store = UsageStore(str(tmp_path / "consumi.db"))
    yield store
    store.close()


class _App(dict):
    pass


def _app(usage, tetto):
    app = _App()
    app[USAGE_KEY] = usage
    from hiris.app.live_value import LiveValue
    app[CHAT_SETTINGS_KEY] = LiveValue(ChatSettings(daily_turn_cap=tetto))
    return app


def test_si_contano_i_turni_di_chi_li_ha_aperti_nel_giorno(usage):
    """Il giorno della casa ha due bordi: il primo istante dentro, quello di
    domani fuori. Mutazione ESEGUITA (R224-4): la condizione `ts < ?` tolta
    dalla query di `count_turns` -- rossa, si contano anche i turni di
    domani."""
    since, until = day_boundaries("2026-10-29", None)
    _turno(usage, MARTA, ADESSO)
    _turno(usage, MARTA, ADESSO + 60, specie="promessa")
    _turno(usage, PAOLO, ADESSO)
    _turno(usage, MARTA, since - 1)
    _turno(usage, MARTA, until)
    _turno(usage, MARTA, until + 3600)
    assert usage.count_turns(MARTA, since=since, until=until) == 2
    assert usage.count_turns(PAOLO, since=since, until=until) == 1


def test_il_tetto_pieno_ferma_chi_non_amministra(usage):
    """Mutazione ESEGUITA: `turns >= limit` diventato `turns > limit` -- rossa,
    il terzo turno passa con il tetto a due."""
    _turno(usage, MARTA, ADESSO)
    app = _app(usage, 2)
    assert daily_turns_refusal(app, MARTA, administers=False, now=ADESSO) is None
    _turno(usage, MARTA, ADESSO + 1)
    assert daily_turns_refusal(app, MARTA, administers=False, now=ADESSO) == {
        "turns": 2, "limit": 2}


def test_chi_amministra_e_il_tetto_spento_non_si_fermano(usage):
    for i in range(5):
        _turno(usage, MARTA, ADESSO + i)
    assert daily_turns_refusal(_app(usage, 2), MARTA, administers=True, now=ADESSO) is None
    assert daily_turns_refusal(_app(usage, 0), MARTA, administers=False, now=ADESSO) is None


def test_di_fabbrica_il_tetto_e_spento():
    assert ChatSettings().daily_turn_cap == 0


def test_l_impostazione_si_salva_si_rilegge_e_si_valida(tmp_path):
    impostazioni = validate(ChatSettings(), {"daily_turn_cap": 30})
    assert impostazioni.daily_turn_cap == 30
    impostazioni.save(str(tmp_path))
    assert ChatSettings.load(str(tmp_path)).daily_turn_cap == 30
    with open(os.path.join(str(tmp_path), "impostazioni_chat.json"), encoding="utf-8") as f:
        assert json.load(f)["daily_turn_cap"] == 30
    with pytest.raises(Rejection):
        validate(ChatSettings(), {"daily_turn_cap": -1})


def test_un_turno_del_ponte_di_una_promessa_porta_chi_l_ha_chiesta():
    """Senza, il tetto non conterebbe le promesse servite dal ponte. Mutazione
    ESEGUITA: il ramo `PROMISE_SPECIES` tolto da `_turn_subject` -- rossa."""
    job = {"kind": "promessa", "thread": ChatThread("persona:u-marta", "pannello")}
    assert _turn_subject(job)["id"] == "u-marta"
    assert _turn_subject({"kind": "chat", "context": {"soggetto": MARTA}}) == MARTA
    assert _turn_subject({"kind": "analista"}) is None


@pytest.mark.asyncio
async def test_una_promessa_di_chi_ha_il_tetto_pieno_non_parte(usage, monkeypatch):
    """Il turno di una promessa `chiedi` si ferma prima di ogni strada, col
    perche'. Mutazione ESEGUITA: il controllo tolto da `interpreta_promise`
    -- rossa, la promessa prosegue verso la partenza (che su questa app senza
    modelli solleva)."""
    import time

    async def soffitto_utente(app, promise):
        from hiris.app.api.soffitto import consente
        return MARTA, consente(MARTA, ruolo="utente")

    monkeypatch.setattr(exchange, "promise_ceiling", soffitto_utente)
    _turno(usage, MARTA, time.time())
    esito = await exchange.interpreta_promise(_app(usage, 1), {"id": 1, "thread": None})
    assert "1 al giorno" in esito["errore"]
    assert "domani" in esito["errore"]


@pytest_asyncio.fixture
async def casa(aiohttp_client, tmp_path, monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    app = _compose(tmp_path, access=True)
    app[CHAT_SETTINGS_KEY].set(ChatSettings(daily_turn_cap=1))
    app[USAGE_KEY] = UsageStore(os.path.join(str(tmp_path), "consumi.db"))
    client = await aiohttp_client(app)
    yield client
    app[USAGE_KEY].close()
    close_all_stores()


@pytest.mark.asyncio
async def test_la_chat_risponde_429_a_chi_ha_il_tetto_pieno(casa):
    """Mutazione ESEGUITA: il controllo tolto da `handle_chat` -- rossa, la
    richiesta va avanti."""
    import time
    _turno(casa.app[USAGE_KEY], MARTA, time.time())
    risposta = await casa.post("/api/chat", json={"message": "ciao"},
                               headers=_persona("u-marta"))
    assert risposta.status == 429
    corpo = await risposta.json()
    assert corpo["error"] == "daily_turns_reached"
    assert (corpo["turns"], corpo["limit"]) == (1, 1)


@pytest.mark.asyncio
async def test_la_chat_non_ferma_chi_amministra(casa):
    import time
    _turno(casa.app[USAGE_KEY], PAOLO, time.time())
    risposta = await casa.post("/api/chat", json={"message": "ciao"},
                               headers=_persona("u-admin"))
    assert risposta.status != 429


@pytest.mark.asyncio
async def test_il_turno_di_una_promessa_sulla_catena_si_conta_per_chi_l_ha_chiesta(usage):
    """Il tetto conta le promesse sulla catena solo se il turno porta chi l'ha
    chiesta fino all'archivio dei consumi. Mutazione ESEGUITA (R224-4):
    `chain_turn(..., soggetto=None)` in `interpreta_promise` -- rossa, il
    turno finisce sotto `nessuno:-` e Marta non ne ha aperto nessuno."""
    from hiris.app.llm_router import LLM_ROUTER_KEY
    from hiris.app.startup import live_values
    from tests._runner_finto import RunnerFinto

    async def _concludi(_runner, **kwargs):
        await kwargs["dispatcher"].dispatch(
            "conclude", {"avvisare": False, "testo": "tutto a posto"})

    app = {**live_values(), LLM_ROUTER_KEY: RunnerFinto(turno=_concludi),
           USAGE_KEY: usage}
    promessa = {"id": "p1", "frase": "fra un'ora guarda la caldaia",
                "domanda": "e' accesa?", "istantanea": [],
                "thread": ChatThread("persona:u-marta", "pannello")}
    esito = await exchange.interpreta_promise(app, promessa)
    assert esito == {"avvisare": False, "testo": "tutto a posto"}, esito
    import time
    since, until = day_boundaries(local_date(time.time(), None).isoformat(), None)
    assert usage.count_turns(MARTA, since=since, until=until) == 1
