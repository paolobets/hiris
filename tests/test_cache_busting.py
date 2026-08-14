"""Cache-busting for static assets (server._inject_version / _asset_fingerprint).

Regression coverage for the bug where a config-page menu item dead-clicked
because a stale main.js was served: the old scheme
keyed the ?v= query string on a single global app version, so edits made without
a version bump reused the same URL and browsers served the cached file.

The fix fingerprints each asset by its own content hash, so any real edit busts
that file's cache automatically.
"""
import logging
import os

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from hiris.app import server
from hiris.app.server import create_app
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    """App vera (create_app()), gusci letti da disco come in _on_startup, ma
    senza avviare ha_client/scheduler/ecc -- questi test riguardano solo il
    guscio HTML e il servizio statico, non il resto del boot."""
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    app["ha_client"] = mock_ha
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()

    static_dir = os.path.join(os.path.dirname(server.__file__), "static")
    for fname, key in (("index.html", "html_index"), ("config.html", "html_config")):
        with open(os.path.join(static_dir, fname), encoding="utf-8") as f:
            app[key] = f.read()

    return await aiohttp_client(app)


def test_inject_version_appends_per_file_content_hash():
    html = (
        '<link rel="stylesheet" href="static/hiris.css">'
        '<script src="static/config/main.js"></script>'
        '<script src="static/config/memoria-route.js"></script>'
    )
    out = server._inject_version(html, "0.21.0")
    # Every local asset gets a ?v= fingerprint.
    assert 'static/hiris.css?v=' in out
    assert 'static/config/main.js?v=' in out
    assert 'static/config/memoria-route.js?v=' in out


def test_different_files_get_different_hashes():
    html = (
        '<script src="static/config/main.js"></script>'
        '<script src="static/config/memoria-route.js"></script>'
    )
    out = server._inject_version(html, "0.21.0")
    main_v = out.split("main.js?v=")[1].split('"')[0]
    mem_v = out.split("memoria-route.js?v=")[1].split('"')[0]
    assert main_v != mem_v


def test_external_and_non_target_urls_untouched():
    html = (
        '<link href="https://fonts.googleapis.com/css2?family=Geist&display=swap" rel="stylesheet">'
        '<link rel="icon" href="static/hiris-icon.svg">'
        '<script src="static/config/main.js"></script>'
    )
    out = server._inject_version(html, "0.21.0")
    # External font URL is left alone (not a local static .js/.css ref).
    assert 'display=swap"' in out
    assert "swap?v=" not in out
    # .svg is not a cache-busting target.
    assert 'href="static/hiris-icon.svg"' in out


def test_fingerprint_falls_back_when_file_missing():
    assert server._asset_fingerprint("static/does-not-exist.js", "FALLBACK") == "FALLBACK"


def test_fingerprint_changes_when_content_changes(tmp_path, monkeypatch):
    scratch = tmp_path / "asset.js"
    scratch.write_text("first")
    monkeypatch.setattr(server, "_STATIC_DIR", str(tmp_path))
    server._ASSET_FP_CACHE.clear()

    h1 = server._asset_fingerprint("static/asset.js", "fb")
    # Rewrite with different content and a strictly newer mtime.
    scratch.write_text("second-different")
    st = scratch.stat()
    os.utime(scratch, (st.st_mtime + 5, st.st_mtime + 5))
    h2 = server._asset_fingerprint("static/asset.js", "fb")

    assert h1 != "fb" and h2 != "fb"
    assert h1 != h2


def test_build_stamp_deterministic_and_changes_with_content(tmp_path):
    """Build stamp: uguale a parita' di contenuto, DIVERSO se un file cambia.
    Serve a verificare in UI/health quale build gira davvero (cache vs container
    non ricostruito)."""
    (tmp_path / "a.js").write_text("console.log(1)")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "b.css").write_text("body{}")
    s1 = server._compute_build_stamp(str(tmp_path))
    s2 = server._compute_build_stamp(str(tmp_path))
    assert s1 == s2 and len(s1) == 12
    (tmp_path / "a.js").write_text("console.log(2)")   # contenuto cambia -> stamp cambia
    assert server._compute_build_stamp(str(tmp_path)) != s1


def test_build_stamp_reflects_rename(tmp_path):
    """Anche un rename (path nell'hash) cambia lo stamp."""
    (tmp_path / "a.js").write_text("x")
    s1 = server._compute_build_stamp(str(tmp_path))
    (tmp_path / "a.js").rename(tmp_path / "b.js")
    assert server._compute_build_stamp(str(tmp_path)) != s1


# --- Task B8: il guscio dichiara da quale build e' nato -------------------


def test_inject_version_adds_hiris_build_meta_with_the_given_stamp():
    html = "<head><title>x</title></head><body></body>"
    out = server._inject_version(html, "0.21.0", "abc123def456")
    assert '<meta name="hiris-build" content="abc123def456">' in out


def test_inject_version_without_build_stamp_adds_no_meta():
    """Retrocompatibilita' dei test esistenti (che non passano build_stamp) e
    del comportamento quando il chiamante non ce l'ha: nessuna <meta> finta."""
    html = "<head><title>x</title></head><body></body>"
    out = server._inject_version(html, "0.21.0")
    assert "hiris-build" not in out


@pytest.mark.asyncio
async def test_both_shells_declare_the_running_build_stamp(client):
    """Mutazione da uccidere: la <meta> manca in UNO dei due gusci -- solo
    colpendo le rotte vere (GET / e GET /config), non la funzione isolata, un
    dimenticanza in una delle due chiamate a _inject_version si vede."""
    app = client.app
    stamp = app["build_stamp"]
    assert stamp  # precondizione: create_app() l'ha calcolato da static/ reale

    resp_index = await client.get("/")
    resp_config = await client.get("/config")
    assert resp_index.status == 200
    assert resp_config.status == 200
    html_index = await resp_index.text()
    html_config = await resp_config.text()

    needle = f'<meta name="hiris-build" content="{stamp}">'
    assert needle in html_index, "manca la <meta> nel guscio della chat (/)"
    assert needle in html_config, "manca la <meta> nel guscio della configurazione (/config)"


@pytest.mark.asyncio
async def test_stale_asset_fingerprint_is_logged_as_warning(client, caplog):
    """Punto 5 del brief: un asset richiesto con ?v=<impronta sbagliata> deve
    produrre UNA riga di log warning col nome file, l'impronta chiesta e
    quella attuale -- e continuare a servire il file (non cambia risposta)."""
    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        resp = await client.get("/static/chat/main.js?v=impronta-inventata-e-sbagliata")
    assert resp.status == 200  # si continua a servire il file
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"attesa esattamente una riga di warning, trovate {len(warnings)}"
    msg = warnings[0].getMessage()
    assert "chat/main.js" in msg
    assert "impronta-inventata-e-sbagliata" in msg


@pytest.mark.asyncio
async def test_asset_fingerprint_matching_current_is_not_logged(client, caplog):
    """Mutazione da uccidere: loggare SEMPRE, anche quando l'impronta chiesta
    e' quella giusta -- rumore che nasconderebbe il segnale."""
    static_dir = os.path.join(os.path.dirname(server.__file__), "static")
    correct = server._asset_fingerprint("static/chat/main.js", "fallback")
    assert correct != "fallback"

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        resp = await client.get(f"/static/chat/main.js?v={correct}")
    assert resp.status == 200
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [], f"non doveva loggare nulla con l'impronta corretta, trovato: {warnings}"
