"""Le costruzioni rimaste a meta' si risanano all'avvio.

Il cablaggio dell'officina -- chi tiene cosa, l'ordine col battito, la
chiusura allo spegnimento, le cinque rotte -- si guarda sull'app avviata, in
`tests/test_cablaggio_dell_avvio.py` (Tappa 1 dello sprint «Una fonte sola di
verita'»): fino al 03/10/2026 stava qui, come testo cercato in `server.py`."""
import inspect

from hiris.app import server


def test_le_costruzioni_rimaste_in_corso_si_risanano_all_avvio(tmp_path):
    """Senza questa chiamata una proposta rivendicata e mai conclusa resta un
    fantasma: invisibile, non applicabile, e cancellata in silenzio a 90 giorni.

    **Questo test prova la CHIAMATA, non la sua presenza nel sorgente, e la
    ragione e' un difetto vissuto.** La versione precedente diceva
    `assert 'app["constructions"].risana(' in sorgente` -- e una parola chiave
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
        avvio({"constructions": archivio}, _time, _FintoLogger(avvisi))

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
    marcatore = '    try:\n        app["constructions"].risana('
    inizio = src.index(marcatore)
    fine_marcatore = 'logger.warning("risanamento delle costruzioni in sospeso fallito: %s", exc)'
    fine = src.index(fine_marcatore, inizio) + len(fine_marcatore)
    corpo = textwrap.dedent(src[inizio:fine])
    firma = "def _risana(app, _time, logger):\n"
    namespace: dict = {}
    exec(compile(firma + textwrap.indent(corpo, "    "),
                 "<_on_startup risanamento costruzioni>", "exec"), namespace)
    return namespace["_risana"]


