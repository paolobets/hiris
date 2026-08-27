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
import shutil
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.chat_store import close_all_stores
from hiris.app.server import create_app


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


@pytest.fixture
def static_snapshot(tmp_path, monkeypatch):
    """Congela `hiris/app/static/` per la durata del test (m5, review
    finale). `_asset_fingerprint` viene chiamato DUE VOLTE attorno a una
    richiesta -- una volta dal test per sapere l'impronta "corretta", una
    volta dal middleware durante la chiamata -- e prima di questo fix
    entrambe leggevano l'albero VIVO: una scrittura concorrente in
    `static/` fra le due letture (un editor aperto, un altro agente, un
    `git checkout`) fa divergere i due valori e colora la corsa. Puntare
    `_STATIC_DIR` a una copia presa UNA volta all'inizio del test rende le
    due letture deterministe, indipendenti da cosa succede all'albero vero
    nel frattempo."""
    sorgente = os.path.join(os.path.dirname(server.__file__), "static")
    copia = tmp_path / "static_snapshot"
    shutil.copytree(sorgente, copia)
    monkeypatch.setattr(server, "_STATIC_DIR", str(copia))
    server._ASSET_FP_CACHE.clear()
    yield str(copia)
    server._ASSET_FP_CACHE.clear()


def test_static_snapshot_ripunta_STATIC_DIR_alla_copia_non_al_vivo(static_snapshot):
    """m8 (ri-review): la fixture `static_snapshot` prova solo di saper
    copiare (`shutil.copytree`), mai che qualcuno la usi -- resa inerte
    (nessun `monkeypatch` di `server._STATIC_DIR`) lasciava 14/14 verdi.
    Qui si pinza il cablaggio dal lato che conta: `server._STATIC_DIR`
    (letto da `_asset_fingerprint` e dal middleware che serve /static/*)
    deve puntare ESATTAMENTE alla copia che la fixture restituisce, mai
    all'albero static/ vivo."""
    vivo = os.path.join(os.path.dirname(server.__file__), "static")
    assert server._STATIC_DIR == static_snapshot
    assert server._STATIC_DIR != vivo


def _solo_i_nostri(records, logger_name="hiris.app.server"):
    """I record WARNING di `logger_name`, non di qualunque cosa propaghi
    alla radice (m4, review finale). `caplog.records` raccoglie i record di
    OGNI logger che arrivi li' -- `caplog.at_level(level, logger=...)`
    regola il LIVELLO di quel logger, non filtra la raccolta: un warning
    estraneo emesso durante la chiamata (qualunque dipendenza) farebbe
    cadere un conteggio non filtrato per nome, anche quando il nostro
    logger non ha detto niente."""
    return [r for r in records if r.name == logger_name and r.levelno == logging.WARNING]


@pytest.mark.asyncio
async def test_stale_asset_fingerprint_is_logged_as_warning(client, static_snapshot, caplog):
    """Punto 5 del brief: un asset richiesto con ?v=<impronta sbagliata> deve
    produrre UNA riga di log warning col nome file, l'impronta chiesta e
    quella attuale -- e continuare a servire il file (non cambia risposta)."""
    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        resp = await client.get("/static/chat/main.js?v=impronta-inventata-e-sbagliata")
    assert resp.status == 200  # si continua a servire il file
    warnings = _solo_i_nostri(caplog.records)
    assert len(warnings) == 1, f"attesa esattamente una riga di warning, trovate {len(warnings)}"
    msg = warnings[0].getMessage()
    assert "chat/main.js" in msg
    assert "impronta-inventata-e-sbagliata" in msg


@pytest.mark.asyncio
async def test_asset_fingerprint_matching_current_is_not_logged(client, static_snapshot, caplog):
    """Mutazione da uccidere: loggare SEMPRE, anche quando l'impronta chiesta
    e' quella giusta -- rumore che nasconderebbe il segnale."""
    correct = server._asset_fingerprint("static/chat/main.js", "fallback")
    assert correct != "fallback"

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        resp = await client.get(f"/static/chat/main.js?v={correct}")
    assert resp.status == 200
    warnings = _solo_i_nostri(caplog.records)
    assert warnings == [], f"non doveva loggare nulla con l'impronta corretta, trovato: {warnings}"


def test_asset_fingerprint_letture_ripetute_restano_coerenti_con_una_scrittura_concorrente(
        tmp_path, monkeypatch):
    """m5 (review finale): prova il MECCANISMO su cui si appoggia
    `static_snapshot` -- MAI sul repo vero, su un albero finto in
    `tmp_path` che sta al posto di `static/` VIVO. Con `_STATIC_DIR`
    puntato a un'istantanea congelata, due letture di `_asset_fingerprint`
    per lo stesso file restano identiche anche se la sorgente VIVA cambia
    fra le due -- esattamente le due letture che nella suite vera fa una
    volta il test (l'impronta "corretta") e una volta il middleware
    (durante la richiesta)."""
    vivo = tmp_path / "vivo"
    vivo.mkdir()
    (vivo / "main.js").write_text("console.log('v1')")

    istantanea = tmp_path / "istantanea"
    shutil.copytree(vivo, istantanea)
    monkeypatch.setattr(server, "_STATIC_DIR", str(istantanea))
    server._ASSET_FP_CACHE.clear()

    prima = server._asset_fingerprint("static/main.js", "fallback")
    assert prima != "fallback"

    # La scrittura concorrente: qualcosa cambia l'albero VIVO -- ma
    # _STATIC_DIR punta all'istantanea, non al vivo. mtime spostato avanti
    # esplicitamente (stesso accorgimento di
    # test_fingerprint_changes_when_content_changes qui sopra): la cache di
    # _asset_fingerprint e' chiave per mtime, e senza uno scarto certo la
    # scrittura potrebbe capitare nella stessa risoluzione del clock e
    # mascherare da sola la divergenza che questo test vuole provare.
    vivo_file = vivo / "main.js"
    vivo_file.write_text("console.log('v2 -- scrittura concorrente')")
    st = vivo_file.stat()
    os.utime(vivo_file, (st.st_mtime + 5, st.st_mtime + 5))

    dopo = server._asset_fingerprint("static/main.js", "fallback")
    assert prima == dopo, (
        "con _STATIC_DIR su un'istantanea congelata, una scrittura sull'albero vivo "
        "non deve mai far divergere due letture della stessa impronta")


@pytest.mark.asyncio
async def test_asset_fingerprint_matching_current_ignora_warning_di_altri_logger(client, caplog):
    """m4 (review finale): `caplog.records` raccoglie i record di QUALUNQUE
    logger propagato alla radice -- non solo `hiris.app.server` -- perche'
    `at_level(..., logger="hiris.app.server")` regola il LIVELLO di quel
    logger, non filtra la RACCOLTA. Un warning emesso da tutt'altro (qui una
    libreria finta, ma vale per qualunque dipendenza) durante la chiamata
    farebbe cadere un conteggio non filtrato per nome, anche se il NOSTRO
    logger non ha detto niente."""
    correct = server._asset_fingerprint("static/chat/main.js", "fallback")
    assert correct != "fallback"
    estraneo = logging.getLogger("una.libreria.estranea.a.hiris")

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        estraneo.warning("rumore che non riguarda l'impronta di nessun asset")
        resp = await client.get(f"/static/chat/main.js?v={correct}")
    assert resp.status == 200

    # Precondizione: il warning estraneo E' finito in caplog.records --
    # altrimenti questo test non proverebbe niente sulla fragilita'.
    assert any(r.name == "una.libreria.estranea.a.hiris" for r in caplog.records)

    warnings = _solo_i_nostri(caplog.records)
    assert warnings == [], (
        f"il warning di 'una.libreria.estranea.a.hiris' non deve contare per il "
        f"logger hiris.app.server, trovato: {warnings}")
