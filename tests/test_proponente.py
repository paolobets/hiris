"""Il proponente con `propose` (piano degli attori, strato 4, Task 4.2; D12).

Il proponente chiama lo stesso `propose` della chat: l'officina compone e
valida DENTRO il turno, e se rifiuta il modello vede il perche' e corregge.
Il turno si chiude con un esito per osservazione -- «costruita», «a_mano»,
«niente» -- e l'id di una proposta costruita lo dice l'archivio delle
costruzioni (`ConstructionStore.proposed_in`), non il modello.

Le prove del cancello §7.1 (nessuna scrittura verso Home Assistant dal turno)
stanno in `tests/test_mind_actuator_guards.py`.
"""
from __future__ import annotations

import json

import pytest

from hiris.app import steering
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.home_space import historian
from hiris.app.mind import proposer_round as pr
from hiris.app.mind import proposer_turn as pt
from hiris.app.mind.analyst import evidence_of, observation_key
from hiris.app.mind.store import ObservationsStore
from hiris.app.usage.store import UsageStore

OGGI = historian.today(historian.house_timezone(None)).isoformat()


def osservazioni():
    """Due osservazioni aperte dell'analista, come le scrive `apply_analysis`."""
    return [
        {"soggetto": "dev1", "nome": "Scaldabagno", "misura": "prelievo",
         "chiave": None, "innesco": 1, "base": 19, "valore": 4.0,
         "cosa": "il prelievo notturno e' salito", "spiegato": None,
         "cosa_cambierebbe": "meno spesa"},
        {"soggetto": "dev2", "nome": "Lavatrice", "misura": "prelievo",
         "chiave": None, "innesco": 2, "base": 19, "valore": 1.0,
         "cosa": "lava sempre alle 19", "spiegato": None,
         "cosa_cambierebbe": None},
    ]


_INTENZIONE_BUONA = {"gesto": "crea", "dominio": "automation",
                     "alias": "Scaldabagno di notte", "innesco": [], "azioni": []}


class _Officina:
    """L'officina dal lato del turno: rifiuta un'intenzione senza `alias`,
    altrimenti scrive nell'archivio vero delle costruzioni, col turno."""

    def __init__(self, archivio):
        self.archivio = archivio
        self.chiamate = []

    async def propose(self, intent, *, actor, exchange, now, thread=None,
                      reveal_before=True, refuse_high=False):
        self.chiamate.append({"intent": intent, "actor": actor,
                              "exchange": exchange})
        if not intent.get("alias"):
            return {"errore": "manca l'alias dell'automazione"}
        nata = self.archivio.propose(
            operation=intent["gesto"], domain=intent["dominio"], key="k1",
            actor=actor, exchange=exchange, phrase=intent.get("frase"),
            prima=None, dopo={"alias": intent["alias"]}, helper=[],
            preview="anteprima", stakes=None, now=now)
        return {"proposta_id": nata["id"], "anteprima": "anteprima"}


class _Modello:
    """Il modello dal lato del giro: esegue i passi che gli si danno -- le
    chiamate di strumento col dispatcher del turno, poi la risposta -- e tiene
    cio' che gli strumenti gli hanno risposto."""

    def __init__(self, *turni):
        self.turni = list(turni)
        self.domande: list[str] = []
        self.risultati: list[dict] = []
        self.strumenti: list[list[str]] = []
        self.last_tool_calls: list = []

    async def chat(self, **kwargs):
        self.domande.append(kwargs["user_message"])
        self.strumenti.append([d["name"] for d in kwargs.get("tools") or []])
        chiamate, risposta = self.turni.pop(0)
        for nome, argomenti in chiamate:
            self.risultati.append(await kwargs["dispatcher"].dispatch(nome, argomenti))
        return risposta(self.risultati) if callable(risposta) else risposta


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    usage = UsageStore(str(tmp_path / "consumi.db"))
    costruzioni = ConstructionStore(str(tmp_path / "costruzioni.db"))
    store.replace_analysis(OGGI, {"osservazioni": osservazioni(),
                                  "fondamento": {"giorni": 3, "impronta": "aaa"}})
    app = {"observations": store, "usage": usage, "constructions": costruzioni,
           "workshop": _Officina(costruzioni), "bridge_active": False}
    try:
        yield app
    finally:
        store.close()
        usage.close()
        costruzioni.close()


def _id_nato(risultati):
    return next(r["proposta_id"] for r in risultati if "proposta_id" in r)


# -- Passo 1: le prove rosse --------------------------------------------------

@pytest.mark.asyncio
async def test_l_officina_RIFIUTA_dentro_il_turno_il_modello_corregge(casa):
    """D12: niente piu' proposte perse dopo il turno (R0, M2: 2 su 2). La
    prima intenzione e' storta, l'officina risponde col perche', la seconda
    passa, e la risposta cita l'id che l'officina ha dato.

    Rossa sul giro di prima: il proponente non aveva strumenti, e la sua
    intenzione arrivava all'officina dopo il turno. Mutazione ESEGUITA
    (06/10/2026): il giro della catena senza `tools` -- rossa."""
    app = casa
    storta = {k: v for k, v in _INTENZIONE_BUONA.items() if k != "alias"}
    app["llm_router"] = _Modello((
        [("propose", storta), ("propose", _INTENZIONE_BUONA)],
        lambda risultati: json.dumps({"esiti": [
            {"osservazione": 0, "esito": "costruita",
             "proposta_id": _id_nato(risultati)},
            {"osservazione": 1, "esito": "niente", "perche": "e' un'abitudine"}]})))

    esito = await pr.proposer_round(app)

    modello = app["llm_router"]
    # Gli strumenti sulla catena vengono dalla dichiarazione del mestiere.
    assert "propose" in modello.strumenti[0] and "execute" not in modello.strumenti[0]
    assert "errore" in modello.risultati[0]
    assert esito["problemi"] == []
    accanto = pt.outcomes_of(app["observations"].analysis(OGGI))
    assert [o["esito"] for o in accanto] == ["costruita", "niente"]
    assert accanto[0]["proposta_id"] == _id_nato(modello.risultati)
    assert app["constructions"].read(accanto[0]["proposta_id"])["origine"] == \
        steering.PROPOSER_SPECIES
    assert app["usage"].turns()[0]["outcome"] == steering.SUCCEEDED


@pytest.mark.asyncio
async def test_COSTRUITA_senza_una_chiamata_riuscita_si_rifiuta(casa):
    """Il modello non puo' dichiarare una proposta che non c'e': l'id lo dice
    l'archivio delle costruzioni, per il turno.

    Mutazione ESEGUITA (06/10/2026, Passo 5): `apply_outcomes` che accetta
    un «costruita» con qualunque `proposta_id` -- rossa."""
    app = casa
    app["llm_router"] = _Modello(([], json.dumps({"esiti": [
        {"osservazione": 0, "esito": "costruita", "proposta_id": "inventato"},
        {"osservazione": 1, "esito": "niente", "perche": "abitudine"}]})))

    esito = await pr.proposer_round(app)

    assert any("inventato" in p for p in esito["problemi"])
    # L'esito buono resta; quello storto lascia aperta la sua osservazione.
    aperte = pt.open_observations(app["observations"].analysis(OGGI), {})
    assert [o["soggetto"] for o in aperte] == ["dev1"]
    riga = app["usage"].turns()[0]
    assert riga["outcome"] == steering.REFUSED
    assert steering.refused_problems(app["usage"], steering.PROPOSER_SPECIES)


@pytest.mark.asyncio
async def test_un_id_nato_in_UN_ALTRO_turno_non_vale(casa):
    """L'id cita una proposta vera, ma di un altro turno: non e' nata qui.

    Mutazione ESEGUITA (06/10/2026): `proposed_in` che non guarda il turno --
    rossa."""
    app = casa
    vecchia = app["constructions"].propose(
        operation="crea", domain="automation", key="k0",
        actor=steering.PROPOSER_SPECIES, exchange="un-altro-turno", phrase=None,
        prima=None, dopo={}, helper=[], preview="", stakes=None,
        now=1_758_000_000.0)["id"]
    app["llm_router"] = _Modello(([], json.dumps({"esiti": [
        {"osservazione": 0, "esito": "costruita", "proposta_id": vecchia},
        {"osservazione": 1, "esito": "niente", "perche": "abitudine"}]})))

    esito = await pr.proposer_round(app)

    assert any(vecchia in p for p in esito["problemi"])


def test_un_osservazione_SPIEGATA_dall_analista_non_arriva_al_proponente():
    """D1 del refactor: l'indagine e' dell'analista, e cio' che ha spiegato e'
    chiuso.

    Mutazione ESEGUITA (06/10/2026): `open_observations` senza il controllo
    di `spiegato` -- rossa."""
    spiegata, aperta = osservazioni()
    spiegata["spiegato"] = "c'erano ospiti"
    analisi = {"osservazioni": [spiegata, aperta]}

    restano = pt.open_observations(analisi, {})

    assert [o["soggetto"] for o in restano] == ["dev2"]
    assert "Scaldabagno" not in pt.build_question(restano)


# -- La specie, dalla sua dichiarazione (Passo 2) -----------------------------

def test_il_catalogo_e_i_lettori_dell_analista_piu_PROPOSE_della_tabella():
    """`propose` si chiede alla tabella degli strumenti: lo STESSO dizionario
    della chat, non una copia."""
    from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
    from hiris.app.mind.analyst_turn import READERS

    dichiarata = steering.SPECIES[steering.PROPOSER_SPECIES]
    assert set(dichiarata.tools_for_turn()) == {*READERS, "propose"}
    definizione_chat = next(d for d in KNOWLEDGE_TOOLS if d["name"] == "propose")
    assert any(d is definizione_chat for d in dichiarata.catalog_for_turn())
    assert dichiarata.guard is not None and not dichiarata.self_contained


class _Sotto:
    def __init__(self):
        self.chiamate = []

    async def dispatch(self, nome, argomenti):
        self.chiamate.append((nome, argomenti))
        return {"ok": True}


@pytest.mark.asyncio
async def test_il_guardiano_rifiuta_cio_che_non_e_suo():
    """`execute` scrive in casa, `compute` e' dell'analista, `confirm` applica:
    nessuno arriva al dispatcher della chat, e a rifiutarli e' il guardiano
    del proponente -- non quello dell'analista sotto di lui, che `compute` lo
    servirebbe.

    Mutazione ESEGUITA (06/10/2026): il guardiano che passa tutto a quello
    dell'analista -- rossa (`compute` non e' rifiutato «mentre propongo»)."""
    sotto = _Sotto()
    guardiano = pt.ProposerDispatcher(sotto, ha=None, house=None, timezone=None)
    for nome in ("execute", "compute", "confirm", "remember"):
        risposta = await guardiano.dispatch(nome, {})
        assert "mentre propongo" in risposta.get("errore", ""), (nome, risposta)
    assert sotto.chiamate == []
    await guardiano.dispatch("search", {"query": "x"})
    assert sotto.chiamate == [("search", {"query": "x"})]


@pytest.mark.asyncio
async def test_a_propose_non_arriva_una_FRASE_inventata():
    """Nessuno parla al proponente: una `frase` sarebbe una citazione
    inventata, archiviata accanto alla proposta."""
    sotto = _Sotto()
    guardiano = pt.ProposerDispatcher(sotto, ha=None, house=None, timezone=None)
    await guardiano.dispatch("propose", {**_INTENZIONE_BUONA, "frase": "me l'ha detto Paolo"})
    ((nome, argomenti),) = sotto.chiamate
    assert nome == "propose" and "frase" not in argomenti


@pytest.mark.asyncio
async def test_la_proposta_esce_FIRMATA_dal_proponente(casa):
    """Il dispatcher della chat firmava «chat» in tre gestori: una proposta
    del proponente sarebbe uscita dalla chat.

    Mutazione ESEGUITA (06/10/2026): `create_tool_dispatcher` che non passa
    `actor` -- rossa («chat»)."""
    app = casa
    guardiano = await pt.guard(app, "turno-1")
    await guardiano.dispatch("propose", _INTENZIONE_BUONA)
    ((chiamata),) = app["workshop"].chiamate
    assert chiamata["actor"] == steering.PROPOSER_SPECIES
    assert chiamata["exchange"] == "turno-1"


# -- Le proposte da fare a mano (Passo 4) -------------------------------------

def _risposta_manuale(*_):
    return json.dumps({"esiti": [
        {"osservazione": 0, "esito": "a_mano", "testo": "Abbassa il termostato",
         "perche": "il prelievo e' notturno"},
        {"osservazione": 1, "esito": "niente", "perche": "abitudine"}]})


@pytest.mark.asyncio
async def test_A_MANO_va_nell_archivio_gemello_con_l_impronta_e_la_prova(casa):
    app = casa
    app["llm_router"] = _Modello(([], _risposta_manuale()))

    await pr.proposer_round(app)

    (proposta,) = app["observations"].proposals()
    assert proposta["impronta"] == observation_key(osservazioni()[0])
    assert proposta["prova"] == evidence_of(osservazioni()[0])
    accanto = pt.outcomes_of(app["observations"].analysis(OGGI))
    # «a mano» non si copia accanto all'osservazione: la proposta ha gia'
    # l'impronta.
    assert [o["esito"] for o in accanto] == ["niente"]


@pytest.mark.asyncio
async def test_un_giro_dopo_non_RICHIEDE_cio_che_ha_un_esito(casa):
    app = casa
    app["llm_router"] = _Modello(([], _risposta_manuale()))
    await pr.proposer_round(app)
    assert await pr.proposer_round(app) is None
    assert len(app["llm_router"].domande) == 1


def test_una_proposta_RIFIUTATA_torna_in_coda_solo_se_la_prova_cambia():
    """La promessa della rotta delle proposte (`handlers_proposals`): fino al
    06/10/2026 non era vera, il giro saltava ogni impronta gia' vista.

    Mutazione ESEGUITA (06/10/2026): `open_observations` che salta ogni
    impronta decisa a qualunque prova -- rossa."""
    riga = osservazioni()[0]
    chiave = observation_key(riga)
    analisi = {"osservazioni": [riga]}
    decise = {chiave: evidence_of(riga)}
    assert pt.open_observations(analisi, decise) == []
    cambiata = {**riga, "base": 25}
    assert pt.open_observations({"osservazioni": [cambiata]}, decise) == [cambiata]
    # In attesa: non si duplica, a qualunque prova.
    assert pt.open_observations({"osservazioni": [cambiata]}, decise,
                                waiting={chiave}) == []


# -- Il ponte ------------------------------------------------------------------

class _Coda:
    def __init__(self):
        self.accodati = []
        self.turno = None

    def enqueue(self, kind, wake, context, deadline, *, now=None, thread=None,
                priority=None):
        self.accodati.append({"kind": kind, "wake": wake, "context": context})
        return "job-1"

    def latest(self, kind):
        return self.turno


@pytest.mark.asyncio
async def test_sul_PONTE_si_accoda_e_si_raccoglie_con_l_id_del_turno(casa, monkeypatch):
    """La sveglia porta le impronte in ordine: chi raccoglie rinumera le
    stesse osservazioni. L'id della proposta lo dice l'archivio, col turno
    che il runner mette nella decisione (`exchange_id`).

    Mutazione ESEGUITA (06/10/2026): la raccolta che non passa
    `exchange_id` all'archivio -- rossa (l'esito «costruita» si rifiuta)."""
    app = casa
    coda = app["reasoning_queue"] = _Coda()
    monkeypatch.setattr(steering, "who_answers", lambda app: ("ponte", ""))
    await pr.proposer_round(app)
    (accodato,) = coda.accodati
    assert accodato["kind"] == pt.PROPOSAL_TURN_KIND
    assert accodato["wake"]["impronte"] == [observation_key(o) for o in osservazioni()]

    nata = app["constructions"].propose(
        operation="crea", domain="automation", key="k1",
        actor=steering.PROPOSER_SPECIES, exchange="xch-1", phrase=None,
        prima=None, dopo={}, helper=[], preview="", stakes=None,
        now=1_758_000_000.0)["id"]
    ident = app["usage"].log_turn(
        species=steering.PROPOSER_SPECIES, provider="subscription", model="m",
        channel="ponte", duration_ms=1, iterations=1, tools=[],
        outcome="riuscito", now=1_758_000_000.0)
    coda.turno = {"status": "decided", "wake": accodato["wake"],
                  "decided_ts": 0, "decision": {
                      "reply": json.dumps({"esiti": [
                          {"osservazione": 0, "esito": "costruita", "proposta_id": nata},
                          {"osservazione": 1, "esito": "niente", "perche": "x"}]}),
                      "outcome": "riuscito", "turn_id": ident,
                      "exchange_id": "xch-1"}}

    esito = await pr.proposer_round(app)

    accanto = pt.outcomes_of(app["observations"].analysis(OGGI))
    assert [o.get("proposta_id") for o in accanto] == [nata, None]
    assert esito["problemi"] == []
    # Una seconda lettura dello stesso turno non riscrive niente.
    await pr.proposer_round(app)
    assert len(pt.outcomes_of(app["observations"].analysis(OGGI))) == 2


@pytest.mark.asyncio
async def test_un_analisi_RIFATTA_dopo_una_raccolta_viene_chiesta(casa, monkeypatch):
    """Il turno raccolto resta l'ultimo della sua specie: se l'analisi del
    giorno si rifa' con un'osservazione nuova, il giro deve chiederla, non
    fermarsi sulla raccolta di prima.

    Mutazione ESEGUITA (06/10/2026): il giro che esce dopo una raccolta senza
    problemi, come quello dell'attuatore -- rossa (niente accodato)."""
    app = casa
    coda = app["reasoning_queue"] = _Coda()
    monkeypatch.setattr(steering, "who_answers", lambda app: ("ponte", ""))
    coda.turno = {"status": "decided", "decided_ts": 0,
                  "wake": {"giorno": OGGI, "impronte": [
                      observation_key(o) for o in osservazioni()]},
                  "decision": {"reply": json.dumps({"esiti": [
                      {"osservazione": 0, "esito": "niente", "perche": "x"},
                      {"osservazione": 1, "esito": "niente", "perche": "y"}]}),
                      "outcome": "riuscito"}}
    await pr.proposer_round(app)
    assert coda.accodati == []

    analisi = app["observations"].analysis(OGGI)
    nuova = {**osservazioni()[0], "soggetto": "dev3", "nome": "Forno"}
    app["observations"].replace_analysis(
        OGGI, {**analisi, "osservazioni": [*analisi["osservazioni"], nuova]})
    await pr.proposer_round(app)

    (accodato,) = coda.accodati
    assert accodato["wake"]["impronte"] == [observation_key(nuova)]


def test_i_segnaposto_nei_testi_tornano_ai_nomi_veri():
    """Il modello ha visto la casa coperta: cio' che scrive torna in chiaro
    prima di arrivare all'archivio."""

    class _Maschera:
        def unmask(self, valore):
            return valore.replace("person.#1", "person.paolo")

    esito = pt.apply_outcomes(osservazioni()[:1], json.dumps({"esiti": [
        {"osservazione": 0, "esito": "a_mano", "testo": "chiedi a person.#1",
         "perche": "e' sua"}]}), presence=_Maschera())
    assert esito["esiti"][0]["testo"] == "chiedi a person.paolo"


def test_un_osservazione_SENZA_esito_e_un_problema():
    esito = pt.apply_outcomes(osservazioni(), json.dumps({"esiti": [
        {"osservazione": 1, "esito": "niente", "perche": "x"}]}))
    assert esito["problemi"] == ["non hanno un esito le osservazioni 0"]
    assert [o["impronta"] for o in esito["esiti"]] == [observation_key(osservazioni()[1])]
