import pytest
from aiohttp import web

from hiris.app.api.handlers_gateway_policy import (
    GATEWAY_CATEGORIES,
    READ_TOOLS,
    PROPOSE_TOOLS,
    apply_saved_policy,
    derive_execute_policy,
    handle_get_gateway_policy,
    handle_save_gateway_policy,
    load_categories,
    save_categories,
)


def test_derive_empty_is_read_only():
    pol = derive_execute_policy({})
    assert "get_home_status" in pol["tools"]
    assert "call_ha_service" not in pol["tools"]
    assert pol["allowed_services"] is None
    assert pol["allowed_entities"] is None


def test_derive_green_light_adds_call_service_and_glob():
    pol = derive_execute_policy({"light": "green"})
    assert "call_ha_service" in pol["tools"]
    assert pol["allowed_services"] == ["light.*"]
    assert pol["allowed_entities"] == ["light.*"]


def test_derive_yellow_red_requestable_but_held():
    pol = derive_execute_policy({"lock": "red", "climate": "yellow"})
    # requestable (the handler routes them to approval)...
    assert "call_ha_service" in pol["tools"]
    # ...but NOT directly executable (not in the green whitelist)
    assert pol["allowed_services"] is None
    # the tiers map drives the routing
    assert pol["tiers"] == {"lock": "red", "climate": "yellow"}


def test_derive_mixed_tiers():
    pol = derive_execute_policy({"light": "green", "climate": "yellow", "lock": "red", "fan": "off"})
    assert pol["allowed_services"] == ["light.*"]          # only green is whitelisted
    assert pol["tiers"] == {"light": "green", "climate": "yellow", "lock": "red"}


def test_save_load_roundtrip_and_validation(tmp_path):
    save_categories(str(tmp_path), {"light": "green", "bogus": "green", "lock": "weird"})
    cats = load_categories(str(tmp_path))
    assert cats == {"light": "green"}      # invalid id and invalid level dropped


def test_load_missing_is_empty(tmp_path):
    assert load_categories(str(tmp_path)) == {}


def test_apply_saved_policy_overrides(tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["execute_policy"] = {"tools": [], "allowed_entities": None, "allowed_services": None}
    save_categories(str(tmp_path), {"scene": "green"})
    apply_saved_policy(app)
    assert "call_ha_service" in app["execute_policy"]["tools"]
    assert app["execute_policy"]["allowed_services"] == ["scene.*"]


def _app(tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["execute_policy"] = {"tools": [], "allowed_entities": None, "allowed_services": None}
    app.router.add_get("/api/gateway/policy", handle_get_gateway_policy)
    app.router.add_post("/api/gateway/policy", handle_save_gateway_policy)
    return app


@pytest.mark.asyncio
async def test_get_returns_categories(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/api/gateway/policy")
    assert resp.status == 200
    data = await resp.json()
    assert len(data["categories"]) == len(GATEWAY_CATEGORIES)
    assert data["levels"] == {}


# ---------------------------------------------------------------------------
# S-1/M-7 (review indipendente su bee3ab1): il frontend duplicava a mano la
# denylist DANGEROUS_DOMAINS (con "garage_door", che non e' nemmeno una
# categoria valida qui sotto -- vedi GATEWAY_CATEGORIES) senza alcuna difesa
# contro la deriva da security/semaphore.py. Il flag "dangerous" per
# categoria e' ora calcolato qui, un'unica fonte, stesso principio gia' in
# uso per handle_autonomy_summary.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_categories_flag_dangerous_domains(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/api/gateway/policy")
    data = await resp.json()
    by_id = {c["id"]: c for c in data["categories"]}
    assert by_id["lock"]["dangerous"] is True
    assert by_id["alarm_control_panel"]["dangerous"] is True
    assert by_id["cover"]["dangerous"] is True
    assert by_id["siren"]["dangerous"] is True
    assert by_id["light"]["dangerous"] is False
    assert "garage_door" not in by_id, (
        "garage_door non e' una categoria valida (GATEWAY_CATEGORIES) -- "
        "un frontend che la nomina parla di qualcosa che l'utente non trova mai")


@pytest.mark.asyncio
async def test_post_saves_and_updates_execute_policy(aiohttp_client, tmp_path):
    app = _app(tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post("/api/gateway/policy", json={"levels": {"light": "green"}})
    assert resp.status == 200
    data = await resp.json()
    assert data["levels"] == {"light": "green"}
    assert "call_ha_service" in data["execute_policy"]["tools"]
    # persisted: a fresh GET reflects it
    resp2 = await client.get("/api/gateway/policy")
    assert (await resp2.json())["levels"] == {"light": "green"}


def test_get_history_is_a_read_tool():
    assert "get_history" in READ_TOOLS


def test_derived_policy_exposes_get_history():
    pol = derive_execute_policy({"light": "green"})
    assert "get_history" in pol["tools"]


def test_get_automation_config_is_read_tool():
    assert "get_automation_config" in READ_TOOLS


def test_propose_tools_always_in_derived_policy():
    pol = derive_execute_policy({})          # no categories at all
    for t in ("create_automation_proposal", "save_knowledge", "list_tasks", "cancel_task"):
        assert t in pol["tools"]
    assert "call_ha_service" not in pol["tools"]   # not actionable -> no action tool
    assert "create_task" not in pol["tools"]       # create_task needs a green domain to constrain it


def test_create_task_exposed_only_when_actionable():
    assert "create_task" not in derive_execute_policy({})["tools"]
    assert "create_task" not in derive_execute_policy({"light": "off"})["tools"]
    pol = derive_execute_policy({"light": "green"})
    assert "create_task" in pol["tools"]
    assert pol["allowed_services"] == ["light.*"]   # so the task's actions are constrained


def test_green_category_still_adds_call_service():
    pol = derive_execute_policy({"light": "green"})
    assert "call_ha_service" in pol["tools"]
    assert "create_automation_proposal" in pol["tools"]


# ---------------------------------------------------------------------------
# Per-entity override tests (TDD: added before implementation)
# ---------------------------------------------------------------------------
from hiris.app.api.handlers_gateway_policy import effective_tier, load_entities


def test_effective_tier_entity_overrides_domain():
    tiers = {"switch": "green"}; ent = {"switch.gate": "off", "switch.lamp": "red"}
    assert effective_tier("switch.gate", tiers, ent) == "off"      # override beats green
    assert effective_tier("switch.lamp", tiers, ent) == "red"
    assert effective_tier("switch.other", tiers, ent) == "green"   # falls back to domain
    assert effective_tier("fan.x", tiers, ent) == "off"            # unconfigured -> off


def test_derive_includes_green_entity_in_off_domain():
    pol = derive_execute_policy({"switch": "off"}, {"switch.lamp": "green"})
    assert "switch.lamp" in (pol["allowed_entities"] or [])
    assert "switch.*" in (pol["allowed_services"] or [])
    assert pol["entity_tiers"]["switch.lamp"] == "green"
    assert "call_ha_service" in pol["tools"]                       # green entity -> actionable


def test_derive_entity_off_override_recorded():
    pol = derive_execute_policy({"switch": "green"}, {"switch.gate": "off"})
    assert pol["entity_tiers"]["switch.gate"] == "off"
    assert "switch.*" in (pol["allowed_entities"] or [])           # domain still green-globbed


def test_save_and_load_entities_roundtrip(tmp_path):
    d = str(tmp_path)
    save_categories(d, {"switch": "green"}, entities={"switch.gate": "off", "bad id": "green"})
    ents = load_entities(d)
    assert ents == {"switch.gate": "off"}                          # malformed id dropped


# ---------------------------------------------------------------------------
# handle_autonomy_summary: backend-authoritative Autonomia summary (review
# finding, SP-4 Fase B Task 4) -- the Chatbot editor used to recompute the
# tier client-side WITHOUT the DANGEROUS_DOMAINS denylist, so it could show
# "green" for e.g. cover.* even though gate_action always deny_dangerous it.
# The endpoint now uses security.semaphore.summarize_autonomy, the SAME
# function real enforcement is built from -- no drift possible.
# ---------------------------------------------------------------------------
from hiris.app.api.handlers_gateway_policy import handle_autonomy_summary


def _summary_app(tmp_path):
    app = _app(tmp_path)
    app.router.add_post("/api/gateway/autonomy-summary", handle_autonomy_summary)
    return app


@pytest.mark.asyncio
async def test_autonomy_summary_dangerous_domain_never_green_even_if_configured_green(aiohttp_client, tmp_path):
    save_categories(str(tmp_path), {"cover": "green"})
    app = _summary_app(tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post("/api/gateway/autonomy-summary", json={"entities": ["cover.living"]})
    assert resp.status == 200
    data = await resp.json()
    assert data["counts"] == {"green": 0, "yellow": 0, "red": 0, "off": 0, "dangerous": 1}
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_autonomy_summary_mixed_scope(aiohttp_client, tmp_path):
    save_categories(str(tmp_path), {"light": "green", "switch": "red"}, entities={"fan.y": "off"})
    app = _summary_app(tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post("/api/gateway/autonomy-summary", json={
        "entities": ["light.kitchen", "switch.x", "cover.living", "fan.y"],
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["counts"] == {"green": 1, "yellow": 0, "red": 1, "off": 1, "dangerous": 1}
    assert data["total"] == 4


@pytest.mark.asyncio
async def test_autonomy_summary_rejects_non_list_entities(aiohttp_client, tmp_path):
    app = _summary_app(tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post("/api/gateway/autonomy-summary", json={"entities": "not-a-list"})
    assert resp.status == 400
