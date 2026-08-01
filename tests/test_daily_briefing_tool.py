"""Slice 7 (Maggiordomo) Task 5: on-demand chat tool `daily_briefing`.

Unlike the scheduled `run_daily_briefing` (server.py Task 4), which gates
`allow_sensitive` on `LLMRouter.automatic_allows_sensitive()`, the dispatch()
call for `daily_briefing` gates `allow_sensitive` on the SAME two signals
`recall_knowledge` already uses: the per-agent `knowledge_allow_sensitive`
config and whether the current chat backend is `cloud`. Sensitive deadlines
are surfaced only when the agent config allows it AND the backend is local
(not cloud) -- fail-closed whenever either signal says otherwise (still
counted in bundle["counts"]["hidden_sensitive"] regardless of visibility).

Le batterie scariche NON sono piu' ricalcolate dal briefing: arrivano dalle
segnalazioni gia' prodotte dai controlli di salute del Brain (`check_low_battery`
-> `AdvisoryStore`), unica fonte di verita' sul fatto "questa batteria e'
scarica". Di conseguenza `detectors.battery.min_pct` non ha piu' effetto sul
briefing e senza AdvisoryStore il briefing non segnala batterie invece di
ricalcolarle. Le aperture (porte/finestre) continuano a venire dalla EntityCache.

It also returns the deterministic `render_briefing_template(bundle)` string
directly (no `compose_briefing`/LLM call): the chat model, already mid-reply,
narrates it itself. Read-only: no HA service call, no semaforo.
"""
from datetime import date, timedelta

import pytest

from hiris.app.brain.advisory_store import AdvisoryStore
from hiris.app.brain.health_checks import check_low_battery
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.watcher.policy import save_policy


class _FakeHA:
    pass


def _stato_batteria(eid: str, pct: str, nome: str) -> dict:
    """Voce di EntityCache.all_states() per un sensore di batteria."""
    return {"id": eid, "state": pct, "name": nome, "unit": "%",
            "domain": "sensor", "device_class": "battery"}


def _advisory_store_con_batteria(tmp_path, *, pct: str, nome: str) -> AdvisoryStore:
    """AdvisoryStore popolato dal controllo di salute vero, non a mano: le voci
    hanno la stessa forma che il Brain produce in esercizio."""
    store = AdvisoryStore(str(tmp_path / "advisory.db"))
    store.reconcile(
        check_low_battery([_stato_batteria("sensor.batteria_reale", pct, nome)]),
        {"low_battery"},
    )
    return store


class _FakeEntityCache:
    """Minimal stand-in for EntityCache.all_states() — a LIST of flat dicts,
    same shape used by tests/test_briefing_bundle.py."""

    def __init__(self, states: list[dict] | None = None) -> None:
        self._states = states or []

    def all_states(self) -> list[dict]:
        return list(self._states)


def _due(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_daily_briefing_returns_nonempty_text_with_obligation(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI in scadenza",
                    due_date=_due(2), sensitivity="normal")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert out.strip() != ""
    assert "TARI in scadenza" in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_hides_sensitive_obligation_fail_closed(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert "Cartella clinica riservata" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_no_knowledge_store_returns_friendly_fallback():
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=None, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert out.strip() != ""


@pytest.mark.asyncio
async def test_daily_briefing_never_raises_when_entity_cache_broken(tmp_path):
    class _BrokenCache:
        def all_states(self):
            raise RuntimeError("boom")

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Bolletta", due_date=_due(1),
                    sensitivity="normal")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_BrokenCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert "Bolletta" in out  # deadlines still surfaced despite home-status failure
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_shows_sensitive_when_allowed_and_local(tmp_path):
    """Fix A: sensitive deadlines are surfaced when BOTH the per-agent config
    allows them AND the chat backend is local (cloud=False) — mirrors
    recall_knowledge's allow_sensitive model."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=True, cloud=False,
    )

    assert "Cartella clinica riservata" in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_hides_sensitive_when_cloud_even_if_allowed(tmp_path):
    """Fix A: cloud=True fails closed even when the agent config allows
    sensitive content — locality gate wins."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=True, cloud=True,
    )

    assert "Cartella clinica riservata" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_hides_sensitive_when_not_allowed_even_if_local(tmp_path):
    """Fix A: local backend alone isn't enough — the agent config must also
    allow sensitive content, else it stays hidden."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=False, cloud=False,
    )

    assert "Cartella clinica riservata" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_riporta_le_batterie_dalle_segnalazioni(tmp_path):
    """Le batterie citate nel resoconto vengono dalle segnalazioni del Brain:
    con una segnalazione attiva il briefing la cita, pur avendo una cache
    entita' vuota (nessun ricalcolo possibile)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    advisory = _advisory_store_con_batteria(tmp_path, pct="7", nome="Termostato salotto")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache(),
                                 advisory_store=advisory)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert "Termostato salotto" in out
    assert "7" in out
    advisory.close()
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_non_ricalcola_le_batterie_dalla_cache(tmp_path):
    """Nessuna segnalazione attiva significa nessuna batteria nel resoconto,
    anche se la cache contiene un sensore scarico che il vecchio calcolo
    avrebbe segnalato. Le aperture, che restano di competenza della cache,
    continuano a comparire."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    advisory = AdvisoryStore(str(tmp_path / "advisory.db"))
    cache = _FakeEntityCache([
        _stato_batteria("sensor.batteria_fantasma", "3", "Batteria fantasma"),
        {"id": "binary_sensor.ingresso", "state": "on", "name": "Ingresso",
         "unit": "", "domain": "binary_sensor", "device_class": "door"},
    ])
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=cache,
                                 advisory_store=advisory)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert "Batteria fantasma" not in out
    assert "Ingresso" in out
    advisory.close()
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_senza_advisory_store_non_ricalcola(tmp_path):
    """Fonte unica anche quando manca: senza AdvisoryStore il briefing non
    segnala batterie invece di tornare a calcolarle dalla cache.

    L'apertura in cache e' l'ancora positiva: dimostra che il resoconto e'
    stato prodotto davvero e non e' il messaggio del ramo d'errore, che
    passerebbe la sola verifica di non-vuoto.
    """
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    cache = _FakeEntityCache([
        _stato_batteria("sensor.batteria_fantasma", "3", "Batteria fantasma"),
        {"id": "binary_sensor.ingresso", "state": "on", "name": "Ingresso",
         "unit": "", "domain": "binary_sensor", "device_class": "door"},
    ])
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=cache)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert "Ingresso" in out
    assert "Batteria fantasma" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_ignora_le_segnalazioni_messe_a_tacere(tmp_path):
    """Una segnalazione `dismissed` e' stata messa a tacere dall'utente: il
    briefing non deve farla riemergere.

    L'apertura in cache e' l'ancora positiva: senza, il messaggio del ramo
    d'errore soddisferebbe da solo la verifica negativa.
    """
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    advisory = _advisory_store_con_batteria(tmp_path, pct="7", nome="Termostato salotto")
    riga = advisory.list(status="open")[0]
    advisory.set_status(riga["id"], "dismissed")
    cache = _FakeEntityCache([
        {"id": "binary_sensor.ingresso", "state": "on", "name": "Ingresso",
         "unit": "", "domain": "binary_sensor", "device_class": "door"},
    ])
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=cache,
                                 advisory_store=advisory)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert "Ingresso" in out
    assert "Termostato salotto" not in out
    advisory.close()
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_ignora_la_soglia_salvata_nella_policy(tmp_path):
    """Cambiamento visibile dichiarato: `detectors.battery.min_pct` non governa
    piu' il briefing. Con soglia salvata a 50 e una batteria al 40% in cache,
    ma nessuna segnalazione attiva, il resoconto non cita nulla.

    L'apertura in cache e' l'ancora positiva: prova che il resoconto e' stato
    composto, non che il briefing e' esploso restituendo il testo di ripiego.
    """
    data_dir = str(tmp_path / "data")
    save_policy(data_dir, {"detectors": {"battery": {"min_pct": 50}}})
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    advisory = AdvisoryStore(str(tmp_path / "advisory.db"))
    cache = _FakeEntityCache([
        _stato_batteria("sensor.batteria_z", "40", "Batteria z"),
        {"id": "binary_sensor.ingresso", "state": "on", "name": "Ingresso",
         "unit": "", "domain": "binary_sensor", "device_class": "door"},
    ])
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=cache,
                                 advisory_store=advisory, data_dir=data_dir)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert "Ingresso" in out
    assert "Batteria z" not in out
    advisory.close()
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_shows_hidden_sensitive_count(tmp_path):
    """Fix C: when sensitive deadlines were withheld, the briefing text
    surfaces the hidden count as a trust signal."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=False, cloud=True,
    )

    assert "1" in out
    assert "riservat" in out.lower()
    store.close()


def test_daily_briefing_tool_declared_in_chat_tool_schema():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, DAILY_BRIEFING_TOOL_DEF

    names = [t["name"] for t in ALL_TOOL_DEFS]
    assert "daily_briefing" in names
    assert DAILY_BRIEFING_TOOL_DEF in ALL_TOOL_DEFS
    # No required inputs — invocable with an empty/optional object.
    assert DAILY_BRIEFING_TOOL_DEF["input_schema"].get("required", []) == []


def test_daily_briefing_not_in_evaluation_only_tools():
    """Read-only chat tool, same treatment as recall_knowledge/save_knowledge:
    not exposed to non-chat evaluation agents (no llm_router there either,
    and evaluation agents don't need an on-demand butler summary)."""
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS

    assert "daily_briefing" not in EVALUATION_ONLY_TOOLS
