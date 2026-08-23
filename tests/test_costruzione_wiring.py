"""L'officina esiste nell'app vera, e nasce DOPO cio' di cui ha bisogno."""
import inspect

from hiris.app import server


def test_l_officina_e_l_archivio_sono_cablati():
    sorgente = inspect.getsource(server)
    assert 'app["costruzioni"] = ArchivioCostruzioni(' in sorgente
    assert 'app["officina"] = Officina(' in sorgente


def test_l_officina_nasce_dopo_la_cronaca_che_le_serve():
    """La cronaca e' un ingresso dell'officina: se nascesse dopo, ogni atto
    resterebbe senza riga di registro -- in silenzio."""
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["cronaca"] = Cronaca(') < sorgente.index('app["officina"] = Officina(')


def test_i_due_archivi_si_chiudono_allo_spegnimento():
    sorgente = inspect.getsource(server)
    assert 'if "costruzioni" in app:' in sorgente
    assert 'app["costruzioni"].close()' in sorgente


def test_le_costruzioni_rimaste_in_corso_si_risanano_all_avvio():
    """Senza questa chiamata una proposta rivendicata e mai conclusa resta un
    fantasma: invisibile, non applicabile, e cancellata in silenzio a 90 giorni."""
    sorgente = inspect.getsource(server)
    assert 'app["costruzioni"].risana(' in sorgente
