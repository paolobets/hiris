"""Cache-busting for static assets (server._inject_version / _asset_fingerprint).

Regression coverage for the bug where config-page menu items (Storicizzazione,
Accessi Gateway) dead-clicked because a stale main.js was served: the old scheme
keyed the ?v= query string on a single global app version, so edits made without
a version bump reused the same URL and browsers served the cached file.

The fix fingerprints each asset by its own content hash, so any real edit busts
that file's cache automatically.
"""
import os

from hiris.app import server


def test_inject_version_appends_per_file_content_hash():
    html = (
        '<link rel="stylesheet" href="static/hiris.css">'
        '<script src="static/config/main.js"></script>'
        '<script src="static/config/gateway-route.js"></script>'
    )
    out = server._inject_version(html, "0.21.0")
    # Every local asset gets a ?v= fingerprint.
    assert 'static/hiris.css?v=' in out
    assert 'static/config/main.js?v=' in out
    assert 'static/config/gateway-route.js?v=' in out


def test_different_files_get_different_hashes():
    html = (
        '<script src="static/config/main.js"></script>'
        '<script src="static/config/gateway-route.js"></script>'
    )
    out = server._inject_version(html, "0.21.0")
    main_v = out.split("main.js?v=")[1].split('"')[0]
    gw_v = out.split("gateway-route.js?v=")[1].split('"')[0]
    assert main_v != gw_v


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
