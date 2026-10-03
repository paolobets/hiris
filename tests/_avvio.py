"""L'app del prodotto avviata davvero, per le prove che prima ne leggevano il
testo (Tappa 1 dello sprint «Una fonte sola di verita'»).

Il montaggio e' quello della fotografia delle porte
(`scripts/fotografia_porte.py::mounted`): `create_app()` e poi
`_on_startup`, su una casa congelata che risponde dai file della casa
sintetica (`tests/_casa_sintetica.py`). E' l'unico punto in cui le prove e gli
attrezzi avviano il prodotto: una seconda montatura sarebbe una seconda idea
di «avvio».

**Un avvio per FILE, non per prova**: costa secondi (misurato il 03/10/2026:
circa sei). La fixture e' di modulo, e le prove di un file la condividono --
quindi non la modificano. Chi deve preparare la casa o l'ambiente PRIMA
dell'avvio usa `fotografia_porte.mounted` direttamente, dentro la prova.

Si importa nel file di prova: `from tests._avvio import started_app`.
"""
import contextlib
import os
import sys
from pathlib import Path
from unittest import mock

import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

from tests._casa_sintetica import synthetic_inputs


class RecordingHouse(fotografia_porte.FrozenHouse):
    """La casa congelata che ricorda chi si e' iscritto ai suoi eventi, e in
    che ordine.

    E' la casa che l'avvio trova in `app["ha_client"]`: una prova chiede a lei
    QUALI ascoltatori l'avvio ha registrato -- e li chiama -- invece di cercare
    `add_state_listener(` nel testo di `server.py`. La firma e' quella con cui
    `_on_startup` costruisce `HAClient`."""

    def __init__(self, base_url=None, token=None) -> None:
        super().__init__(synthetic_inputs())
        #: `(nome del metodo, ascoltatore)`, nell'ordine dell'iscrizione.
        self.listeners: list[tuple[str, object]] = []

    def registered(self, kind: str) -> list:
        """Gli ascoltatori iscritti con `add_<kind>_listener`, in ordine."""
        return [callback for name, callback in self.listeners
                if name == f"add_{kind}_listener"]

    def __getattr__(self, name: str):
        if name.startswith("add_") and name.endswith("_listener"):
            def register(callback, *args, **kwargs):
                self.listeners.append((name, callback))
            return register
        return super().__getattr__(name)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def started_app(tmp_path_factory):
    """L'app avviata sulla casa sintetica, spenta alla fine del file. La casa
    e' una `RecordingHouse`: `app["ha_client"].listeners` dice chi l'avvio ha
    iscritto ai suoi eventi."""
    data_dir = str(tmp_path_factory.mktemp("avvio"))
    async with fotografia_porte.mounted(synthetic_inputs(), data_dir,
                                        RecordingHouse) as app:
        yield app


#: Da quale variabile d'ambiente l'avvio legge la credenziale di ogni
#: provider. E' l'INGRESSO delle prove che preparano le credenziali, non una
#: regola: `credential_environment` le scrive TUTTE, vuote quelle assenti,
#: perche' una credenziale nell'ambiente di chi lancia la suite non entri
#: nell'avvio.
CREDENTIAL_VARIABLES = {"subscription": "CLAUDE_CODE_OAUTH_TOKEN",
                        "claude": "CLAUDE_API_KEY",
                        "openai": "OPENAI_API_KEY",
                        "openrouter": "OPENROUTER_API_KEY",
                        "ollama": "LOCAL_MODEL_URL"}

#: Un indirizzo di Ollama che non risponde: la verifica di raggiungibilita'
#: dell'avvio fallisce subito invece di uscire dalla macchina.
UNREACHABLE_OLLAMA = "http://127.0.0.1:9"


#: Il registro di `server.py`, per chi legge cio' che l'avvio scrive. Il
#: montaggio mette `hiris` a CRITICAL durante `_on_startup` e `_on_cleanup`, e
#: lo rimette com'era mentre l'app e' accesa. Chi vuole vedere cio' che scrive
#: L'AVVIO stesso da' quindi il livello al FIGLIO, che vale per il figlio
#: (`caplog.at_level(livello, logger=SERVER_LOGGER)`), e i suoi record
#: risalgono comunque fino al gestore di `caplog`.
SERVER_LOGGER = "hiris.app.server"


def credential_environment(present) -> dict[str, str]:
    """L'ambiente in cui hanno una credenziale i SOLI provider in `present`
    (un nome, o un dizionario `provider -> bool`)."""
    if isinstance(present, dict):
        present = [name for name, there in present.items() if there]
    values = {"ollama": UNREACHABLE_OLLAMA}
    return {variable: (values.get(provider, "credenziale-di-prova")
                       if provider in present else "")
            for provider, variable in CREDENTIAL_VARIABLES.items()}


@contextlib.asynccontextmanager
async def started_with(data_dir, environment: dict | None = None,
                       house_class=RecordingHouse):
    """L'app avviata DENTRO la prova, su una `data_dir` che la prova ha gia'
    preparato e con le variabili d'ambiente che la prova le da'
    (`environment`, sopra quelle del montaggio). Per chi deve guardare cosa
    l'avvio fa di cio' che trova: un archivio scritto prima, una credenziale
    presente o assente. Spenta all'uscita dal blocco `async with`."""
    with mock.patch.dict(os.environ, environment or {}):
        async with fotografia_porte.mounted(synthetic_inputs(), str(data_dir),
                                            house_class) as app:
            yield app


def router_routes(app=None) -> dict[str, str]:
    """`"METODO modello" -> nome del gestore`, dal router VERO dell'app.

    Il router e' il fatto, il sorgente una sua descrizione: una rotta
    registrata in un'altra forma (`add_route`, una funzione di `api/`, un
    modulo nuovo) qui compare, una regex su `server.py` no. Basta
    `create_app()`, senza avvio: le rotte si registrano li'. HEAD resta fuori
    (aiohttp la aggiunge da se' accanto a ogni GET)."""
    from hiris.app.server import create_app

    app = app if app is not None else create_app()
    return {f"{route.method} {route.resource.canonical}":
            getattr(route.handler, "__name__", repr(route.handler))
            for route in app.router.routes()
            if route.resource is not None and route.method != "HEAD"}
