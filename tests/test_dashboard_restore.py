import json

import pytest

from hiris.app.api.handlers_dashboards import (
    handle_restore_dashboard, handle_list_dashboard_backups,
)
from hiris.app.proxy.dashboard_backups import save_backup
from hiris.app.proxy.ha_client import HAClient


class FakeHA:
    def __init__(self, result=None):
        self.result = result or {"ok": True, "url_path": "casa-mia"}
        self.saved = None

    async def save_dashboard_config(self, url_path, config):
        self.saved = (url_path, config)
        return self.result


class FakeRequest:
    def __init__(self, app, url_path="casa-mia"):
        self.app = app
        self.match_info = {"url_path": url_path}


@pytest.mark.asyncio
async def test_restore_reapplies_latest_snapshot(tmp_path):
    old = {"views": [{"title": "VECCHIA"}]}
    save_backup(str(tmp_path), "casa-mia", old)
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", old)


@pytest.mark.asyncio
async def test_restore_without_backup_is_404(tmp_path):
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 404
    assert ha.saved is None


@pytest.mark.asyncio
async def test_restore_of_strategy_snapshot_succeeds(tmp_path):
    """Sequenza reale che si rompeva: replace su una plancia a strategia ->
    snapshot salvato -> Annulla -> save_dashboard_config con uno snapshot senza
    'views'. Qui usiamo il VERO HAClient (solo il WS e' finto) perche' il bug
    stava nella sua validazione, non nell'handler."""
    old = {"strategy": {"type": "areas"}}
    save_backup(str(tmp_path), "casa-mia", old)
    calls = []

    async def fake_ws(cmd, payload=None):
        calls.append((cmd, payload or {}))
        return {"success": True}

    ha = HAClient.__new__(HAClient)   # niente __init__: serve solo il WS
    ha._ws_command = fake_ws
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert calls == [("lovelace/config/save",
                      {"url_path": "casa-mia", "config": old})]


@pytest.mark.asyncio
async def test_restore_reports_ha_failure(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": []})
    ha = FakeHA(result={"error": "boom"})
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 502


@pytest.mark.asyncio
async def test_restore_di_snapshot_legacy_senza_istante(tmp_path):
    """Uno snapshot scritto prima dell'introduzione dell'istante resta
    ripristinabile: 'istante sconosciuto', non errore."""
    import os
    old = {"views": [{"title": "VECCHIA"}]}
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), "w", encoding="utf-8") as fh:
        json.dump({"casa-mia": [{"config": old}]}, fh)
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", old)


# --- endpoint di elenco -----------------------------------------------------

def _corpo(resp):
    return json.loads(resp.body)


@pytest.mark.asyncio
async def test_elenco_restituisce_i_metadati(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    resp = await handle_list_dashboard_backups(FakeRequest({"data_dir": str(tmp_path)}))
    assert resp.status == 200
    corpo = _corpo(resp)
    assert len(corpo["backups"]) == 1
    voce = corpo["backups"][0]
    assert voce["url_path"] == "casa-mia"
    assert voce["count"] == 1
    assert isinstance(voce["saved_at"], str)


@pytest.mark.asyncio
async def test_elenco_non_espone_le_config(tmp_path):
    """Gli snapshot contengono le plance dell'utente: l'elenco e' metadati e basta."""
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "SEGRETO"}]})
    resp = await handle_list_dashboard_backups(FakeRequest({"data_dir": str(tmp_path)}))
    assert "SEGRETO" not in resp.body.decode("utf-8")
    assert set(_corpo(resp)["backups"][0]) == {"url_path", "saved_at", "count"}


@pytest.mark.asyncio
async def test_elenco_vuoto_senza_snapshot(tmp_path):
    resp = await handle_list_dashboard_backups(FakeRequest({"data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert _corpo(resp) == {"backups": []}


@pytest.mark.asyncio
async def test_elenco_senza_data_dir_e_503(tmp_path):
    resp = await handle_list_dashboard_backups(FakeRequest({}))
    assert resp.status == 503


@pytest.mark.asyncio
async def test_le_due_rotte_non_si_sovrappongono():
    """La rotta di elenco non deve essere catturata da quella di restore (e
    viceversa): si verifica sul router reale, non a occhio."""
    from aiohttp.test_utils import make_mocked_request
    from hiris.app.server import create_app
    app = create_app()
    elenco = await app.router.resolve(
        make_mocked_request("GET", "/api/dashboards/backups", app=app))
    assert elenco.handler is handle_list_dashboard_backups
    restore = await app.router.resolve(
        make_mocked_request("POST", "/api/dashboards/casa-mia/restore", app=app))
    assert restore.handler is handle_restore_dashboard
