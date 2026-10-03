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
import sys
from pathlib import Path

import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

from tests._casa_sintetica import synthetic_inputs


class RecordingHouse(fotografia_porte.FrozenHouse):
    """La casa congelata che ricorda chi si e' iscritto ai suoi eventi, e in
    che ordine, e quante volte le si sono chiesti gli stati.

    E' la casa che l'avvio trova in `app["ha_client"]`: una prova chiede a lei
    QUALI ascoltatori l'avvio ha registrato -- e li chiama -- invece di cercare
    `add_state_listener(` nel testo di `server.py`. La firma e' quella con cui
    `_on_startup` costruisce `HAClient`."""

    def __init__(self, base_url=None, token=None) -> None:
        super().__init__(synthetic_inputs())
        #: `(nome del metodo, ascoltatore)`, nell'ordine dell'iscrizione.
        self.listeners: list[tuple[str, object]] = []
        self.state_reads = 0

    async def get_states(self, entity_ids):
        self.state_reads += 1
        return await super().get_states(entity_ids)

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
