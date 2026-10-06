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
import json

import pytest

from hiris.app import server
from hiris.app.home_space import historian
from hiris.app.mind.store import ObservationsStore

OGGI = historian.today(historian.house_timezone(None)).isoformat()


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

    def enqueue(self, kind, wake, job, deadline, now=None, priority=None, thread=None):
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
    assert coda.accodati[0][0] == "proposta"


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


# ---------------------------------------------------------------------------
# Il gesto PROPOSTA (spec §3): due forme, due archivi, una pagina.
# ---------------------------------------------------------------------------

class _FintaOfficina:
    """L'officina dal lato del giro: `propose` compone e NON scrive in casa."""

    def __init__(self, esito=None):
        self.intenzioni = []
        self._esito = esito or {"proposta_id": "c1", "anteprima": "diff"}

    async def propose(self, intent, *, actor, exchange, now):
        self.intenzioni.append((intent, actor))
        return self._esito


def _modello_proponente(costruibile, intenzione=None):
    corpo = {"osservazione": 0, "gesto": "proposta",
             "trovato": "Sposta la lavatrice nel primo pomeriggio",
             "costruibile": costruibile}
    if intenzione is not None:
        corpo["intenzione"] = intenzione
    return _FintoModello(risposta=json.dumps({"esiti": [corpo]}))


@pytest.mark.asyncio
async def test_una_proposta_NON_COSTRUIBILE_finisce_nell_archivio_delle_proposte(casa):
    """«Sposta i consumi nel pomeriggio» non e' un oggetto di Home Assistant:
    e' una cosa che fai tu, e va nella coda che la pagina mostra accanto alle
    altre.

    Mutazione: mandarla all'officina -- rossa (l'officina la rifiuterebbe, e
    la proposta sparirebbe)."""
    app, store, _modello = casa
    app["llm_router"] = _modello_proponente(False)
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    righe = store.proposals()
    assert len(righe) == 1
    assert righe[0]["testo"].startswith("Sposta la lavatrice")
    assert righe[0]["impronta"] == "dev1|prelievo|None|1"
    assert righe[0]["prova"]["base"] == 19, "senza la prova non si riapre mai"


@pytest.mark.asyncio
async def test_una_proposta_COSTRUIBILE_passa_dall_OFFICINA(casa):
    """«L'attuatore non guadagna un canale di scrittura suo» (25/08): passa da
    `costruisci`, che compone e valida contro QUESTA casa e non scrive niente.

    Mutazione: scriverla nell'archivio delle proposte a mano -- rossa (niente
    anteprima, niente diff, e un «crea» che non ha nulla da creare)."""
    app, store, _modello = casa
    officina = _FintaOfficina()
    app["workshop"] = officina
    app["llm_router"] = _modello_proponente(
        True, {"gesto": "crea", "dominio": "automation",
               # La forma che l'officina accetta (Tappa 6, Task 5): fino al
               # 05/10/2026 qui c'era `"richiesto": "accendi la lavatrice
               # alle 14"`, che `workshop.propose` rifiuta -- la prova
               # difendeva la forma sbagliata con un'officina finta.
               "innesco": [{"trigger": "time", "at": "14:00:00"}]})
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    assert officina.intenzioni, "l'officina non e' stata chiamata"
    intento, attore = officina.intenzioni[0]
    assert intento["gesto"] == "crea"
    assert attore == "proponente", "chi ha proposto deve restare scritto"
    assert store.proposals() == [], "una costruibile non va nell'archivio a mano"


@pytest.mark.asyncio
async def test_una_costruibile_SENZA_intenzione_si_rifiuta(casa):
    """Una proposta «costruibile» senza l'intenzione strutturata non e'
    costruibile: l'officina vuole gesto, dominio e il resto, e una frase in
    prosa non li ha.

    Mutazione: mandare all'officina un'intenzione vuota -- rossa."""
    app, store, _modello = casa
    app["workshop"] = _FintaOfficina()
    app["llm_router"] = _modello_proponente(True)
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    assert "attuazione" not in store.analysis(OGGI), (
        "una risposta storta non si archivia: il giro dopo riprova")


@pytest.mark.asyncio
async def test_la_stessa_proposta_non_si_scrive_DUE_volte(casa):
    """L'anti-ripetizione, dal lato dell'archivio: una domanda che ha gia' una
    proposta -- in qualunque stato -- non ne genera una seconda.

    Mutazione: non leggere le proposte decise -- rossa (una coda che cresce
    ogni giorno con la stessa riga)."""
    app, store, _modello = casa
    app["llm_router"] = _modello_proponente(False)
    store.replace_analysis(OGGI, _analisi())
    await server.actuator_round(app)

    store.replace_analysis(OGGI, _analisi(impronta="bbb"))
    await server.actuator_round(app)

    assert len(store.proposals()) == 1


@pytest.mark.asyncio
async def test_PIN_sulla_catena_la_proposta_si_archivia_E_l_attuazione_si_scrive(casa):
    """Pin della fetta «l'attuatore sul ponte» (28/09/2026), scritto PRIMA di
    toccare il giro: sulla catena lo stesso turno archivia la proposta da fare
    a mano **e** scrive l'attuazione col suo fondamento. La coda «esito ->
    proposte -> scrittura» si e' spostata in una funzione sola condivisa col
    ponte, e questo pin dice che la strada della catena non e' cambiata.

    Mutazione ESEGUITA: togliere l'archiviazione delle proposte dalla coda
    comune -- rossa."""
    app, store, _modello = casa
    app["llm_router"] = _modello_proponente(False)
    store.replace_analysis(OGGI, _analisi())

    await server.actuator_round(app)

    assert [r["impronta"] for r in store.proposals()] == ["dev1|prelievo|None|1"]
    attuazione = store.analysis(OGGI)["attuazione"]
    assert attuazione["su_fondamento"] == "aaa"
    assert attuazione["esiti"][0]["gesto"] == "proposta"
    assert attuazione["esiti"][0]["impronta"] == "dev1|prelievo|None|1"


# ---------------------------------------------------------------------------
# Le proposte raccolte dal PONTE (fetta «l'attuatore sul ponte», 28/09/2026).
#
# Il secondo difetto dietro il primo: la raccolta del ponte applicava la
# risposta e scriveva l'attuazione, ma **non archiviava le proposte** ne' le
# passava all'officina. Mai visto, perche' la risposta del ponte era sempre
# vuota -- il ponte non ragionava la specie.
# ---------------------------------------------------------------------------

def _risposta_proponente(costruibile, intenzione=None):
    corpo = {"osservazione": 0, "gesto": "proposta",
             "trovato": "Sposta la lavatrice nel primo pomeriggio",
             "costruibile": costruibile}
    if intenzione is not None:
        corpo["intenzione"] = intenzione
    return json.dumps({"esiti": [corpo]})


def _bridge_replied(app, risposta):
    app.update({"bridge_active": True,
                "models_config": {"ponte": {"scadenza_min": 10}},
                "reasoning_queue": _FintaCoda(
                    {"wake": {"giorno": OGGI}, "decision": {"reply": risposta}})})


@pytest.mark.asyncio
async def test_col_PONTE_una_proposta_da_fare_a_mano_si_ARCHIVIA(casa, piano_acceso):
    """Come sulla catena: la proposta che fa una persona va nella coda che la
    pagina mostra, con la sua impronta e la sua prova.

    Mutazione ESEGUITA: la raccolta del ponte che scrive senza passare dalla
    coda comune (com'era) -- rossa."""
    app, store, modello = casa
    store.replace_analysis(OGGI, _analisi())
    _bridge_replied(app, _risposta_proponente(False))

    await server.actuator_round(app)

    righe = store.proposals()
    assert [r["impronta"] for r in righe] == ["dev1|prelievo|None|1"]
    assert store.analysis(OGGI)["attuazione"]["su_fondamento"] == "aaa"
    assert modello.chiamate == 0


@pytest.mark.asyncio
async def test_col_PONTE_una_proposta_COSTRUIBILE_passa_dall_OFFICINA(casa, piano_acceso):
    """Come sulla catena: una costruibile passa da `costruisci`, e l'attuatore
    resta senza un canale di scrittura suo.

    Mutazione ESEGUITA: la raccolta del ponte che scrive senza passare dalla
    coda comune (com'era) -- rossa."""
    app, store, _modello = casa
    officina = _FintaOfficina()
    app["workshop"] = officina
    store.replace_analysis(OGGI, _analisi())
    _bridge_replied(app, _risposta_proponente(
        True, {"gesto": "crea", "dominio": "automation",
               # La forma che l'officina accetta (Tappa 6, Task 5): fino al
               # 05/10/2026 qui c'era `"richiesto": "accendi la lavatrice
               # alle 14"`, che `workshop.propose` rifiuta -- la prova
               # difendeva la forma sbagliata con un'officina finta.
               "innesco": [{"trigger": "time", "at": "14:00:00"}]}))

    await server.actuator_round(app)

    assert [(i["gesto"], attore) for i, attore in officina.intenzioni] == [
        ("crea", "proponente")]
    assert store.proposals() == []
