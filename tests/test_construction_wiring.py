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
        '        read_timezone=lambda: _timezone_from_home_space_store(app.get("archivio_casa")))'
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


def test_le_costruzioni_rimaste_in_corso_si_risanano_all_avvio(tmp_path):
    """Senza questa chiamata una proposta rivendicata e mai conclusa resta un
    fantasma: invisibile, non applicabile, e cancellata in silenzio a 90 giorni.

    **Questo test prova la CHIAMATA, non la sua presenza nel sorgente, e la
    ragione e' un difetto vissuto.** La versione precedente diceva
    `assert 'app["costruzioni"].risana(' in sorgente` -- e una parola chiave
    SBAGLIATA la soddisfaceva uguale. Il 29/08 la conversione di `action/` ha
    rinominato il parametro nella `def` (`adesso -> now`) e ha lasciato indietro
    il chiamante: `risana(adesso=...)` contro `def risana(*, now)`. **Il
    `try/except Exception` che avvolge la riga inghiottiva il `TypeError` in un
    warning, quindi il risanamento non e' mai avvenuto** -- in produzione, dal
    29 agosto -- e questo test e' rimasto verde per tre giorni. E' il difetto
    n.1 del progetto commesso dentro il test che sorvegliava la riga rotta.

    Adesso il blocco di `_on_startup` si ESEGUE, su un archivio vero con una
    proposta lasciata `in_corso`, e si guarda il DATO: la riga deve essere
    finita in uno stato terminale. Una parola chiave sbagliata non la sposta,
    perche' la chiamata non parte nemmeno -- e il `try/except` che nasconde
    l'errore al log non puo' nascondere una riga che non e' cambiata.

    Provato per mutazione: rimesso `adesso=` in `server.py`, questo test va
    rosso su `stato == "in_corso"` (e la riga di warning lo nomina).
    """
    import time as _time

    from hiris.app.action.construction.revisions import ConstructionStore

    archivio = ConstructionStore(str(tmp_path / "costruzioni.db"))
    try:
        ident = archivio.propose(
            operation="scrivi", domain="automation", key="test.risana",
            actor="prova", exchange=None, phrase=None, prima=None, dopo=None,
            helper=[], preview="", now=_time.time())["id"]
        # `claim` la porta a `in_corso`: e' lo stato che un riavvio a meta'
        # lascia sul disco, ed e' l'unica cosa che `risana()` sa chiudere.
        archivio.claim(ident, now=_time.time())
        assert archivio.read(ident)["stato"] == "in_corso"

        avvio = _blocco_risanamento_costruzioni()
        avvisi: list[str] = []
        avvio({"costruzioni": archivio}, _time, _FintoLogger(avvisi))

        assert archivio.read(ident)["stato"] != "in_corso", (
            "la proposta e' rimasta `in_corso`: il risanamento non e' partito"
            + (f" -- il blocco ha loggato {avvisi}" if avvisi else ""))
        assert not avvisi, f"il risanamento ha fallito ed e' stato inghiottito: {avvisi}"
    finally:
        archivio.close()


class _FintoLogger:
    """Raccoglie i `warning` invece di stamparli: il blocco di produzione
    inghiotte l'eccezione in un log, e senza questa finta l'unica prova del
    guasto sarebbe uscita su stderr, dove nessun assert la vede."""

    def __init__(self, avvisi: list[str]) -> None:
        self._avvisi = avvisi

    def warning(self, msg, *args) -> None:
        self._avvisi.append(msg % args if args else msg)


def _blocco_risanamento_costruzioni():
    """Il blocco VERO di `_on_startup`, estratto e reso chiamabile.

    Stessa tecnica di `tests/test_websocket_startup.py` e
    `tests/test_options_migration.py`: si esegue il codice di produzione, non
    una sua parafrasi, cosi' che toglierlo da `_on_startup` -- o sbagliarne una
    parola chiave -- faccia fallire il test invece di lasciarlo verde.
    """
    import textwrap

    src = inspect.getsource(server._on_startup)
    marcatore = '    try:\n        app["costruzioni"].risana('
    inizio = src.index(marcatore)
    fine_marcatore = 'logger.warning("risanamento delle costruzioni in sospeso fallito: %s", exc)'
    fine = src.index(fine_marcatore, inizio) + len(fine_marcatore)
    corpo = textwrap.dedent(src[inizio:fine])
    firma = "def _risana(app, _time, logger):\n"
    namespace: dict = {}
    exec(compile(firma + textwrap.indent(corpo, "    "),
                 "<_on_startup risanamento costruzioni>", "exec"), namespace)
    return namespace["_risana"]


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
    """Ondata finale, punto 6: la registrazione di `/reject` non era pinnata
    da nessun test, e le altre quattro erano pinnate solo per SOTTOSTRINGA
    (`'"/api/constructions/{id}/confirm"' in sorgente`), che una registrazione
    commentata avrebbe lasciato passare -- la sottostringa combacia UGUALE
    dentro un commento (`# app.router.add_post(...)` la contiene per intero),
    quindi `in sorgente` da solo non basta: serve una riga, non solo un
    frammento (misurato mutando `add_post(".../reject"...)` in un
    commento -- la vecchia forma restava verde). Si cerca la riga ESATTA
    (spogliata dell'indentazione) fra le righe del sorgente, non un
    sottinsieme di caratteri al suo interno."""
    sorgente = inspect.getsource(server)
    righe = [r.strip() for r in sorgente.splitlines()]
    for attesa in (
        'app.router.add_get("/api/constructions", handle_get_constructions)',
        'app.router.add_get("/api/constructions/{id}", handle_get_construction)',
        'app.router.add_post("/api/constructions/{id}/confirm", handle_confirm_construction)',
        'app.router.add_post("/api/constructions/{id}/restore", handle_restore_construction)',
        'app.router.add_post("/api/constructions/{id}/reject", handle_reject_construction)',
    ):
        assert attesa in righe, f"rotta non registrata (o commentata): {attesa}"
