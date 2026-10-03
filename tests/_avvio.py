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


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def started_app(tmp_path_factory):
    """L'app avviata sulla casa sintetica, spenta alla fine del file."""
    data_dir = str(tmp_path_factory.mktemp("avvio"))
    async with fotografia_porte.mounted(synthetic_inputs(), data_dir) as app:
        yield app
