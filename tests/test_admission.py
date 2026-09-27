"""Il cancello al confine (spec 2026-09-27 §3): chi non amministra entra solo
dove la lista di ammissione lo lascia entrare.

Si prova con l'app VERA (`create_app`) e il confine acceso: le due valvole
della suite (`HIRIS_ALLOW_NO_TOKEN`, `HIRIS_ALLOW_NO_CSRF`) sono tolte in ogni
prova di questo file, perche' con quelle accese un rifiuto del confine
diventerebbe un 200 e ogni prova sarebbe verde senza provare niente.

La prima sezione sono i PIN: il comportamento di prima del cancello, scritto e
visto verde sul codice di partenza (302ae885) prima di cambiare qualunque
cosa. Per un amministratore, per i servizi firmati, per il ponte e per lo
sviluppo il cancello non deve cambiare niente.
"""
import asyncio
import base64
import re
import secrets
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import credenziale_ponte
from hiris.app.api import canali
from hiris.app.api.servizi import ServiziStore
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.memory.store import MemoryStore
from hiris.app.server import create_app

_INGRESS = {"X-Ingress-Path": "/api/hassio_ingress/abc/"}
_UTENTI = {"utenti": [
    {"id": "u-admin", "nome": "Paolo", "amministratore": True,
     "proprietario": True, "sistema": False},
    {"id": "u-marta", "nome": "Marta", "amministratore": False,
     "proprietario": False, "sistema": False}]}


@pytest.fixture(autouse=True)
def confine_vero(monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    yield
    close_all_stores()


def _compose(tmp_path):
    app = create_app()
    ha = AsyncMock()
    ha.start = AsyncMock()
    ha.stop = AsyncMock()
    ha.add_state_listener = MagicMock()
    ha.start_websocket = AsyncMock()
    ha.users = AsyncMock(return_value=_UTENTI)
    app["ha_client"] = ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["supervisor_ingress_cidrs"] = ["0.0.0.0/0"]  # il client di prova e' locale
    app["memory_store"] = MemoryStore(str(tmp_path / "memoria.db"))
    app["servizi"] = ServiziStore(str(tmp_path / "servizi.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def casa(aiohttp_client, tmp_path):
    app = _compose(tmp_path)
    client = await aiohttp_client(app)
    yield client
    app["memory_store"].close()
    app["servizi"].close()


def _persona(utente, **altre):
    return {**_INGRESS, "X-Remote-User-Id": utente, "X-Requested-With": "fetch", **altre}


def live_routes(app) -> set[tuple[str, str]]:
    """Ogni `(metodo, modello)` del router VERO -- HEAD, statici e rotte
    aggiunte con `add_route` compresi. Mai una regex su `server.py`: il router
    e' il fatto, il sorgente e' una sua descrizione."""
    return {(route.method, route.resource.canonical)
            for route in app.router.routes() if route.resource is not None}


def _concrete(canonical: str) -> str:
    """Un percorso vero per un modello: i parametri diventano `x`, lo statico
    un file che esiste."""
    if canonical == "/static":
        return "/static/hiris-icon.svg"
    return re.sub(r"\{[^}]+\}", "x", canonical)


async def _ask(client, method, path, headers, **kw):
    """Una richiesta con un tetto di tempo: una rotta che aspetta (un turno di
    chat, un'attesa lunga) non deve fermare la spazzata."""
    try:
        response = await asyncio.wait_for(
            client.request(method, path, headers=headers, **kw), timeout=15)
    except TimeoutError:
        return "attesa"
    return response.status


def _sign(privata, pubblica, method, path, body=b""):
    momento = time.time()
    unico = secrets.token_hex(8)
    firma = base64.b64encode(privata.sign(
        canali.materia_firmata(method, path, momento, unico, body))).decode("ascii")
    return {"X-HIRIS-Servizio": pubblica, "X-HIRIS-Momento": str(int(momento)),
            "X-HIRIS-Unico": unico, "X-HIRIS-Firma": firma}


def _service(app, ruolo):
    privata = Ed25519PrivateKey.generate()
    pubblica = base64.b64encode(
        privata.public_key().public_bytes_raw()).decode("ascii")
    adesso = time.time()
    app["servizi"].presenta(nome="retropanel", chiave=pubblica,
                            indirizzo="192.168.1.31", now_ts=adesso)
    app["servizi"].approva(pubblica, ruolo=ruolo, specie="luogo", now_ts=adesso)
    return privata, pubblica


# --- PIN: il comportamento di prima del cancello (verdi su 302ae885) ----------

#: Lo status che un AMMINISTRATORE dall'ingress riceve su ogni rotta del
#: router, misurato sul codice di partenza (302ae885, 27/09/2026) con questa
#: fixture e in quest'ordine (la spazzata scrive: `PUT /api/chat-settings`
#: viene dopo la sua lettura). I 503 sono archivi che la fixture non monta, i
#: 400 corpi vuoti: non contano i numeri, conta che il cancello non ne cambi
#: nessuno (security-constraints 2.28).
ADMIN_SWEEP_302AE885 = {
    "DELETE /api/agenda/{id}": 503, "DELETE /api/chat/conversations/{id}": 404,
    "DELETE /api/memories/{id}": 400, "GET /": 503, "GET /api/agenda": 503,
    "GET /api/briefing": 200, "GET /api/chat-settings": 200,
    "GET /api/chat/conversations": 200, "GET /api/chat/history": 200,
    "GET /api/chat/reply/{job_id}": 503, "GET /api/config": 200,
    "GET /api/constructions": 503, "GET /api/constructions/{id}": 503,
    "GET /api/entities": 503, "GET /api/executions/{id}": 503,
    "GET /api/health": 200, "GET /api/home-space": 200, "GET /api/memories": 200,
    "GET /api/mind/analysis": 503, "GET /api/mind/knowledge": 503,
    "GET /api/mind/report": 503, "GET /api/mind/watching": 503,
    "GET /api/misure": 200, "GET /api/models": 200, "GET /api/models/config": 200,
    "GET /api/pending": 503, "GET /api/services": 200, "GET /api/usage": 200,
    "GET /api/usage/history": 200, "GET /config": 503, "GET /static": 200,
    "HEAD /": 503, "HEAD /api/agenda": 503, "HEAD /api/briefing": 200,
    "HEAD /api/chat-settings": 200, "HEAD /api/chat/conversations": 200,
    "HEAD /api/chat/history": 200, "HEAD /api/chat/reply/{job_id}": 503,
    "HEAD /api/config": 200, "HEAD /api/constructions": 503,
    "HEAD /api/constructions/{id}": 503, "HEAD /api/entities": 503,
    "HEAD /api/executions/{id}": 503, "HEAD /api/health": 200,
    "HEAD /api/home-space": 200, "HEAD /api/memories": 200,
    "HEAD /api/mind/analysis": 503, "HEAD /api/mind/knowledge": 503,
    "HEAD /api/mind/report": 503, "HEAD /api/mind/watching": 503,
    "HEAD /api/misure": 200, "HEAD /api/models": 200,
    "HEAD /api/models/config": 200, "HEAD /api/pending": 503,
    "HEAD /api/services": 200, "HEAD /api/usage": 200,
    "HEAD /api/usage/history": 200, "HEAD /config": 503, "HEAD /static": 200,
    "PATCH /api/memories/{id}": 400, "POST /api/agenda/read": 503,
    "POST /api/chat": 400, "POST /api/chat/conversations": 200,
    "POST /api/chat/conversations/{id}/resume": 404,
    "POST /api/constructions/{id}/confirm": 503,
    "POST /api/constructions/{id}/reject": 503,
    "POST /api/constructions/{id}/restore": 503, "POST /api/mcp": 401,
    "POST /api/mind/judgment": 503, "POST /api/mind/objective": 503,
    "POST /api/proposals/{id}/done": 503, "POST /api/proposals/{id}/redo": 503,
    "POST /api/proposals/{id}/reject": 503, "POST /api/reasoning/claim": 401,
    "POST /api/reasoning/submit": 401, "POST /api/services/approve": 400,
    "POST /api/services/present": 403, "POST /api/services/revoke": 404,
    "POST /api/services/window/close": 200, "POST /api/services/window/open": 200,
    "POST /api/usage/reset": 409, "PUT /api/chat-settings": 200,
    "PUT /api/models/config": 200,
}


async def admin_sweep(client) -> dict:
    statuses = {}
    for method, canonical in sorted(live_routes(client.app)):
        kw = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
        statuses[f"{method} {canonical}"] = await _ask(
            client, method, _concrete(canonical), _persona("u-admin"), **kw)
    return statuses


@pytest.mark.asyncio
async def test_PIN_un_amministratore_dall_ingress_riceve_cio_che_riceveva(casa):
    """Pin 1 (2.28): la spazzata dell'amministratore su ogni rotta, uguale
    status per status a quella misurata sul codice di partenza."""
    statuses = await admin_sweep(casa)

    cambiate = {rotta: (atteso, statuses.get(rotta))
                for rotta, atteso in ADMIN_SWEEP_302AE885.items()
                if statuses.get(rotta) != atteso}
    assert not cambiate, f"per l'amministratore è cambiato: {cambiate}"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,status", [
    ("GET", "/api/nope", 404),
    ("GET", "/api/memories/", 404),
    ("OPTIONS", "/api/chat", 405),
    ("PROPFIND", "/", 405),
    ("HEAD", "/api/health", 200),
])
async def test_PIN_rotte_ignote_e_verbi_strani_per_l_amministratore(casa, method, path, status):
    """Pin 2: per l'amministratore una rotta che non c'e' resta un 404 e un
    verbo che non c'e' un 405 -- il cancello chiude chi non amministra, non
    cambia le risposte di chi amministra."""
    assert await _ask(casa, method, path, _persona("u-admin")) == status


@pytest.mark.asyncio
@pytest.mark.parametrize("path,statuses", [
    ("/static/hiris-icon.svg", {200}),
    ("/static/../server.py", {403, 404}),
    ("/static/%2e%2e/server.py", {403, 404}),
    ("/static/", {403, 404}),
])
async def test_PIN_lo_statico_per_l_amministratore(casa, path, statuses):
    """Pin 3: lo statico si serve, e la protezione di aiohttp dalla risalita
    delle cartelle resta la sua."""
    assert await _ask(casa, "GET", path, _persona("u-admin")) in statuses


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,status", [
    ("PUT", "/api/models/config", 200),
    ("POST", "/api/usage/reset", 409),
])
async def test_PIN_un_servizio_utente_firmato_passa_come_prima(casa, method, path, status):
    """Pin 4: un servizio approvato come `utente` raggiunge queste rotte oggi
    (`consente_metodo` guarda solo lettura contro scrittura -- rischio
    dichiarato, security-constraints 5.9): il cancello non lo tocca, perche'
    vale solo per le persone dall'ingress."""
    privata, pubblica = _service(casa.app, "utente")
    body = b"{}"
    headers = {**_sign(privata, pubblica, method, path, body),
               "Content-Type": "application/json", "X-Requested-With": "fetch"}

    assert await _ask(casa, method, path, headers, data=body) == status


@pytest.mark.asyncio
async def test_PIN_l_amministratore_vede_TUTTI_i_ricordi(casa):
    """Pin 5 (3.6): l'amministratore vede ogni ricordo, orfani compresi."""
    store = casa.app["memory_store"]
    store.remember("la caldaia fa rumore", said_by="persona:u-marta")
    store.remember("il cane dorme in cucina", said_by="persona:u-admin")
    store.remember("un ricordo senza autore")

    corpo = await (await casa.get("/api/memories", headers=_persona("u-admin"))).json()

    assert sorted(m["testo"] for m in corpo["memories"]) == [
        "il cane dorme in cucina", "la caldaia fa rumore", "un ricordo senza autore"]


@pytest.mark.asyncio
async def test_PIN_impostazioni_e_salute_per_l_amministratore(casa):
    """Pin 6: le chiavi che l'amministratore riceve da `/api/chat-settings` e
    da `/api/health` (la diagnostica compresa)."""
    impostazioni = await (await casa.get("/api/chat-settings",
                                         headers=_persona("u-admin"))).json()
    salute = await (await casa.get("/api/health", headers=_persona("u-admin"))).json()

    assert "system_prompt" in impostazioni
    assert set(salute) == {"status", "version", "build", "ponte", "riparazione",
                           "istantanea"}


@pytest.mark.asyncio
async def test_PIN_il_ruolo_NON_si_legge_per_chi_non_e_una_persona(casa, monkeypatch):
    """Pin 7 (2.19): firma, credenziale di turno, accoppiamento e sviluppo
    non chiedono mai a Home Assistant chi e' amministratore."""
    app = casa.app
    privata, pubblica = _service(app, "lettore")
    await casa.post("/api/services/window/open", headers=_persona("u-admin"))
    app["ha_client"].users.reset_mock()

    firmata = await casa.get("/api/health",
                             headers=_sign(privata, pubblica, "GET", "/api/health"))
    turno = await casa.get("/api/health", headers=credenziale_ponte(app, "segreto-di-turno"))
    presentata = await casa.post("/api/services/present",
                                 json={"nome": "x", "chiave": _service_key()})
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")
    sviluppo = await casa.get("/api/health")

    assert [firmata.status, turno.status, presentata.status, sviluppo.status] == [
        200, 200, 200, 200]
    assert app["ha_client"].users.await_count == 0


def _service_key() -> str:
    return base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode("ascii")


@pytest.mark.asyncio
async def test_PIN_le_intestazioni_del_rifiuto_401(casa):
    """Pin 8: il rifiuto di chi non ha credenziali esce dal middleware prima
    di `_security_headers`, e oggi porta solo le intestazioni di aiohttp."""
    risposta = await casa.get("/api/health")

    assert risposta.status == 401
    assert "Content-Security-Policy" not in risposta.headers
    assert risposta.headers["Content-Type"].startswith("application/json")
