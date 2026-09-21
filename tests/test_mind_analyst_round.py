"""Il GIRO dell'analista: quando gira davvero, e quando tace.

**Il difetto che queste prove nascono per chiudere** (trovato dal proprietario
il 20/09/2026, leggendo il ritmo): il giro chiedeva «c'e' gia' un'analisi per
oggi?» e, se c'era, taceva fino all'indomani. Ma il fondamento dell'analisi --
i resoconti che legge -- **puo' cambiare nello stesso giorno**, in due modi che
esistono davvero:

1. `backfill_one_report` gira ogni cinque minuti e scrive il resoconto di un
   giorno che mancava (Home Assistant irraggiungibile, add-on riavviato);
2. quando un giudizio cambia, i giorni con l'impronta vecchia si rifanno da
   soli, uno ogni cinque minuti.

In entrambi i casi l'analisi restava quella di prima, **per sempre**: quel
giorno non veniva piu' riletto, e l'indomani si analizzava l'indomani. E' la
terza volta che questo prodotto paga la stessa forma -- *la porta salta chi ha
gia' una risposta, anche quando la risposta e' vecchia*: le altre due sono
`devices_to_ask`, che salta i dispositivi con una ricetta rotta, e i dieci
dispositivi bloccati da un rifiuto che nessuno faceva scadere.

La cura e' quella che il prodotto usa gia' un piano piu' sotto: **l'impronta**.
L'analisi porta il proprio fondamento, e il giro chiede «c'e' gia' un'analisi
SU QUESTO fondamento?».

Queste sono le prime prove che fanno girare `server.analyst_round` per intero:
prima d'ora nessuna toccava i giri dello schedulatore, ed e' anche per questo
che il difetto ha potuto vivere.
"""
import json

import pytest

from hiris.app import server
from hiris.app.mind.store import ObservationsStore


class _FintoModello:
    """Il modello, dal lato del giro: conta le chiamate e risponde silenzio.

    **Il silenzio e' un esito legittimo** (spec §10), e va bene per queste
    prove: qui si misura QUANDO il giro chiede, non cosa il modello risponde.
    """

    def __init__(self):
        self.chiamate = 0

    async def chat(self, **kwargs):
        self.chiamate += 1
        return json.dumps({"osservazioni": []})


def _resoconto(giorno, valore=1.0):
    return {"giorno": giorno, "obiettivo": None,
            "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "operazione": "somma_periodo", "valore": valore,
                        "unita": "kWh", "copertura": 1.0}],
            "forme": [], "cronaca": []}


@pytest.fixture()
def casa(tmp_path):
    """Un archivio con tre giorni di resoconti, e l'app minima del giro."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    for giorno in ("2026-09-15", "2026-09-16", "2026-09-17"):
        store.replace_report(giorno, _resoconto(giorno))
    modello = _FintoModello()
    app = {"observations": store, "llm_router": modello, "bridge_active": False}
    try:
        yield app, store, modello
    finally:
        store.close()


@pytest.mark.asyncio
async def test_un_giorno_senza_analisi_FA_un_turno_e_scrive_il_fondamento(casa):
    """Mutazione: non attaccare il fondamento all'analisi -- rossa (il giro
    dopo non saprebbe su cosa era stata scritta)."""
    app, store, modello = casa

    await server.analyst_round(app)

    import datetime

    from hiris.app.home_space.historian import home_space_zone

    assert modello.chiamate == 1
    # Il giorno si calcola **come lo calcola il giro** (fuso della casa), non
    # con l'orologio di chi fa girare la suite: una prova che guarda un altro
    # giorno passerebbe o cadrebbe a seconda dell'ora.
    fuso = server._timezone_from_home_space_store(None)
    oggi = datetime.datetime.now(home_space_zone(fuso)).date().isoformat()
    scritta = store.analysis(oggi)
    assert scritta is not None, "il giro non ha scritto l'analisi di oggi"
    assert scritta.get("fondamento"), "l'analisi non dice su cosa e' stata scritta"


@pytest.mark.asyncio
async def test_lo_STESSO_fondamento_non_fa_girare_niente(casa):
    """Ventiquattro giri al giorno, un turno solo: e' la ragione per cui il
    giro esiste orario e l'analisi e' giornaliera.

    Mutazione: togliere il confronto e chiedere sempre -- rossa (24 turni da
    35.000 token)."""
    app, _store, modello = casa

    await server.analyst_round(app)
    await server.analyst_round(app)
    await server.analyst_round(app)

    assert modello.chiamate == 1


@pytest.mark.asyncio
async def test_un_resoconto_RECUPERATO_rifa_l_analisi(casa):
    """Il caso vero numero uno: `backfill_one_report` scrive alle 15:00 il
    resoconto di un giorno che mancava. L'analisi delle 14:00 non lo ha visto.

    Mutazione: tenere il vecchio confronto (`analysis(oggi) is not None`) --
    rossa (il giorno recuperato non entra in nessuna analisi, mai)."""
    app, store, modello = casa
    await server.analyst_round(app)
    assert modello.chiamate == 1

    store.replace_report("2026-09-14", _resoconto("2026-09-14"))

    await server.analyst_round(app)
    assert modello.chiamate == 2, "il resoconto recuperato non ha fatto rifare l'analisi"


@pytest.mark.asyncio
async def test_un_giorno_RIFATTO_rifa_l_analisi(casa):
    """Il caso vero numero due: correggi un giudizio, e il giorno si rifa' da
    solo. Il contenuto puo' essere identico -- e' l'ISTANTE di scrittura a
    dire che qualcuno lo ha toccato.

    Mutazione: mettere nel fondamento i soli giorni e non quando sono stati
    scritti -- rossa (un giorno rifatto e' invisibile)."""
    app, store, modello = casa
    await server.analyst_round(app)

    store.replace_report("2026-09-16", _resoconto("2026-09-16"))

    await server.analyst_round(app)
    assert modello.chiamate == 2, "un giorno rifatto non ha fatto rifare l'analisi"


@pytest.mark.asyncio
async def test_l_analisi_rifatta_SOSTITUISCE_e_non_si_accoda(casa):
    """Due verita' sullo stesso giorno sono il difetto che «costruire» ha gia'
    pagato: `replace_analysis` sostituisce, e il fondamento nuovo prende il
    posto del vecchio.

    Mutazione: scrivere l'analisi senza aggiornare il fondamento -- rossa (il
    giro rifarebbe l'analisi a ogni ora, per sempre)."""
    app, store, modello = casa
    await server.analyst_round(app)
    store.replace_report("2026-09-14", _resoconto("2026-09-14"))
    await server.analyst_round(app)
    conteggio = modello.chiamate

    await server.analyst_round(app)

    assert modello.chiamate == conteggio, (
        "dopo aver rifatto l'analisi il giro ha chiesto di nuovo: il fondamento "
        "scritto non e' quello su cui e' stata rifatta")
