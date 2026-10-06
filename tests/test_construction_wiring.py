"""Le costruzioni rimaste a meta' si risanano all'avvio.

Il cablaggio dell'officina -- chi tiene cosa, l'ordine col battito, la
chiusura allo spegnimento, le cinque rotte -- si guarda sull'app avviata, in
`tests/test_cablaggio_dell_avvio.py` (Tappa 1 dello sprint «Una fonte sola di
verita'»): fino al 03/10/2026 stava qui, come testo cercato in `server.py`."""
import logging

import pytest


@pytest.mark.asyncio
async def test_le_costruzioni_rimaste_in_corso_si_risanano_all_avvio(tmp_path, caplog):
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

    Si guarda il DATO: un archivio vero, con una proposta lasciata
    `in_corso`, scritto nella `data_dir` PRIMA dell'avvio; dopo l'avvio la
    riga deve essere in uno stato terminale, e il registro non deve dire che
    il risanamento e' fallito. Fino al 03/10/2026 il blocco si ritagliava dal
    testo di `_on_startup`; adesso l'avvio gira davvero
    (`tests/_avvio.py::started_with`).

    Mutazione ESEGUITA (03/10/2026, sull'avvio vero): rimesso
    `risana(adesso=...)` -- rossa su `stato == "in_corso"`, e la riga di
    warning lo nomina.
    """
    import time as _time

    from hiris.app.action.construction.revisions import ConstructionStore
    from tests._avvio import SERVER_LOGGER, started_with

    archivio = ConstructionStore(str(tmp_path / "costruzioni.db"))
    try:
        ident = archivio.propose(
            operation="scrivi", domain="automation", key="test.risana",
            actor="prova", exchange=None, phrase=None, prima=None, dopo=None,
            helper=[], preview="", stakes=None, now=_time.time())["id"]
        # `claim` la porta a `in_corso`: e' lo stato che un riavvio a meta'
        # lascia sul disco, ed e' l'unica cosa che `risana()` sa chiudere.
        archivio.claim(ident, now=_time.time())
        assert archivio.read(ident)["stato"] == "in_corso"
    finally:
        archivio.close()

    with caplog.at_level(logging.WARNING, logger=SERVER_LOGGER):
        async with started_with(tmp_path) as app:
            stato = app["constructions"].read(ident)["stato"]
    avvisi = [rec.getMessage() for rec in caplog.records
              if "risanamento delle costruzioni" in rec.getMessage()]
    assert stato != "in_corso", (
        "la proposta e' rimasta `in_corso`: il risanamento non e' partito"
        + (f" -- l'avvio ha loggato {avvisi}" if avvisi else ""))
    assert not avvisi, f"il risanamento ha fallito ed e' stato inghiottito: {avvisi}"
