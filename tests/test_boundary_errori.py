"""La chiave d'errore segue il confine (Tappa 4, Task 2; C-06, S-25; D2).

Su HTTP, verso le pagine e i servizi firmati, un errore esce come `error`;
verso il modello resta `errore`, perche' li' e' il dominio. Lo ha deciso il
glossario del 01/09, lo applica `api/boundary.py`, e Paolo il 05/10/2026 l'ha
confermato (D2 «il confine»).

**L'elenco delle rotte si chiede al router**, non si ricopia (CLAUDE.md, I-0):
la prova costruisce l'app vera senza archivi -- `on_startup` svuotato, come
`tests/test_api.py` -- e chiama ogni rotta `/api/` con i parametri riempiti a
caso e un corpo vuoto. Un'app senza archivi risponde d'errore quasi ovunque:
e' proprio il modo di provocarli tutti senza scriverne l'elenco.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from hiris.app.api.boundary import error_body, error_response
from hiris.app.chat_store import close_all_stores
from hiris.app.server import create_app


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "1")
    monkeypatch.setenv("HIRIS_ALLOW_NO_CSRF", "1")
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def bare_client(aiohttp_client, tmp_path):
    """L'app vera, senza nessun archivio: ogni rotta che ne chiede uno sbaglia."""
    app = create_app()
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


def _api_routes(app) -> list[tuple[str, str]]:
    """Le rotte `/api/` del router, con i parametri del percorso riempiti."""
    routes = []
    for route in app.router.routes():
        if route.method in ("HEAD", "*"):
            continue
        canonical = route.resource.canonical if route.resource else ""
        if not canonical.startswith("/api/"):
            continue
        path = canonical
        while "{" in path:
            start = path.index("{")
            path = path[:start] + "1" + path[path.index("}", start) + 1:]
        routes.append((route.method, path))
    return routes


# Lista d'AMMISSIONE delle risposte d'errore che non hanno ancora la forma
# comune, ognuna con la ragione. Chiude per difetto.
_NOT_YET = {
    ("POST", "/api/usage/reset"): (
        "il 409 senza archivio dei consumi porta il resoconto «non misurato» "
        "intero (`measured`, `reason`, `message`), che la pagina Consumi legge: "
        "fuori dal perimetro del Task 2 della Tappa 4, domanda aperta a Paolo"),
}


async def _provoked_errors(client) -> dict[tuple[str, str], tuple[int, object]]:
    errors = {}
    for method, path in _api_routes(client.server.app):
        kwargs = {} if method == "GET" else {"json": {}}
        resp = await client.request(method, path, **kwargs)
        if resp.status < 400:
            continue
        if "json" not in (resp.headers.get("Content-Type") or ""):
            continue
        errors[(method, path)] = (resp.status, json.loads(await resp.text()))
    return errors


@pytest.mark.asyncio
async def test_every_provoked_http_error_says_error_not_errore(bare_client):
    errors = await _provoked_errors(bare_client)
    # La derivazione non si e' svuotata: un router che non desse piu' rotte, o
    # un'app che rispondesse 200 a tutto, farebbe passare la prova senza
    # guardare niente. 30 e' sotto il numero misurato il 05/10/2026 su questo
    # ramo: 34 risposte d'errore JSON provocate, su 51 rotte `/api/`.
    assert len(errors) >= 30, sorted(errors)
    wrong = {}
    for key, (status, body) in errors.items():
        if key in _NOT_YET:
            continue
        if not isinstance(body, dict):
            wrong[key] = (status, body)
            continue
        if "jsonrpc" in body:
            # L'involucro di JSON-RPC (MCP) ha la SUA chiave `error`, un
            # oggetto: e' la lingua del protocollo, non la nostra.
            if not isinstance(body.get("error"), dict):
                wrong[key] = (status, body)
            continue
        if "errore" in body or not isinstance(body.get("error"), str):
            wrong[key] = (status, body)
    assert not wrong, f"risposte d'errore HTTP fuori dal confine: {wrong}"


def test_error_body_is_the_one_shape():
    assert error_body("archivio non disponibile") == {"error": "archivio non disponibile"}
    assert error_body("troppi", limit=3) == {"error": "troppi", "limit": 3}


def test_error_response_carries_status_and_body():
    resp = error_response(404, "non c'e'", turns=2)
    assert resp.status == 404
    assert json.loads(resp.text) == {"error": "non c'e'", "turns": 2}


# --- La chiave si scrive in un posto solo -----------------------------------
#
# La prova qui sopra vede le risposte che un'app senza archivi sa provocare;
# questa vede il SORGENTE, quindi anche i rami che quella non raggiunge (un
# 404 di un id che non c'e', un 409, un rifiuto del cancello). La proprieta':
# fuori da `api/boundary.py` nessun modulo del confine HTTP scrive di suo un
# dizionario con la chiave `error` o `errore` -- li scrive `error_response`.
#
# I moduli si chiedono: quelli dei gestori del router, quelli dei middleware,
# e ogni modulo del pacchetto `api/` (dove vivono i rifiuti che i gestori
# chiamano: `soffitto.require_builder`, `admission._refusal`).

# Lista d'AMMISSIONE (CLAUDE.md, I-0): chiude per difetto, ogni voce ha la
# ragione, e il numero e' quello misurato il 05/10/2026 -- uno in piu' e' un
# dizionario nuovo che qualcuno deve ammettere per iscritto.
_ADMITTED = {
    ("hiris.app.api.handlers_mcp", "errore"): (
        4, ("risultati di strumento per il MODELLO del ponte, dentro il `content` "
            "di JSON-RPC: e' il dominio, e resta italiano (D2)")),
    ("hiris.app.api.handlers_mcp", "error"): (
        1, ("l'involucro d'errore di JSON-RPC, `{code, message}`: la lingua del "
            "protocollo MCP, non la nostra forma")),
    ("hiris.app.api.soffitto", "errore"): (
        1, ("l'esito di `HAClient.users()` ricostruito per un'eccezione: e' la "
            "forma del client verso Home Assistant, non una risposta HTTP")),
}


def _boundary_modules() -> dict[str, str]:
    """Il sorgente che parla HTTP, chiesto al router e al pacchetto `api/`.

    Per i moduli di `api/` il modulo intero; per un gestore che vive altrove
    (`server.py`, che fa anche il cervello e porta `errore` di dominio) la
    sola funzione del gestore, o la prova guarderebbe cio' che HTTP non e'.
    """
    import importlib
    import inspect
    import pkgutil
    import textwrap

    import hiris.app.api as api_package

    app = create_app()
    package = api_package.__name__
    sources = {f"{package}.{info.name}": inspect.getsource(
        importlib.import_module(f"{package}.{info.name}"))
        for info in pkgutil.iter_modules(api_package.__path__)}
    for handler in [r.handler for r in app.router.routes()] + list(app.middlewares):
        module = getattr(handler, "__module__", "") or ""
        if module.startswith("hiris.app") and not module.startswith(package + "."):
            # `dedent`: un gestore nato da una fabbrica (i due gusci HTML,
            # `server._serve_shell`, C-29) e' una funzione annidata, e il
            # suo sorgente arriva indentato.
            sources[f"{module}.{handler.__name__}"] = textwrap.dedent(
                inspect.getsource(handler))
    sources.pop(f"{package}.boundary", None)
    return sources


def _error_keys(source: str) -> dict[str, int]:
    import ast

    counts: dict[str, int] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value in ("error", "errore"):
                    counts[key.value] = counts.get(key.value, 0) + 1
    return counts


def test_boundary_modules_are_asked_not_copied():
    modules = _boundary_modules()
    # La derivazione non si e' svuotata: senza le rotte o il pacchetto la prova
    # sotto passerebbe guardando niente. Tre dei moduli che il 05/10/2026
    # scrivevano `errore` su HTTP (S-25), e un gestore di `server.py`.
    for name in ("hiris.app.api.handlers_mind", "hiris.app.api.admission",
                 "hiris.app.api.middleware_internal_auth",
                 "hiris.app.server._handle_health"):
        assert name in modules, sorted(modules)


def test_no_boundary_module_writes_the_error_key_by_hand():
    found = {}
    for name, source in _boundary_modules().items():
        for key, count in _error_keys(source).items():
            found[(name, key)] = count
    admitted = {k: v[0] for k, v in _ADMITTED.items()}
    assert found == admitted, (
        "un modulo del confine HTTP scrive la chiave d'errore di suo: passi da "
        "`boundary.error_response` (o, se va al modello, si ammetta con la "
        f"ragione). Trovati: {found}")


# --- C-50, la parte che la pagina non vede ------------------------------------

@pytest.mark.asyncio
async def test_chat_input_refusals_speak_italian(bare_client):
    """I due rifiuti d'ingresso della chat erano in inglese (C-50). La pagina
    non li puo' provocare -- manda sempre JSON, e un messaggio vuoto non parte
    -- ma un servizio firmato si', e legge cio' che legge chiunque altro."""
    resp = await bare_client.post("/api/chat", data=b"{non json",
                                  headers={"Content-Type": "application/json"})
    assert resp.status == 400
    assert await resp.json() == {"error": "Il corpo della richiesta non è JSON valido."}
    resp = await bare_client.post("/api/chat", json={"message": "   "})
    assert resp.status == 400
    assert await resp.json() == {
        "error": "Manca il messaggio: il campo `message` è vuoto."}


# --- C-52 --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_services_503_does_not_pretend_an_empty_list(bare_client):
    """`{"servizi": []}` accanto al 503 diceva «nessun servizio» dove il fatto
    e' «non so»: la regola scritta in `handlers_mind.py` («503, non un elenco
    vuoto»), che `handle_services` contraddiceva (C-52)."""
    resp = await bare_client.get("/api/services")
    assert resp.status == 503
    assert await resp.json() == {"error": "archivio non disponibile"}


# --- C-07 --------------------------------------------------------------------

def test_unknown_id_sentence_is_written_once():
    """«Non ho nessun X con quell'identificatore» vive in
    `chat_thread.unknown_id_text` e solo li' (C-07): era scritta a mano in
    nove punti fra rotte e archivi. Si cerca la coda della frase in tutto il
    prodotto; i file si chiedono alla cartella."""
    import pathlib

    from hiris.app.chat_thread import unknown_id_text

    app_dir = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"
    tail = "quell’identificatore"
    holders = sorted(str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py")
                     if tail in p.read_text(encoding="utf-8"))
    assert holders == ["chat_thread.py"], holders
    assert unknown_id_text("nessuna promessa") == (
        "non ho nessuna promessa con quell’identificatore.")
    assert unknown_id_text("nessun servizio", by="quella chiave") == (
        "non ho nessun servizio con quella chiave.")
