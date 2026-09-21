"""Il GIRO dell'attuatore (spec 2026-09-21 §4): quando gira, e quando tace.

**Un'analisi, un'attuazione** -- la disciplina che l'analista applica a se'
(*un giorno, un'analisi*), applicata un piano piu' su. Il riferimento e'
l'ANALISI e non il giorno, e non e' un dettaglio: dalla 3.55.0 un'analisi si
rifa' quando cambia il suo fondamento, e un'attuazione fatta su quella vecchia
non vale piu'.

Il giro si aggancia allo stesso battito orario dell'analista e non fa niente
finche' l'analisi di oggi non c'e'. Cosi' parte quando l'analisi e' finita,
qualunque ora sia, senza inventare un orario.
"""
import datetime
import json

import pytest

from hiris.app import server
from hiris.app.home_space.historian import home_space_zone
from hiris.app.mind.store import ObservationsStore

OGGI = datetime.datetime.now(
    home_space_zone(server._timezone_from_home_space_store(None))).date().isoformat()


def _oss(**extra):
    riga = {"soggetto": "dev1", "misura": "prelievo", "chiave": None, "innesco": 1,
            "base": 19, "cosa": "il prelievo si stacca dal solito",
            "cosa_cambierebbe": "spostare i consumi nelle ore di sole"}
    riga.update(extra)
    return riga


def _analisi(*osservazioni, impronta="aaa"):
    return {"osservazioni": list(osservazioni) or [_oss()],
            "fondamento": {"giorni": 3, "impronta": impronta}}


class _FintoModello:
    """Il modello dal lato del giro: conta le chiamate e risponde un'indagine."""

    def __init__(self, risposta=None):
        self.chiamate = 0
        self.domande = []
        self._risposta = risposta

    async def chat(self, **kwargs):
        self.chiamate += 1
        self.domande.append(kwargs.get("user_message") or "")
        if self._risposta is not None:
            return self._risposta
        return json.dumps({"esiti": [
            {"osservazione": 0, "gesto": "indagine",
             "trovato": "il prelievo e' avvenuto fra le 19 e le 22"}]})


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    modello = _FintoModello()
    app = {"observations": store, "llm_router": modello, "bridge_active": False}
    try:
        yield app, store, modello
    finally:
        store.close()


@pytest.mark.asyncio
async def test_senza_analisi_non_gira_NIENTE(casa):
    """Un turno su niente e' un turno sprecato, e l'attuatore non ha nessun
    lavoro che non venga dall'analista.

    Mutazione: girare comunque -- rossa."""
    app, _store, modello = casa

    await server.actuator_round(app)

    assert modello.chiamate == 0


@pytest.mark.asyncio
async def test_un_analisi_una_ATTUAZIONE(casa):
    """Ventiquattro giri al giorno, un turno solo.

    Mutazione: togliere il confronto col fondamento -- rossa (un turno
    all'ora)."""
    app, store, modello = casa
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)
    await server.actuator_round(app)
    await server.actuator_round(app)

    assert modello.chiamate == 1


@pytest.mark.asyncio
async def test_l_attuazione_si_scrive_DENTRO_l_analisi(casa):
    """Gli esiti stanno accanto alle osservazioni che li hanno generati: sono
    la risposta a quelle domande, e in un archivio a parte servirebbe una
    giuntura per rimetterli insieme.

    Mutazione: non scrivere l'attuazione -- rossa."""
    app, store, _modello = casa
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    attuazione = store.analysis(OGGI)["attuazione"]
    assert attuazione["esiti"][0]["trovato"].startswith("il prelievo")
    assert attuazione["su_fondamento"] == "aaa"


@pytest.mark.asyncio
async def test_un_analisi_RIFATTA_fa_un_attuazione_nuova(casa):
    """Dalla 3.55.0 un'analisi si rifa' quando cambia il suo fondamento:
    l'attuazione fatta su quella vecchia parlava di numeri che non ci sono
    piu'.

    Mutazione: legare l'attuazione al GIORNO invece che al fondamento --
    rossa."""
    app, store, modello = casa
    store.replace_analysis(OGGI, _analisi())
    await server.actuator_round(app)

    store.replace_analysis(OGGI, _analisi(impronta="bbb"))

    await server.actuator_round(app)
    assert modello.chiamate == 2


@pytest.mark.asyncio
async def test_un_analisi_SENZA_osservazioni_non_fa_girare_niente(casa):
    """Il silenzio dell'analista e' un esito, e non c'e' niente da attuare.

    Mutazione: chiedere comunque -- rossa (un turno per un elenco vuoto)."""
    app, store, modello = casa
    store.replace_analysis(OGGI, {"osservazioni": [],
                                  "fondamento": {"giorni": 3, "impronta": "aaa"}})

    await server.actuator_round(app)

    assert modello.chiamate == 0


@pytest.mark.asyncio
async def test_una_risposta_STORTA_non_si_archivia_e_si_riprova(casa):
    """Stessa legge dell'analista: un'attuazione con dentro dei problemi non e'
    un'attuazione, e scriverla direbbe che quel giorno e' stato attuato.

    Mutazione: scrivere l'attuazione anche coi problemi -- rossa (il giro dopo
    non riproverebbe)."""
    app, store, _modello = casa
    app["llm_router"] = _FintoModello(risposta=json.dumps(
        {"esiti": [{"osservazione": 9, "gesto": "spegni"}]}))
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    assert "attuazione" not in store.analysis(OGGI)
    await server.actuator_round(app)
    assert app["llm_router"].chiamate == 2, "un giro storto deve riprovare"


# ---------------------------------------------------------------------------
# Il ponte: il piano risponde minuti dopo, da un altro processo.
# ---------------------------------------------------------------------------

class _FintaCoda:
    """La coda del ponte dal lato del giro: tiene un turno e la sua risposta.

    `count_exchanges_today` sta qui perche' `steering` la interroga per il
    tetto giornaliero del piano: una finta che non la avesse manderebbe il
    giro sulla catena, e la prova direbbe di provare il ponte provando altro.
    """

    def __init__(self, turno=None):
        self.turno = turno
        self.accodati = []

    def latest(self, kind):
        return self.turno

    def count_exchanges_today(self):
        return 0

    def enqueue(self, kind, wake, job, deadline, now=None):
        self.accodati.append((kind, wake, job))


@pytest.fixture()
def piano_acceso(monkeypatch):
    """Il token del Piano Max, finto: senza, `steering` manda alla catena."""
    monkeypatch.setattr("hiris.app.steering.subscription_has_token", lambda: True)


@pytest.mark.asyncio
async def test_col_PONTE_acceso_il_turno_si_accoda_e_non_si_chiama_il_modello(casa, piano_acceso):
    """Il ponte gira altrove e risponde minuti dopo: il giro accoda e torna
    subito, come fa l'analista.

    Mutazione: chiamare comunque il modello della catena -- rossa (si
    pagherebbe a consumo un turno che il piano copre)."""
    app, store, modello = casa
    coda = _FintaCoda()
    app.update({"bridge_active": True, "reasoning_queue": coda,
                "models_config": {"ponte": {"scadenza_min": 10}},
                })
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    assert modello.chiamate == 0
    assert coda.accodati, "il turno non e' stato accodato al piano"
    assert coda.accodati[0][0] == "attuazione"


@pytest.mark.asyncio
async def test_la_risposta_del_PONTE_si_raccoglie_e_si_archivia(casa, piano_acceso):
    """**Un turno raccolto non si rilegge**, e la traccia e' l'attuazione
    stessa: quando c'e', la risposta e' gia' stata applicata.

    Mutazione: non raccogliere -- rossa (il piano risponde e nessuno lo
    ascolta: il ponte resterebbe muto per sempre)."""
    app, store, modello = casa
    store.replace_analysis(OGGI, _analisi())
    risposta = json.dumps({"esiti": [
        {"osservazione": 0, "gesto": "indagine", "trovato": "risposto dal piano"}]})
    app.update({"bridge_active": True,
                "models_config": {"ponte": {"scadenza_min": 10}},
                "reasoning_queue": _FintaCoda(
                    {"wake": {"giorno": OGGI}, "decision": {"reply": risposta}})})

    await server.actuator_round(app)

    attuazione = store.analysis(OGGI)["attuazione"]
    assert attuazione["esiti"][0]["trovato"] == "risposto dal piano"
    assert modello.chiamate == 0
