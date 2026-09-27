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
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiohttp import web
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import credenziale_ponte, firma, servizio_approvato
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
     "proprietario": False, "sistema": False},
    {"id": "u-lettore", "nome": "Lia", "amministratore": False,
     "sola_lettura": True, "proprietario": False, "sistema": False}]}


@pytest.fixture(autouse=True)
def confine_vero(monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    yield
    close_all_stores()


def _compose(tmp_path, *, access=None):
    app = create_app()
    if access is not None:
        app["non_admin_access"] = access
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
    privata, pubblica = servizio_approvato(casa.app, "utente")
    body = b"{}"
    headers = {**firma(privata, pubblica, method, path, body),
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
    privata, pubblica = servizio_approvato(app, "lettore")
    await casa.post("/api/services/window/open", headers=_persona("u-admin"))
    app["ha_client"].users.reset_mock()

    firmata = await casa.get("/api/health",
                             headers=firma(privata, pubblica, "GET", "/api/health"))
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


# --- il cancello (spec 2026-09-27 §3, security-constraints 2.1-2.29) --------

from hiris.app.api import admission
from hiris.app.api.admission import (
    ADMISSION,
    NOT_ADMITTED,
    OPTION_OFF,
    ROLES_UNREADABLE,
    UNKNOWN_PERSON,
)


def _pagina(testo: str) -> bytes:
    """La pagina di rifiuto di un guscio, come la compone il cancello: la
    forma e' fissa, cambia solo il testo."""
    return admission._PAGES[testo]


@pytest_asyncio.fixture
async def aperta(aiohttp_client, tmp_path):
    """L'opzione accesa: chi non amministra entra dove la lista lo ammette."""
    app = _compose(tmp_path, access=True)
    client = await aiohttp_client(app)
    yield client
    app["memory_store"].close()
    app["servizi"].close()


@pytest_asyncio.fixture
async def chiusa(aiohttp_client, tmp_path):
    """L'opzione spenta, esplicita: nessuna prova si appoggia al difetto."""
    app = _compose(tmp_path, access=False)
    client = await aiohttp_client(app)
    yield client
    app["memory_store"].close()
    app["servizi"].close()


_MUTANTI = ("POST", "PUT", "PATCH", "DELETE")


async def _risposta(client, method, path, headers, **kw):
    if path.startswith("//"):
        # Il client di prova leggerebbe `//api/...` come un indirizzo di un
        # altro host: la barra doppia si manda nel percorso, come un browser.
        response = await asyncio.wait_for(client.session.request(
            method, client.make_url("/").with_path(path, encoded=True),
            headers=headers, **kw), timeout=15)
    else:
        response = await asyncio.wait_for(
            client.request(method, path, headers=headers, **kw), timeout=15)
    return response.status, await response.read()


def _rifiuto_json(testo):
    import json
    return json.dumps({"errore": testo}).encode("utf-8")


async def _gate_refused(client, method, path, headers, testo=NOT_ADMITTED, **kw):
    status, body = await _risposta(client, method, path, headers, **kw)
    return status == 403 and body == _rifiuto_json(testo)


def test_la_lista_nomina_solo_rotte_VERE_del_router():
    """Nessun fantasma (2.27): ogni voce e' una rotta del router vivo.

    Mutazione ESEGUITA: tolta `add_get("/api/memories", ...)` da `server.py`
    -- rossa col nome della voce."""
    vive = live_routes(create_app())
    fantasmi = [(m, c) for m, c, _ in ADMISSION if (m, c) not in vive]

    assert not fantasmi, f"voci della lista che il router non ha: {fantasmi}"


def test_la_derivazione_dal_router_VEDE_le_rotte():
    """Il pavimento (2.27): se la derivazione si rompesse, le prove sotto
    sarebbero verdi su un insieme vuoto.

    Mutazione ESEGUITA: derivare solo le rotte con `{` nel modello -- rossa."""
    vive = live_routes(create_app())

    assert len(vive) > 40, f"ne ho derivate solo {len(vive)}"
    assert ("HEAD", "/api/health") in vive and ("GET", "/static") in vive


def test_ogni_voce_porta_la_sua_RAGIONE_e_nessuna_e_doppia():
    assert len({(m, c) for m, c, _ in ADMISSION}) == len(ADMISSION)
    for method, canonical, reason in ADMISSION:
        assert method == method.upper() and method != "HEAD", (method, canonical)
        assert canonical.startswith("/"), canonical
        assert reason and len(reason) > 20, f"«{method} {canonical}» senza ragione"


#: Cio' che chi non amministra NON deve mai raggiungere (security-constraints
#: 2.22). Non e' una copia della lista: e' l'altra meta' della decisione, e la
#: prova sotto dice che le due meta' non si toccano.
_VIETATE_PREFISSI = ("/api/usage", "/api/models", "/api/entities", "/api/home-space",
                     "/api/briefing", "/api/mind/", "/api/services",
                     "/api/constructions", "/api/proposals", "/api/misure",
                     "/api/reasoning/", "/api/mcp")
_VIETATE_ESATTE = {("PUT", "/api/chat-settings"), ("PATCH", "/api/memories/{id}"),
                   ("DELETE", "/api/memories/{id}")}


def test_la_lista_NON_tocca_le_rotte_vietate():
    """Mutazione ESEGUITA: aggiunta a `ADMISSION` la voce `GET /api/usage` --
    rossa."""
    toccate = [(m, c) for m, c, _ in ADMISSION
               if c.startswith(_VIETATE_PREFISSI) or (m, c) in _VIETATE_ESATTE]

    assert not toccate, f"la lista ammette rotte vietate: {toccate}"



_CHI = {"amministratore": "u-admin", "utente": "u-marta",
        "ignoto": "u-sconosciuto", "anonimo": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("chi", list(_CHI))
@pytest.mark.parametrize("accesa", [True, False])
@pytest.mark.parametrize("ammessa", [True, False])
async def test_la_TABELLA_delle_regole(aiohttp_client, tmp_path, chi, accesa, ammessa):
    """2.6: {amministratore, utente, ignoto, anonimo} x {accesa, spenta} x
    {ammessa, no}. Passa l'amministratore sempre; l'utente solo su una rotta
    ammessa con l'opzione accesa; ignoto e anonimo mai."""
    app = _compose(tmp_path, access=accesa)
    client = await aiohttp_client(app)
    utente = _CHI[chi]
    headers = ({**_INGRESS, "X-Requested-With": "fetch"} if utente is None
               else _persona(utente))
    path = "/api/config" if ammessa else "/api/models"
    passa = chi == "amministratore" or (chi == "utente" and accesa and ammessa)

    status, body = await _risposta(client, "GET", path, headers)

    if not accesa:
        atteso = OPTION_OFF
    elif chi in ("ignoto", "anonimo"):
        atteso = UNKNOWN_PERSON
    else:
        atteso = NOT_ADMITTED
    if passa:
        assert status == 200, body
    else:
        assert (status, body) == (403, _rifiuto_json(atteso))
    app["memory_store"].close()
    app["servizi"].close()


@pytest.mark.asyncio
async def test_ogni_rotta_NON_in_lista_e_chiusa_a_chi_non_amministra(aperta):
    """**Il cancello, derivato dal router vivo** (2.27): per ogni rotta che la
    lista non nomina -- HEAD, statico e rotte future compresi -- una persona
    non amministratrice riceve lo stesso 403, senza che nessuno l'abbia
    elencata qui.

    Mutazione ESEGUITA: aggiunta a `server.py` una
    `router.add_get("/api/prova", handle_config)` senza toccare la lista --
    la prova la vede e resta verde, perche' la rotta nasce chiusa. Che la
    derivazione non si sia rotta lo dice il pavimento qui sopra."""
    ammesse = {(m, c) for m, c, _ in ADMISSION}
    aperte = []
    for method, canonical in sorted(live_routes(aperta.app)):
        guardata = "GET" if method == "HEAD" else method
        if (guardata, canonical) in ammesse:
            continue
        kw = {"json": {}} if method in _MUTANTI else {}
        status, body = await _risposta(aperta, method, _concrete(canonical),
                                       _persona("u-marta"), **kw)
        if method == "HEAD":
            if status != 403:
                aperte.append((method, canonical, status))
        elif (status, body) != (403, _rifiuto_json(NOT_ADMITTED)):
            aperte.append((method, canonical, status))

    assert not aperte, f"rotte fuori lista raggiunte da chi non amministra: {aperte}"


@pytest.mark.asyncio
async def test_con_l_opzione_spenta_NIENTE_si_apre_a_chi_non_amministra(chiusa):
    """2.7: gusci, statico e `/api/health` compresi."""
    aperte = []
    for method, canonical in sorted(live_routes(chiusa.app)):
        kw = {"json": {}} if method in _MUTANTI else {}
        status, body = await _risposta(chiusa, method, _concrete(canonical),
                                       _persona("u-marta"), **kw)
        if status != 403 or (method != "HEAD" and body not in (
                _rifiuto_json(OPTION_OFF), _pagina(OPTION_OFF))):
            aperte.append((method, canonical, status))

    assert not aperte, aperte


@pytest.mark.asyncio
async def test_ogni_voce_della_lista_si_APRE_a_chi_non_amministra(aperta):
    """La contropartita: una voce ammessa non riceve il rifiuto del cancello
    (riceve cio' che il suo gestore risponde)."""
    chiuse = []
    for method, canonical, _ in ADMISSION:
        kw = {"json": {}} if method in _MUTANTI else {}
        if await _gate_refused(aperta, method, _concrete(canonical),
                               _persona("u-marta"), **kw):
            chiuse.append((method, canonical))

    assert not chiuse


@pytest.mark.asyncio
async def test_una_rotta_NUOVA_nasce_chiusa(aiohttp_client, tmp_path):
    """Una rotta aggiunta al router senza toccare la lista e' chiusa a chi non
    amministra e aperta all'amministratore."""
    app = _compose(tmp_path, access=True)

    async def prova(request):
        return web.json_response({"ok": True})

    app.router.add_get("/api/prova", prova)
    client = await aiohttp_client(app)

    assert await _gate_refused(client, "GET", "/api/prova", _persona("u-marta"))
    assert (await _risposta(client, "GET", "/api/prova", _persona("u-admin")))[0] == 200
    app["memory_store"].close()
    app["servizi"].close()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/nope"), ("GET", "/api/memories/"), ("OPTIONS", "/api/chat"),
    ("PROPFIND", "/api/chat"), ("GET", "/api/memories%2F1"),
    ("GET", "//api/memories"), ("GET", "/api/Memories"),
    ("HEAD", "/api/models/config"),
])
async def test_cio_che_non_risolve_esattamente_e_CHIUSO(aperta, method, path):
    """2.2, 2.11-2.14: rotte che non esistono, barre in piu', maiuscole,
    codifiche e verbi strani ricevono lo stesso 403 di una rotta vietata --
    mai 404 o 405, che direbbero cosa esiste (2.16). HEAD solo dove e' ammesso
    GET (R-2.13): `/api/models/config` no."""
    status, body = await _risposta(aperta, method, path, _persona("u-marta"))

    assert status == 403
    if method != "HEAD":
        # La forma segue il percorso, non la rotta: `//api/...` non comincia
        # per `/api/` ed e' la pagina -- la stessa per ogni percorso cosi'.
        assert body == (_rifiuto_json(NOT_ADMITTED) if path.startswith("/api/")
                        else _pagina(NOT_ADMITTED))


@pytest.mark.asyncio
async def test_il_PROPFIND_sul_guscio_e_la_stessa_pagina_di_rifiuto(aperta):
    status, body = await _risposta(aperta, "PROPFIND", "/", _persona("u-marta"))

    assert (status, body) == (403, _pagina(NOT_ADMITTED))


@pytest.mark.asyncio
async def test_la_query_non_apre_niente_e_non_chiude_la_voce_esatta(aperta):
    """`/api/memories?x=/api/chat` e' la voce ammessa `GET /api/memories`: la
    query non si guarda, in nessuno dei due versi."""
    status, _ = await _risposta(aperta, "GET", "/api/memories?x=/api/chat",
                                _persona("u-marta"))

    assert status == 200


@pytest.mark.asyncio
async def test_HEAD_passa_dove_passa_GET(aperta):
    assert (await _risposta(aperta, "HEAD", "/api/health", _persona("u-marta")))[0] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/static/../server.py", "/static/%2e%2e/server.py",
                                  "/static/"])
async def test_lo_statico_non_risale_le_cartelle(aperta, path):
    """2.15: lo statico e' ammesso per IDENTITA' della risorsa, e la
    protezione di aiohttp resta la sua."""
    assert (await _risposta(aperta, "GET", path, _persona("u-marta")))[0] != 200


@pytest.mark.asyncio
async def test_lo_statico_si_serve_a_chi_non_amministra(aperta):
    assert (await _risposta(aperta, "GET", "/static/hiris-icon.svg",
                            _persona("u-marta")))[0] == 200


def test_lo_statico_e_ammesso_solo_come_RISORSA_STATICA():
    """Una rotta qualunque che si chiamasse `/static` non erediterebbe
    l'ammissione della cartella.

    Mutazione ESEGUITA: togliere il controllo `isinstance(..., StaticResource)`
    -- rossa."""
    app = web.Application()

    async def finta(request):
        return web.Response()

    app.router.add_get("/static", finta)
    [route] = [r for r in app.router.routes() if r.method == "GET"]

    class _Match:
        pass

    match = _Match()
    match.route = route
    assert admission.admitted("GET", match) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
async def test_nessun_ORACOLO_sull_esistenza_di_un_ricordo(aperta, method):
    """2.16: un ricordo che c'e' e uno che non c'e' rispondono uguale, e
    quello che c'e' resta com'era."""
    store = aperta.app["memory_store"]
    ident = store.remember("la caldaia fa rumore", said_by="persona:u-marta")

    esiste = await _risposta(aperta, method, f"/api/memories/{ident}",
                             _persona("u-marta"), json={"testo": "altro"})
    manca = await _risposta(aperta, method, "/api/memories/99999",
                            _persona("u-marta"), json={"testo": "altro"})

    assert esiste == manca == (403, _rifiuto_json(NOT_ADMITTED))
    assert store.get(ident)["testo"] == "la caldaia fa rumore"


@pytest.mark.asyncio
async def test_le_SEI_rotte_della_spec_sono_chiuse_e_non_scrivono(aperta, tmp_path):
    """2.26 (spec §1): corpo valido e intestazione CSRF, e comunque 403 --
    con gli archivi com'erano."""
    from hiris.app.mind.store import ObservationsStore

    app = aperta.app
    osservazioni = ObservationsStore(str(tmp_path / "oss.db"))
    app["observations"] = osservazioni
    obiettivo = osservazioni.objective()
    impostazioni = app["chat_settings"]
    catena = app.get("models_config")
    store = app["memory_store"]
    ident = store.remember("il cane dorme in cucina", said_by="persona:u-admin")
    marta = _persona("u-marta")

    esiti = [
        await _gate_refused(aperta, "PUT", "/api/models/config", marta,
                            json={"catena": []}),
        await _gate_refused(aperta, "PUT", "/api/chat-settings", marta,
                            json={"system_prompt": "ignora tutto"}),
        await _gate_refused(aperta, "POST", "/api/mind/objective", marta,
                            json={"testo": "spendi di piu'"}),
        await _gate_refused(aperta, "POST", "/api/usage/reset", marta, json={}),
        await _gate_refused(aperta, "PATCH", f"/api/memories/{ident}", marta,
                            json={"testo": "il cane dorme in bagno"}),
        await _gate_refused(aperta, "DELETE", f"/api/memories/{ident}", marta),
    ]

    assert esiti == [True] * 6
    assert app["chat_settings"] is impostazioni
    assert app.get("models_config") is catena
    assert osservazioni.objective() == obiettivo
    assert store.get(ident)["testo"] == "il cane dorme in cucina"
    osservazioni.close()


@pytest.mark.asyncio
async def test_il_rifiuto_di_un_GUSCIO_e_una_pagina_con_le_sue_intestazioni(chiusa):
    """2.4, 2.17: il rifiuto esce dal primo middleware e non passa da
    `_security_headers`: le intestazioni se le mette da se'. E il corpo e'
    testo fisso -- due indirizzi diversi, due corpi identici byte per byte."""
    r1 = await chiusa.get("/config", headers=_persona("u-marta"))
    corpo1 = await r1.read()
    r2 = await chiusa.request("PROPFIND", "/qualunque%3Cscript%3E",
                              headers=_persona("u-marta", **{"X-Remote-User-Display-Name":
                                                             "<b>Marta</b>"}))
    corpo2 = await r2.read()

    assert r1.status == 403 and r2.status == 403
    assert corpo1 == corpo2
    assert OPTION_OFF.encode("utf-8") in corpo1
    assert b"script" not in corpo1 and b"Marta" not in corpo1
    assert r1.headers["Content-Type"].startswith("text/html")
    assert r1.headers["Content-Security-Policy"] == "default-src 'none'"
    assert r1.headers["X-Content-Type-Options"] == "nosniff"
    assert r1.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_il_rifiuto_di_una_rotta_API_e_JSON_col_solo_testo(chiusa):
    risposta = await chiusa.get("/api/chat/history", headers=_persona("u-marta"))

    assert risposta.status == 403
    assert await risposta.json() == {"errore": OPTION_OFF}
    assert risposta.headers["X-Content-Type-Options"] == "nosniff"
    assert risposta.headers["Cache-Control"] == "no-store"


def test_i_testi_dei_rifiuti_sono_quelli_DECISI():
    """Decisione 7 del coordinatore e fix round 1 (punto 11): alla lettera."""
    assert UNKNOWN_PERSON == (
        "Home Assistant non mi ha detto chi sei: HIRIS risponde solo agli "
        "utenti di Home Assistant che riconosce. Se sei appena stato aggiunto, "
        "riprova tra un minuto.")
    assert OPTION_OFF == ("HIRIS in questa casa è riservato agli amministratori: "
                          "chiedi a chi lo gestisce di attivarlo per tutti.")
    assert NOT_ADMITTED == "Questa parte di HIRIS è riservata agli amministratori."
    assert ROLES_UNREADABLE == ("Non ho potuto leggere i ruoli da Home Assistant: "
                                "riprova tra poco.")


@pytest.mark.asyncio
async def test_il_rifiuto_si_scrive_a_INFO_col_MODELLO_e_la_chiave(aperta, caplog):
    """2.18: il modello della rotta (mai il percorso decodificato: un `%0A`
    farebbe una riga finta), la chiave del soggetto, mai il nome.

    Mutazione ESEGUITA: `request.path` al posto del modello -- rossa."""
    caplog.set_level("INFO", logger="hiris.app.api.admission")

    await aperta.get("/api/constructions/abc%0Acancello:%20concesso",
                     headers=_persona("u-marta", **{"X-Remote-User-Display-Name":
                                                    "Nome Riservato"}))

    [riga] = [r for r in caplog.records if r.name == "hiris.app.api.admission"]
    testo = riga.getMessage()
    assert riga.levelname == "INFO"
    assert "/api/constructions/{id}" in testo and "persona:u-marta" in testo
    assert "\n" not in testo and "concesso" not in testo
    assert "Nome Riservato" not in testo and "Marta" not in testo


@pytest.mark.asyncio
async def test_il_CSRF_resta_davanti_alle_rotte_ammesse(aperta):
    """2.3: il cancello dice DOVE si entra, non toglie il resto del confine."""
    headers = {**_INGRESS, "X-Remote-User-Id": "u-marta"}

    risposta = await aperta.post("/api/chat", json={"message": "ciao"}, headers=headers)

    assert risposta.status == 403
    assert await risposta.json() == {"error": "csrf_required"}


@pytest.mark.asyncio
async def test_il_flusso_SSE_si_ferma_prima_di_partire(chiusa):
    """2.21: la chat in streaming e' `POST /api/chat` con Accept
    event-stream: il cancello risponde prima."""
    risposta = await chiusa.post(
        "/api/chat", json={"message": "ciao"},
        headers=_persona("u-marta", Accept="text/event-stream"))

    assert risposta.status == 403
    assert await risposta.json() == {"errore": OPTION_OFF}


@pytest.mark.asyncio
async def test_senza_il_client_di_HA_nessuna_persona_entra(aiohttp_client, tmp_path):
    """2.29: nessun ramo «senza client passa»."""
    app = _compose(tmp_path, access=True)
    app["ha_client"] = None
    client = await aiohttp_client(app)

    for utente in ("u-admin", "u-marta"):
        assert await _gate_refused(client, "GET", "/api/config", _persona(utente),
                                   testo=ROLES_UNREADABLE)
    app["memory_store"].close()
    app["servizi"].close()


@pytest.mark.asyncio
async def test_ruoli_ILLEGGIBILI_chiudono_anche_owner_col_suo_testo(
        aperta, caplog, monkeypatch):
    """R-2.8: il proprietario e' chiuso fuori, col testo che dice perche'; la
    riga d'errore esce una volta; e appena Home Assistant risponde, si
    rientra.

    Mutazione ESEGUITA: `letto` ignorato (sempre il testo della lista) --
    rossa."""
    from hiris.app.api import soffitto

    caplog.set_level("ERROR", logger="hiris.app.api.soffitto")
    ha = aperta.app["ha_client"]
    ha.users = AsyncMock(return_value={"errore": "Home Assistant non ha risposto"})
    adesso = [1_000_000.0]
    monkeypatch.setattr(soffitto.time, "time", lambda: adesso[0])

    rifiuti = [await _gate_refused(aperta, "GET", "/api/config", _persona("u-admin"),
                                   testo=ROLES_UNREADABLE) for _ in range(3)]
    errori = [r for r in caplog.records
              if r.name == "hiris.app.api.soffitto" and r.levelname == "ERROR"]

    assert rifiuti == [True, True, True]
    assert len(errori) == 1
    ha.users = AsyncMock(return_value=_UTENTI)
    adesso[0] += soffitto.GATE_FAILURE_HOLD_S
    assert (await _risposta(aperta, "GET", "/api/config", _persona("u-admin")))[0] == 200


@pytest.mark.asyncio
async def test_un_guasto_NON_si_moltiplica_per_ogni_asset(aperta):
    """R-2.9: venti file della pagina durante un guasto, UNA chiamata a
    `config/auth/list`.

    Mutazione ESEGUITA: `hold_failure_s` a zero nel cancello -- rossa
    (venti chiamate)."""
    ha = aperta.app["ha_client"]
    ha.users = AsyncMock(return_value={"errore": "Home Assistant non ha risposto"})

    for _ in range(20):
        await aperta.get("/static/hiris-icon.svg", headers=_persona("u-marta"))

    assert ha.users.await_count <= 2


@pytest.mark.asyncio
async def test_la_voce_di_menu_che_FALLISCE_non_apre_niente(chiusa, monkeypatch):
    """1.7: il cancello legge l'opzione e il ruolo, mai l'esito della voce di
    menu. `update_panel` fallisce, l'opzione e' spenta: chi non amministra
    resta fuori."""
    from hiris.app import panel_visibility

    app = chiusa.app
    ha = app["ha_client"]
    ha.ws_ready = asyncio.Event()
    ha.ws_ready.set()
    ha.update_panel = AsyncMock(return_value={"errore": "rotto", "codice": "unknown_error"})
    ha.panels = AsyncMock(return_value={"errore": "rotto"})

    async def slug(_token):
        return {"slug": "6354e165_hiris"}

    monkeypatch.setattr(panel_visibility, "read_own_slug", slug)
    await panel_visibility.sync_panel_visibility(app)

    assert ha.update_panel.await_count == 1
    assert await _gate_refused(chiusa, "GET", "/api/config", _persona("u-marta"),
                               testo=OPTION_OFF)


def test_il_cancello_non_conosce_la_VOCE_DI_MENU():
    """1.7: nessun import del modulo della voce di menu nel cancello."""
    import ast
    import pathlib
    radice = pathlib.Path(admission.__file__).parent
    for nome in ("admission.py", "middleware_internal_auth.py"):
        albero = ast.parse((radice / nome).read_text(encoding="utf-8"))
        moduli = {getattr(n, "module", None) or "" for n in ast.walk(albero)
                  if isinstance(n, ast.ImportFrom)}
        moduli |= {a.name for n in ast.walk(albero) if isinstance(n, ast.Import)
                   for a in n.names}
        assert not any("panel_visibility" in m for m in moduli), nome


def test_il_cancello_sta_DOPO_il_soggetto_e_PRIMA_del_gestore():
    """2.1: nel ramo dell'ingress, fra `request["soggetto"] = ...` e
    `return await handler(request)`.

    Mutazione ESEGUITA: spostato il cancello dopo `handler` -- rossa."""
    import ast
    import inspect

    from hiris.app.api import middleware_internal_auth as mia

    albero = ast.parse(inspect.getsource(mia.internal_auth_middleware))
    ramo = next(n for n in ast.walk(albero) if isinstance(n, ast.If)
                and "_is_supervisor_ingress" in ast.unparse(n.test))
    righe = [ast.unparse(s) for s in ramo.body]
    soggetto = next(i for i, r in enumerate(righe) if "request['soggetto']" in r)
    cancello = next(i for i, r in enumerate(righe) if "admission_refusal" in r)
    gestore = next(i for i, r in enumerate(righe) if "await handler(request)" in r)

    assert soggetto < cancello < gestore


@pytest.mark.asyncio
async def test_la_salute_di_chi_non_amministra_dice_solo_STATO_e_VERSIONE(aperta):
    """R-2.23 e fix round 1 (I1): la diagnostica (`ponte`, `riparazione`,
    `istantanea`) resta all'amministratore; l'impronta del guscio (`build`),
    che il guscio porta gia' scritta, arriva a tutti."""
    corpo = await (await aperta.get("/api/health", headers=_persona("u-marta"))).json()
    admin = await (await aperta.get("/api/health", headers=_persona("u-admin"))).json()

    assert set(corpo) == {"status", "version", "build"}
    assert set(admin) == {"status", "version", "build", "ponte", "riparazione",
                          "istantanea"}


@pytest.mark.asyncio
async def test_chi_ha_SOLA_LETTURA_entra_come_chi_non_amministra(aperta):
    assert (await _risposta(aperta, "GET", "/api/config", _persona("u-lettore")))[0] == 200
    assert await _gate_refused(aperta, "GET", "/api/models", _persona("u-lettore"))


# --- la chat segue i diritti di Home Assistant (ruling R-2.10b, R-2.25) -----

from hiris.app.api.soffitto import (
    ADMIN_READS_REFUSAL,
    boundary_role,
    ceiling_for,
    consente,
)
from hiris.app.home_space.tools import ToolDispatcher


class _HaLettore:
    """Home Assistant che risponde: conta cosa gli si chiede."""

    def __init__(self):
        self.chiesto = []

    async def system_log(self):
        self.chiesto.append("system_log/list")
        return {"voci": [{"level": "ERROR", "message": "zigbee giu'"}]}

    async def automation_traces(self, automation_id):
        self.chiesto.append("trace/list")
        return {"esecuzioni": []}

    async def automation_trace(self, automation_id, run_id):
        self.chiesto.append("trace/get")
        return {"esecuzione": {}}


class _Porta:
    def __init__(self):
        self.eseguite = []

    async def execute(self, arguments, *, actor, subject):
        self.eseguite.append(arguments["servizio"])
        return {"esito": "fatto"}


_PERSONA_MARTA = {"specie": "persona", "id": "u-marta"}


def _chat(ruolo, *, ha=None, porta=None):
    soffitto = None if ruolo is None else consente(_PERSONA_MARTA, ruolo=ruolo)
    return ToolDispatcher(None, None, ha=ha, actuator=porta, soffitto=soffitto,
                          subject=_PERSONA_MARTA)


@pytest.mark.asyncio
@pytest.mark.parametrize("strumento,argomenti", [
    ("system_log", {}),
    ("automation_trace", {"entita": "automation.luci"}),
    ("automation_trace", {"entita": "automation.luci", "esecuzione": "r-1"}),
])
@pytest.mark.parametrize("ruolo", ["utente", "lettore"])
async def test_le_letture_RISERVATE_agli_amministratori_non_escono_dalla_chat(
        strumento, argomenti, ruolo):
    """`system_log/list`, `trace/list` e `trace/get` sono
    `@websocket_api.require_admin` in Core 2026.9.3 (verificato il 27/09/2026):
    HIRIS, che parla da amministratore, non li legge per chi non lo e'.

    Mutazione ESEGUITA: tolto il controllo da `_system_log` -- rossa (la voce
    del registro arriva al modello)."""
    ha = _HaLettore()

    esito = await _chat(ruolo, ha=ha).dispatch(strumento, argomenti)

    assert esito == {"errore": ADMIN_READS_REFUSAL}
    assert ha.chiesto == [], "Home Assistant e' stato interrogato lo stesso"


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo", ["amministratore", None])
async def test_l_amministratore_e_i_turni_senza_persona_leggono_come_prima(ruolo):
    """Il metro opposto: chi amministra, e i turni che nessuna persona ha
    aperto (`soffitto=None`: promesse, osservatore), leggono il registro."""
    ha = _HaLettore()

    esito = await _chat(ruolo, ha=ha).dispatch("system_log", {})

    assert esito["voci"][0]["message"] == "zigbee giu'"


@pytest.mark.asyncio
async def test_chi_ha_SOLA_LETTURA_non_comanda_dalla_chat():
    """R-2.10b: a una persona del gruppo `system-read-only` Home Assistant
    nega di chiamare servizi (READ_ONLY_POLICY). Dalla chat, lo stesso.

    Mutazione ESEGUITA: tolto il controllo da `_execute` -- rossa (la porta
    esegue)."""
    porta = _Porta()

    esito = await _chat("lettore", porta=porta).dispatch(
        "execute", {"servizio": "light.turn_on", "bersaglio": {"entity_id": ["light.x"]}})

    assert "sola lettura" in esito["errore"]
    assert porta.eseguite == []


@pytest.mark.asyncio
async def test_chi_e_UTENTE_comanda_dalla_chat_come_prima():
    porta = _Porta()

    await _chat("utente", porta=porta).dispatch(
        "execute", {"servizio": "light.turn_on", "bersaglio": {"entity_id": ["light.x"]}})

    assert porta.eseguite == ["light.turn_on"]


@pytest.mark.asyncio
async def test_il_ruolo_di_SOLA_LETTURA_arriva_al_soffitto_della_chat(casa):
    """Dalla riga di Home Assistant al soffitto: `sola_lettura` diventa
    `lettore`, che legge e non comanda ne' costruisce.

    Mutazione ESEGUITA: `_role_of` senza il ramo `sola_lettura` -- rossa."""
    soffitto = await ceiling_for(casa.app, {"specie": "persona", "id": "u-lettore"})

    assert soffitto["ruolo"] == "lettore"
    assert (soffitto["leggere"], soffitto["comandare"], soffitto["costruire"],
            soffitto["amministrare"]) == (True, False, False, False)
    visto = await boundary_role(casa.app, {"specie": "persona", "id": "u-lettore"})
    assert (visto.role, visto.read, visto.known) == ("lettore", True, True)


@pytest.mark.asyncio
async def test_lo_SVILUPPO_non_si_restringe_per_ruolo(monkeypatch):
    """Lo sviluppo (`HIRIS_ALLOW_NO_TOKEN`) ha l'autenticazione spenta per
    definizione: `execute` e il registro restano aperti (fix round 1, I3,
    `soffitto.denies`).

    Mutazione ESEGUITA: `denies` senza l'eccezione dello sviluppo -- rossa
    (e rossa anche `test_chat_briefing::test_conversazione_4`)."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")
    sviluppo = {"specie": "sviluppo", "id": None}
    ha, porta = _HaLettore(), _Porta()
    chat = ToolDispatcher(None, None, ha=ha, actuator=porta,
                          soffitto=consente(sviluppo, ruolo=None), subject=sviluppo)

    registro = await chat.dispatch("system_log", {})
    await chat.dispatch("execute", {"servizio": "light.turn_on",
                                    "bersaglio": {"entity_id": ["light.x"]}})

    assert registro["voci"] and porta.eseguite == ["light.turn_on"]


# --- fix round 1 del Task 2 -------------------------------------------------

from hiris.app.api.soffitto import ADMIN_SERVICES_REFUSAL, denies


@pytest.mark.asyncio
@pytest.mark.parametrize("servizio", ["homeassistant.restart", "homeassistant.stop",
                                      "homeassistant.reload_all",
                                      "homeassistant.set_location",
                                      "homeassistant.save_persistent_states"])
async def test_i_servizi_di_HA_riservati_agli_amministratori_non_partono(servizio):
    """M-1: il dominio `homeassistant` e' universale per la porta, e HIRIS
    chiama col proprio token. Core 2026.9.3 registra `stop`, `restart`,
    `reload_*`, `set_location`, `check_config` con
    `async_register_admin_service`.

    Mutazione ESEGUITA: tolto il controllo sul dominio da `_execute` --
    rossa."""
    porta = _Porta()

    esito = await _chat("utente", porta=porta).dispatch(
        "execute", {"servizio": servizio, "bersaglio": {"entity_id": ["light.x"]}})

    assert esito == {"errore": ADMIN_SERVICES_REFUSAL}
    assert porta.eseguite == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo,servizio,passa", [
    ("utente", "homeassistant.turn_on", True),
    ("utente", "homeassistant.toggle", True),
    ("utente", "homeassistant.update_entity", True),
    ("amministratore", "homeassistant.restart", True),
])
async def test_i_servizi_di_HA_concessi_restano_concessi(ruolo, servizio, passa):
    porta = _Porta()

    await _chat(ruolo, porta=porta).dispatch(
        "execute", {"servizio": servizio, "bersaglio": {"entity_id": ["light.x"]}})

    assert (porta.eseguite == [servizio]) is passa


def test_la_domanda_UNICA_al_soffitto(monkeypatch):
    """I3: lo sviluppo non si restringe per ruolo -- ma solo con
    l'interruttore acceso (fix round 2); una macchina senza ruolo si', e un
    turno senza soffitto (l'osservatore) no.

    Mutazione ESEGUITA: `denies` senza l'eccezione dello sviluppo -- rossa."""
    sviluppo = {"specie": "sviluppo", "id": None}
    nessuno = {"specie": "nessuno", "id": None}

    assert denies(consente(sviluppo, ruolo=None), "comandare", sviluppo) is True
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")
    assert denies(consente(sviluppo, ruolo=None), "comandare", sviluppo) is False
    assert denies(consente(nessuno, ruolo=None), "comandare", nessuno) is True
    assert denies(None, "amministrare", None) is False
    assert denies(consente(_PERSONA_MARTA, ruolo="utente"), "amministrare",
                  _PERSONA_MARTA) is True


@pytest.mark.asyncio
async def test_senza_GRUPPI_in_HA_non_si_entra(aiohttp_client, tmp_path, caplog):
    """I5: un utente che non e' il proprietario e non ha gruppi, in Home
    Assistant, non ha permessi (`merge_policies([])`). Il cancello lo chiude
    anche sulle rotte della lista, e il registro dice perche'.

    Mutazione ESEGUITA: `_role_of` senza il ramo `senza_gruppi` -- rossa."""
    caplog.set_level("INFO", logger="hiris.app.api.admission")
    app = _compose(tmp_path, access=True)
    app["ha_client"].users = AsyncMock(return_value={"utenti": [
        *_UTENTI["utenti"],
        {"id": "u-vuoto", "nome": "Vuoto", "amministratore": False,
         "senza_gruppi": True, "proprietario": False, "sistema": False}]})
    client = await aiohttp_client(app)

    assert await _gate_refused(client, "GET", "/api/config", _persona("u-vuoto"))
    [riga] = [r.getMessage() for r in caplog.records
              if r.name == "hiris.app.api.admission"]
    assert "senza gruppi in Home Assistant" in riga
    app["memory_store"].close()
    app["servizi"].close()


@pytest.mark.asyncio
async def test_UNA_lettura_dei_ruoli_per_tante_richieste_insieme(casa):
    """I2: una pagina chiede i suoi file tutti insieme; a copia scaduta, una
    sola `config/auth/list` per tutti.

    Mutazione ESEGUITA: tolta la lettura condivisa (ogni chiamante chiama
    `users()`) -- rossa (otto chiamate)."""
    from hiris.app.api.soffitto import _ha_users

    ha = casa.app["ha_client"]
    entrata = asyncio.Event()

    async def lenta():
        await entrata.wait()
        return _UTENTI

    ha.users = AsyncMock(side_effect=lenta)
    letture = [asyncio.ensure_future(_ha_users(casa.app)) for _ in range(8)]
    await asyncio.sleep(0)
    entrata.set()
    esiti = await asyncio.gather(*letture)

    assert ha.users.await_count == 1
    assert all(e is not None and "u-marta" in e for e in esiti)


@pytest.mark.asyncio
async def test_il_cancello_lascia_il_RUOLO_sulla_richiesta(aiohttp_client, tmp_path):
    """I4: chi viene dopo il cancello legge il ruolo da qui, senza chiedere di
    nuovo a Home Assistant.

    Mutazione ESEGUITA: il cancello non scrive `request["ruolo"]` -- rossa."""
    app = _compose(tmp_path, access=True)

    async def eco(request):
        return web.json_response({"ruolo": request.get("ruolo"),
                                  "letto": request.get("ruolo_letto")})

    app.router.add_get("/api/prova-ruolo", eco)
    client = await aiohttp_client(app)

    corpo = await (await client.get("/api/prova-ruolo", headers=_persona("u-admin"))).json()

    assert corpo == {"ruolo": "amministratore", "letto": True}
    app["memory_store"].close()
    app["servizi"].close()


@pytest.mark.asyncio
async def test_un_asset_rifiutato_NON_scrive_una_riga(chiusa, caplog):
    """Punto 12: un guscio rifiutato si porta dietro i suoi file; una riga
    per il guscio, nessuna per gli asset.

    Mutazione ESEGUITA: tolto il controllo `_is_static` -- rossa."""
    caplog.set_level("INFO", logger="hiris.app.api.admission")

    await chiusa.get("/config", headers=_persona("u-marta"))
    for nome in ("hiris-icon.svg", "hiris-theme.css", "hiris-fonts.css"):
        await chiusa.get(f"/static/{nome}", headers=_persona("u-marta"))

    righe = [r for r in caplog.records if r.name == "hiris.app.api.admission"]
    assert len(righe) == 1 and "/config" in righe[0].getMessage()


def test_solo_la_pagina_dei_ruoli_illeggibili_si_ricarica():
    """Punto 12: il guasto dei ruoli si risolve da se', gli altri rifiuti no."""
    assert b'http-equiv="refresh"' in _pagina(ROLES_UNREADABLE)
    for testo in (OPTION_OFF, NOT_ADMITTED, UNKNOWN_PERSON):
        assert b"refresh" not in _pagina(testo)


def test_nello_statico_non_ci_sono_segreti():
    """2.15: lo statico si serve a chi non amministra -- niente in quella
    cartella deve somigliare a una credenziale."""
    import pathlib
    cartella = pathlib.Path(admission.__file__).parents[1] / "static"
    sospetti = re.compile(r"(sk-[A-Za-z0-9]{16,}|sk-ant-|eyJ[A-Za-z0-9_-]{20,}\.|"
                          r"api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}|Bearer\s+[A-Za-z0-9._-]{16,}|"
                          r"-----BEGIN)")
    trovati = [f"{f.name}: {m.group(0)[:20]}"
               for f in cartella.rglob("*") if f.is_file()
               and f.suffix in (".js", ".html", ".css", ".svg", ".json")
               for m in [sospetti.search(f.read_text(encoding="utf-8", errors="ignore"))]
               if m]

    assert not trovati, trovati


# --- H-1: il turno di una promessa porta il soffitto di chi l'ha chiesta ------

class _HaDiMarta(_HaLettore):
    async def users(self):
        return _UTENTI


class _RunnerCheLegge:
    """Chiede il registro e le tracce, poi conclude: cio' che un modello
    farebbe se glielo si chiedesse in una promessa."""

    def __init__(self):
        self.risposte = []
        self.contesto = None

    async def chat(self, **kwargs):
        self.contesto = kwargs.get("context_str")
        d = kwargs["dispatcher"]
        self.risposte.append(await d.dispatch("system_log", {}))
        self.risposte.append(await d.dispatch("automation_trace",
                                              {"entita": "automation.luci"}))
        await d.dispatch("conclude", {"avvisare": False, "testo": "fatto"})


@pytest.mark.asyncio
async def test_la_promessa_di_chi_non_amministra_NON_legge_il_registro():
    """H-1, strada sincrona: la promessa di Marta si sveglia, il turno chiede
    il registro, Home Assistant non viene nemmeno interrogato.

    Mutazione ESEGUITA: `interpreta_promise` col dispatcher senza soffitto --
    rossa (il registro arriva al modello)."""
    from hiris.app.api.soffitto import prepara_ruoli
    from hiris.app.chat_thread import ChatThread
    from hiris.app.keeper.exchange import interpreta_promise

    ha, runner = _HaDiMarta(), _RunnerCheLegge()
    app = {"llm_router": runner, "ha_client": ha}
    prepara_ruoli(app)
    promessa = {"id": "p1", "frase": "fra un'ora guarda il registro",
                "domanda": "ci sono errori?", "istantanea": [],
                "thread": ChatThread("persona:u-marta", "pannello")}

    esito = await interpreta_promise(app, promessa)

    assert esito["testo"] == "fatto"
    assert runner.risposte[0] == {"errore": ADMIN_READS_REFUSAL}
    assert ha.chiesto == []


@pytest.mark.asyncio
async def test_la_promessa_dell_amministratore_legge_come_prima():
    from hiris.app.api.soffitto import prepara_ruoli
    from hiris.app.chat_thread import ChatThread
    from hiris.app.keeper.exchange import interpreta_promise

    ha, runner = _HaDiMarta(), _RunnerCheLegge()
    app = {"llm_router": runner, "ha_client": ha}
    prepara_ruoli(app)
    promessa = {"id": "p1", "frase": "guarda il registro", "domanda": "errori?",
                "istantanea": [], "thread": ChatThread("persona:u-admin", "pannello")}

    await interpreta_promise(app, promessa)

    assert "system_log/list" in ha.chiesto


@pytest.mark.asyncio
async def test_la_promessa_di_chi_non_amministra_NON_legge_dal_PONTE(casa):
    """H-1, strada del ponte: il turno arriva su `/api/mcp` con la
    credenziale di turno e `X-HIRIS-Promessa`; il soffitto e' quello di chi
    ha chiesto la promessa.

    Mutazione ESEGUITA: il ramo della promessa in `handle_mcp` senza soffitto
    -- rossa."""
    from hiris.app.chat_thread import ChatThread
    from hiris.app.keeper.store import AgendaStore

    app = casa.app
    ha = _HaDiMarta()
    ha.users = AsyncMock(return_value=_UTENTI)
    app["ha_client"] = ha
    agenda = AgendaStore(str(pathlib_tmp(app) / "promesse.db"))
    app["agenda"] = agenda
    adesso = time.time()
    ident = agenda.create({"specie": "chiedi", "frase": "fra un'ora il registro",
                           "quando_ts": adesso + 10, "domanda": "errori?"},
                          thread=ChatThread("persona:u-marta", "pannello"),
                          now=adesso)["promessa"]["id"]
    assert agenda.prendi(ident, now=adesso + 11) is True

    risposta = await casa.post("/api/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "system_log", "arguments": {}}},
        headers={**credenziale_ponte(app, "turno-della-promessa"),
                 "X-HIRIS-Promessa": ident})
    corpo = await risposta.json()
    agenda.close()

    assert ADMIN_READS_REFUSAL in json_text(corpo)
    assert ha.chiesto == []


def pathlib_tmp(app):
    import pathlib
    return pathlib.Path(app["data_dir"])


def json_text(corpo) -> str:
    import json
    return json.dumps(corpo, ensure_ascii=False)


# --- L-2: il corpo di un'automazione non esce da `view` per chi non amministra

_CORPO = {"alias": "Luci all'alba", "trigger": [{"platform": "sun",
                                                  "event": "CORPO-RISERVATO"}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("ruolo,vede", [("utente", False), ("lettore", False),
                                        ("amministratore", True), (None, True)])
async def test_il_CORPO_di_un_automazione_e_degli_amministratori(tmp_path, ruolo, vede):
    """`automation/config` e' `@websocket_api.require_admin` in Core 2026.9.3,
    `script/config` no. Il nucleo della chat non porta i corpi; `view` si':
    a chi non amministra dice che l'automazione c'e', non cosa fa.

    Mutazione ESEGUITA: tolto il controllo `amministrare` da `_view` --
    rossa."""
    from hiris.app.memory.store import MemoryStore
    from tests.test_knowledge_tools import _semina_casa

    casa_seminata = _semina_casa(tmp_path, comportamento=[
        {"id": "automation.luci_alba", "tipo": "automazione",
         "nome": "Luci all'alba", "corpo": _CORPO},
        {"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte",
         "corpo": {"alias": "CORPO-DELLO-SCRIPT"}}])
    memoria = MemoryStore(str(tmp_path / "memoria.db"))
    soffitto = None if ruolo is None else consente(_PERSONA_MARTA, ruolo=ruolo)
    chat = ToolDispatcher(casa_seminata, memoria, soffitto=soffitto,
                          subject=_PERSONA_MARTA)

    automazione = await chat.dispatch("view", {"tipo": "automazione",
                                               "riferimento": "automation.luci_alba"})
    script = await chat.dispatch("view", {"tipo": "script",
                                          "riferimento": "script.buonanotte"})
    memoria.close()
    casa_seminata.close()

    assert ("CORPO-RISERVATO" in json_text(automazione)) is vede
    assert ("solo agli amministratori" in json_text(automazione)) is not vede
    assert automazione["esiste"] is True
    assert "CORPO-DELLO-SCRIPT" in json_text(script)


# --- fix round 2: la bozza di chi non amministra non rivela il «prima» -------

_CORPO_ATTUALE = {"id": "1771", "alias": "Tapparelle all'alba",
                  "description": "SEGRETO",
                  "triggers": [{"trigger": "sun", "event": "sunrise"}],
                  "actions": [{"action": "lock.unlock",
                               "target": {"entity_id": "lock.porta"}}]}


def _officina(tmp_path):
    from hiris.app.action.construction.revisions import ConstructionStore
    from hiris.app.action.construction.workshop import Workshop
    from hiris.app.action.journal import Journal
    from tests.test_construction_workshop import FintoHA

    archivio = ConstructionStore(str(tmp_path / "costruzioni.db"))
    cronaca = Journal(str(tmp_path / "azioni.db"))
    ha = FintoHA(leggi={"corpo": dict(_CORPO_ATTUALE)})
    return Workshop(ha, archivio, cronaca), archivio, cronaca


@pytest.mark.asyncio
@pytest.mark.parametrize("soffitto,dominio,rivela", [
    (consente(_PERSONA_MARTA, ruolo="utente"), "automation", False),
    (consente(_PERSONA_MARTA, ruolo="lettore"), "scene", False),
    # Il soffitto di un risveglio senza ruolo verificato: niente.
    ({"leggere": False, "comandare": False, "costruire": False,
      "amministrare": False, "ruolo": None, "perche": "x"}, "automation", False),
    (consente(_PERSONA_MARTA, ruolo="utente"), "script", True),
    (consente(_PERSONA_MARTA, ruolo="amministratore"), "automation", True),
    (None, "automation", True),
])
async def test_la_BOZZA_di_chi_non_amministra_non_rivela_com_e_adesso(
        tmp_path, soffitto, dominio, rivela):
    """Fix round 2, punto 1: `propose modifica` legge il corpo attuale col
    token di amministratore di HIRIS, e l'anteprima lo riassumeva («Prima:»
    con descrizione e servizi chiamati). Per automazioni e scene Home
    Assistant quel corpo lo mostra solo agli amministratori
    (`components/config/view.py`, `@require_admin`, Core 2026.9.3); gli
    script restano come in `view`. Il «prima» resta archiviato intero.

    Mutazione ESEGUITA: `_propose` con `reveal_before=True` sempre -- rossa."""
    from tests.test_construction_workshop import _intento

    officina, archivio, cronaca = _officina(tmp_path)
    chat = ToolDispatcher(None, None, workshop=officina, soffitto=soffitto,
                          subject=_PERSONA_MARTA, exchange="t-1")
    intento = _intento(gesto="modifica", chiave="1771", dominio=dominio)
    if dominio == "scene":
        intento.update(richiesto="scena", innesco=[], azioni=[],
                       stati=[{"entity_id": "light.cucina", "state": "on"}])
    elif dominio == "script":
        intento.update(richiesto="script", innesco=[])

    esito = await chat.dispatch("propose", intento)
    testo = json_text(esito)
    stored_before = (archivio.read(esito["proposta_id"]) or {}).get("prima") \
        if "proposta_id" in esito else None
    archivio.close()
    cronaca.close()

    assert "proposta_id" in esito, esito
    assert ("SEGRETO" in testo) is rivela
    assert ("lock.unlock" in testo) is rivela
    assert ("com'è adesso lo vedono solo gli amministratori" in testo) is not rivela
    assert "Tapparelle all'alba" in testo, "l'alias e' pubblico e resta"
    assert stored_before == _CORPO_ATTUALE, "il «prima» si archivia intero"


@pytest.mark.asyncio
async def test_una_promessa_nata_in_SVILUPPO_non_legge_in_produzione(monkeypatch):
    """Fix round 2, punto 2: l'eccezione dello sviluppo la decide
    l'interruttore, non la specie. Una promessa col filo `sviluppo:-` che si
    sveglia con l'interruttore spento non legge il registro.

    Mutazione ESEGUITA: `denies` che guarda solo la specie -- rossa."""
    from hiris.app.api.soffitto import prepara_ruoli
    from hiris.app.chat_thread import ChatThread
    from hiris.app.keeper.exchange import interpreta_promise

    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    ha, runner = _HaDiMarta(), _RunnerCheLegge()
    app = {"llm_router": runner, "ha_client": ha}
    prepara_ruoli(app)
    promessa = {"id": "p1", "frase": "guarda il registro", "domanda": "errori?",
                "istantanea": [], "thread": ChatThread("sviluppo:-", "sviluppo")}

    await interpreta_promise(app, promessa)

    assert runner.risposte[0] == {"errore": ADMIN_READS_REFUSAL}
    assert ha.chiesto == []

    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")
    ha2, runner2 = _HaDiMarta(), _RunnerCheLegge()
    app2 = {"llm_router": runner2, "ha_client": ha2}
    prepara_ruoli(app2)
    await interpreta_promise(app2, promessa)
    assert "system_log/list" in ha2.chiesto, "con l'interruttore acceso, come ieri"


@pytest.mark.asyncio
async def test_l_orfana_ADOTTATA_dal_proprietario_legge_coi_suoi_diritti(tmp_path):
    """Fix round 2, punto 4: una promessa di prima delle promesse divise si
    sveglia, l'orologio la da' al proprietario (`owner_thread`), e il suo
    `chiedi` legge il registro coi diritti di lui."""
    from hiris.app.api.soffitto import ceiling_at_wake, prepara_ruoli
    from hiris.app.chat_thread import ChatThread
    from hiris.app.keeper.exchange import interpreta_promise
    from hiris.app.keeper.recipient import Recipients
    from hiris.app.keeper.store import AgendaStore
    from hiris.app.keeper.sweeper import Sweeper

    ha, runner = _HaDiMarta(), _RunnerCheLegge()
    app = {"llm_router": runner, "ha_client": ha}
    prepara_ruoli(app)
    agenda = AgendaStore(str(tmp_path / "promesse.db"))
    adesso = time.time()
    agenda._conn.execute(
        "INSERT INTO promesse(id,specie,frase,quando_ts,domanda,recapito,stato,"
        "nata_ts) VALUES('vecchia','chiedi','detta prima',?,'errori?',NULL,"
        "'in_attesa',?)", (adesso - 1, adesso - 100))
    agenda._conn.commit()
    proprietario = ChatThread("persona:u-admin", "pannello")

    async def _nessun_telefono(_subject):
        return Recipients((), "nessun telefono")

    async def _owner():
        return proprietario

    orologio = Sweeper(
        agenda, execute=None, interpreta=lambda p: interpreta_promise(app, p),
        recipients=_nessun_telefono, write_to_thread=lambda *a, **k: True,
        ceiling=lambda s: ceiling_at_wake(app, s), owner_thread=_owner)

    await orologio.batti(adesso)
    riga = agenda.read("vecchia")
    agenda.close()

    assert riga["thread"] == proprietario
    assert runner.risposte and runner.risposte[0].get("voci"), runner.risposte
    assert "system_log/list" in ha.chiesto
