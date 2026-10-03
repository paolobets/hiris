"""Quante volte l'avvio legge Home Assistant: il numero di partenza.

Il requisito R18 dello sprint «Una fonte sola di verita'» vuole che «la casa
si legga una volta all'avvio». Per far scendere un numero bisogna prima
averlo: fino al 01/10/2026 era solo letto dal codice («circa 17 connessioni
piu' 4 letture intere», spec §1.4), mai contato eseguendo.

Questa prova AVVIA DAVVERO `server._on_startup` -- con lo stesso montaggio
della fotografia delle porte (`fotografia_porte.mounted`), che e' l'unico
punto in cui gli attrezzi avviano il prodotto -- su una casa sintetica che
conta ogni metodo che le viene chiesto.

**Fin dove conta: l'avvio intero** (D1 del piano della Tappa 2, deciso dal
proprietario il 03/10/2026). Non si ferma al ritorno di `_on_startup`: conta
anche la prima connessione del websocket, che in produzione avvisa gli
ascoltatori («riconnessione») e fa rileggere specchio, anagrafe,
comportamento e plance, e aspetta che quelle riletture rimandate siano
finite. Fino al 03/10/2026 la casa finta buttava gli ascoltatori e la prova
contava 2 e 2: meno del vero.

**Cosa conta e cosa no, dichiarato.** Conta le chiamate che passano da
`HAClient`. NON conta chi lo aggira parlando con Home Assistant o col
Supervisor per conto suo (voce E-06 del registro): quelle chiamate qui vanno a
un indirizzo che rifiuta subito, e l'avvio prosegue come fa in produzione.

I TETTI sono i numeri misurati il 03/10/2026 (v3.73.2): sono quelli di
PARTENZA della Tappa 2, che li porta a 1 e 1 (R18). Alzarli e' una riga di
diff che una revisione vede.

Mutazione ESEGUITA: aggiunta in `_on_startup` una seconda
`await entity_cache.load(ha_client)` -- rossa (`get_states`: 3, tetto 2).
Rieseguita il 03/10/2026 sull'avvio intero: rossa (`get_states`: 5, tetto 4).
Rieseguita il 03/10/2026 sulla casa finta col client vero (Tappa 2, Task 4):
rossa (`get_states`: 5, tetto 4).
"""
import asyncio
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casa_finta
import fotografia_porte

from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

#: Le letture dell'INTERA casa: stati e registri. Sono quelle che R18 vuole a una.
WHOLE_HOUSE_CEILINGS = {"get_states": 4, "read_registries": 3}
#: Cio' che non e' una domanda alla casa: il ciclo di vita, gli ascoltatori
#: (iscriversi non e' bussare) e cio' che la casa finta registra.
NOT_QUESTIONS = ("ws_ready", "start", "stop", "start_websocket", "calls", "connections",
                 "served")


def _counting_house(calls: collections.Counter):
    class CountingHouse(fotografia_porte.FrozenHouse):
        """La casa congelata -- il client vero sugli ingressi sintetici
        (`scripts/casa_finta.py`) --, col contatore dei metodi chiesti.

        Fino al Task 4 della Tappa 2 un metodo che non sapeva servire
        rispondeva `{}`: una lettura nuova all'avvio sarebbe passata contata
        ma con una risposta inventata. Adesso un comando che gli ingressi non
        portano solleva col suo nome (`UnservedCommand`), e l'avvio si ferma."""

        def __init__(self, base_url=None, token=None) -> None:
            super().__init__(synthetic_inputs())

        def __getattribute__(self, name: str):
            attribute = object.__getattribute__(self, name)
            if (not name.startswith("_") and name not in NOT_QUESTIONS
                    and not name.endswith("_listener")):
                calls[name] += 1
            return attribute

    return CountingHouse


def startup_calls(tmp_path) -> dict[str, int]:
    """Avvia e spegne l'app vera; restituisce quante volte ogni metodo del
    client e' stato chiesto durante l'avvio intero: `_on_startup`, la prima
    connessione e i lavori che ha rimandato (`mounted` consegna l'app solo
    quando sono finiti)."""
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


# ── la prima connessione: la casa finta avvisa come il client vero ─────────

#: Il tetto dell'attesa della prima connessione. Una connessione finta non fa
#: I/O e si chiude in pochi passaggi del ciclo: il tetto serve solo a non
#: restare appesi se la connessione non avviene affatto.
CONNECTION_TIMEOUT_S = 5


async def _heard_at_first_connection(house) -> dict[str, list]:
    """Chi ascolta cosa, dalla sola prima connessione di `house`."""
    heard: dict[str, list] = {kind: [] for kind in casa_finta.listener_kinds()}
    for kind, received in heard.items():
        getattr(house, f"add_{kind}_listener")(received.append)
    await house.start_websocket()
    await asyncio.wait_for(house._session.connected.wait(), CONNECTION_TIMEOUT_S)
    await house.stop()
    return heard


def test_la_prima_connessione_della_casa_finta_avvisa_come_il_client_vero():
    """La casa finta ignorava gli ascoltatori: la rilettura che la prima
    connessione fa fare a specchio, anagrafe, comportamento e plance non
    passava mai, e il contatore d'avvio contava meno del vero (misurato il
    03/10/2026: 2 e 2 invece di 4 e 3, piano della Tappa 2, D1).

    Mutazioni ESEGUITE (03/10/2026): `start_websocket` della casa finta torna
    a non aprire niente -- rossa (la connessione non avviene); la casa finta
    torna a rispondere `lambda: None` agli `add_*_listener` -- rossa
    (servizi, topologia e plance non sentono niente); `listener_kinds()`
    restituisce `()` -- rossa (la derivazione e' vuota). Aggiunto a
    `HAClient` un genere nuovo (`add_ghost_listener`, avvisato da
    `_ws_loop`): verde senza toccare ne' la prova ne' la casa finta; tolto lo
    stesso genere dalla sola derivazione -- rossa (la casa finta non ha la
    lista che `_ws_loop` percorre, e la connessione non arriva in fondo)."""
    async def real() -> dict[str, list]:
        client = HAClient("http://casa.invalid", "token")
        client._session = casa_finta.SilentConnection()
        return await _heard_at_first_connection(client)

    async def frozen() -> dict[str, list]:
        return await _heard_at_first_connection(
            fotografia_porte.FrozenHouse(synthetic_inputs()))

    expected = asyncio.run(real())
    # La derivazione non si e' svuotata: il client vero avvisa qualcuno alla
    # prima connessione, o il confronto qui sotto sarebbe vuoto contro vuoto.
    assert any(expected.values()), expected
    assert asyncio.run(frozen()) == expected


def test_il_montaggio_consegna_l_app_a_riletture_della_prima_connessione_finite(tmp_path):
    """`startup_calls` conta fino a quando i lavori rimandati dalla prima
    connessione sono finiti: lo garantisce `mounted`, che consegna l'app solo
    dopo. Senza, le riletture con antirimbalzo partirebbero mentre l'app e'
    gia' in uso, e il contatore -- che ha solo tetti -- le perderebbe in
    silenzio, restando verde.

    Mutazioni ESEGUITE (03/10/2026): `_first_connection_settled` aspetta la
    connessione ma non i lavori rimandati -- rossa (anagrafe, comportamento e
    plance ancora in volo); `mounted` non chiama `_first_connection_settled`
    -- rossa (nessun lavoro rimandato: la connessione non e' ancora
    avvenuta)."""
    async def boot() -> tuple[list[str], list[str]]:
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
            deferred = app["ha_client"]._session.deferred_work
            return (sorted(task.get_name() for task in deferred),
                    sorted(task.get_name() for task in deferred if not task.done()))

    deferred, unfinished = asyncio.run(boot())
    # La prima connessione rimanda qualcosa: se non rimandasse niente la prova
    # sotto guarderebbe un insieme vuoto.
    assert deferred, "la prima connessione non ha rimandato nessun lavoro"
    assert not unfinished, f"lavori della prima connessione ancora in volo: {unfinished}"
