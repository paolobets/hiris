"""La voce di menu di HIRIS e l'opzione che la governa (spec 2026-09-27 §2).

L'opzione `non_admin_access` e' l'unica fonte della scelta: si legge UNA volta
in `create_app` e da li' in poi vive in `app["non_admin_access"]`. All'avvio
HIRIS chiede al Supervisor il proprio slug, scrive in Home Assistant l'override
della sua voce di menu (`frontend/update_panel`) e rilegge `get_panels` per
dire nel registro lo stato VERO della voce.

Forme verificate il 27/09/2026 sul sorgente, non dedotte:
- Home Assistant Core 2026.9.3, `components/frontend/__init__.py`:
  `frontend/update_panel` accetta `url_path` + `require_admin: bool | None`
  (`None` toglie la chiave dell'override), risponde `not_found` a un pannello
  sconosciuto; `get_panels` torna `{url_path: {..., "require_admin",
  "show_in_sidebar"}}` con l'override gia' applicato.
- `components/websocket_api/const.py`: un comando che HA non conosce risponde
  col codice `unknown_command` (e' cosi' che risponde un HA piu' vecchio della
  2026.3, dove `frontend/update_panel` non esiste).
- Supervisor 2026.09.2, `api/apps.py::get_app_for_request`: `/addons/self/info`
  risolve l'add-on che chiama, e la risposta e' `{"result": "ok", "data":
  {"slug": ...}}` (`api/utils.py::api_return_ok`).

Le finte qui sotto fingono il FILO (il messaggio WebSocket intero, la risposta
HTTP del Supervisor), non i metodi di `HAClient`: cosi' la prova passa dai
metodi veri e asserisce cio' che arriva davvero a Home Assistant.
"""
import asyncio
import logging
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiohttp import web

from hiris.app import panel_visibility, server
from hiris.app.chat_settings import ChatSettings
from hiris.app.proxy.ha_client import HAClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOUSE_SLUG = "6354e165_hiris"   # lo slug vero sulla casa, 27/09/2026


class _FiloHA(HAClient):
    """Un `HAClient` vero con il solo filo WebSocket finto.

    `risposte` associa un tipo di comando al messaggio INTERO che Home
    Assistant manderebbe (`{success, result, error}`), oppure `None` per «la
    connessione non c'e'». `sospeso` fa restare appeso un tipo: serve a provare
    che l'avvio non aspetta Home Assistant."""

    def __init__(self, risposte: dict, sospeso: str | None = None):
        super().__init__("http://supervisor/core", "token-finto")
        self._risposte = risposte
        self._sospeso = sospeso
        self.mandati: list[tuple[str, dict | None]] = []

    async def _ws_command(self, msg_type, extra=None, timeout=10.0):
        self.mandati.append((msg_type, extra))
        if msg_type == self._sospeso:
            await asyncio.Event().wait()
        return self._risposte.get(msg_type)


_PANNELLI = {
    HOUSE_SLUG: {"url_path": HOUSE_SLUG, "require_admin": False,
                   "show_in_sidebar": True, "title": "HIRIS"},
    "altro_addon": {"url_path": "altro_addon", "require_admin": True,
                    "show_in_sidebar": True, "title": "ALTRO-PANNELLO-SEGRETO"},
}
_OK = {"success": True, "result": None}


def _risposte_buone():
    return {"frontend/update_panel": _OK,
            "get_panels": {"success": True, "result": _PANNELLI}}


@pytest_asyncio.fixture
async def supervisor(aiohttp_server, monkeypatch):
    """Un Supervisor finto sul filo HTTP vero. `stato["corpo"]` e
    `stato["status"]` decidono la risposta; `stato["chieste"]` registra
    percorso e intestazione d'autorizzazione di ogni richiesta."""
    stato = {"status": 200, "chieste": [],
             "corpo": {"result": "ok", "data": {"slug": HOUSE_SLUG}}}

    async def info(request):
        stato["chieste"].append((request.path, request.headers.get("Authorization")))
        return web.json_response(stato["corpo"], status=stato["status"])

    app = web.Application()
    app.router.add_get("/addons/self/info", info)
    srv = await aiohttp_server(app)
    monkeypatch.setattr(panel_visibility, "SUPERVISOR_URL",
                        str(srv.make_url("")).rstrip("/"))
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token-del-supervisor")
    return stato


def _app(accesso: bool, ha):
    return {"non_admin_access": accesso, "ha_client": ha}


# ── L'opzione: una lettura, rigida, chiusa nel dubbio ────────────────────────

@pytest.mark.parametrize("grezzo, atteso", [
    ("true", True), ("TRUE", True), (" true\n", True),
    ("false", False), ("", False), ("0", False), ("1", False), ("yes", False),
    ("on", False), ("null", False), ("vero", False), (None, False),
])
def test_l_opzione_si_legge_rigida_e_nel_dubbio_e_spenta(monkeypatch, grezzo, atteso):
    """Solo «true» apre. `bashio::config` di un `bool` scrive `true`/`false`:
    ogni altra forma e' un errore di chi l'ha scritta, e un errore non apre.
    Mutazione: riusare `env_util.env_bool` (che accetta `yes`/`1`/`on`) -- rossa."""
    if grezzo is None:
        monkeypatch.delenv("HIRIS_NON_ADMIN_ACCESS", raising=False)
    else:
        monkeypatch.setenv("HIRIS_NON_ADMIN_ACCESS", grezzo)

    app = server.create_app()

    assert app["non_admin_access"] is atteso


def test_l_opzione_nasce_in_create_app_e_non_si_rilegge(monkeypatch):
    """Letta una volta: cambiare l'ambiente dopo `create_app` non cambia niente.
    Il valore c'e' PRIMA dell'avvio, quando l'app si puo' ancora scrivere."""
    monkeypatch.setenv("HIRIS_NON_ADMIN_ACCESS", "false")
    app = server.create_app()
    monkeypatch.setenv("HIRIS_NON_ADMIN_ACCESS", "true")

    assert app["non_admin_access"] is False


def test_l_opzione_ha_una_casa_sola():
    """Una lettura dell'ambiente e una scrittura in `app[...]`, entrambe in
    `create_app`; nessuna rotta la riscrive. Il conteggio si fa sul sorgente
    di tutta l'app, cosi' una seconda lettura aggiunta domani lo rompe."""
    letture, scritture = [], []
    for f in (ROOT / "hiris" / "app").rglob("*.py"):
        testo = f.read_text(encoding="utf-8")
        letture += [f.name for _ in re.finditer(r'"HIRIS_NON_ADMIN_ACCESS"', testo)]
        scritture += [f.name for _ in re.finditer(
            r'\[\s*"non_admin_access"\s*\]\s*=(?!=)', testo)]
    assert letture == ["server.py"], letture
    assert scritture == ["server.py"], scritture
    create_app = (ROOT / "hiris" / "app" / "server.py").read_text(encoding="utf-8")
    corpo = create_app[create_app.index("def create_app("):]
    assert '"HIRIS_NON_ADMIN_ACCESS"' in corpo and 'app["non_admin_access"] =' in corpo


def test_l_opzione_arriva_dal_manifest_al_codice():
    """La catena `config.yaml` → `run.sh` → variabile d'ambiente: spenta per
    difetto, booleana nello schema, esportata col nome che il codice legge."""
    import yaml
    cfg = yaml.safe_load((ROOT / "hiris" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["options"]["non_admin_access"] is False
    assert cfg["schema"]["non_admin_access"] == "bool"
    run_sh = (ROOT / "hiris" / "run.sh").read_text(encoding="utf-8")
    assert "export HIRIS_NON_ADMIN_ACCESS=$(bashio::config 'non_admin_access')" in run_sh


# ── La voce di menu: cosa arriva a Home Assistant ────────────────────────────

@pytest.mark.asyncio
async def test_opzione_accesa_la_voce_si_apre_a_tutti(supervisor):
    """Il comando esatto, e niente di piu': né `title`, né `icon`, né
    `show_in_sidebar` -- HIRIS tocca solo cio' che l'opzione decide."""
    ha = _FiloHA(_risposte_buone())

    await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.mandati == [
        ("frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": False}),
        ("get_panels", None),
    ]


@pytest.mark.asyncio
async def test_opzione_spenta_toglie_l_override(supervisor):
    """`None` e non `True`: toglie l'override e torna il predefinito di Home
    Assistant senza lasciare tracce. Mutazione: mandare `True` -- rossa."""
    ha = _FiloHA(_risposte_buone())

    await panel_visibility.sync_panel_visibility(_app(False, ha))

    assert ha.mandati[0] == (
        "frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": None})


@pytest.mark.asyncio
async def test_lo_slug_e_quello_che_dice_il_supervisor(supervisor):
    """Mai scritto a mano: un'installazione da un altro repository ha un altro
    prefisso, e l'override finirebbe su un pannello che non esiste."""
    supervisor["corpo"] = {"result": "ok", "data": {"slug": "abc123_hiris"}}
    ha = _FiloHA(_risposte_buone())

    await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.mandati[0][1]["url_path"] == "abc123_hiris"
    assert supervisor["chieste"] == [
        ("/addons/self/info", "Bearer token-del-supervisor")]


@pytest.mark.asyncio
@pytest.mark.parametrize("corpo, status", [
    ({"result": "ok", "data": {"slug": "../x"}}, 200),
    ({"result": "ok", "data": {"slug": ""}}, 200),
    ({"result": "ok", "data": {"slug": "Hiris-Maiuscolo"}}, 200),
    ({"result": "ok", "data": {"slug": 42}}, 200),
    ({"result": "ok", "data": {}}, 200),
    ({"result": "ok", "data": "non un oggetto"}, 200),
    ({"result": "error", "message": "no"}, 403),
    ({"result": "error", "message": "boom"}, 500),
])
async def test_uno_slug_che_non_si_sa_non_tocca_niente(supervisor, caplog, corpo, status):
    """Uno slug assente, vuoto o di forma strana non diventa un `url_path`:
    nessun comando parte, e il registro dice perche'. Mutazione: togliere la
    validazione della forma -- rossa su `../x`."""
    supervisor["corpo"], supervisor["status"] = corpo, status
    ha = _FiloHA(_risposte_buone())

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.mandati == []
    assert any("slug" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_un_supervisor_che_non_risponde_non_ferma_niente(monkeypatch, caplog):
    """Nessun Supervisor raggiungibile (sviluppo, o rete giu'): una riga nel
    registro, nessuna eccezione, nessun comando a Home Assistant."""
    monkeypatch.setattr(panel_visibility, "SUPERVISOR_URL", "http://127.0.0.1:9")
    ha = _FiloHA(_risposte_buone())

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.mandati == []
    assert any("slug" in r.getMessage() for r in caplog.records), caplog.text


# ── Gli esiti di Home Assistant: detti una volta, mai ritentati ─────────────

@pytest.mark.asyncio
async def test_home_assistant_troppo_vecchio_lo_dice_e_prosegue(supervisor, caplog):
    """Prima della 2026.3 `frontend/update_panel` non esiste: la voce resta ai
    soli amministratori, e il registro lo dice con queste parole."""
    risposte = _risposte_buone()
    risposte["frontend/update_panel"] = {
        "success": False,
        "error": {"code": "unknown_command", "message": "Unknown command."}}
    ha = _FiloHA(risposte)

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert [t for t, _ in ha.mandati].count("frontend/update_panel") == 1
    righe = [r.getMessage() for r in caplog.records]
    assert any("2026.3" in r and "amministratori" in r for r in righe), righe


@pytest.mark.asyncio
@pytest.mark.parametrize("risposta, motivo", [
    ({"success": False, "error": {"code": "unauthorized", "message": "Unauthorized"}},
     "Unauthorized"),
    ({"success": False, "error": {"code": "not_found", "message": "Panel not found"}},
     "Panel not found"),
    (None, "Home Assistant non ha risposto"),
])
async def test_un_altro_errore_si_dice_una_volta(supervisor, caplog, risposta, motivo):
    """Il motivo nel registro, un solo tentativo, nessuna eccezione che esca
    dall'avvio. Mutazione: ritentare in un ciclo -- rossa sul conteggio."""
    risposte = _risposte_buone()
    risposte["frontend/update_panel"] = risposta
    ha = _FiloHA(risposte)

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert [t for t, _ in ha.mandati].count("frontend/update_panel") == 1
    assert any(motivo in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_il_registro_dice_lo_stato_vero_della_sola_voce_di_hiris(supervisor, caplog):
    """Lo stato si RILEGGE da `get_panels`, non si deduce dal comando mandato:
    e' cio' che Home Assistant applica davvero. E si dice solo della voce di
    HIRIS -- gli altri pannelli della casa non sono affar suo."""
    risposte = _risposte_buone()
    risposte["get_panels"] = {"success": True, "result": {
        **_PANNELLI,
        HOUSE_SLUG: {**_PANNELLI[HOUSE_SLUG], "require_admin": True}}}
    ha = _FiloHA(risposte)

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    righe = [r.getMessage() for r in caplog.records]
    stato = [r for r in righe if HOUSE_SLUG in r and "amministratori" in r]
    assert stato, righe   # l'override chiesto era False, HA dice True: vince HA
    assert not any("ALTRO-PANNELLO-SEGRETO" in r or "altro_addon" in r for r in righe)


@pytest.mark.asyncio
async def test_la_voce_aperta_si_dice_aperta(supervisor, caplog):
    ha = _FiloHA(_risposte_buone())

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    righe = [r.getMessage() for r in caplog.records]
    assert any(HOUSE_SLUG in r and "tutti" in r for r in righe), righe


@pytest.mark.asyncio
async def test_nessun_segreto_del_supervisor_finisce_nel_registro(supervisor, caplog):
    """`/addons/self/info` porta anche le opzioni dell'add-on, chiavi API
    comprese: il corpo non si scrive mai, neanche quando e' malformato."""
    for slug in (HOUSE_SLUG, "../x"):
        supervisor["corpo"] = {"result": "ok", "data": {
            "slug": slug, "options": {"claude_api_key": "sk-TEST-LEAK"}}}
        with caplog.at_level(logging.DEBUG):
            await panel_visibility.sync_panel_visibility(
                _app(True, _FiloHA(_risposte_buone())))

    assert "sk-TEST-LEAK" not in caplog.text
    assert "token-del-supervisor" not in caplog.text


# ── L'avvio: non aspetta Home Assistant ─────────────────────────────────────

@pytest.mark.asyncio
async def test_l_avvio_chiama_la_sincronia_e_non_la_aspetta(aiohttp_client, supervisor,
                                                              monkeypatch, tmp_path):
    """Il cablaggio vero di `create_app`: la sincronia parte all'avvio, e una
    Home Assistant che non risponde non tiene chiuso `/api/health`.
    Mutazione: aspettarla dentro l'avvio -- rossa (il client non parte)."""
    monkeypatch.setenv("HIRIS_NON_ADMIN_ACCESS", "true")
    app = server.create_app()
    app.on_startup.remove(server._on_startup)
    app.on_cleanup.clear()
    ha = _FiloHA(_risposte_buone(), sospeso="frontend/update_panel")
    app["ha_client"] = ha
    app["chat_settings"] = ChatSettings()
    runner = AsyncMock()
    runner.last_tool_calls = []
    app["claude_runner"] = runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["entity_cache"] = MagicMock()

    client = await asyncio.wait_for(aiohttp_client(app), timeout=5)
    try:
        resp = await client.get("/api/health")
        assert resp.status == 200
        for _ in range(100):
            if ha.mandati:
                break
            await asyncio.sleep(0.01)
        assert ha.mandati == [
            ("frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": False})]
    finally:
        for task in list(server._background_tasks):
            if task.get_name() == "panel_visibility":
                task.cancel()


def test_il_cancello_non_dipende_dalla_voce_di_menu():
    """La sicurezza non dipende mai dal menu (spec §2): chi stabilisce il
    soggetto non legge l'esito della sincronia."""
    auth = (ROOT / "hiris" / "app" / "api" / "middleware_internal_auth.py").read_text(
        encoding="utf-8")
    assert "panel_visibility" not in auth
