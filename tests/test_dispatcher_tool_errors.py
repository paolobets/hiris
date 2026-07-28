"""Bug fix: dispatch() built kwargs for several tool branches (notably
create_automation_proposal) from bare inputs["..."] access. When the LLM's
tool call omitted a required field, that raised a KeyError *before* the
tool's own validation ever ran -- and the blanket `except Exception` at the
bottom of dispatch() swallowed it into the generic, unhelpful
"Strumento '...' non riuscito. Riprova più tardi." message, with the
proposal never persisted.

These tests pin the fix: a missing required field must come back as a
specific, actionable error naming the field -- not the generic fallback --
for create_automation_proposal (explicit up-front validation) AND for
sibling branches sharing the same bare-access pattern (generic KeyError
handling in dispatch()). A fully-populated call must still succeed."""
import pytest
from hiris.app.proxy.proposal_store import ProposalStore
from hiris.app.tools.dispatcher import ToolDispatcher

_GENERIC_MSG_FRAGMENT = "non riuscito"


class _FakeHA:
    async def call_service(self, d, s, data):
        return {"ok": True}


@pytest.fixture
def store(tmp_path):
    s = ProposalStore(db_path=str(tmp_path / "proposals.db"), scheduler=None)
    yield s
    s.close()


def _dispatcher(store):
    return ToolDispatcher(ha_client=_FakeHA(), notify_config={}, proposal_store=store)


def _proposal_args(**overrides):
    base = {
        "type": "ha_automation",
        "name": "Spegni luci salotto",
        "description": "Spegne le luci del salotto alle 23:00",
        "config": {"alias": "Spegni luci salotto", "trigger": [], "action": []},
        "routing_reason": "Trigger orario semplice -- Layer 1 e' sufficiente",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_missing_routing_reason_returns_specific_error(store):
    inputs = _proposal_args()
    del inputs["routing_reason"]
    d = _dispatcher(store)

    result = await d.dispatch("create_automation_proposal", inputs, chatbot_id="hiris-default")

    assert "error" in result
    assert "routing_reason" in result["error"]
    assert _GENERIC_MSG_FRAGMENT not in result["error"]
    # and genuinely nothing was persisted
    assert await store.list() == []


@pytest.mark.asyncio
async def test_missing_config_returns_specific_error(store):
    inputs = _proposal_args()
    del inputs["config"]
    d = _dispatcher(store)

    result = await d.dispatch("create_automation_proposal", inputs, chatbot_id="hiris-default")

    assert "error" in result
    assert "config" in result["error"]
    assert _GENERIC_MSG_FRAGMENT not in result["error"]
    assert await store.list() == []


@pytest.mark.asyncio
async def test_all_required_fields_present_still_creates_proposal(store):
    """Guard against over-tightening: a fully-populated call must still work."""
    inputs = _proposal_args()
    d = _dispatcher(store)

    result = await d.dispatch("create_automation_proposal", inputs, chatbot_id="hiris-default")

    assert "error" not in result
    assert result["status"] == "pending"
    saved = await store.get(result["proposal_id"])
    assert saved is not None
    assert saved["name"] == "Spegni luci salotto"


@pytest.mark.asyncio
async def test_sibling_branch_missing_field_returns_specific_error(store):
    """send_notification builds its call from bare inputs["channel"] the same
    way create_automation_proposal did -- the shared dispatch()-level KeyError
    handler must catch it too, not just the one branch that got a bespoke
    up-front check."""
    d = _dispatcher(store)

    result = await d.dispatch("send_notification", {"message": "ciao"}, chatbot_id="hiris-default")

    assert "error" in result
    assert "channel" in result["error"]
    assert _GENERIC_MSG_FRAGMENT not in result["error"]
