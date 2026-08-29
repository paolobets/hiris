"""L'officina esiste nell'app vera, e nasce DOPO cio' di cui ha bisogno."""
import inspect

from hiris.app import server


def test_l_officina_e_l_archivio_sono_cablati():
    sorgente = inspect.getsource(server)
    assert 'app["costruzioni"] = ConstructionStore(' in sorgente
    assert 'app["officina"] = Workshop(' in sorgente


def test_l_officina_riceve_solo_ha_e_cronaca_non_la_porta():
    """«un canale, una porta» (spec §2.1): l'officina scrive automazioni,
    la porta esegue servizi -- sono due canali di scrittura diversi e non
    devono confondersi. Si assert la chiamata INTERA, argomenti compresi,
    non solo il suo prefisso: un domani in cui qualcuno aggiungesse
    `app["porta_azione"]` come quarto argomento (il difetto che il brief
    nomina per nome) farebbe arrossire questo test, non uno che si accontenta
    di vedere 'Workshop(' da qualche parte.

    Dal Task 11 la chiamata porta anche `read_timezone` (il fuso della casa,
    non del container, nella data dell'anteprima di ripristino): l'assert
    resta sull'intera chiamata, ora su piu' righe."""
    sorgente = inspect.getsource(server)
    inizio = sorgente.index('app["officina"] = Workshop(')
    fine = sorgente.index(")\n", inizio) + 1
    chiamata = sorgente[inizio:fine]
    assert chiamata == (
        'app["officina"] = Workshop(\n'
        '        ha_client, app["costruzioni"], app["cronaca"],\n'
        '        read_timezone=lambda: _fuso_da_archivio_casa(app.get("archivio_casa")))'
    )
    assert "porta_azione" not in chiamata


def test_l_officina_nasce_dopo_la_cronaca_che_le_serve():
    """La cronaca e' un ingresso dell'officina: se nascesse dopo, ogni atto
    resterebbe senza riga di registro -- in silenzio."""
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["cronaca"] = Journal(') < sorgente.index(
        'app["officina"] = Workshop(')


def test_i_due_archivi_si_chiudono_nel_gestore_di_spegnimento():
    """Le due `close()` devono stare DENTRO `_on_cleanup`, il gestore che
    aiohttp chiama davvero allo spegnimento -- non semplicemente da qualche
    parte nel modulo, dove una `close()` scritta in un gestore mai registrato
    (o mai chiamato) passerebbe comunque. Si ispeziona il sorgente della
    SOLA funzione di cleanup, non del modulo intero."""
    sorgente_cleanup = inspect.getsource(server._on_cleanup)
    assert 'if "costruzioni" in app:' in sorgente_cleanup
    assert 'app["costruzioni"].close()' in sorgente_cleanup


def test_le_costruzioni_rimaste_in_corso_si_risanano_all_avvio():
    """Senza questa chiamata una proposta rivendicata e mai conclusa resta un
    fantasma: invisibile, non applicabile, e cancellata in silenzio a 90 giorni."""
    sorgente = inspect.getsource(server)
    assert 'app["costruzioni"].risana(' in sorgente


def test_il_risanamento_delle_costruzioni_precede_il_battito_dello_schedulatore():
    """L'ordine e' la proprieta' per cui questo task esiste: se il
    risanamento delle proposte `in_corso` scattasse DOPO che il battito
    dello schedulatore e' stato registrato, un giro dello scheduler potrebbe
    partire (durante lo stesso `_on_startup`, prima che questa riga corra) e
    toccare una riga che `risana()` avrebbe dovuto dichiarare incerta --
    riaprendo in silenzio lo stato fantasma che questo stesso task chiude.
    L'ancora e' l'id del job di battito (univoco nel file), non la
    formattazione multilinea della chiamata a `scheduler.add_job`."""
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["costruzioni"].risana(') < sorgente.index(
        'id="hiris_schedulatore_battito"')


def test_le_cinque_rotte_sono_registrate():
    """Ondata finale, punto 6: la registrazione di `/rifiuta` non era pinnata
    da nessun test, e le altre quattro erano pinnate solo per SOTTOSTRINGA
    (`'"/api/costruzioni/{id}/conferma"' in sorgente`), che una registrazione
    commentata avrebbe lasciato passare -- la sottostringa combacia UGUALE
    dentro un commento (`# app.router.add_post(...)` la contiene per intero),
    quindi `in sorgente` da solo non basta: serve una riga, non solo un
    frammento (misurato mutando `add_post(".../rifiuta"...)` in un
    commento -- la vecchia forma restava verde). Si cerca la riga ESATTA
    (spogliata dell'indentazione) fra le righe del sorgente, non un
    sottinsieme di caratteri al suo interno."""
    sorgente = inspect.getsource(server)
    righe = [r.strip() for r in sorgente.splitlines()]
    for attesa in (
        'app.router.add_get("/api/costruzioni", handle_get_costruzioni)',
        'app.router.add_get("/api/costruzioni/{id}", handle_get_costruzione)',
        'app.router.add_post("/api/costruzioni/{id}/conferma", handle_conferma_costruzione)',
        'app.router.add_post("/api/costruzioni/{id}/ripristina", handle_ripristina_costruzione)',
        'app.router.add_post("/api/costruzioni/{id}/rifiuta", handle_rifiuta_costruzione)',
    ):
        assert attesa in righe, f"rotta non registrata (o commentata): {attesa}"
