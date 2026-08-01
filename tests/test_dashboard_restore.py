import json

import pytest

from hiris.app.api.handlers_dashboards import (
    handle_restore_dashboard, handle_list_dashboard_backups,
)
from hiris.app.proxy.dashboard_backups import save_backup, latest_backup, list_backups
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


# --- il ripristino consuma lo snapshot --------------------------------------

@pytest.mark.asyncio
async def test_restore_riuscito_consuma_lo_snapshot(tmp_path):
    """Dopo il ripristino lo snapshot E' lo stato corrente della plancia:
    continuare a elencarlo significherebbe offrire un "annulla" a vuoto, e
    dopo un refresh l'utente si ritroverebbe a poter annullare una cosa
    gia' annullata."""
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "VECCHIA"}]})
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert list_backups(str(tmp_path)) == []
    elenco = await handle_list_dashboard_backups(FakeRequest({"data_dir": str(tmp_path)}))
    assert _corpo(elenco) == {"backups": []}


@pytest.mark.asyncio
async def test_restore_consuma_solo_lo_snapshot_riapplicato(tmp_path):
    """Le versioni ancora piu' vecchie restano: un secondo Annulla deve poter
    tornare piu' indietro."""
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "VECCHIA"}]})
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "ATTUALE"}]})
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", {"views": [{"title": "ATTUALE"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "VECCHIA"}]}


@pytest.mark.asyncio
async def test_restore_fallito_non_consuma_lo_snapshot(tmp_path):
    """Se HA rifiuta la scrittura il ripristino non e' avvenuto: lo snapshot
    deve restare, altrimenti il tentativo fallito brucia l'unica via di
    ritorno e l'utente non puo' nemmeno riprovare."""
    old = {"views": [{"title": "VECCHIA"}]}
    save_backup(str(tmp_path), "casa-mia", old)
    ha = FakeHA(result={"error": "boom"})
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 502
    assert latest_backup(str(tmp_path), "casa-mia") == old
    assert [v["url_path"] for v in list_backups(str(tmp_path))] == ["casa-mia"]


@pytest.mark.asyncio
async def test_restore_non_tocca_gli_snapshot_delle_altre_plance(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "altra-casa", {"views": [{"title": "B"}]})
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": FakeHA(), "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert [v["url_path"] for v in list_backups(str(tmp_path))] == ["altra-casa"]


@pytest.mark.asyncio
async def test_restore_non_consuma_uno_snapshot_salvato_nel_frattempo(tmp_path):
    """La scrittura verso HA e' un await: in quella finestra un apply 'replace'
    concorrente (secondo tab, gateway MCP) puo' salvare un nuovo snapshot per
    la stessa plancia. Il consumo e' per identita', quindi non deve toccare
    quello nuovo: e' l'unica via di ritorno di quella sostituzione."""
    riapplicata = {"views": [{"title": "RIAPPLICATA"}]}
    save_backup(str(tmp_path), "casa-mia", riapplicata)

    class HAConcorrente(FakeHA):
        async def save_dashboard_config(self, url_path, config):
            # Mentre HA scrive, un altro percorso salva il proprio snapshot.
            save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "CONCORRENTE"}]})
            return await super().save_dashboard_config(url_path, config)

    ha = HAConcorrente()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    # Per l'utente il ripristino e' avvenuto davvero: 200, non un errore.
    assert resp.status == 200
    assert ha.saved == ("casa-mia", riapplicata)
    # Lo snapshot della sostituzione concorrente e' ancora li'.
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "CONCORRENTE"}]}
    assert [v["url_path"] for v in list_backups(str(tmp_path))] == ["casa-mia"]


@pytest.mark.asyncio
async def test_restore_resta_un_successo_se_il_consumo_fallisce(tmp_path, monkeypatch):
    """La plancia e' stata davvero ripristinata: un problema nel consumare lo
    snapshot non deve diventare un errore in faccia all'utente. Resta un 200,
    tracciato lato server."""
    import hiris.app.api.handlers_dashboards as mod
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "VECCHIA"}]})
    monkeypatch.setattr(mod, "discard_latest_backup", lambda *a, **k: False)
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert _corpo(resp) == {"ok": True, "url_path": "casa-mia"}


@pytest.mark.asyncio
async def test_restore_senza_snapshot_non_consuma_nulla(tmp_path):
    """Il 404 arriva prima di qualunque scrittura: niente HA, niente consumo."""
    save_backup(str(tmp_path), "altra-casa", {"views": [{"title": "B"}]})
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}, url_path="casa-mia"))
    assert resp.status == 404
    assert ha.saved is None
    assert [v["url_path"] for v in list_backups(str(tmp_path))] == ["altra-casa"]


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
