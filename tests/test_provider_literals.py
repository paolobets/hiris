"""La tabella dei provider e' l'unica casa degli id (Tappa 7, Task 9).

Due prove, e servono tutte e due.

**Nessun letterale fuori dalla tabella.** Un id di provider scritto a mano
fuori da `providers.py` e' una copia della tabella: il giorno in cui la tabella
cambia, la copia resta. Fino al Task 9 i cinque id erano scritti in tredici
posti -- tre ordini, sei definizioni della credenziale, due vocabolari dei
consumi, la pagina Modelli due volte -- e ogni coppia era un doppione. Gli
id si chiedono al SORGENTE (l'albero sintattico del Python, il codice senza
commenti del JavaScript), non a un elenco ricopiato qui.

**Un sesto provider arriva da solo.** Il contrario della prima, e la ragione
per cui la prima vale: un provider aggiunto alla tabella compare nella pagina
Modelli e nella catena senza che nessun altro file lo sappia.
"""
import ast
import re
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app import providers
from tests.test_api import client  # noqa: F401

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

#: LE AMMISSIONI, e chiudono per difetto: un letterale nuovo e' vietato finche'
#: qualcuno non lo ammette qui, con la ragione. Ognuna e' un nome che appartiene
#: a un ALTRO sistema e coincide per caso con l'id di un provider.
AMMESSI_PY = {
    ("main.py", "openai"):
        "il nome del logger della libreria `openai`, che si zittisce",
    ("backends/openai_compat_runner.py", "openai"):
        "il nome del MODULO Python dell'SDK, che si sonda per le sue eccezioni",
    ("agent/runner.py", "claude"):
        "il nome dell'eseguibile della CLI del ponte, fuori dall'immagine",
    ("server.py", "ollama"):
        "la chiave fittizia che l'endpoint compatibile OpenAI di Ollama chiede",
}

#: Nel JavaScript non ce n'e' nessuna: la pagina riceve gli id nel payload.
AMMESSI_JS: dict[tuple[str, str], str] = {}


def _python_literals(path: Path) -> Counter:
    """Le costanti stringa UGUALI a un id: un id dentro una frase («claude-
    opus-4-7», «Claude API») non e' l'id."""
    found: Counter = Counter()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and node.value in providers.ids():
            found[node.value] += 1
    return found


def _js_code(text: str) -> str:
    senza = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", senza)


def _js_literals(text: str) -> Counter:
    """Gli id nel codice senza commenti, come PAROLA intera: fra apici, come
    chiave di un oggetto o come proprieta' (`.ollama`). Un id dentro un nome
    composto (`claude-opus`, `--consumo-claude`) non e' l'id."""
    found: Counter = Counter()
    for pid in providers.ids():
        found[pid] = len(re.findall(r"(?<![\w-])" + re.escape(pid) + r"(?![\w-])",
                                    _js_code(text)))
    return +found


def test_la_ricerca_vede_davvero_gli_id():
    """Il cancello che non guarda niente sembra vivo: si prova sulla tabella
    stessa, che li scrive tutti, e su un pezzo di JavaScript con un id fra
    apici e uno solo nei commenti."""
    assert set(_python_literals(APP / "providers.py")) == set(providers.ids())
    pid = providers.ids()[0]
    assert _js_literals(f"/* {pid} */ var x = '{pid}';") == Counter({pid: 1})


def test_nessun_id_di_provider_e_scritto_fuori_dalla_tabella_nel_python():
    """Mutazione eseguita (07/10/2026): in `usage/store.py::importa_legacy`
    il ripiego `CLAUDE.id` riscritto `"claude"` -> rosso, la differenza nomina
    `('usage/store.py', 'claude')`. Ripristinato, `git diff` senza la
    mutazione."""
    trovati = {}
    for path in sorted(APP.rglob("*.py")):
        if path.name == "providers.py" and path.parent == APP:
            continue
        for pid, quanti in _python_literals(path).items():
            trovati[(path.relative_to(APP).as_posix(), pid)] = quanti
    assert set(trovati) == set(AMMESSI_PY), (
        "letterali di id fuori dalla tabella dei provider: si chiedono a "
        "`providers.py` (`CLAUDE.id`, `ids()`, `get()`), o si ammettono in "
        f"AMMESSI_PY con la ragione. Nuovi: {sorted(set(trovati) - set(AMMESSI_PY))}; "
        f"ammessi e spariti: {sorted(set(AMMESSI_PY) - set(trovati))}")


def test_nessun_id_di_provider_e_scritto_nel_javascript():
    """Mutazione eseguita (07/10/2026): `var FIXED_ORDER = ['claude', ...]`
    rimesso in `config/models-route.js` -> rosso, la differenza nomina i
    cinque id in quel file. Ripristinato, `git diff` senza la mutazione."""
    trovati = {}
    for path in sorted((APP / "static").rglob("*.js")):
        for pid in _js_literals(path.read_text(encoding="utf-8")):
            trovati[(path.relative_to(APP / "static").as_posix(), pid)] = True
    assert set(trovati) == set(AMMESSI_JS), (
        "la pagina riceve gli id dal server (`ordine_fisso`, `preset`, le "
        f"righe): trovati {sorted(set(trovati) - set(AMMESSI_JS))}")


# ---------------------------------------------------------------------------
# Un sesto provider
# ---------------------------------------------------------------------------

SESTO = providers.Provider(
    id="sesto",
    name="Il sesto",
    nature="a consumo",
    privacy="I tuoi messaggi passano dal sesto.",
    missing_reason="manca la chiave",
    credential=lambda sources: bool(sources.get("sesto_api_key")),
    model_path=("provider_models", "sesto"),
    auto_model="sesto-1",
)


def _runner(risposta):
    r = MagicMock()
    r.chat = AsyncMock(return_value=risposta)
    r.last_tool_calls = []
    return r


@pytest.mark.asyncio
async def test_un_sesto_provider_compare_nella_pagina_e_nella_catena(client, monkeypatch):
    """La tabella si allunga di una riga, e nient'altro cambia: il sesto
    compare nell'ordine fisso che la pagina riceve e fra chi sta fuori dalla
    catena, ci entra con una PUT, e il router lo interpella.

    Mutazioni eseguite (07/10/2026), ognuna rossa per la ragione giusta e
    ripristinata (`git diff` senza la mutazione):
    - `page_payload` con l'ordine fisso scritto a mano (i cinque di oggi) ->
      rosso su `ordine_fisso`;
    - `LLMRouter._backend_map` sui quattro nomi di oggi scritti a mano ->
      rosso sulla catena: il sesto non risponde, e non entra;
    - `compose_topology` con «Fuori dalla catena» sui cinque id di oggi ->
      rosso sulla riga del sesto."""
    from hiris.app.llm_router import LLMRouter
    from hiris.app.server import _recompute_chain

    monkeypatch.setattr(providers, "PROVIDERS", providers.PROVIDERS + (SESTO,))
    app = client.app
    app["sesto_api_key"] = "una-chiave"
    app["claude_api_key"] = "sk-test"
    router = LLMRouter(claude=_runner("da claude"), sesto=_runner("dal sesto"),
                       model_chain=["claude"])
    app["llm_router"] = router
    app["recompute_chain"] = lambda: _recompute_chain(app)
    app["model_chain"] = ["claude"]

    body = await (await client.get("/api/models/config")).json()
    assert body["ordine_fisso"][-1] == "sesto"
    fuori = {r["id"]: r for r in body["fuori_catena"]}
    assert fuori["sesto"]["nome"] == "Il sesto"
    assert fuori["sesto"]["ha_credenziale"] is True
    assert fuori["sesto"]["riordinabile"] is True

    resp = await client.put("/api/models/config",
                            json={"chain_order": ["sesto", "claude"]})
    assert resp.status == 200
    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["sesto", "claude"]
    assert await router.chat(model="auto") == "dal sesto"
