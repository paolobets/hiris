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
metodi veri e asserisce cio' che arriva davvero a Home Assistant. Dalla Tappa 2
(Task 12) il filo WebSocket e' quello della casa finta comune
(`scripts/casa_finta.py`), e la scrittura `frontend/update_panel` la casa la
registra in `calls`, non la esegue.
"""
import asyncio
import logging
import math
import pathlib
import re
import sys
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiohttp import web

from hiris.app import panel_visibility, server
from hiris.app.chat_settings import ChatSettings

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from casa_finta import CasaFinta

HOUSE_SLUG = "6354e165_hiris"   # lo slug vero sulla casa, 27/09/2026


def _filo_appeso(sospeso: str) -> CasaFinta:
    """Home Assistant collegato (`ws_ready` acceso) che non risponde mai a
    `sospeso` (`delay=` della casa finta, `math.inf`): il comando parte, e il
    client vero aspetta sotto il suo tetto. Serve a provare che l'avvio non
    aspetta Home Assistant, e il tetto della sincronia. Fino al Task 12 della
    Tappa 2 era `_FiloAppeso`, un `HAClient` col `_ws_send` sostituito a mano,
    che restava appeso anche oltre il tetto del vero."""
    ha = CasaFinta({}, answers={sospeso: lambda extra: None,
                                "get_panels": lambda extra: _PANNELLI},
                   delay={sospeso: math.inf})
    ha.ws_ready.set()
    return ha


_PANNELLI = {
    HOUSE_SLUG: {"url_path": HOUSE_SLUG, "require_admin": False,
                   "show_in_sidebar": True, "title": "HIRIS"},
    "altro_addon": {"url_path": "altro_addon", "require_admin": True,
                    "show_in_sidebar": True, "title": "ALTRO-PANNELLO-SEGRETO"},
}


def _casa(pannelli=None, *, refuse=None, silence=(), pronto: bool = True) -> CasaFinta:
    """La casa finta che accetta l'override (`frontend/update_panel` risponde
    `null`, come `websocket_update_panel`) e rilegge `pannelli`. `refuse` e
    `silence` sono il rifiuto vero (`{"code", "message"}`) e il silenzio.
    `pronto=False` finge un nucleo non ancora collegato: `ws_ready` resta
    spento finche' la prova non lo accende. Con `pronto` si accende qui: la
    casa finta non lo accende piu' alla nascita (Tappa 2, Task 7), lo accende
    il websocket di lunga vita, che queste prove non aprono."""
    pannelli = _PANNELLI if pannelli is None else pannelli
    ha = CasaFinta({}, answers={"frontend/update_panel": lambda extra: None,
                                "get_panels": lambda extra: pannelli},
                   refuse=refuse, silence=silence)
    if pronto:
        ha.ws_ready.set()
    return ha


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
    Mutazione: accettare anche `yes`/`1`/`on` -- rossa."""
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
    """Una lettura dell'ambiente e una scrittura in `app[...]`, in tutto il
    prodotto; nessuna rotta la riscrive. Il conteggio si fa sul sorgente di
    tutta l'app, cosi' una seconda lettura aggiunta domani lo rompe.

    CHE quella lettura e quella scrittura siano di `create_app` lo provano le
    due prove qui sopra, chiamandola: `create_app()` porta il valore, e
    cambiare l'ambiente dopo non lo cambia. Fino al 03/10/2026 questa prova lo
    cercava anche nel testo di `server.py`, da `def create_app(` in giu' --
    cioe' pretendeva che l'app si costruisse in QUEL file (Tappa 1 dello sprint
    «Una fonte sola di verita'»).

    Mutazione ESEGUITA: una seconda lettura di `"HIRIS_NON_ADMIN_ACCESS"` in
    `hiris/app/api/handlers_config.py` -- rossa."""
    letture, scritture = [], []
    moduli = sorted((ROOT / "hiris" / "app").rglob("*.py"))
    assert len(moduli) > 50, f"la derivazione dei moduli si e' rotta: {len(moduli)}"
    for f in moduli:
        testo = f.read_text(encoding="utf-8")
        letture += [f.name for _ in re.finditer(r'"HIRIS_NON_ADMIN_ACCESS"', testo)]
        scritture += [f.name for _ in re.finditer(
            r'\[\s*"non_admin_access"\s*\]\s*=(?!=)', testo)]
    assert len(letture) == 1, letture
    assert len(scritture) == 1, scritture


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
    ha = _casa()

    await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.calls == [
        ("frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": False}),
        ("get_panels", None),
    ]


@pytest.mark.asyncio
async def test_opzione_spenta_toglie_l_override(supervisor):
    """`None` e non `True`: toglie l'override e torna il predefinito di Home
    Assistant senza lasciare tracce. Mutazione: mandare `True` -- rossa."""
    ha = _casa()

    await panel_visibility.sync_panel_visibility(_app(False, ha))

    assert ha.calls[0] == (
        "frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": None})


@pytest.mark.asyncio
async def test_lo_slug_e_quello_che_dice_il_supervisor(supervisor):
    """Mai scritto a mano: un'installazione da un altro repository ha un altro
    prefisso, e l'override finirebbe su un pannello che non esiste."""
    supervisor["corpo"] = {"result": "ok", "data": {"slug": "abc123_hiris"}}
    ha = _casa()

    await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.calls[0][1]["url_path"] == "abc123_hiris"
    assert supervisor["chieste"] == [
        ("/addons/self/info", "Bearer token-del-supervisor")]


@pytest.mark.asyncio
@pytest.mark.parametrize("corpo, status", [
    ({"result": "ok", "data": {"slug": "../x"}}, 200),
    ({"result": "ok", "data": {"slug": f"{HOUSE_SLUG}\n"}}, 200),
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
    ha = _casa()

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.calls == []
    assert any("slug" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_un_supervisor_che_non_risponde_non_ferma_niente(monkeypatch, caplog):
    """Nessun Supervisor raggiungibile (sviluppo, o rete giu'): una riga nel
    registro, nessuna eccezione, nessun comando a Home Assistant. Il token
    c'e': senza, non si chiama nessuno (la prova qui sotto)."""
    monkeypatch.setattr(panel_visibility, "SUPERVISOR_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token-del-supervisor")
    ha = _casa()

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert ha.calls == []
    assert any("slug" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, ""])
async def test_senza_supervisor_non_si_chiama_nessuno(supervisor, monkeypatch, caplog,
                                                      token):
    """Review finale, punto 4: senza `SUPERVISOR_TOKEN` (sviluppo locale,
    `.smoke-test`) non c'e' un Supervisor da chiamare. Una riga `info` che lo
    dice, nessuna richiesta a `http://supervisor`, nessun comando a Home
    Assistant -- e non l'avviso sullo slug a ogni avvio.

    Mutazione ESEGUITA: tolto il ritorno anticipato sul token vuoto in
    `_sync` -- rossa (la richiesta parte e la riga e' l'avviso sullo slug)."""
    if token is None:
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    else:
        monkeypatch.setenv("SUPERVISOR_TOKEN", token)
    ha = _casa()

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert supervisor["chieste"] == []
    assert ha.calls == []
    righe = [(r.levelname, r.getMessage()) for r in caplog.records]
    assert righe == [("INFO", "nessun Supervisor: la voce di menu non si tocca")], righe


# ── Gli esiti di Home Assistant: detti una volta, mai ritentati ─────────────

@pytest.mark.asyncio
async def test_home_assistant_troppo_vecchio_lo_dice_e_prosegue(supervisor, caplog):
    """Prima della 2026.3 `frontend/update_panel` non esiste: la voce resta ai
    soli amministratori, e il registro lo dice con queste parole."""
    ha = _casa(refuse={"frontend/update_panel":
                       {"code": "unknown_command", "message": "Unknown command."}})

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert [t for t, _ in ha.calls].count("frontend/update_panel") == 1
    righe = [r.getMessage() for r in caplog.records]
    assert any("2026.3" in r and "amministratori" in r for r in righe), righe


@pytest.mark.asyncio
@pytest.mark.parametrize("rifiuto, motivo", [
    ({"code": "unauthorized", "message": "Unauthorized"}, "Unauthorized"),
    ({"code": "not_found", "message": "Panel not found"}, "Panel not found"),
    (None, "Home Assistant non ha risposto"),
])
async def test_un_altro_errore_si_dice_una_volta(supervisor, caplog, rifiuto, motivo):
    """Il motivo nel registro, un solo tentativo, nessuna eccezione che esca
    dall'avvio. `None` e' il silenzio: la connessione non c'e'. Mutazione:
    ritentare in un ciclo -- rossa sul conteggio."""
    ha = (_casa(silence={"frontend/update_panel"}) if rifiuto is None else
          _casa(refuse={"frontend/update_panel": rifiuto}))

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    assert [t for t, _ in ha.calls].count("frontend/update_panel") == 1
    assert any(motivo in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_il_registro_dice_lo_stato_vero_della_sola_voce_di_hiris(supervisor, caplog):
    """Lo stato si RILEGGE da `get_panels`, non si deduce dal comando mandato:
    e' cio' che Home Assistant applica davvero. E si dice solo della voce di
    HIRIS -- gli altri pannelli della casa non sono affar suo."""
    ha = _casa({**_PANNELLI,
                HOUSE_SLUG: {**_PANNELLI[HOUSE_SLUG], "require_admin": True}})

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    righe = [r.getMessage() for r in caplog.records]
    stato = [r for r in righe if HOUSE_SLUG in r and "amministratori" in r]
    assert stato, righe   # l'override chiesto era False, HA dice True: vince HA
    assert not any("ALTRO-PANNELLO-SEGRETO" in r or "altro_addon" in r for r in righe)


@pytest.mark.asyncio
async def test_la_voce_aperta_si_dice_aperta(supervisor, caplog):
    ha = _casa()

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
                _app(True, _casa()))

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
    ha = _filo_appeso("frontend/update_panel")
    app["ha_client"] = ha
    app["chat_settings"] = ChatSettings()
    runner = AsyncMock()
    runner.last_tool_calls = []
    app["claude_runner"] = runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["entity_cache"] = MagicMock()

    client = await asyncio.wait_for(aiohttp_client(app), timeout=5)
    resp = await client.get("/api/health")
    assert resp.status == 200
    for _ in range(100):
        if ha.calls:
            break
        await asyncio.sleep(0.01)
    assert ha.calls == [
        ("frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": False})]
    # Niente arresto a mano: la sincronia appesa la ferma `_on_cleanup`,
    # alla chiusura del client (la prova qui sotto).


def test_il_cancello_non_dipende_dalla_voce_di_menu():
    """La sicurezza non dipende mai dal menu (spec §2): chi stabilisce il
    soggetto non legge l'esito della sincronia."""
    auth = (ROOT / "hiris" / "app" / "api" / "middleware_internal_auth.py").read_text(
        encoding="utf-8")
    assert "panel_visibility" not in auth


# ── L'attesa del nucleo: una chiamata sola, dopo che Home Assistant c'e' ─────

@pytest.mark.asyncio
async def test_la_chiamata_aspetta_che_home_assistant_ci_sia(supervisor):
    """L'add-on parte prima del nucleo (`startup: services`): la chiamata parte
    solo quando il WebSocket di HIRIS si e' autenticato, e parte una volta.
    Mutazione: non aspettare `ws_ready` -- rossa (il comando parte subito)."""
    ha = _casa(pronto=False)
    task = asyncio.create_task(panel_visibility.sync_panel_visibility(_app(True, ha)))
    await asyncio.sleep(0.2)
    assert ha.calls == []

    ha.ws_ready.set()
    await asyncio.wait_for(task, timeout=5)

    assert ha.calls == [
        ("frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": False}),
        ("get_panels", None),
    ]


@pytest.mark.asyncio
async def test_un_nucleo_che_non_arriva_si_dice_e_non_si_chiama(supervisor, caplog,
                                                                 monkeypatch):
    """Oltre il tetto: una riga che lo dice, nessun comando, nessuna eccezione."""
    monkeypatch.setattr(panel_visibility, "SYNC_CEILING_S", 0.2)
    ha = _casa(pronto=False)

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await asyncio.wait_for(
            panel_visibility.sync_panel_visibility(_app(True, ha)), timeout=5)

    assert ha.calls == []
    righe = [r.getMessage() for r in caplog.records]
    assert len(righe) == 1 and "non si è collegato" in righe[0], righe


@pytest.mark.asyncio
async def test_un_nucleo_collegato_che_non_risponde_si_dice_e_non_solleva(
        supervisor, caplog, monkeypatch):
    """Il ramo `else` del tetto: il WebSocket c'e', ma `frontend/update_panel`
    resta appeso oltre `SYNC_CEILING_S`. Una riga che dice «non ha
    risposto», nessuna eccezione, nessuna rilettura.

    Mutazione ESEGUITA: i due rami del tetto scambiati (`if
    ha.ws_ready.is_set()`) -- rossa (la riga dice «non si è collegato»)."""
    monkeypatch.setattr(panel_visibility, "SYNC_CEILING_S", 0.2)
    ha = _filo_appeso("frontend/update_panel")

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await asyncio.wait_for(
            panel_visibility.sync_panel_visibility(_app(True, ha)), timeout=5)

    assert ha.calls == [
        ("frontend/update_panel", {"url_path": HOUSE_SLUG, "require_admin": False})]
    righe = [r.getMessage() for r in caplog.records]
    assert len(righe) == 1 and "non ha risposto" in righe[0], righe


@pytest.mark.asyncio
async def test_la_sincronia_appesa_si_ferma_alla_chiusura(supervisor):
    """Review finale: il tetto e' di dieci minuti, e un arresto durante
    l'attesa lasciava un compito pendente distrutto a chiusura. `_on_cleanup`
    lo ferma e lo aspetta.

    Mutazione ESEGUITA: tolto l'arresto di `panel_sync_task` da
    `_on_cleanup` -- rossa (il compito e' ancora vivo dopo la chiusura).

    **Rieseguita il 04/10/2026 (Tappa 2, Task 12), ed era VERDE** -- anche
    sulla prova com'era, con la finta di prima: `wait_for(_on_cleanup, 5)`
    alla scadenza CANCELLA `_on_cleanup`, la cancellazione scende nel
    compito che stava aspettando, e il `suppress(CancelledError)` di
    `_on_cleanup` la inghiotte -- il compito risultava fermo e la prova verde,
    in cinque secondi invece che subito. Adesso si misura il tempo della
    chiusura, senza tetto che cancelli: con la mutazione la chiusura aspetta
    il tetto del client vero sul comando appeso (10 s) -- rossa."""
    ha = _filo_appeso("frontend/update_panel")
    app = _app(True, ha)
    await server.start_panel_sync(app)
    for _ in range(100):
        if ha.calls:
            break
        await asyncio.sleep(0.01)
    assert ha.calls, "precondizione: la sincronia e' appesa su update_panel"

    start = time.monotonic()
    await server._on_cleanup(app)

    assert time.monotonic() - start < 1.0, "la chiusura ha aspettato la sincronia appesa"
    assert app["panel_sync_task"].done()


@pytest.mark.asyncio
async def test_rifiuto_e_rilettura_fallita_stanno_in_una_riga(supervisor, caplog):
    """Quando l'override fallisce e neanche la rilettura riesce, il registro lo
    dice in UNA riga: due righe separate si leggono come due guasti."""
    ha = _casa(silence={"frontend/update_panel", "get_panels"})

    with caplog.at_level(logging.INFO, logger="hiris.app.panel_visibility"):
        await panel_visibility.sync_panel_visibility(_app(True, ha))

    righe = [r.getMessage() for r in caplog.records]
    assert len(righe) == 1, righe
    assert "rifiutato" in righe[0] and "stato non riletto" in righe[0], righe


def test_la_sincronia_parte_dopo_l_avvio_che_crea_il_client():
    """`start_panel_sync` legge `app["ha_client"]`, che nasce in `_on_startup`:
    l'ordine dei due e' un fatto, e si pinna."""
    app = server.create_app()
    hooks = list(app.on_startup)
    assert server._on_startup in hooks and server.start_panel_sync in hooks
    assert hooks.index(server.start_panel_sync) > hooks.index(server._on_startup)
