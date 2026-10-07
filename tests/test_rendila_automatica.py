"""«Rendila automatica» (attori, strato 4, Task 4.5; D15 del piano degli
strati 3-4, e le tre scelte del proprietario del 06/10/2026).

Su una proposta da fare a mano, chi amministra dice «voglio che succeda da
sola». Il comando non crea niente: fa comporre al proponente un'automazione
con `propose`, che arriva fra le costruzioni con anteprima e conferma. Quando
nasce, la proposta a mano si chiude col legame. Un'automazione che agisce su
serrature o allarme si rifiuta dentro il turno; su una proposta gia' `alto`
il comando non esiste, ne' nella pagina ne' nella rotta.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from hiris.app import background, steering
from hiris.app.action.construction import stakes, workshop
from hiris.app.api.handlers_constructions import _both_queues
from hiris.app.api.handlers_proposals import handle_proposal_automate
from hiris.app.mind import automate_turn as at
from hiris.app.mind import proposal_redo
from hiris.app.mind.store import ObservationsStore
from hiris.app.reasoning.consegna import consegna
from hiris.app.reasoning.queue import ReasoningQueue
from hiris.app.usage.store import UsageStore
from tests.test_api_proposte import _richiesta
from tests.test_construction_workshop import _intento, banco  # noqa: F401

_SERRATURA = [{"action": "lock.unlock", "target": {"entity_id": "lock.ingresso"}}]


class _Modello:
    """Il modello sulla catena: esegue le chiamate di strumento col
    dispatcher del turno, poi risponde."""

    def __init__(self, chiamate, risposta):
        self.chiamate = chiamate
        self.risposta = risposta
        self.risultati: list[dict] = []
        self.strumenti: list[str] = []
        self.last_tool_calls: list = []

    async def chat(self, **kwargs):
        self.strumenti = [d["name"] for d in kwargs.get("tools") or []]
        for nome, argomenti in self.chiamate:
            self.risultati.append(await kwargs["dispatcher"].dispatch(nome, argomenti))
        return self.risposta(self.risultati) if callable(self.risposta) else self.risposta


@pytest.fixture()
def casa(tmp_path, banco):
    officina, _ha, costruzioni, _ = banco
    store = ObservationsStore(str(tmp_path / "oss.db"))
    usage = UsageStore(str(tmp_path / "consumi.db"))
    ident = store.add_proposal(
        text="Spegni lo scaldabagno di notte", perche="il prelievo notturno e' salito",
        fingerprint="dev1|prelievo|None|1", prova={"base": 19}, stakes=None,
        now_ts=100.0)
    app = {"observations": store, "usage": usage, "constructions": costruzioni,
           "workshop": officina, "bridge_active": False}
    try:
        yield app, store, ident
    finally:
        store.close()
        usage.close()


async def _premi(app, ident):
    risposta = await handle_proposal_automate(_richiesta(app, {"id": ident}))
    # Sulla catena il turno gira in un compito: la prova lo aspetta.
    await asyncio.gather(*list(background.background_tasks))
    return risposta


def _riga(store, ident):
    return next(p for p in store.proposals() if p["id"] == ident)


@pytest.mark.asyncio
async def test_NASCE_l_automazione_e_la_proposta_a_mano_si_chiude_col_legame(casa):
    """La scelta del proprietario: chiudere col legame. Mutazione ESEGUITA
    (06/10/2026): `settle` senza `automate_proposal` -- rossa (la proposta
    resta in attesa e senza id)."""
    app, store, ident = casa
    app["llm_router"] = _Modello([("propose", _intento())],
                                 lambda r: json.dumps({"proposta_id": r[0]["proposta_id"]}))

    risposta = await _premi(app, ident)

    assert risposta.status == 202
    nata = app["llm_router"].risultati[0]["proposta_id"]
    riga = _riga(store, ident)
    assert riga["stato"] == store.PROPOSAL_AUTOMATED
    assert riga["costruzione_id"] == nata
    # Firmata dal proponente, e misurata sotto la sua specie di turno.
    assert app["constructions"].read(nata, now=1.0)["origine"] == steering.PROPOSER_SPECIES
    assert app["usage"].turns()[0]["species"] == steering.AUTOMATE_SPECIES
    # La pagina legge il legame dalla costruzione: «Nata da».
    righe = await _both_queues(app, app["constructions"], False)
    costruzione = next(r for r in righe if r["id"] == nata)
    assert costruzione["nata_da"] == {"id": ident, "testo": riga["testo"]}
    assert app.get(at.IN_FLIGHT) is None


@pytest.mark.asyncio
async def test_un_automazione_su_una_SERRATURA_si_rifiuta_dentro_il_turno(casa):
    """La scelta del proprietario: rifiutata. L'officina calcola `alto` e
    non archivia; il modello lo dice, e la proposta resta a mano col perche'.

    Mutazione ESEGUITA (06/10/2026): `automate_turn.guard` con
    `refuse_high=False` -- rossa (la costruzione `alto` entra
    nell'archivio)."""
    app, store, ident = casa
    app["llm_router"] = _Modello(
        [("propose", _intento(azioni=_SERRATURA))],
        json.dumps({"perche": "tocca la serratura, che chiede sempre"}))

    await _premi(app, ident)

    assert app["llm_router"].risultati[0] == {"errore": stakes.HIGH_UNATTENDED}
    assert app["constructions"].list(now=1.0, pending_only=False, limit=10) == []
    riga = _riga(store, ident)
    assert riga["stato"] == store.PROPOSAL_PENDING
    assert riga["non_automatizzabile"] == "tocca la serratura, che chiede sempre"
    # E il comando, su quella forma, non c'e' piu'.
    righe = await _both_queues(app, app["constructions"], False)
    assert next(r for r in righe if r["id"] == ident)["automatizzabile"] is False


@pytest.mark.asyncio
async def test_la_rifiuta_l_OFFICINA_non_il_guardiano(banco):
    """Il livello si calcola in un posto solo: lo stesso corpo passa senza
    `refuse_high`. Mutazione ESEGUITA (06/10/2026): la riga del rifiuto in
    `Workshop.propose` tolta -- rossa."""
    officina, _, archivio, _ = banco
    rifiutata = await officina.propose(_intento(azioni=_SERRATURA), actor="x",
                                       exchange="t1", now=1.0, refuse_high=True)
    passata = await officina.propose(_intento(azioni=_SERRATURA), actor="x",
                                     exchange="t2", now=1.0)

    assert rifiutata == {"errore": stakes.HIGH_UNATTENDED}
    assert passata["livello"] == stakes.HIGH
    assert len(archivio.list(now=1.0, pending_only=False, limit=10)) == 1


@pytest.mark.asyncio
async def test_per_ALTO_il_comando_non_esiste_ne_nella_rotta_ne_nella_pagina(casa):
    """D15: per `alto` il comando non c'e'. 403, nessun turno, e la pagina
    non riceve il bottone. Mutazione ESEGUITA (06/10/2026): la riga `alto` di
    `automate_turn.refusal` tolta -- rossa."""
    app, store, _ = casa
    alta = store.add_proposal(text="Chiudi a chiave la sera", perche="x",
                              fingerprint="lock|x|None|1", prova={},
                              stakes=stakes.HIGH, now_ts=200.0)
    app["llm_router"] = _Modello([], "{}")

    risposta = await _premi(app, alta)

    assert risposta.status == 403
    assert app["usage"].turns() == []
    righe = await _both_queues(app, app["constructions"], False)
    assert next(r for r in righe if r["id"] == alta)["automatizzabile"] is False


@pytest.mark.asyncio
async def test_il_guardiano_ammette_solo_un_AUTOMAZIONE_NUOVA(casa):
    """Uno script o una scena non succedono da soli. Mutazione ESEGUITA
    (06/10/2026): `AutomateDispatcher` senza il controllo -- rossa."""
    app, _, _ = casa
    guardiano = await at.guard(app, "t1")

    script = await guardiano.dispatch("propose", _intento(dominio="script"))
    modifica = await guardiano.dispatch("propose", _intento(gesto="modifica"))

    assert "errore" in script and "errore" in modifica
    assert app["constructions"].list(now=1.0, pending_only=False, limit=10) == []


@pytest.mark.asyncio
async def test_un_turno_TRONCATO_non_scrive_niente(casa):
    """Un guasto di passaggio non e' un «non si puo'»: il comando torna.
    Mutazione ESEGUITA (06/10/2026): `settle` che scrive la ragione del
    lettore anche senza un «perche'» -- rossa."""
    app, store, ident = casa
    assert at.settle(app, ident, "t1", "", truncated=True) == "senza_esito"
    assert _riga(store, ident)["non_automatizzabile"] is None


@pytest.mark.asyncio
async def test_sul_PONTE_si_accoda_e_la_consegna_chiude_col_legame(casa, tmp_path):
    """Sul ponte la rotta accoda e torna; mentre il turno e' in volo la
    proposta e' «in preparazione» e un secondo clic non accoda un secondo
    turno; la consegna chiude col legame. Mutazione ESEGUITA (06/10/2026):
    il ramo di `consegna` tolto -- rossa."""
    app, store, ident = casa
    coda = ReasoningQueue(str(tmp_path / "coda.db"))
    app.update({"reasoning_queue": coda, "bridge_active": True,
                "models_config": {}})
    try:
        from unittest.mock import patch

        with patch.object(at, "start", lambda a, s: steering.Start("ponte", "", None)):
            prima = await _premi(app, ident)
            seconda = await _premi(app, ident)
        assert (prima.status, seconda.status) == (202, 409)
        assert at.preparing(app) == ident
        righe = await _both_queues(app, app["constructions"], False)
        assert next(r for r in righe if r["id"] == ident)["in_preparazione"] is True

        nata = app["constructions"].propose(
            operation="crea", domain="automation", key="k1",
            actor=steering.PROPOSER_SPECIES, exchange="turno-ponte", phrase=None,
            prima=None, dopo={}, helper=[], preview="", stakes=None, now=5.0)["id"]
        lavoro = coda.claim(now=10.0)
        esito = await consegna(app, lavoro["job_id"], lavoro["nonce"],
                               {"reply": json.dumps({"proposta_id": nata}),
                                "exchange_id": "turno-ponte"}, now=11.0)

        assert esito == "automazione_automatizzata"
        assert _riga(store, ident)["costruzione_id"] == nata
        assert at.preparing(app) is None
    finally:
        coda.close()


def test_RIFALLA_toglie_il_rifiuto_della_forma_vecchia(tmp_path):
    """Una forma nuova si puo' rendere automatica anche se la vecchia no.
    Mutazione ESEGUITA (06/10/2026): `add_proposal_round` senza
    `automation_refusal=NULL` -- rossa."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        ident = store.add_proposal(text="a", perche="b", fingerprint="f",
                                   prova={}, stakes=None, now_ts=1.0)
        store.refuse_automation(ident, "non si puo'")
        store.add_proposal_round(ident, request="in un altro modo",
                                 outcome="a_mano", turn="t1", text="c",
                                 why="d", now_ts=2.0)
        assert _riga(store, ident)["non_automatizzabile"] is None
    finally:
        store.close()


def test_un_giro_NIENTE_lascia_il_rifiuto_la_forma_e_la_stessa(tmp_path):
    """G68-2 (giro 68), punto 1: con «niente» la forma resta quella che non
    si poteva automatizzare, e il rifiuto resta vero. Mutazione ESEGUITA
    (06/10/2026): `automation_refusal=NULL` scritto per ogni esito -- rossa."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        ident = store.add_proposal(text="a", perche="b", fingerprint="f",
                                   prova={}, stakes=None, now_ts=1.0)
        store.refuse_automation(ident, "non si puo'")
        store.add_proposal_round(ident, request="in un altro modo",
                                 outcome="niente", turn="t1", why="niente da fare",
                                 now_ts=2.0)
        assert _riga(store, ident)["non_automatizzabile"] == "non si puo'"
    finally:
        store.close()


def test_la_domanda_legge_il_filo_per_ESITO(tmp_path):
    """G68-2, punto 2: un giro «niente» non ha una forma scartata, e la
    domanda scriveva «una forma gia' scartata: None». Mutazione ESEGUITA
    (06/10/2026): `round_lines` che legge `scartata` per ogni giro -- rossa."""
    riga = {"testo": "t", "perche": "p", "giri": [
        {"richiesta": "prima", "esito": "a_mano", "scartata": "la vecchia"},
        {"richiesta": "poi", "esito": "niente", "perche": "nessuna forma"},
    ]}
    domanda = at.build_question(riga)
    assert "None" not in domanda
    assert "gia' scartata prima: la vecchia" in domanda
    assert "allora non avevi proposto niente: nessuna forma" in domanda


@pytest.mark.asyncio
@pytest.mark.parametrize("azione", [
    {"action": "script.turn_on", "target": {"entity_id": "script.apri_porta"}},
    {"action": "scene.turn_on", "target": {"entity_id": "scene.esco"}},
    {"action": "automation.trigger", "target": {"entity_id": "automation.notte"}},
    {"action": "homeassistant.turn_on", "target": {"entity_id": "script.apri_porta"}},
])
async def test_uno_SCRIPT_una_SCENA_o_un_AUTOMAZIONE_non_diventano_automatici(banco, azione):
    """G67-1 (giro 67, consigliata A): `script.apri_porta` usciva `lieve` e
    passava, perche' quello che lo script fa non si vede da qui. Con
    `refuse_high` l'officina lo rifiuta; senza, la proposta normale passa.

    Mutazione ESEGUITA (06/10/2026): `unattended_refusal` senza il controllo
    dei domini opachi -- rosse le quattro."""
    officina, _, archivio, _ = banco
    rifiutata = await officina.propose(_intento(azioni=[azione]), actor="x",
                                       exchange="t1", now=1.0, refuse_high=True)
    passata = await officina.propose(_intento(azioni=[azione]), actor="x",
                                     exchange="t2", now=1.0)

    assert rifiutata == {"errore": stakes.opaque_unattended(
        officina._ha.CONFIGURABLE_DOMAINS)}
    assert "proposta_id" in passata
    assert len(archivio.list(now=1.0, pending_only=False, limit=10)) == 1


def test_SERVICE_TEMPLATE_e_un_servizio_e_la_serratura_si_vede():
    """G69-1 (giro 69): Home Assistant accetta il nome del servizio anche in
    `service_template` (`SERVICE_SCHEMA`, `config_validation.py`, letto il
    06/10/2026). Leggendo solo `service`/`action`, `lock.unlock` usciva senza
    livello, senza rifiuto e fuori dall'anteprima.

    Mutazione ESEGUITA (06/10/2026): `service_template` tolta da
    `_SERVICE_KEYS` -- rossa."""
    corpo = {"actions": [{"service_template": "lock.unlock",
                          "target": {"area_id": "ingresso"}}]}
    assert workshop.services_named(corpo) == ["lock.unlock"]
    assert workshop.acted_on("automation", None, corpo) == {"lock"}
    assert workshop.stakes_of({}, "automation", None, corpo) == stakes.HIGH


@pytest.mark.asyncio
@pytest.mark.parametrize("passo", [
    {"action": "{{ 'lock.unlock' }}", "target": {"area_id": "ingresso"}},
    {"service_template": "{% if true %}lock.unlock{% endif %}",
     "target": {"area_id": "ingresso"}},
    {"action": "{{ servizio }}"},
])
async def test_un_servizio_SCRITTO_COME_MODELLO_non_diventa_automatico(banco, passo):
    """G69-1 (giro 69): `action: "{{ 'lock.unlock' }}"` usciva senza livello
    e passava il rifiuto. Il nome lo decide Home Assistant quando gira: con
    `refuse_high` l'officina lo rifiuta; senza, la proposta normale passa,
    ed e' `alto` (scelta di Paolo, 07/10/2026, scheda «Sì, alto»): chi la
    conferma lo sa prima.

    Mutazioni ESEGUITE: `unattended_refusal` senza il controllo dei modelli
    (06/10/2026) -- rosse le tre; `impose` senza il controllo dei modelli
    (07/10/2026) -- rosse le tre."""
    officina, _, archivio, _ = banco
    rifiutata = await officina.propose(_intento(azioni=[passo]), actor="x",
                                       exchange="t1", now=1.0, refuse_high=True)
    passata = await officina.propose(_intento(azioni=[passo]), actor="x",
                                     exchange="t2", now=1.0)

    assert rifiutata == {"errore": stakes.TEMPLATE_UNATTENDED}
    assert "proposta_id" in passata
    assert passata["livello"] == stakes.HIGH
    assert len(archivio.list(now=1.0, pending_only=False, limit=10)) == 1


def test_un_nome_SCRITTO_COME_MODELLO_non_inventa_un_dominio():
    """`domain_of("{{ 'lock.unlock' }}")` darebbe `{{ 'lock`: un dominio che
    non esiste. Il modello resta un nome nell'anteprima, non un dominio.

    Mutazione ESEGUITA (06/10/2026): il filtro `is_template` tolto da
    `domains_acted_on` -- rossa."""
    corpo = {"actions": [{"action": "{{ 'lock.unlock' }}"}]}
    assert workshop.services_named(corpo) == ["{{ 'lock.unlock' }}"]
    assert workshop.acted_on("automation", None, corpo) == set()


@pytest.mark.asyncio
async def test_UNA_ALLA_VOLTA_un_altra_in_preparazione_ferma_il_comando(casa):
    """N67-1 (giro 67): mentre una proposta si prepara, sulle altre il
    comando non c'e' e la rotta risponde 409, senza far partire un turno.

    Mutazione ESEGUITA (06/10/2026): tolto da `refusal` il ramo
    `in_flight is not None` -- rossa."""
    app, store, prima = casa
    seconda = store.add_proposal(text="Spegni il portico", perche="x",
                                 fingerprint="dev2|x|None|1", prova={},
                                 stakes=None, now_ts=200.0)
    app[at.IN_FLIGHT] = prima
    app["llm_router"] = _Modello([], "{}")

    risposta = await handle_proposal_automate(_richiesta(app, {"id": seconda}))

    assert risposta.status == 409
    assert app["usage"].turns() == []
    righe = await _both_queues(app, app["constructions"], False)
    assert next(r for r in righe if r["id"] == seconda)["automatizzabile"] is False


@pytest.mark.asyncio
async def test_sopra_un_RIFALLA_in_corso_non_si_rende_automatica(casa):
    """G68-2 (giro 68), punto 3: «Rifalla» e «Rendila automatica» sulla
    stessa proposta darebbero due costruzioni per una domanda, o un
    rifacimento scartato. Con un rifacimento in volo la rotta risponde 409
    senza turno, e la pagina non mostra il comando.

    Mutazione ESEGUITA (06/10/2026): `refusal` senza il ramo `redoing` --
    rossa."""
    app, _store, prima = casa
    app[proposal_redo.CHAIN_IN_FLIGHT] = {prima}
    app["llm_router"] = _Modello([], "{}")

    risposta = await handle_proposal_automate(_richiesta(app, {"id": prima}))

    assert risposta.status == 409
    assert app["usage"].turns() == []
    righe = await _both_queues(app, app["constructions"], False)
    assert next(r for r in righe if r["id"] == prima)["automatizzabile"] is False


@pytest.mark.asyncio
async def test_mentre_si_prepara_l_automazione_RIFALLA_non_parte(casa):
    """G68-2, punto 3, dall'altra parte: con l'automazione in preparazione
    sulla stessa proposta il rifacimento solleva `InFlight` (la rotta: 409).

    Mutazione ESEGUITA (06/10/2026): `redo` senza il controllo di
    `automate_turn.preparing` -- rossa."""
    app, store, prima = casa
    app[at.IN_FLIGHT] = prima
    app["llm_router"] = _Modello([], "{}")

    with pytest.raises(proposal_redo.InFlight):
        await proposal_redo.redo(app, store, _riga(store, prima), "piu' tardi")
    assert app["usage"].turns() == []


@pytest.mark.asyncio
async def test_una_proposta_ALTA_gia_decisa_risponde_409_non_403(casa):
    """N67-3 (giro 67): il codice segue il testo. Una proposta `alto` gia'
    decisa non e' «il comando non esiste»: e' «non piu' in attesa»."""
    app, store, _ = casa
    alta = store.add_proposal(text="Chiudi a chiave", perche="x",
                              fingerprint="lock|y|None|1", prova={},
                              stakes=stakes.HIGH, now_ts=300.0)
    store.close_proposal(alta, "rifiutata")

    risposta = await handle_proposal_automate(_richiesta(app, {"id": alta}))

    assert risposta.status == 409
