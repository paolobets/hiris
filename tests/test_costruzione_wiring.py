"""L'officina esiste nell'app vera, e nasce DOPO cio' di cui ha bisogno."""
import inspect

from hiris.app import server


def test_l_officina_e_l_archivio_sono_cablati():
    sorgente = inspect.getsource(server)
    assert 'app["costruzioni"] = ArchivioCostruzioni(' in sorgente
    assert 'app["officina"] = Officina(' in sorgente


def test_l_officina_riceve_solo_ha_e_cronaca_non_la_porta():
    """«un canale, una porta» (spec §2.1): l'officina scrive automazioni,
    la porta esegue servizi -- sono due canali di scrittura diversi e non
    devono confondersi. Si assert la chiamata INTERA, argomenti compresi,
    non solo il suo prefisso: un domani in cui qualcuno aggiungesse
    `app["porta_azione"]` come quarto argomento (il difetto che il brief
    nomina per nome) farebbe arrossire questo test, non uno che si accontenta
    di vedere 'Officina(' da qualche parte."""
    sorgente = inspect.getsource(server)
    assert ('app["officina"] = Officina(ha_client, app["costruzioni"], '
            'app["cronaca"])') in sorgente
    riga = next(r for r in sorgente.splitlines()
                if 'app["officina"] = Officina(' in r)
    assert "porta_azione" not in riga


def test_l_officina_nasce_dopo_la_cronaca_che_le_serve():
    """La cronaca e' un ingresso dell'officina: se nascesse dopo, ogni atto
    resterebbe senza riga di registro -- in silenzio."""
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["cronaca"] = Cronaca(') < sorgente.index('app["officina"] = Officina(')


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
