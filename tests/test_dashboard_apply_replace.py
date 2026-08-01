import pytest
from hiris.app.tools.config_tools import apply_ha_config
from hiris.app.proxy.dashboard_backups import latest_backup


class FakeHA:
    def __init__(self, current=None, save_result=None):
        self.current = current if current is not None else {"views": [{"title": "VECCHIA"}]}
        self.save_result = save_result or {"ok": True, "url_path": "casa-mia"}
        self.saved = None
        self.created = None
        self.order = []

    async def get_lovelace_config(self, url_path):
        self.order.append("read")
        return self.current

    async def save_dashboard_config(self, url_path, config):
        self.order.append("save")
        self.saved = (url_path, config)
        return self.save_result

    async def create_dashboard(self, slug, name, config, icon=None, show_in_sidebar=True):
        self.created = (slug, name, config)
        return {"ok": True, "url_path": slug}


NEW = {"views": [{"title": "NUOVA"}]}


@pytest.mark.asyncio
async def test_mode_create_still_calls_create_dashboard(tmp_path):
    ha = FakeHA()
    out = await apply_ha_config(
        ha, {"kind": "dashboard", "slug": "casa-mia", "name": "Casa", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert out.get("ok") is True
    assert ha.created is not None and ha.saved is None


@pytest.mark.asyncio
async def test_mode_replace_saves_snapshot_before_writing(tmp_path):
    ha = FakeHA(current={"views": [{"title": "VECCHIA"}]})
    out = await apply_ha_config(
        ha,
        {"kind": "dashboard", "mode": "replace", "slug": "casa-mia", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert out.get("ok") is True
    assert ha.saved == ("casa-mia", NEW)
    assert ha.created is None, "replace non deve creare una nuova plancia"
    # lo snapshot deve contenere la config PRECEDENTE
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "VECCHIA"}]}
    # e deve essere stato letto PRIMA di scrivere
    assert ha.order == ["read", "save"]


@pytest.mark.asyncio
async def test_replace_aborts_when_current_config_unreadable(tmp_path):
    ha = FakeHA(current={"error": "config dashboard non leggibile"})
    out = await apply_ha_config(
        ha,
        {"kind": "dashboard", "mode": "replace", "slug": "casa-mia", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert "error" in out
    assert ha.saved is None, "mai sovrascrivere senza aver messo al sicuro lo stato precedente"
    assert latest_backup(str(tmp_path), "casa-mia") is None


@pytest.mark.asyncio
async def test_replace_rejects_unknown_mode(tmp_path):
    ha = FakeHA()
    out = await apply_ha_config(
        ha,
        {"kind": "dashboard", "mode": "cancella", "slug": "casa-mia", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert "error" in out
    assert ha.saved is None and ha.created is None


@pytest.mark.asyncio
async def test_replace_without_data_dir_still_writes_but_warns(tmp_path):
    """data_dir assente (chiamanti legacy): si applica comunque, senza snapshot."""
    ha = FakeHA()
    out = await apply_ha_config(
        ha, {"kind": "dashboard", "mode": "replace", "slug": "casa-mia", "ha_config": NEW},
    )
    assert out.get("ok") is True
    assert ha.saved == ("casa-mia", NEW)
