"""Quante volte l'avvio legge Home Assistant: il numero di partenza.

Il requisito R18 dello sprint «Una fonte sola di verita'» vuole che «la casa
si legga una volta all'avvio». Per far scendere un numero bisogna prima
averlo: fino al 01/10/2026 era solo letto dal codice («circa 17 connessioni
piu' 4 letture intere», spec §1.4), mai contato eseguendo.

Questa prova AVVIA DAVVERO `server._on_startup` -- con lo stesso montaggio
della fotografia delle porte (`fotografia_porte.mounted`), che e' l'unico
punto in cui gli attrezzi avviano il prodotto -- su una casa sintetica che
conta ogni metodo che le viene chiesto.

**Cosa conta e cosa no, dichiarato.** Conta le chiamate che passano da
`HAClient`. NON conta chi lo aggira parlando con Home Assistant o col
Supervisor per conto suo (voce E-06 del registro): quelle chiamate qui vanno a
un indirizzo che rifiuta subito, e l'avvio prosegue come fa in produzione.

I TETTI sono i numeri di oggi. La Tappa 2 li abbassa; alzarli e' una riga di
diff che una revisione vede.

Mutazione ESEGUITA: aggiunta in `_on_startup` una seconda
`await entity_cache.load(ha_client)` -- rossa (`get_states`: 3, tetto 2).
"""
import asyncio
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fotografia_porte

from tests._casa_sintetica import synthetic_inputs

#: Le letture dell'INTERA casa: stati e registri. Sono quelle che R18 vuole a una.
WHOLE_HOUSE_CEILINGS = {"get_states": 2, "read_registries": 2}
NOT_QUESTIONS = ("ws_ready", "start", "stop", "start_websocket")


def _counting_house(calls: collections.Counter):
    class CountingHouse(fotografia_porte.FrozenHouse):
        """La casa congelata, col contatore. Un metodo che non sa servire
        risponde vuoto invece di sollevare: qui non si fotografa una porta, si
        conta chi bussa."""

        def __init__(self, base_url=None, token=None) -> None:
            super().__init__(synthetic_inputs())

        def __getattribute__(self, name: str):
            attribute = object.__getattribute__(self, name)
            if not name.startswith("_") and name not in NOT_QUESTIONS:
                calls[name] += 1
            return attribute

        def __getattr__(self, name: str):
            if name.endswith("_listener"):
                return lambda *args, **kwargs: None
            calls[name] += 1

            async def nothing(*args, **kwargs):
                return {}
            return nothing

    return CountingHouse


def startup_calls(tmp_path) -> dict[str, int]:
    """Avvia e spegne l'app vera; restituisce quante volte ogni metodo del
    client e' stato chiesto fino al ritorno di `_on_startup`."""
    calls: collections.Counter = collections.Counter()

    async def boot() -> dict[str, int]:
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path),
                                            _counting_house(calls)):
            return dict(calls)

    return asyncio.run(boot())


def test_l_avvio_legge_la_casa_intera_non_piu_di_oggi(tmp_path, capsys):
    counted = startup_calls(tmp_path)
    with capsys.disabled():
        print("\nchiamate al client durante l'avvio:",
              ", ".join(f"{name} {count}" for name, count in sorted(counted.items())))
    # Un avvio che non chiede niente al client vuol dire che il contatore non
    # e' piu' agganciato: la prova non guarderebbe niente e resterebbe verde.
    assert counted.get("read_registries"), counted
    assert counted.get("get_states"), counted
    over = {name: counted.get(name, 0) for name, ceiling in WHOLE_HOUSE_CEILINGS.items()
            if counted.get(name, 0) > ceiling}
    assert not over, f"letture dell'intera casa oltre il tetto {WHOLE_HOUSE_CEILINGS}: {over}"
