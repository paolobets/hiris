import pytest
from hiris.app.tools.dashboard_tools import propose_dashboard


class FakeStore:
    def __init__(self):
        self.saved = None

    async def save(self, record):
        self.saved = record
        return "p42"


CFG = {"views": [{"title": "Home", "cards": []}]}


@pytest.mark.asyncio
async def test_propose_create_builds_ha_dashboard_proposal():
    store = FakeStore()
    out = await propose_dashboard(store, "create", "casa-mia", CFG, "richiesto in chat", title="Casa Mia")
    assert out["proposal_id"] == "p42"
    rec = store.saved
    assert rec["type"] == "ha_dashboard"
    assert rec["config"]["kind"] == "dashboard"
    assert rec["config"]["mode"] == "create"
    assert rec["config"]["slug"] == "casa-mia"
    assert rec["config"]["name"] == "Casa Mia"
    assert rec["config"]["ha_config"] == CFG


@pytest.mark.asyncio
async def test_propose_replace_does_not_require_title():
    store = FakeStore()
    out = await propose_dashboard(store, "replace", "casa-mia", CFG, "riorganizzo")
    assert "proposal_id" in out
    assert store.saved["config"]["mode"] == "replace"


@pytest.mark.asyncio
async def test_create_without_title_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "create", "casa-mia", CFG, "motivo")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_invalid_url_path_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "create", "casamia", CFG, "motivo", title="X")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_invalid_mode_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "cancella", "casa-mia", CFG, "motivo", title="X")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_config_without_views_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "replace", "casa-mia", {"nope": 1}, "motivo")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_store_failure_returns_generic_error():
    class Boom:
        async def save(self, record):
            raise RuntimeError("/data/secret/path.db is locked")
    out = await propose_dashboard(Boom(), "replace", "casa-mia", CFG, "motivo")
    assert "error" in out
    assert "secret" not in out["error"], "mai fare echo del dettaglio interno"
