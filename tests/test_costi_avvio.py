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

I TETTI sono l'obiettivo di R18: **la casa si legge una volta**,
`get_states` 1 e `read_registries` 1 (Task 7 della Tappa 2, 03/10/2026). Alzarli
e' una riga di diff che una revisione vede. La storia, misurata: 4 e 3 al
03/10/2026 (v3.73.2, l'avvio intero); il Task 5 ha tolto i registri interi dal
primo giro delle condizioni (`read_registries` 2), il Task 6 ha fatto leggere
il comportamento dallo specchio (`get_states` 2); il Task 7 ha rovesciato
l'ordine (D2, «prima l'iscrizione»): l'avvio apre il websocket, aspetta che
Home Assistant confermi l'iscrizione, e POI legge -- la prima connessione non
rilegge piu'.

Mutazione ESEGUITA: aggiunta in `_on_startup` una seconda
`await entity_cache.load(ha_client)` -- rossa (`get_states`: 3, tetto 2).
Rieseguita il 03/10/2026 sull'avvio intero: rossa (`get_states`: 5, tetto 4).
Rieseguita il 03/10/2026 sulla casa finta col client vero (Tappa 2, Task 4):
rossa (`get_states`: 5, tetto 4). Rieseguita col tetto sceso (Task 6): rossa
(`get_states`: 3, tetto 2). Rieseguita col tetto del Task 7: rossa
(`get_states`: 2, tetto 1).
"""
import asyncio
import collections
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casa_finta
import fotografia_porte

from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

#: Le letture dell'INTERA casa: stati e registri. Sono quelle che R18 vuole a una.
WHOLE_HOUSE_CEILINGS = {"get_states": 1, "read_registries": 1}
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


# ── le connessioni: la casa finta avvisa come il client vero ────────────────

#: Il tetto dell'attesa di una connessione. Una connessione finta non fa I/O
#: e si chiude in pochi passaggi del ciclo: il tetto serve solo a non restare
#: appesi se la connessione non avviene affatto.
CONNECTION_TIMEOUT_S = 5


async def _until_listening(connection, count: int) -> None:
    async def poll():
        while connection.listening < count:
            await asyncio.sleep(0)
    await asyncio.wait_for(poll(), CONNECTION_TIMEOUT_S)


async def _heard_over_two_connections(house) -> dict[str, list]:
    """Chi ascolta cosa, dalla prima connessione di `house` e da una seconda,
    dopo una caduta."""
    heard: dict[str, list] = {kind: [] for kind in casa_finta.listener_kinds()}
    for kind, received in heard.items():
        getattr(house, f"add_{kind}_listener")(received.append)
    # La finestra di scollegamento porta due istanti dell'orologio del client:
    # lo stesso orologio di passi, da tutte e due le parti, perche' il
    # confronto guardi chi ascolta e non quando.
    house._clock = itertools.count(1.0).__next__
    await house.start_websocket()
    await _until_listening(house._session, 1)
    house._session.drop()
    await _until_listening(house._session, 2)
    for _ in range(20):
        await asyncio.sleep(0)
    await house.stop()
    return heard


def test_le_connessioni_della_casa_finta_avvisano_come_il_client_vero(monkeypatch):
    """La casa finta ignorava gli ascoltatori: la rilettura che la prima
    connessione faceva fare a specchio, anagrafe, comportamento e plance non
    passava mai, e il contatore d'avvio contava meno del vero (misurato il
    03/10/2026: 2 e 2 invece di 4 e 3, piano della Tappa 2, D1). Dal Task 7 la
    prima connessione non avvisa piu' (D2): l'avviso viene dalla seconda, e la
    prova le guarda tutte e due.

    Mutazioni ESEGUITE (03/10/2026): `start_websocket` della casa finta torna
    a non aprire niente -- rossa (la connessione non avviene); la casa finta
    torna a rispondere `lambda: None` agli `add_*_listener` -- rossa
    (servizi, topologia e plance non sentono niente); `listener_kinds()`
    restituisce `()` -- rossa (la derivazione e' vuota). Aggiunto a
    `HAClient` un genere nuovo (`add_ghost_listener`, avvisato da
    `_ws_loop`): verde senza toccare ne' la prova ne' la casa finta; tolto lo
    stesso genere dalla sola derivazione -- rossa (la casa finta non ha la
    lista che `_ws_loop` percorre, e la connessione non arriva in fondo)."""
    from hiris.app.proxy import ha_client as ha_client_module

    # La caduta e' una chiusura pulita, che dal 07/10/2026 riparte dopo la
    # pausa di una caduta (S-29): a zero, si prova la sequenza, non l'orologio.
    monkeypatch.setattr(ha_client_module, "RECONNECT_DELAY_S", 0)

    async def real() -> dict[str, list]:
        client = HAClient("http://casa.invalid", "token")
        # La stessa casa dall'altra parte del filo: l'elenco iniziale delle
        # integrazioni viene dagli stessi ingressi.
        client._session = casa_finta.CasaFinta(synthetic_inputs())._session
        return await _heard_over_two_connections(client)

    async def frozen() -> dict[str, list]:
        return await _heard_over_two_connections(
            fotografia_porte.FrozenHouse(synthetic_inputs()))

    expected = asyncio.run(real())
    # La derivazione non si e' svuotata: il client vero avvisa qualcuno alla
    # seconda connessione, o il confronto qui sotto sarebbe vuoto contro vuoto.
    assert expected["topology"] == ["riconnessione"], expected
    assert asyncio.run(frozen()) == expected


def test_l_avvio_si_iscrive_prima_di_leggere_e_la_prima_connessione_non_rilegge(tmp_path):
    """D2 della Tappa 2, «prima l'iscrizione» (03/10/2026): l'avvio apre il
    websocket, si iscrive agli stati, aspetta che Home Assistant confermi
    (`ws_ready`), e POI legge la casa una volta. Fino a quel giorno leggeva
    prima e si iscriveva alla fine, e la prima connessione rileggeva tutto
    per coprire la finestra fra le due.

    `mounted` consegna l'app solo dopo la prima connessione e i lavori che ha
    rimandato (`_first_connection_settled`): qui la prova che non ne ha
    rimandato nessuno.

    Mutazioni ESEGUITE (03/10/2026, Task 7): `await entity_cache.load(...)`
    rimessa prima dell'apertura del websocket -- rossa (la lettura degli
    stati precede l'iscrizione); tolto il salto della prima connessione in
    `_ws_loop` -- rossa (anagrafe, comportamento e plance rimandati)."""
    async def boot():
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
            house = app["ha_client"]
            return (list(house._session.sent), list(house._session.sent_after),
                    [command for command, _extra in house.calls],
                    sorted(task.get_name() for task in house._session.deferred_work),
                    house._session.listening)

    sent, sent_after, calls, deferred, listening = asyncio.run(boot())
    subscription = next(i for i, message in enumerate(sent)
                        if message.get("event_type") == "state_changed")
    assert "/api/states" in calls, calls
    # Quante domande erano gia' partite quando ci si e' iscritti: nessuna
    # lettura degli stati fra quelle.
    assert "/api/states" not in calls[:sent_after[subscription]]
    assert listening == 1
    assert deferred == [], f"la prima connessione ha rimandato: {deferred}"


def test_l_avvio_finisce_anche_se_home_assistant_non_risponde(tmp_path, monkeypatch):
    """«Cosa guardare in revisione», 3: l'add-on parte prima del nucleo
    (`startup: services`). L'attesa della prima connessione ha un tetto,
    l'avvio finisce lo stesso, e chiede che la prima connessione -- quando
    arrivera' -- faccia rileggere cio' che l'avvio ha letto nel vuoto.

    Mutazione ESEGUITA (03/10/2026, Task 7): tolta la chiamata a
    `reread_after_first_connection` -- rossa (la prima connessione non
    rileggerebbe)."""
    from hiris.app import server
    from hiris.app.proxy import ha_client as ha_client_module

    monkeypatch.setattr(server, "FIRST_CONNECTION_CEILING_S", 0.05)
    # Dopo il rifiuto il client aspetta: la connessione non arriva durante
    # l'avvio, come quando il nucleo non e' ancora su.
    monkeypatch.setattr(ha_client_module, "AUTH_RETRY_FIRST_S", 3600)

    def unreachable(base_url=None, token=None):
        house = fotografia_porte.FrozenHouse(synthetic_inputs())
        house._session.refuse_next_auth("Home Assistant is starting")
        return house

    async def boot():
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path),
                                            unreachable) as app:
            return app["ha_client"]._reread_at_first_connection, \
                app["entity_cache"].loaded

    asked, loaded = asyncio.run(boot())
    assert asked
    # La casa finta risponde alle letture anche senza websocket: l'avvio ha
    # letto lo stesso, non ha aspettato la connessione per sempre.
    assert loaded


def _announced_kinds() -> list[str]:
    """I generi di ascoltatori che l'avviso «riconnessione» raggiunge,
    CHIESTI al client vero: uno per genere su un `HAClient` nudo, poi
    l'avviso, e si guarda chi l'ha ricevuto. Non ricopiati da
    `_announce_reconnection`: un genere nuovo avvisato entra da solo."""
    client = HAClient(base_url="http://ha.test", token="t")
    reached: list[str] = []
    for kind in casa_finta.listener_kinds():
        getattr(client, f"add_{kind}_listener")(
            lambda *_args, kind=kind: reached.append(kind))
    client._announce_reconnection()
    return sorted(set(reached))


def test_la_derivazione_degli_avvisati_contiene_quelli_di_oggi():
    assert set(_announced_kinds()) >= {"topology", "dashboard", "service"}, \
        _announced_kinds()


def test_la_prima_connessione_subito_dopo_il_tetto_avvisa_ogni_ascoltatore(tmp_path,
                                                                            monkeypatch):
    """La corsa all'avvio (revisione del ramo, 04/10/2026). Se Home Assistant
    non conferma entro il tetto, l'avvio chiede che la prima connessione
    faccia rileggere (`reread_after_first_connection`). Se quella
    connessione arriva SUBITO -- mentre l'avvio e' ancora fra l'apertura del
    websocket e le iscrizioni -- l'avviso va a chi e' iscritto in quel
    momento: chi si iscrive dopo non lo riceve, e la sua copia della casa
    (lo specchio letto nel vuoto, l'anagrafe, il comportamento, le plance)
    resta vuota fino al primo evento di registro.

    La prova fa arrivare la connessione esattamente li': l'apertura del
    websocket e' sostituita da un tetto gia' scaduto seguito dalla
    connessione, e si confrontano gli ascoltatori iscritti nell'istante
    dell'avviso con quelli iscritti a fine avvio, per ogni genere che
    l'avviso raggiunge."""
    from hiris.app import server

    announced = _announced_kinds()
    # Chi era iscritto quando l'avviso e' arrivato, genere per genere: lo
    # scrive una SONDA iscritta col metodo pubblico del client nell'istante in
    # cui l'avvio apre il websocket, e chiamata dall'avviso vero.
    at_announcement: dict[str, list] = {}
    probes: list = []

    async def connection_right_after_the_ceiling(ha_client) -> bool:
        for kind in announced:
            listeners = getattr(ha_client, f"_{kind}_listeners")

            def probe(*_args, kind=kind, listeners=listeners):
                at_announcement.setdefault(kind, [cb for cb in listeners
                                                  if cb not in probes])
            probes.append(probe)
            getattr(ha_client, f"add_{kind}_listener")(probe)
        # Il tetto e' scaduto: l'avvio chiede la rilettura alla prima
        # connessione, come `_open_websocket` ...
        ha_client.reread_after_first_connection()
        # ... e la connessione arriva subito, prima che l'avvio prosegua.
        await ha_client.start_websocket()
        await asyncio.wait_for(ha_client.ws_ready.wait(), 10)
        return False

    monkeypatch.setattr(server, "_open_websocket", connection_right_after_the_ceiling)

    async def boot():
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
            house = app["ha_client"]
            return {kind: [cb for cb in getattr(house, f"_{kind}_listeners")
                           if cb not in probes] for kind in announced}

    at_end = asyncio.run(boot())
    assert sorted(at_announcement) == announced, "la prima connessione non ha avvisato"
    for kind in announced:
        assert at_end[kind], f"nessun ascoltatore `{kind}` a fine avvio"
        missed = [listener for listener in at_end[kind]
                  if listener not in at_announcement[kind]]
        assert not missed, (
            f"`{kind}`: {len(missed)} ascoltatori iscritti dopo l'avviso della "
            "prima connessione, che non l'hanno ricevuto")
