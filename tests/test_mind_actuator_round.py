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


# ---------------------------------------------------------------------------
# La riparazione: l'unico gesto che scrive senza chiedere (spec §2).
# ---------------------------------------------------------------------------

class _FintaAnagrafe:
    """L'anagrafe dal lato del giro: i dispositivi e il fuso della casa.

    `reference_frame` sta qui perche' il giro ci legge il fuso: senza, il
    giorno si calcolerebbe altrove e la prova proverebbe un'altra cosa."""

    def read(self):
        return {"dispositivi": [{"id": "dev2", "nome": "Inverter"}]}

    def reference_frame(self):
        return {}


def _oss_ricetta_rotta():
    return _oss(soggetto="dev2", misura="consumo", innesco=3, base=0,
                cosa="la misura non si calcola piu'",
                spiegato="il registro non sa piu' eseguire primo_ultimo",
                cosa_cambierebbe="ripristinare il calcolo")


@pytest.mark.asyncio
async def test_una_ricetta_ROTTA_si_riscrive_da_sola_e_lo_DICHIARA(casa, monkeypatch):
    """Spec §2, gesto 2. **E' lo stesso atto che il giro notturno delle
    ricette fa gia' senza chiedere**: non e' un potere nuovo, e' lo stesso
    potere applicato a una riga che esiste ed e' rotta -- quella che
    `devices_to_ask` non riguardera' mai, perche' salta chi una ricetta ce
    l'ha.

    Mutazione: proporre invece di riparare -- rossa (nessuna ricetta
    riscritta, e un consiglio tecnico in coda al posto di un fatto)."""
    app, store, _modello = casa
    app.update({"knowledge": object(), "home_space_store": _FintaAnagrafe()})
    chiamate = []

    async def _finta_ask(runner, sapere, home_space, device_id, **kwargs):
        chiamate.append(device_id)
        return {"scritta": True}

    monkeypatch.setattr(server.recipe_turn, "ask", _finta_ask)
    store.replace_analysis(OGGI, _analisi(_oss_ricetta_rotta()))

    await server.actuator_round(app)

    assert chiamate == ["dev2"], "la ricetta rotta non e' stata riscritta"
    esiti = store.analysis(OGGI)["attuazione"]["esiti"]
    riparazioni = [e for e in esiti if e["gesto"] == "riparazione"]
    assert riparazioni and riparazioni[0]["riscritta"] is True
    assert riparazioni[0]["soggetto"] == "dev2"


@pytest.mark.asyncio
async def test_senza_il_SAPERE_non_si_finge_nessuna_riparazione(casa):
    """L'add-on puo' essere partito a meta'. Una riparazione dichiarata e non
    avvenuta sarebbe una bugia archiviata, e il giorno dopo nessuno
    riproverebbe.

    Mutazione: scrivere l'esito prima di sapere com'e' andata -- rossa."""
    app, store, _modello = casa
    store.replace_analysis(OGGI, _analisi(_oss_ricetta_rotta()))

    await server.actuator_round(app)

    esiti = (store.analysis(OGGI).get("attuazione") or {}).get("esiti") or []
    assert [e for e in esiti if e["gesto"] == "riparazione"] == []


@pytest.mark.asyncio
async def test_un_esito_si_lega_all_IMPRONTA_dell_osservazione_non_alla_posizione(casa):
    """Il modello si riferisce a un'osservazione col suo NUMERO nell'elenco
    che gli abbiamo dato, e quell'elenco e' gia' filtrato (`to_handle`): la
    posizione vale dentro quel giro e basta. Archiviarla vorrebbe dire legare
    un esito a una riga che domani potrebbe essere un'altra.

    Mutazione: archiviare `osservazione` (l'indice) invece dell'impronta --
    rossa."""
    app, store, _modello = casa
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    esito = store.analysis(OGGI)["attuazione"]["esiti"][0]
    from hiris.app.mind import actuator

    assert esito["impronta"] == actuator.observation_key(_oss())


@pytest.mark.asyncio
async def test_col_ponte_un_turno_IN_VOLO_non_ne_accoda_un_secondo(casa, piano_acceso):
    """La guardia che all'attuatore mancava del tutto: senza, il ponte
    riceverebbe una domanda a ogni giro -- una coda di domande identiche che
    nessuno leggera' mai. E' lo stesso difetto che ha tenuto l'analista muto
    cinque giorni, preso dal verso opposto.

    Mutazione: togliere la guardia -- rossa (due accodamenti)."""
    import time as _t
    app, store, _modello = casa
    coda = _FintaCoda()
    coda.turno = {"status": "pending", "deadline_ts": _t.time() + 600,
                  "wake": {"giorno": OGGI}, "decision": None}
    app.update({"bridge_active": True, "reasoning_queue": coda,
                "models_config": {"ponte": {"scadenza_min": 10}}})
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    assert coda.accodati == [], "un secondo turno accodato mentre il primo aspetta"
