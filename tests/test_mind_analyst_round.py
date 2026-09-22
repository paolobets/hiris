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


# ---------------------------------------------------------------------------
# La guardia del ponte: un turno SCADUTO non e' in volo.
#
# **Difetto vivo, misurato sulla casa il 21/09/2026**: l'analista non scriveva
# un'analisi dal 16/09 -- cinque giorni, coi resoconti tutti archiviati. Il
# 17/09 un turno era stato accodato al ponte; poi il ponte e' stato spento, e
# la spazzata delle scadenze gira SOLO a ponte acceso (`server.py`: «mai
# accodare in una coda che nessuno spazza»). Quel turno e' rimasto `pending`
# per sempre, e `_analyst_turn_in_flight` -- che guardava solo «c'e' una
# risposta?» -- ha risposto «in volo» a ogni giro, per sempre.
#
# Le guardie gemelle dello scope e delle ricette, nello stesso file, lo
# scrivono da settimane: «uno scaduto NON e' in volo: se lo fosse, il giro
# aspetterebbe per sempre una risposta che nessuno dara' piu'». L'analista e'
# nato senza quella riga.
# ---------------------------------------------------------------------------

class _CodaConTurnoFermo:
    """Un turno accodato e mai risposto, con la scadenza passata."""

    def __init__(self, deadline_ts, status="pending"):
        self.turno = {"status": status, "deadline_ts": deadline_ts,
                      "wake": {"giorno": "2026-09-17"}, "decision": None}
        self.accodati = []

    def latest(self, kind):
        return self.turno

    def count_exchanges_today(self):
        return 0

    def enqueue(self, kind, wake, job, deadline, now=None):
        self.accodati.append(kind)


@pytest.mark.asyncio
async def test_un_turno_SCADUTO_non_blocca_l_analista_per_sempre(casa):
    """Mutazione: la guardia vecchia (`not reply`) -- rossa, e la casa resta
    senza analisi finche' qualcuno non se ne accorge."""
    app, _store, modello = casa
    app["reasoning_queue"] = _CodaConTurnoFermo(deadline_ts=1.0)

    await server.analyst_round(app)

    assert modello.chiamate == 1, (
        "un turno scaduto ha bloccato l'analista: e' il difetto del 17-21/09")


@pytest.mark.asyncio
async def test_un_turno_ANCORA_VALIDO_blocca_l_analista(casa):
    """La contropartita: senza di lei basterebbe togliere la guardia, e il
    ponte riceverebbe una domanda a ogni giro.

    Mutazione: togliere la guardia -- rossa."""
    import time as _t
    app, _store, modello = casa
    app["reasoning_queue"] = _CodaConTurnoFermo(deadline_ts=_t.time() + 600)

    await server.analyst_round(app)

    assert modello.chiamate == 0


# ---------------------------------------------------------------------------
# **Il difetto del 17-22/09, misurato sulla casa vera il 22/09/2026.**
#
# Il fix di 3.56.1 aveva chiuso `_turn_in_flight`. Cinque giorni dopo l'analista
# taceva ancora, e il registro dell'add-on diceva perche':
#
#   analista: risposta rifiutata per 2026-09-17 -- l'osservazione 1 parla di
#   «Presa Smart · potenza_media_min_max», che non e' fra le misure consegnate
#
# Non stava analizzando oggi: rimasticava il turno del 17. Quel turno e'
# `decided` con una risposta vera che **non puo' mai essere accettata**, e:
#
#   - una risposta rifiutata non si archivia (giusto: direbbe che quel giorno
#     e' stato analizzato);
#   - quindi `store.analysis("2026-09-17")` resta `None` per sempre;
#   - quindi il raccoglitore la riapplica a ogni giro, la rifiuta, e torna
#     `risposta: True` -- perche' il modello HA risposto, solo male;
#   - e `analyst_round` esce li', per sempre.
#
# **Quinta occorrenza della stessa forma**: la porta salta chi ha gia' una
# risposta, anche quando la risposta e' rotta. E ancora una volta la guardia
# che serviva c'era gia' nei fratelli: `_collect_recipe_turn` pretende
# `status == "decided"`, `_collect_actuator_turn` pretende `giorno == oggi`.
# L'analista era nato senza entrambe.
# ---------------------------------------------------------------------------

class _CodaConRispostaINACCETTABILE:
    """Un turno del ponte, RISPOSTO, di un altro giorno, che la validazione
    non potra' mai accettare."""

    def __init__(self, giorno="2026-09-17"):
        self.turno = {
            "status": "decided", "deadline_ts": 1.0,
            "wake": {"giorno": giorno},
            "decision": {"reply": '{"osservazioni": [{"soggetto": "Presa Smart",'
                                  ' "misura": "potenza", "chiave": null,'
                                  ' "innesco": 1, "cosa": "x",'
                                  ' "cosa_cambierebbe": "y"}]}'},
        }
        self.accodati = []

    def latest(self, kind):
        return self.turno

    def count_exchanges_today(self):
        return 0

    def enqueue(self, kind, wake, job, deadline, now=None):
        self.accodati.append(kind)


@pytest.mark.asyncio
async def test_una_risposta_di_UN_ALTRO_GIORNO_non_blocca_l_analista(casa):
    """**Il difetto vero, e costa sei giorni di silenzio.**

    Un turno risposto per il 17 non dice niente su oggi: riapplicarlo non puo'
    produrre l'analisi di oggi, e se quella risposta e' inaccettabile il giro
    non arrivera' MAI a guardare oggi.

    Mutazione ESEGUITA: togliere la guardia del giorno -- rossa, e la casa
    resta senza analisi finche' qualcuno non legge il registro.
    """
    app, _store, modello = casa
    app["reasoning_queue"] = _CodaConRispostaINACCETTABILE()

    await server.analyst_round(app)

    assert modello.chiamate == 1, (
        "un turno di un altro giorno ha impedito l'analisi di oggi: e' il "
        "difetto del 17-22/09")


@pytest.mark.asyncio
async def test_un_turno_ANCORA_SENZA_RISPOSTA_non_si_raccoglie(casa):
    """La seconda guardia mancante, quella che i fratelli hanno: un turno
    `pending` non ha niente da raccogliere, e provarci produce un esito finto
    («il modello non ha risposto») che a valle si legge come un giro gia' fatto.

    Mutazione: togliere il controllo sullo stato -- rossa."""
    app, store, _modello = casa
    coda = _CodaConRispostaINACCETTABILE()
    coda.turno["status"] = "pending"
    coda.turno["decision"] = None
    coda.turno["wake"] = {"giorno": _oggi(app)}
    app["reasoning_queue"] = coda

    # Si guarda il RACCOGLITORE, non il giro: dal giro non si distinguerebbe
    # «non ho raccolto niente» da «ho raccolto un esito vuoto», e una prova che
    # non distingue i due casi resta verde anche senza la guardia.
    raccolto = server._collect_analyst_turn(app, store, _oggi(app))

    assert raccolto is None, (
        "un turno «pending» ha prodotto un esito: e' l'esito finto «il modello "
        "non ha risposto», che a valle si legge come un giro gia' fatto")


def _oggi(app):
    from datetime import datetime

    from hiris.app.home_space.historian import home_space_zone
    fuso = server._timezone_from_home_space_store(app.get("home_space_store"))
    return datetime.now(home_space_zone(fuso)).date().strftime("%Y-%m-%d")
