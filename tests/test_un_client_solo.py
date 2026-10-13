"""Verso Home Assistant e il Supervisor parla solo `HAClient` (E-06).

Fino alla Chiusura dello sprint (F5, 13/10/2026) c'erano tre client verso lo
stesso sistema: `HAClient`, la sessione WebSocket della disinstallazione della
card (`action/installation.py`) e quella del Supervisor per lo slug
(`panel_visibility.read_own_slug`). Tre timeout, tre forme d'errore, e due
porte di scrittura fuori dal client che il cancello dell'attuatore deriva.

Il cancello: fuori da `proxy/` nessun modulo apre una sessione HTTP o un
WebSocket, salvo quelli ammessi qui sotto, che parlano con i PROVIDER dei
modelli e non con la casa. I moduli si chiedono alla cartella, le chiamate
all'albero del codice.
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"

#: Le aperture di una connessione, per nome della chiamata.
OPENINGS = frozenset({"ClientSession", "ws_connect"})

#: Lista di AMMISSIONE: i moduli fuori da `proxy/` che aprono una connessione,
#: con la ragione. Nessuno parla con Home Assistant o col Supervisor.
AMMESSI: dict[str, str] = {
    "api/handlers_models.py": (
        "gli elenchi dei modelli dai provider (Anthropic, OpenAI, OpenRouter, "
        "Ollama), per la pagina Modelli"),
    "server.py": "il controllo d'avvio dell'indirizzo di Ollama, un provider",
}


def openings() -> dict[str, int]:
    """`{modulo: aperture}` per ogni modulo del prodotto fuori da `proxy/`."""
    found: dict[str, int] = {}
    for path in sorted(APP.rglob("*.py")):
        module = path.relative_to(APP).as_posix()
        if module.startswith("proxy/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (func.attr if isinstance(func, ast.Attribute)
                        else func.id if isinstance(func, ast.Name) else None)
                if name in OPENINGS:
                    count += 1
        if count:
            found[module] = count
    return found


def test_la_derivazione_vede_le_aperture_dei_provider():
    """Un insieme vuoto sarebbe un cancello che non guarda piu' niente."""
    assert "api/handlers_models.py" in openings()


def test_fuori_dal_client_nessuno_apre_una_connessione_non_ammessa():
    """Mutazione ESEGUITA (13/10/2026): un `aiohttp.ClientSession()` in
    `action/installation.py` -- rossa, e nomina il modulo."""
    extra = sorted(set(openings()) - set(AMMESSI))
    assert not extra, (
        f"{extra} aprono una connessione fuori da `proxy/`: verso Home Assistant "
        "e il Supervisor si parla da `HAClient`. Se e' un provider, ammettilo in "
        "AMMESSI con la ragione")


def test_ogni_ammissione_e_ancora_vera():
    """L'ammissione puo' solo accorciarsi: un modulo che non apre piu' niente
    esce dall'elenco."""
    stale = sorted(set(AMMESSI) - set(openings()))
    assert not stale, f"{stale} non aprono piu' connessioni: togli l'ammissione"
